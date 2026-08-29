"""Untrusted-message analysis that never changes system policy or sends mail."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from typing import Iterable, Mapping
from uuid import uuid4

from ...bus import InMemoryEventBus
from ...contracts import CommunicationMessage
from ...events import Event, EventCategory, EventState
from ...persistence.repositories import RuntimeRepository


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
