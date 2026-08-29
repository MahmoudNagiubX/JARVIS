"""Safe event/schedule automation; actions remain ordinary service calls."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime, time, timedelta
from typing import Any, Mapping
from uuid import uuid4

from ..bus import InMemoryEventBus
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository


@dataclass(frozen=True, slots=True)
class AutomationTrigger:
    kind: str
    value: str


@dataclass(frozen=True, slots=True)
class AutomationCondition:
    key: str
    operator: str = "equals"
    value: object = True


@dataclass(frozen=True, slots=True)
class AutomationAction:
    kind: str
    target: str
    arguments: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AutomationRule:
    rule_id: str
    owner_id: str
    name: str
    trigger: AutomationTrigger
    conditions: tuple[AutomationCondition, ...] = ()
    actions: tuple[AutomationAction, ...] = ()
    risk_level: str = "safe"
    cooldown_seconds: float = 300.0
    enabled: bool = True
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AutomationRun:
    run_id: str
    rule_id: str
    status: str
    trigger_event_id: str | None
    result: Mapping[str, object]
    started_at: datetime
    completed_at: datetime | None = None


class AutomationService:
    """Rules can orchestrate approved services but cannot execute raw commands."""

    ALLOWED_ACTIONS = frozenset({"skill", "mission", "notification", "briefing"})

    def __init__(self, repository: RuntimeRepository, event_bus: InMemoryEventBus, *, skill_executor: Any = None, missions: Any = None, notifications: Any = None, briefings: Any = None) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.skill_executor = skill_executor
        self.missions = missions
        self.notifications = notifications
        self.briefings = briefings
        self._rules: dict[str, AutomationRule] = {}
        self._subscriptions: dict[str, object] = {}

    async def create(self, rule: AutomationRule) -> AutomationRule:
        if self.repository.owner(rule.owner_id) is None:
            raise ValueError("automation owner is unavailable")
        if not rule.name.strip() or not rule.trigger.value.strip() or rule.trigger.kind not in {"schedule", "event", "world_state", "device_state", "goal_state", "workspace_event", "finding"}:
            raise ValueError("automation name and supported trigger are required")
        conditions = rule.conditions if isinstance(rule.conditions, tuple) else tuple(rule.conditions)
        actions = rule.actions if isinstance(rule.actions, tuple) else (rule.actions,)
        if any(action.kind not in self.ALLOWED_ACTIONS or action.target.startswith(("cmd:", "shell:", "python:")) for action in actions):
            raise ValueError("automation actions must target skills, missions, notifications, or briefings")
        now = datetime.now(UTC)
        normalized = replace(rule, rule_id=rule.rule_id or f"automation-{uuid4()}", conditions=conditions, actions=actions, created_at=rule.created_at or now, updated_at=now)
        self._rules[normalized.rule_id] = normalized
        self.repository.insert_automation_rule(normalized)
        if normalized.trigger.kind in {"event", "workspace_event", "finding"} and normalized.trigger.value:
            self._subscriptions[normalized.rule_id] = self.event_bus.subscribe(normalized.trigger.value, self.handle_event)
        return normalized

    async def list(self, owner_id: str) -> tuple[AutomationRule, ...]:
        for row in self.repository.automation_rules(owner_id):
            if row["id"] not in self._rules:
                self._hydrate(row)
        return tuple(sorted((item for item in self._rules.values() if item.owner_id == owner_id), key=lambda item: item.rule_id))

    async def get(self, owner_id: str, rule_id: str) -> AutomationRule | None:
        item = self._rules.get(rule_id)
        if item is not None:
            return item if item.owner_id == owner_id else None
        row = self.repository.automation_rule(owner_id, rule_id)
        return self._hydrate(row) if row else None

    async def set_enabled(self, owner_id: str, rule_id: str, enabled: bool) -> AutomationRule:
        current = await self.get(owner_id, rule_id)
        if current is None:
            raise KeyError(rule_id)
        updated = replace(current, enabled=enabled, updated_at=datetime.now(UTC))
        self._rules[rule_id] = updated
        self.repository.insert_automation_rule(updated)
        return updated

    async def handle_event(self, event: Event, *, context: Mapping[str, object] | None = None) -> tuple[AutomationRun, ...]:
        if event.category is EventCategory.AUTOMATION:
            return ()
        owner_id = event.payload.get("owner_id") if isinstance(event.payload.get("owner_id"), str) else event.actor_id
        if not owner_id:
            return ()
        runs: list[AutomationRun] = []
        for rule in await self.list(owner_id):
            if not rule.enabled or not self._trigger_matches(rule.trigger, event):
                continue
            merged = {**dict(context or {}), **dict(event.payload), "event_type": event.event_type}
            if not all(self._condition_matches(condition, merged) for condition in rule.conditions):
                await self._emit("automation.suppressed", rule, {"reason": "condition_false", "event_id": event.event_id})
                continue
            if rule.last_run_at and datetime.now(UTC) - rule.last_run_at < timedelta(seconds=rule.cooldown_seconds):
                await self._emit("automation.suppressed", rule, {"reason": "cooldown", "event_id": event.event_id})
                continue
            run = await self._run(rule, event, merged)
            runs.append(run)
        return tuple(runs)

    async def run_schedule(self, owner_id: str, *, now: datetime | None = None, context: Mapping[str, object] | None = None) -> tuple[AutomationRun, ...]:
        current = now or datetime.now(UTC)
        runs: list[AutomationRun] = []
        for rule in await self.list(owner_id):
            if not rule.enabled or rule.trigger.kind != "schedule" or not self._schedule_matches(rule.trigger.value, current):
                continue
            if rule.last_run_at and current - rule.last_run_at < timedelta(seconds=rule.cooldown_seconds):
                continue
            runs.append(await self._run(rule, None, context or {}))
        return tuple(runs)

    async def _run(self, rule: AutomationRule, event: Event | None, context: Mapping[str, object]) -> AutomationRun:
        started = datetime.now(UTC)
        await self._emit("automation.triggered", rule, {"event_id": event.event_id if event else None})
        results: list[Mapping[str, object]] = []
        status = "completed"
        for action in rule.actions:
            try:
                if action.kind == "skill":
                    identity, device = context.get("identity"), context.get("device")
                    if self.skill_executor is None or identity is None or device is None:
                        result = {"status": "suppressed", "error_code": "skill_context_unavailable"}
                    else:
                        output = await self.skill_executor.execute(action.target, action.arguments, identity, device)
                        result = asdict(output)
                elif action.kind == "mission":
                    result = {"status": "suppressed", "error_code": "mission_creation_requires_explicit_context"}
                elif action.kind == "notification":
                    if self.notifications is None:
                        result = {"status": "suppressed", "error_code": "notifications_unavailable"}
                    else:
                        item = await self.notifications.create(rule.owner_id, str(action.arguments.get("title", rule.name)), str(action.arguments.get("message", action.target)), severity=str(action.arguments.get("severity", "info")), source="automation", dedup_key=f"automation:{rule.rule_id}")
                        result = {"status": "completed", "notification_id": item.notification_id}
                elif action.kind == "briefing":
                    if self.briefings is None:
                        result = {"status": "suppressed", "error_code": "briefings_unavailable"}
                    else:
                        item = await self.briefings.generate(rule.owner_id, action.target)
                        result = {"status": "completed" if item else "no_useful_information", "briefing_id": item.briefing_id if item else None}
                else:
                    result = {"status": "suppressed", "error_code": "unsupported_action"}
                results.append(result)
                if result.get("status") in {"denied", "failed", "suppressed"}:
                    status = "awaiting_approval" if result.get("error_code") == "approval_required" else "failed"
            except Exception as exc:
                results.append({"status": "failed", "error_code": exc.__class__.__name__})
                status = "failed"
        completed = datetime.now(UTC)
        run = AutomationRun(f"automation-run-{uuid4()}", rule.rule_id, status, event.event_id if event else None, {"actions": results}, started, completed)
        self.repository.insert_automation_run(run)
        updated = replace(rule, last_run_at=completed, updated_at=completed)
        self._rules[rule.rule_id] = updated
        self.repository.insert_automation_rule(updated)
        await self._emit("automation.completed" if status == "completed" else "automation.failed", updated, {"run_id": run.run_id, "status": status}, EventState.COMPLETED if status == "completed" else EventState.FAILED)
        return run

    @staticmethod
    def _trigger_matches(trigger: AutomationTrigger, event: Event) -> bool:
        if trigger.kind not in {"event", "workspace_event", "finding"}:
            return False
        return trigger.value in {event.event_type, "*"} or (trigger.kind == "workspace_event" and event.category is EventCategory.WORKSPACE) or (trigger.kind == "finding" and event.category is EventCategory.INTELLIGENCE)

    @staticmethod
    def _condition_matches(condition: AutomationCondition, values: Mapping[str, object]) -> bool:
        actual = values.get(condition.key)
        if condition.operator == "equals": return actual == condition.value
        if condition.operator == "not_equals": return actual != condition.value
        if condition.operator == "contains": return condition.value in actual if isinstance(actual, (str, list, tuple, set)) else False
        if condition.operator == "in": return actual in condition.value if isinstance(condition.value, (list, tuple, set)) else False
        if condition.operator == "exists": return (actual is not None) is bool(condition.value)
        return False

    @staticmethod
    def _schedule_matches(value: str, now: datetime) -> bool:
        # Supported deliberately small format: HH:MM UTC or '*' for manual ticks.
        if value == "*": return True
        try:
            hour, minute = (int(part) for part in value.split(":", 1))
            return now.hour == hour and now.minute == minute
        except (ValueError, TypeError):
            return False

    def _hydrate(self, row: Mapping[str, object] | None) -> AutomationRule | None:
        if row is None: return None
        import json
        trigger = AutomationTrigger(**json.loads(str(row["trigger_json"])))
        conditions = tuple(AutomationCondition(**item) for item in json.loads(str(row["conditions_json"])))
        actions = tuple(AutomationAction(**item) for item in json.loads(str(row["actions_json"])))
        item = AutomationRule(str(row["id"]), str(row["owner_id"]), str(row["name"]), trigger, conditions, actions, str(row["risk_level"]), float(row["cooldown_seconds"]), bool(row["enabled"]), self._time(row.get("last_run_at")), self._time(row.get("next_run_at")), self._time(row.get("created_at")), self._time(row.get("updated_at")))
        self._rules[item.rule_id] = item
        if item.trigger.kind in {"event", "workspace_event", "finding"} and item.trigger.value and item.rule_id not in self._subscriptions:
            self._subscriptions[item.rule_id] = self.event_bus.subscribe(item.trigger.value, self.handle_event)
        return item

    async def _emit(self, name: str, rule: AutomationRule, payload: Mapping[str, object], state: EventState = EventState.EMITTED) -> None:
        event = Event.create(name, EventCategory.AUTOMATION, correlation_id=rule.rule_id, actor_id=rule.owner_id, payload={"owner_id": rule.owner_id, "automation_id": rule.rule_id, **dict(payload)}, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)

    @staticmethod
    def _time(value: object) -> datetime | None:
        if not isinstance(value, str): return None
        try: return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError: return None
