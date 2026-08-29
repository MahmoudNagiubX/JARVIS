"""Safe event/schedule automation; actions remain ordinary service calls."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime, time, timedelta
from typing import Any, Callable, Mapping
from uuid import uuid4

from ..bus import InMemoryEventBus
from ..contracts import DeviceIdentity, Identity
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
    binding_id: str | None = None


@dataclass(frozen=True, slots=True)
class AutomationExecutionBinding:
    binding_id: str
    rule_id: str
    owner_id: str
    identity_id: str
    device_id: str
    service_principal: str
    scopes: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    created_by: str = ""
    enabled: bool = True
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
    child_ids: tuple[str, ...] = ()
    binding_id: str | None = None
    correlation_id: str | None = None


class AutomationService:
    """Rules can orchestrate approved services but cannot execute raw commands."""

    ALLOWED_ACTIONS = frozenset({"skill", "mission", "notification", "briefing"})

    def __init__(self, repository: RuntimeRepository, event_bus: InMemoryEventBus, *, skill_executor: Any = None, missions: Any = None, notifications: Any = None, briefings: Any = None, online_checker: Callable[[], bool] | None = None) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.skill_executor = skill_executor
        self.missions = missions
        self.notifications = notifications
        self.briefings = briefings
        self.online_checker = online_checker or (lambda: True)
        self._rules: dict[str, AutomationRule] = {}
        self._subscriptions: dict[str, object] = {}

    async def create(self, rule: AutomationRule, identity: Identity | None = None, device: DeviceIdentity | None = None) -> AutomationRule:
        if self.repository.owner(rule.owner_id) is None:
            raise ValueError("automation owner is unavailable")
        if not rule.name.strip() or not rule.trigger.value.strip() or rule.trigger.kind not in {"schedule", "event", "world_state", "device_state", "goal_state", "workspace_event", "finding"}:
            raise ValueError("automation name and supported trigger are required")
        if rule.risk_level not in {"read", "safe", "reversible", "consequential", "critical", "forbidden_autonomous"}:
            raise ValueError("unknown automation risk level")
        if rule.risk_level in {"critical", "forbidden_autonomous"}:
            raise ValueError("automation risk is forbidden")
        if not 0 <= rule.cooldown_seconds <= 86_400:
            raise ValueError("automation cooldown is out of bounds")
        conditions = rule.conditions if isinstance(rule.conditions, tuple) else tuple(rule.conditions)
        actions = rule.actions if isinstance(rule.actions, tuple) else (rule.actions,)
        if any(action.kind not in self.ALLOWED_ACTIONS or action.target.startswith(("cmd:", "shell:", "python:")) for action in actions):
            raise ValueError("automation actions must target skills, missions, notifications, or briefings")
        now = datetime.now(UTC)
        rule_id = rule.rule_id or f"automation-{uuid4()}"
        identity_row = self.repository.first_identity(rule.owner_id)
        device_row = self.repository.first_device(rule.owner_id)
        if identity is not None and identity.owner_id != rule.owner_id:
            raise PermissionError("automation_owner_binding_mismatch")
        if identity is not None:
            identity_id = identity.identity_id
        elif identity_row is not None:
            identity_id = str(identity_row["id"])
        else:
            raise ValueError("automation identity binding is unavailable")
        if device is not None:
            if device.owner_id != rule.owner_id:
                raise PermissionError("automation_device_owner_mismatch")
            device_id = device.device_id
            scopes = tuple(sorted(device.scopes))
            capabilities = tuple(sorted(device.capabilities))
        else:
            device_id = str(device_row["id"]) if device_row else "local-service"
            scopes = tuple(json.loads(str(device_row["scopes_json"]))) if device_row else ()
            capabilities = tuple(json.loads(str(device_row["capabilities_json"]))) if device_row else ()
        binding_id = rule.binding_id or f"automation-binding-{uuid4()}"
        binding = AutomationExecutionBinding(binding_id, rule_id, rule.owner_id, identity_id, device_id, "bound-device" if device is not None else "owner-local-service", scopes, capabilities, identity.identity_id if identity is not None else rule.owner_id, rule.enabled, now, now)
        normalized = replace(rule, rule_id=rule_id, conditions=conditions, actions=actions, created_at=rule.created_at or now, updated_at=now, binding_id=binding_id)
        self._rules[normalized.rule_id] = normalized
        self.repository.insert_automation_rule(normalized)
        self.repository.insert_automation_binding(binding)
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
        if updated.binding_id:
            self.repository.update_automation_binding(updated.binding_id, enabled=enabled, updated_at=updated.updated_at)
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
        child_ids: list[str] = []
        status = "completed"
        binding = self.repository.automation_binding(rule.rule_id, rule.owner_id)
        principal = self._resolve_binding(binding)
        if binding is None or principal is None or not self.online_checker():
            results.append({"status": "suppressed", "error_code": "automation_execution_binding_unavailable" if binding is None or principal is None else "automation_offline"})
            status = "failed"
        else:
            identity, device = principal
        for action in rule.actions if status == "completed" else ():
            try:
                if action.kind == "skill":
                    if self.skill_executor is None:
                        result = {"status": "suppressed", "error_code": "skill_context_unavailable"}
                    else:
                        output = await self.skill_executor.execute(action.target, action.arguments, identity, device)
                        result = asdict(output)
                        if output.execution_id:
                            child_ids.append(output.execution_id)
                        if output.approval_id:
                            child_ids.append(output.approval_id)
                elif action.kind == "mission":
                    if self.missions is None:
                        result = {"status": "suppressed", "error_code": "missions_unavailable"}
                    else:
                        title = str(action.arguments.get("title", action.target)).strip()
                        request = str(action.arguments.get("request", action.target)).strip()
                        mission_type = __import__("jarvis.contracts", fromlist=["Mission"]).Mission
                        mission = await self.missions.create(mission_type("", rule.owner_id, request, title))
                        mission = await self.missions.plan(rule.owner_id, mission.mission_id)
                        result = {"status": "completed", "mission_id": mission.mission_id, "mission_status": mission.status.value}
                        child_ids.append(mission.mission_id)
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
                if result.get("status") in {"approval_required", "waiting_approval"} or result.get("error_code") == "approval_required":
                    status = "awaiting_approval"
                elif result.get("status") in {"denied", "failed", "suppressed"}:
                    status = "failed"
            except Exception as exc:
                results.append({"status": "failed", "error_code": exc.__class__.__name__})
                status = "failed"
        completed = datetime.now(UTC)
        run = AutomationRun(f"automation-run-{uuid4()}", rule.rule_id, status, event.event_id if event else None, {"actions": results, "child_ids": tuple(child_ids), "binding_id": rule.binding_id}, started, completed, tuple(child_ids), rule.binding_id, rule.rule_id)
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
        trigger = AutomationTrigger(**json.loads(str(row["trigger_json"])))
        conditions = tuple(AutomationCondition(**item) for item in json.loads(str(row["conditions_json"])))
        actions = tuple(AutomationAction(**item) for item in json.loads(str(row["actions_json"])))
        binding = self.repository.automation_binding(str(row["id"]), str(row["owner_id"]))
        item = AutomationRule(str(row["id"]), str(row["owner_id"]), str(row["name"]), trigger, conditions, actions, str(row["risk_level"]), float(row["cooldown_seconds"]), bool(row["enabled"]), self._time(row.get("last_run_at")), self._time(row.get("next_run_at")), self._time(row.get("created_at")), self._time(row.get("updated_at")), str(binding["id"]) if binding else None)
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

    def _resolve_binding(self, row: Mapping[str, object] | None) -> tuple[Identity, DeviceIdentity] | None:
        if row is None or not bool(row.get("enabled")):
            return None
        identity_row = self.repository.identity(str(row.get("identity_id")))
        if identity_row is None or str(identity_row.get("owner_id")) != str(row.get("owner_id")):
            return None
        device_id = str(row.get("device_id"))
        device_row = self.repository.device(device_id)
        if device_id != "local-service" and (device_row is None or str(device_row.get("status")) != "active"):
            return None
        roles = frozenset(json.loads(str(identity_row.get("roles_json", "[]"))))
        if device_row is None:
            device_kind, platform = "local-service", "local"
            capabilities = frozenset(json.loads(str(row.get("capabilities_json", "[]"))))
            scopes = frozenset(json.loads(str(row.get("scopes_json", "[]"))))
        else:
            device_kind, platform = str(device_row["device_kind"]), str(device_row["platform"])
            capabilities = frozenset(json.loads(str(device_row["capabilities_json"])))
            scopes = frozenset(json.loads(str(device_row["scopes_json"])))
        return (
            Identity(str(identity_row["id"]), str(identity_row["display_name"]), str(identity_row["owner_id"]), roles),
            DeviceIdentity(device_id, str(row["owner_id"]), device_kind, platform, capabilities, scopes),
        )
