"""Bounded orchestration for personal modes and daily operations."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import uuid4

from ..bus import InMemoryEventBus
from ..contracts import DeviceIdentity, Identity, PersonalizationUpdate
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository
from ..world_state.service import DurableWorldStateService


class OperationKind(StrEnum):
    WORK_START = "work_start"
    STUDY_START = "study_start"
    FOCUS_SESSION = "focus_session"
    PROJECT_CHECK = "project_check"
    SYSTEM_CHECK = "system_check"
    END_OF_DAY = "end_of_day"
    WEEKLY_REVIEW = "weekly_review"
    LEAVE_MODE = "leave_mode"
    RETURN_MODE = "return_mode"
    SLEEP_MODE = "sleep_mode"


@dataclass(frozen=True, slots=True)
class ModeState:
    mode_id: str
    owner_id: str
    mode: str
    source: str
    started_at: datetime
    expires_at: datetime | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FocusSession:
    focus_id: str
    owner_id: str
    status: str
    goal_id: str | None = None
    mission_id: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ends_at: datetime | None = None
    ended_at: datetime | None = None
    interruption_reason: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OperationStep:
    name: str
    status: str
    output: dict[str, object] = field(default_factory=dict)
    error: str | None = None
    optional: bool = False


@dataclass(frozen=True, slots=True)
class PersonalOperationResult:
    operation_id: str
    owner_id: str
    operation: str
    overall_status: str
    steps: tuple[OperationStep, ...]
    evidence: tuple[str, ...] = ()
    failed_optional_steps: tuple[str, ...] = ()
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


class PersonalOperationsService:
    """Coordinates existing authorities and does not own goals, tasks, or messages."""

    MODES = frozenset({"normal", "work", "study", "focus", "meeting", "sleep", "do_not_disturb", "away"})

    def __init__(self, repository: RuntimeRepository, event_bus: InMemoryEventBus, world_state: DurableWorldStateService, personalization: Any, *, goals: Any = None, missions: Any = None, briefings: Any = None, notifications: Any = None, automation: Any = None, offline: Any = None) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.world_state = world_state
        self.personalization = personalization
        self.goals = goals
        self.missions = missions
        self.briefings = briefings
        self.notifications = notifications
        self.automation = automation
        self.offline = offline
        self._modes: dict[str, ModeState] = {}
        self._focus: dict[str, FocusSession] = {}

    async def set_mode(self, owner_id: str, mode: str, *, ttl_seconds: float | None = None, source: str = "user", metadata: dict[str, object] | None = None) -> ModeState:
        normalized = mode.strip().casefold()
        if normalized not in self.MODES:
            raise ValueError("unsupported personal mode")
        now = datetime.now(UTC)
        expires = now + timedelta(seconds=ttl_seconds) if ttl_seconds is not None else None
        state = ModeState(f"mode-{uuid4()}", owner_id, normalized, source, now, expires, dict(metadata or {}))
        self._modes[owner_id] = state
        self.repository.insert_personal_mode(state)
        await self.world_state.set_fact(owner_id, "personal.mode", normalized, source="runtime", source_reference=state.mode_id, expires_at=expires, freshness_seconds=ttl_seconds)
        await self._emit("attention.mode_changed", owner_id, {"mode": normalized, "expires_at": expires.isoformat() if expires else None}, EventState.COMPLETED)
        return state

    async def mode(self, owner_id: str, *, now: datetime | None = None) -> ModeState:
        state = self._modes.get(owner_id)
        if state is None:
            rows = self.repository.personal_modes(owner_id, 1)
            if rows:
                state = self._mode_from_row(rows[0])
                self._modes[owner_id] = state
        current = now or datetime.now(UTC)
        if state is None or state.expires_at is not None and state.expires_at <= current:
            return ModeState("mode-default", owner_id, "normal", "default", current)
        return state

    async def modes(self, owner_id: str) -> list[ModeState]:
        values = [self._mode_from_row(row) for row in self.repository.personal_modes(owner_id)]
        current = await self.mode(owner_id)
        if not any(item.mode_id == current.mode_id for item in values):
            values.insert(0, current)
        return values

    async def start_focus(self, owner_id: str, *, duration_seconds: float | None = None, goal_id: str | None = None, mission_id: str | None = None, metadata: dict[str, object] | None = None) -> FocusSession:
        current = await self.focus(owner_id)
        if current is not None:
            return current
        now = datetime.now(UTC)
        session = FocusSession(f"focus-{uuid4()}", owner_id, "active", goal_id, mission_id, now, now + timedelta(seconds=duration_seconds) if duration_seconds else None, metadata=dict(metadata or {}))
        self._focus[owner_id] = session
        self.repository.insert_focus_session(session)
        await self.set_mode(owner_id, "focus", ttl_seconds=duration_seconds, source="focus")
        await self._emit("focus.started", owner_id, {"focus_id": session.focus_id, "goal_id": goal_id, "mission_id": mission_id}, EventState.COMPLETED)
        return session

    async def end_focus(self, owner_id: str, *, reason: str | None = None) -> FocusSession:
        session = await self.focus(owner_id)
        if session is None:
            raise KeyError("active_focus_session")
        ended = replace(session, status="interrupted" if reason else "completed", ended_at=datetime.now(UTC), interruption_reason=reason)
        self._focus[owner_id] = ended
        self.repository.insert_focus_session(ended)
        await self.set_mode(owner_id, "normal", source="focus_end")
        await self._emit("focus.interrupted" if reason else "focus.ended", owner_id, {"focus_id": ended.focus_id, "reason": reason}, EventState.COMPLETED)
        return ended

    async def focus(self, owner_id: str) -> FocusSession | None:
        if owner_id in self._focus:
            item = self._focus[owner_id]
            if item.ends_at and item.ends_at <= datetime.now(UTC) and item.status == "active":
                return await self.end_focus(owner_id, reason="duration_elapsed")
            return item if item.status == "active" else None
        row = self.repository.focus_session(owner_id)
        if row is None:
            return None
        item = self._focus_from_row(row)
        self._focus[owner_id] = item
        return item

    async def run(self, owner_id: str, operation: str, *, identity: Identity | None = None, device: DeviceIdentity | None = None, values: dict[str, object] | None = None) -> PersonalOperationResult:
        if identity is not None and identity.owner_id != owner_id:
            raise PermissionError("operation owner mismatch")
        if device is not None and device.owner_id != owner_id:
            raise PermissionError("operation device mismatch")
        values = values or {}
        try:
            kind = OperationKind(operation)
        except ValueError as exc:
            raise ValueError("unsupported personal operation") from exc
        started = datetime.now(UTC)
        operation_id = f"operation-{uuid4()}"
        await self._emit("personal_operation.started", owner_id, {"operation_id": operation_id, "operation": kind.value}, EventState.ACCEPTED)
        steps: list[OperationStep] = []
        evidence: list[str] = []
        failed_optional: list[str] = []

        async def step(name: str, action: Any, *, optional: bool = False) -> None:
            try:
                output = await action() if action is not None else {}
                output = output if isinstance(output, dict) else {"value": output}
                steps.append(OperationStep(name, "completed", output, optional=optional))
                evidence.extend(str(item) for item in output.get("evidence", ()) if isinstance(item, str))
                await self._emit("personal_operation.step_completed", owner_id, {"operation_id": operation_id, "step": name}, EventState.COMPLETED)
            except Exception as exc:
                steps.append(OperationStep(name, "unavailable" if optional else "failed", {}, exc.__class__.__name__, optional))
                if optional:
                    failed_optional.append(name)
                else:
                    raise

        if kind is OperationKind.WORK_START:
            await step("mode", lambda: self._mode_output(awaitable=self.set_mode(owner_id, "work", source="operation")))
            await step("project_check", lambda: self._project_check(owner_id), optional=True)
            await step("active_goals_missions", lambda: self._goal_mission_check(owner_id), optional=True)
            await step("briefing", lambda: self._briefing(owner_id, "work_start"), optional=True)
            await step("system_check", lambda: self._system_check(), optional=True)
        elif kind is OperationKind.STUDY_START:
            await step("mode", lambda: self._mode_output(awaitable=self.set_mode(owner_id, "study", source="operation", metadata={"goal_id": values.get("goal_id")})))
            await step("learning_context", lambda: self._goal_mission_check(owner_id, goal_id=values.get("goal_id") if isinstance(values.get("goal_id"), str) else None), optional=True)
            await step("briefing", lambda: self._briefing(owner_id, "study_start"), optional=True)
            await step("study_preferences", lambda: self._preference_output(owner_id, "study_mode_preferences"), optional=True)
        elif kind is OperationKind.FOCUS_SESSION:
            if str(values.get("action", "start")) == "end":
                await step("focus_end", lambda: self._focus_output(awaitable=self.end_focus(owner_id)))
            else:
                await step("focus_start", lambda: self._focus_output(awaitable=self.start_focus(owner_id, duration_seconds=float(values["duration_seconds"]) if values.get("duration_seconds") is not None else None, goal_id=values.get("goal_id") if isinstance(values.get("goal_id"), str) else None, mission_id=values.get("mission_id") if isinstance(values.get("mission_id"), str) else None)))
        elif kind is OperationKind.LEAVE_MODE:
            await step("mode", lambda: self._mode_output(awaitable=self.set_mode(owner_id, "away", source="operation")))
        elif kind is OperationKind.RETURN_MODE:
            await step("mode", lambda: self._mode_output(awaitable=self.set_mode(owner_id, "normal", source="operation")))
        elif kind is OperationKind.SLEEP_MODE:
            await step("mode", lambda: self._mode_output(awaitable=self.set_mode(owner_id, "sleep", ttl_seconds=float(values["ttl_seconds"]) if values.get("ttl_seconds") else None, source="operation")))
        elif kind is OperationKind.END_OF_DAY:
            await step("briefing", lambda: self._briefing(owner_id, "end_of_day"))
            await step("mode", lambda: self._mode_output(awaitable=self.set_mode(owner_id, "normal", source="operation")))
        elif kind is OperationKind.WEEKLY_REVIEW:
            await step("briefing", lambda: self._briefing(owner_id, "weekly"))
        elif kind is OperationKind.PROJECT_CHECK:
            await step("projects", lambda: self._project_check(owner_id))
        elif kind is OperationKind.SYSTEM_CHECK:
            await step("system_check", lambda: self._system_check())
        status = "partial" if failed_optional else "completed"
        result = PersonalOperationResult(operation_id, owner_id, kind.value, status, tuple(steps), tuple(dict.fromkeys(evidence)), tuple(failed_optional), started, datetime.now(UTC))
        await self._emit("personal_operation.partial" if status == "partial" else "personal_operation.completed", owner_id, {"operation_id": operation_id, "operation": kind.value, "failed_optional_steps": failed_optional}, EventState.COMPLETED)
        return result

    async def execute(self, owner_id: str, operation: str, *, identity: Identity | None = None, device: DeviceIdentity | None = None, values: dict[str, object] | None = None) -> PersonalOperationResult:
        return await self.run(owner_id, operation, identity=identity, device=device, values=values)

    async def _briefing(self, owner_id: str, briefing_type: str) -> dict[str, object]:
        if self.briefings is None:
            raise RuntimeError("briefing_service_unavailable")
        item = await self.briefings.generate(owner_id, briefing_type)
        return {"briefing_id": item.briefing_id, "evidence": list(item.evidence_ids)} if item else {"briefing_id": None, "evidence": []}

    async def _project_check(self, owner_id: str) -> dict[str, object]:
        projects = self.repository.workspace_projects(owner_id)
        return {"project_count": len(projects), "evidence": [f"project:{item['id']}" for item in projects[:10]]}

    async def _goal_mission_check(self, owner_id: str, *, goal_id: str | None = None) -> dict[str, object]:
        goals = [item for item in self.repository.goals(owner_id) if str(item.get("status")) not in {"completed", "cancelled"} and (goal_id is None or str(item.get("id")) == goal_id)]
        missions = [item for item in self.repository.missions(owner_id) if str(item.get("status")) not in {"completed", "cancelled"}]
        return {"goals": len(goals), "missions": len(missions), "evidence": [f"goal:{item['id']}" for item in goals[:5]] + [f"mission:{item['id']}" for item in missions[:5]]}

    async def _system_check(self) -> dict[str, object]:
        return {"offline": bool(self.offline and not self.offline.state.online), "evidence": ["runtime"]}

    async def _preference_output(self, owner_id: str, key: str) -> dict[str, object]:
        profile = await self.personalization.get(owner_id)
        return {key: profile.values.get(key)}

    @staticmethod
    async def _mode_output(*, awaitable: Any) -> dict[str, object]:
        state = await awaitable
        return {"mode": state.mode, "expires_at": state.expires_at.isoformat() if state.expires_at else None}

    @staticmethod
    async def _focus_output(*, awaitable: Any) -> dict[str, object]:
        state = await awaitable
        return {"focus_id": state.focus_id, "status": state.status}

    @staticmethod
    def _mode_from_row(row: dict[str, object]) -> ModeState:
        return ModeState(str(row["id"]), str(row["owner_id"]), str(row["mode"]), str(row["source"]), datetime.fromisoformat(str(row["started_at"])), datetime.fromisoformat(str(row["expires_at"])) if row.get("expires_at") else None, json.loads(str(row["metadata_json"])))

    @staticmethod
    def _focus_from_row(row: dict[str, object]) -> FocusSession:
        return FocusSession(str(row["id"]), str(row["owner_id"]), str(row["status"]), row.get("goal_id"), row.get("mission_id"), datetime.fromisoformat(str(row["started_at"])), datetime.fromisoformat(str(row["ends_at"])) if row.get("ends_at") else None, datetime.fromisoformat(str(row["ended_at"])) if row.get("ended_at") else None, row.get("interruption_reason"), json.loads(str(row["metadata_json"])))

    async def _emit(self, event_type: str, owner_id: str, payload: dict[str, object], state: EventState = EventState.EMITTED) -> None:
        event = Event.create(event_type, EventCategory.EXPERIENCE, correlation_id=payload.get("operation_id", f"operations-{owner_id}"), actor_id=owner_id, payload={"owner_id": owner_id, **payload}, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)
