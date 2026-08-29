"""Untrusted-message analysis that never changes system policy or sends mail."""

from __future__ import annotations

import re
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, time, timedelta
from typing import Iterable, Mapping
from uuid import uuid4

from ...bus import InMemoryEventBus
from ...contracts import CommunicationMessage
from ...events import Event, EventCategory, EventState
from ...persistence.repositories import RuntimeRepository
from ...time_windows import in_time_window


@dataclass(frozen=True, slots=True)
class CommunicationInsight:
    insight_id: str
    owner_id: str
    thread_id: str
    priority: str
    summary: str
    action_items: tuple[str, ...] = ()
    reply_suggestion: str | None = None
    follow_up_at: datetime | None = None
    untrusted_input: bool = True


@dataclass(frozen=True, slots=True)
class SendPolicy:
    channel: str
    recipient: str
    message_type: str = "normal"
    allowed_context: Mapping[str, object] = field(default_factory=dict)
    time_window: tuple[str, str] | None = None
    risk: str = "approval_required"
    confirmation_requirement: str = "always"

class CommunicationIntelligenceService:
    def __init__(self, repository: RuntimeRepository, event_bus: InMemoryEventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self._insights: dict[str, CommunicationInsight] = {}
        self._policies: list[SendPolicy] = []

    def add_send_policy(self, policy: SendPolicy) -> None:
        if policy.risk not in {"safe", "approval_required", "blocked"}:
            raise ValueError("unsupported send policy risk")
        self._policies.append(policy)

    async def analyze(self, owner_id: str, thread_id: str, messages: Iterable[CommunicationMessage]) -> CommunicationInsight:
        values = tuple(messages)
        if not values:
            raise ValueError("at least one message is required")
        latest = max(values, key=lambda item: item.sent_at)
        content = " ".join(item.content.strip() for item in values if item.content.strip())
        lower = content.casefold()
        priority = "high" if any(word in lower for word in ("urgent", "asap", "blocking", "deadline")) else "normal"
        actions = []
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", content):
            if re.search(r"\b(please|need to|action|todo|follow up|can you)\b", sentence, re.IGNORECASE):
                actions.append(sentence.strip()[:240])
        summary = " ".join(content.split())[:400]
        suggestion = f"Thanks for the update. I’ll review this and follow up." if priority == "high" else f"Thanks, {latest.sender_id}. I’ll review and get back to you."
        insight = CommunicationInsight(f"communication-insight-{uuid4()}", owner_id, thread_id, priority, summary, tuple(dict.fromkeys(actions))[:8], suggestion)
        self._insights[thread_id] = insight
        self.repository.insert_communication_insight(insight)
        await self._emit("communication.insight_created", insight, EventState.COMPLETED)
        return insight

    async def get(self, owner_id: str, thread_id: str) -> CommunicationInsight | None:
        current = self._insights.get(thread_id)
        if current is not None:
            return current if current.owner_id == owner_id else None
        row = self.repository.communication_insight(owner_id, thread_id)
        return self._from_row(row) if row else None

    def can_auto_send(self, owner_id: str, channel: str, recipient: str, *, message_type: str = "normal", context: Mapping[str, object] | None = None, now: datetime | None = None) -> tuple[bool, str]:
        if message_type in {"bulk", "important", "urgent", "sensitive", "financial"}:
            return False, "confirmation_required" if message_type != "bulk" else "bulk_send_denied"
        for policy in self._policies:
            if policy.channel != channel or policy.recipient != recipient or policy.message_type != message_type:
                continue
            if any((context or {}).get(key) != value for key, value in policy.allowed_context.items()):
                continue
            if policy.time_window and not self._in_window(policy.time_window, now or datetime.now(UTC)):
                continue
            if policy.risk == "safe" and policy.confirmation_requirement == "none" and message_type == "normal":
                return True, "explicit_scoped_policy"
            return False, "confirmation_required"
        return False, "no_scoped_auto_send_policy"

    async def draft_reply(self, owner_id: str, message: CommunicationMessage) -> str:
        insight = await self.get(owner_id, message.message_id)
        if insight is None:
            insight = await self.analyze(owner_id, message.message_id, (message,))
        return insight.reply_suggestion or "Thanks for the message. I’ll review it and follow up."

    async def _emit(self, name: str, insight: CommunicationInsight, state: EventState) -> None:
        event = Event.create(name, EventCategory.COMMUNICATION, correlation_id=insight.insight_id, actor_id=insight.owner_id, payload={"owner_id": insight.owner_id, "thread_id": insight.thread_id, "insight_id": insight.insight_id, "priority": insight.priority, "action_item_count": len(insight.action_items), "untrusted_input": True}, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)

    @staticmethod
    def _in_window(window: tuple[str, str], current: datetime) -> bool:
        try:
            start = time.fromisoformat(window[0]); end = time.fromisoformat(window[1])
        except (ValueError, TypeError):
            return False
        value = current.time()
        return start <= value <= end if start <= end else value >= start or value <= end

    @staticmethod
    def _from_row(row: Mapping[str, object]) -> CommunicationInsight:
        import json
        data = json.loads(str(row["insight_json"]))
        return CommunicationInsight(str(row["id"]), str(row["owner_id"]), str(row["thread_id"]), str(data["priority"]), str(data["summary"]), tuple(data.get("action_items", ())), data.get("reply_suggestion"), datetime.fromisoformat(data["follow_up_at"]) if data.get("follow_up_at") else None, True)


@dataclass(frozen=True, slots=True)
class CommunicationFollowUp:
    followup_id: str
    owner_id: str
    thread_id: str
    message_id: str | None
    direction: str
    status: str
    summary: str
    due_at: datetime
    created_at: datetime
    resolved_at: datetime | None = None
    related_goal_id: str | None = None
    related_mission_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AutoSendRule:
    rule_id: str
    owner_id: str
    channel: str
    recipient_allowlist: tuple[str, ...]
    message_class: str = "normal"
    allowed_context: Mapping[str, object] = field(default_factory=dict)
    max_frequency: int = 1
    window_seconds: float = 86400.0
    allowed_time_start: str | None = None
    allowed_time_end: str | None = None
    sensitivity: str = "normal"
    approval_requirement: str = "always"
    enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class CommunicationFollowUpService:
    """Follow-up metadata and scoped send policy; message content stays in CommunicationsHub."""

    def __init__(self, repository: RuntimeRepository, event_bus: InMemoryEventBus, intelligence: CommunicationIntelligenceService | None = None, communications: Any | None = None, personalization: Any | None = None) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.intelligence = intelligence
        self.communications = communications
        self.personalization = personalization
        self._sent: dict[tuple[str, str, str], list[datetime]] = {}

    async def create(self, owner_id: str, thread_id: str, *, message_id: str | None = None, direction: str = "awaiting_other_party", summary: str = "Awaiting reply", due_at: datetime | None = None, delay_seconds: float = 86400.0, related_goal_id: str | None = None, related_mission_id: str | None = None, metadata: Mapping[str, object] | None = None) -> CommunicationFollowUp:
        if not thread_id.strip() or not summary.strip():
            raise ValueError("follow-up thread and summary are required")
        now = datetime.now(UTC)
        item = CommunicationFollowUp(f"followup-{uuid4()}", owner_id, thread_id, message_id, direction, "open", summary[:400], due_at or now + timedelta(seconds=max(1.0, delay_seconds)), now, None, related_goal_id, related_mission_id, dict(metadata or {}))
        self.repository.insert_communication_followup(item)
        await self._emit("communication.followup_created", item)
        return item

    async def list(self, owner_id: str, *, active_only: bool = False) -> tuple[CommunicationFollowUp, ...]:
        statuses = ("open", "due") if active_only else ()
        return tuple(self._from_row(row) for row in self.repository.communication_followups(owner_id, statuses))

    async def acknowledge(self, owner_id: str, followup_id: str) -> CommunicationFollowUp:
        row = self.repository.communication_followup(owner_id, followup_id)
        if row is None:
            raise KeyError(followup_id)
        item = self._from_row(row)
        updated = CommunicationFollowUp(item.followup_id, item.owner_id, item.thread_id, item.message_id, item.direction, "resolved", item.summary, item.due_at, item.created_at, datetime.now(UTC), item.related_goal_id, item.related_mission_id, item.metadata)
        self.repository.insert_communication_followup(updated)
        await self._emit("communication.followup_resolved", updated, EventState.COMPLETED)
        return updated

    async def handle_communication_event(self, event: Event) -> int:
        if event.event_type not in {"communication.received", "communication.sent"}:
            return 0
        owner_id, thread_id = event.payload.get("owner_id"), event.payload.get("thread_id")
        if not isinstance(owner_id, str) or not isinstance(thread_id, str): return 0
        direction = "awaiting_other_party" if event.event_type == "communication.received" else "awaiting_user"
        count = 0
        for item in await self.list(owner_id, active_only=True):
            if item.thread_id == thread_id and item.direction == direction:
                await self.acknowledge(owner_id, item.followup_id); count += 1
        return count

    async def create_follow_up(self, owner_id: str, thread_id: str, **kwargs: object) -> CommunicationFollowUp:
        return await self.create(owner_id, thread_id, **kwargs)  # type: ignore[arg-type]

    async def acknowledge_follow_up(self, owner_id: str, followup_id: str) -> CommunicationFollowUp:
        return await self.acknowledge(owner_id, followup_id)

    async def due(self, owner_id: str, *, now: datetime | None = None) -> tuple[CommunicationFollowUp, ...]:
        current = now or datetime.now(UTC)
        values = []
        for item in await self.list(owner_id, active_only=True):
            if item.due_at <= current:
                due_item = item if item.status == "due" else CommunicationFollowUp(item.followup_id, item.owner_id, item.thread_id, item.message_id, item.direction, "due", item.summary, item.due_at, item.created_at, item.resolved_at, item.related_goal_id, item.related_mission_id, item.metadata)
                self.repository.insert_communication_followup(due_item)
                values.append(due_item)
                if item.status != "due":
                    await self._emit("communication.followup_due", due_item, EventState.COMPLETED)
        return tuple(values)

    async def create_rule(self, owner_id: str, values: Mapping[str, object]) -> AutoSendRule:
        recipients = values.get("recipient_allowlist", values.get("recipients", ()))
        if not isinstance(recipients, (list, tuple)) or not recipients:
            raise ValueError("auto-send recipient allowlist is required")
        now = datetime.now(UTC)
        rule = AutoSendRule(
            str(values.get("rule_id", f"autosend-{uuid4()}")), owner_id, str(values.get("channel", "")), tuple(str(item) for item in recipients), str(values.get("message_class", "normal")),
            dict(values.get("allowed_context", {})) if isinstance(values.get("allowed_context"), dict) else {}, int(values.get("max_frequency", 1)), float(values.get("window_seconds", 86400)), values.get("allowed_time_start") if isinstance(values.get("allowed_time_start"), str) else None, values.get("allowed_time_end") if isinstance(values.get("allowed_time_end"), str) else None, str(values.get("sensitivity", "normal")), str(values.get("approval_requirement", "always")), bool(values.get("enabled", True)), now, now,
        )
        self._validate_rule(rule)
        self.repository.insert_auto_send_rule(rule)
        return rule

    async def rules(self, owner_id: str) -> tuple[AutoSendRule, ...]:
        return tuple(self._rule_from_row(row) for row in self.repository.auto_send_rules(owner_id))

    async def list_auto_send_rules(self, owner_id: str) -> tuple[AutoSendRule, ...]:
        return await self.rules(owner_id)

    async def create_auto_send_rule(self, owner_id: str, values: Mapping[str, object]) -> AutoSendRule:
        return await self.create_rule(owner_id, values)

    async def update_rule(self, owner_id: str, rule_id: str, values: Mapping[str, object]) -> AutoSendRule:
        row = self.repository.auto_send_rule(owner_id, rule_id)
        if row is None:
            raise KeyError(rule_id)
        current = self._rule_from_row(row)
        allowed = {"enabled", "max_frequency", "window_seconds", "allowed_time_start", "allowed_time_end", "approval_requirement", "allowed_context", "recipient_allowlist", "message_class", "sensitivity"}
        if set(values) - allowed:
            raise ValueError("unsupported auto-send rule fields")
        data = {**asdict(current), **dict(values), "updated_at": datetime.now(UTC)}
        updated = AutoSendRule(**{key: data[key] for key in AutoSendRule.__dataclass_fields__})
        self._validate_rule(updated)
        self.repository.insert_auto_send_rule(updated)
        return updated

    def can_auto_send_scoped(self, owner_id: str, channel: str, recipient: str, content: str, *, message_class: str = "normal", context: Mapping[str, object] | None = None, now: datetime | None = None, timezone_name: str | None = None) -> tuple[bool, str]:
        current = now or datetime.now(UTC)
        if not content.strip():
            return False, "empty_message"
        if message_class == "bulk":
            return False, "bulk_send_denied"
        for rule in (self._rule_from_row(row) for row in self.repository.auto_send_rules(owner_id)):
            if not rule.enabled or rule.channel != channel or rule.message_class != message_class or recipient not in rule.recipient_allowlist:
                continue
            if message_class in {"important", "urgent", "sensitive", "financial"} or rule.sensitivity in {"financial", "sensitive"} or rule.approval_requirement != "none":
                return False, "confirmation_required"
            if any((context or {}).get(key) != value for key, value in rule.allowed_context.items()):
                continue
            if not in_time_window(rule.allowed_time_start, rule.allowed_time_end, now=current, timezone_name=timezone_name):
                continue
            fingerprint = hashlib.sha256(f"{channel}|{recipient}|{content.strip()}".encode()).hexdigest()
            attempts = self.repository.auto_send_attempts(owner_id, rule.rule_id, recipient, fingerprint, current - timedelta(seconds=rule.window_seconds))
            if len(attempts) >= rule.max_frequency:
                return False, "rate_limited"
            return True, "explicit_scoped_policy"
        return False, "no_scoped_auto_send_policy"

    async def record_auto_send_attempt(self, owner_id: str, rule_id: str, channel: str, recipient: str, content: str, *, status: str, message_id: str | None = None, error_code: str | None = None, now: datetime | None = None) -> None:
        rule = self.repository.auto_send_rule(owner_id, rule_id)
        if rule is None:
            raise KeyError(rule_id)
        fingerprint = hashlib.sha256(f"{channel}|{recipient}|{content.strip()}".encode()).hexdigest()
        self.repository.insert_auto_send_attempt({"id": f"autosend-attempt-{uuid4()}", "owner_id": owner_id, "rule_id": rule_id, "channel": channel, "recipient": recipient, "fingerprint": fingerprint, "status": status, "message_id": message_id, "attempted_at": now or datetime.now(UTC), "error_code": error_code})

    async def execute_scoped_auto_send(self, owner_id: str, rule_id: str, channel: str, recipient: str, content: str, identity: Any, device: Any, *, message_class: str = "normal", context: Mapping[str, object] | None = None, now: datetime | None = None) -> Any:
        if self.communications is None:
            raise RuntimeError("communications_hub_unavailable")
        row = self.repository.auto_send_rule(owner_id, rule_id)
        if row is None:
            raise KeyError(rule_id)
        rule = self._rule_from_row(row)
        profile = await self.personalization.get(owner_id) if self.personalization is not None else None
        timezone_name = profile.values.get("timezone") if profile and isinstance(profile.values.get("timezone"), str) else None
        allowed, reason = self.can_auto_send_scoped(owner_id, channel, recipient, content, message_class=message_class, context=context, timezone_name=timezone_name, now=now)
        if not allowed or not rule.enabled or rule.channel != channel or rule.message_class != message_class or recipient not in rule.recipient_allowlist:
            await self.record_auto_send_attempt(owner_id, rule_id, channel, recipient, content, status="denied", error_code=reason)
            raise PermissionError(reason)
        result = await self.communications._send_scoped_auto_verified(owner_id, channel, recipient, content, identity, device, rule_id=rule_id)
        await self.record_auto_send_attempt(owner_id, rule_id, channel, recipient, content, status=result.status, message_id=result.message_id, error_code=result.error_code)
        return result

    @staticmethod
    def _validate_rule(rule: AutoSendRule) -> None:
        if not rule.channel.strip() or not rule.recipient_allowlist:
            raise ValueError("auto-send channel and recipient allowlist are required")
        if rule.max_frequency <= 0 or rule.window_seconds <= 0:
            raise ValueError("auto-send frequency and window must be positive")
        if rule.approval_requirement not in {"always", "none"}:
            raise ValueError("unsupported auto-send approval requirement")
        if rule.message_class in {"bulk", "important", "urgent", "sensitive", "financial"}:
            raise ValueError("unsafe auto-send message class")
        if rule.sensitivity in {"financial", "sensitive"}:
            raise ValueError("unsafe auto-send sensitivity")
        if (rule.allowed_time_start is None) != (rule.allowed_time_end is None):
            raise ValueError("auto-send time window requires both endpoints")
        if rule.allowed_time_start:
            try:
                time.fromisoformat(rule.allowed_time_start or "")
                time.fromisoformat(rule.allowed_time_end or "")
            except ValueError as exc:
                raise ValueError("invalid auto-send time window") from exc

    async def _emit(self, event_type: str, item: CommunicationFollowUp, state: EventState = EventState.EMITTED) -> None:
        event = Event.create(event_type, EventCategory.COMMUNICATION, correlation_id=item.followup_id, actor_id=item.owner_id, payload={"owner_id": item.owner_id, "followup_id": item.followup_id, "thread_id": item.thread_id, "status": item.status}, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)

    @staticmethod
    def _from_row(row: Mapping[str, object]) -> CommunicationFollowUp:
        return CommunicationFollowUp(str(row["id"]), str(row["owner_id"]), str(row["thread_id"]), row.get("message_id"), str(row["direction"]), str(row["status"]), str(row["summary"]), datetime.fromisoformat(str(row["due_at"])), datetime.fromisoformat(str(row["created_at"])), datetime.fromisoformat(str(row["resolved_at"])) if row.get("resolved_at") else None, row.get("related_goal_id"), row.get("related_mission_id"), json.loads(str(row["metadata_json"])))

    @staticmethod
    def _rule_from_row(row: Mapping[str, object]) -> AutoSendRule:
        return AutoSendRule(str(row["id"]), str(row["owner_id"]), str(row["channel"]), tuple(json.loads(str(row["recipient_allowlist_json"]))), str(row["message_class"]), json.loads(str(row["allowed_context_json"])), int(row["max_frequency"]), float(row["window_seconds"]), row.get("allowed_time_start"), row.get("allowed_time_end"), str(row["sensitivity"]), str(row["approval_requirement"]), bool(row["enabled"]), datetime.fromisoformat(str(row["created_at"])), datetime.fromisoformat(str(row["updated_at"])))

    @staticmethod
    def _in_window(start: str | None, end: str | None, current: datetime) -> bool:
        if not start or not end:
            return True
        try:
            begin, finish = time.fromisoformat(start), time.fromisoformat(end)
        except ValueError:
            return False
        return begin <= current.time() <= finish if begin <= finish else current.time() >= begin or current.time() <= finish
