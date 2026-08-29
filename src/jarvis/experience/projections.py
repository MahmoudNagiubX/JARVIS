"""Event-derived read models for the HUD and other clients."""

from __future__ import annotations

import inspect
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, replace
from datetime import UTC, datetime
from typing import Any

from ..bus import EventSubscription, InMemoryEventBus
from ..contracts import (
    ApprovalProjection,
    ConversationProjection,
    DeviceProjection,
    EngineeringProjection,
    ExperienceState,
    GoalProjection,
    HudState,
    NotificationProjection,
    ResearchProjection,
    RunProjection,
    SystemStatusProjection,
    VoiceProjection,
)
from ..events import Event, EventCategory, EventState
from ..security import redact


StateLoader = Callable[[str], Awaitable[Mapping[str, object]] | Mapping[str, object]]


class ExperienceProjection:
    """Maintains owner-scoped views from normalized events only.

    The projection deliberately does not expose mutation methods for business
    objects. It is safe to rebuild or discard; authorities remain in the core
    services and their durable repositories.
    """

    def __init__(
        self,
        event_bus: InMemoryEventBus,
        state_loader: StateLoader | None = None,
        *,
        repository: Any | None = None,
        timeline_limit: int = 200,
    ) -> None:
        self.event_bus = event_bus
        self.state_loader = state_loader
        self.repository = repository
        self.timeline_limit = max(20, min(timeline_limit, 1_000))
        self._system = SystemStatusProjection(generated_at=datetime.now(UTC))
        self._states: dict[str, dict[str, Any]] = defaultdict(self._empty_state)
        self._timelines: dict[str, deque[dict[str, object]]] = defaultdict(
            lambda: deque(maxlen=self.timeline_limit)
        )
        self._global_timeline: deque[dict[str, object]] = deque(maxlen=self.timeline_limit)
        self._subscriptions: tuple[EventSubscription, ...] = (event_bus.subscribe("*", self.on_event),)

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {
            "conversation": ConversationProjection(),
            "runs": {},
            "voice": VoiceProjection(),
            "devices": {},
            "goals": {},
            "notifications": {},
            "approvals": {},
            "research": {},
            "engineering": {},
            "missions": {},
            "skills": {},
            "automations": {},
            "briefings": {},
            "intelligence": {},
            "workspace": {},
            "worker_delegations": {},
            "evaluations": {},
            "presence": {},
            "attention": {},
            "operations": {},
            "focus": None,
            "follow_ups": {},
            "home": {},
        }

    async def on_event(self, event: Event) -> None:
        owner = self._owner(event)
        item = self._event_item(event)
        self._global_timeline.append(item)
        if owner:
            owners = (owner,)
            self._timelines[owner].append(item)
        else:
            owners = tuple(self._states) or ()
            for current in owners:
                self._timelines[current].append(item)
        self._update_system(event)
        for current in owners:
            self._apply(current, event)
        if event.event_type != "experience.projection.updated" and owners:
            update = Event.create(
                "experience.projection.updated", EventCategory.EXPERIENCE,
                correlation_id=event.correlation_id, causation_id=event.event_id,
                actor_id=event.actor_id, payload={"owner_id": owners[0], "source_event_id": event.event_id},
                state=EventState.COMPLETED,
            )
            if self.repository is not None:
                self.repository.append_event(update)
            await self.event_bus.publish(update)

    def _owner(self, event: Event) -> str | None:
        value = event.payload.get("owner_id")
        if isinstance(value, str) and value:
            return value
        return event.actor_id

    def _update_system(self, event: Event) -> None:
        state = self._state_for_event(event)
        status = self._system.state if state is None else state
        errors = self._system.error_count + int(event.state is EventState.FAILED or event.severity.value in {"error", "critical"})
        self._system = replace(
            self._system,
            state=status,
            runtime_state="ready" if event.event_type == "system.bootstrap.ready" else self._system.runtime_state,
            event_count=self._system.event_count + 1,
            error_count=errors,
            generated_at=event.timestamp,
        )

    def _apply(self, owner_id: str, event: Event) -> None:
        state = self._states[owner_id]
        payload = event.payload
        event_type = event.event_type
        if event.category.value in {"agent", "conversation", "model"}:
            conversation = state["conversation"]
            state["conversation"] = replace(
                conversation,
                conversation_id=str(payload.get("conversation_id", conversation.conversation_id or "")) or conversation.conversation_id,
                session_id=str(payload.get("session_id", conversation.session_id or "")) or conversation.session_id,
                state=event.state.value,
                last_message=str(payload.get("text", payload.get("content", conversation.last_message or ""))) or conversation.last_message,
                response=str(payload.get("response", conversation.response or "")) or conversation.response,
            )
        run_id = payload.get("run_id")
        if isinstance(run_id, str) and run_id:
            status = self._status_from_event(event)
            previous = state["runs"].get(run_id, RunProjection(run_id, "queued"))
            state["runs"][run_id] = replace(
                previous,
                status=status,
                correlation_id=event.correlation_id,
                pending_approval_id=payload.get("approval_id", previous.pending_approval_id),
                error_code=payload.get("error_code", previous.error_code),
                updated_at=event.timestamp,
            )
        if event.category.value == "voice":
            state["voice"] = VoiceProjection(event_type.rsplit(".", 1)[-1], dict(payload))
        device_id = payload.get("device_id")
        if isinstance(device_id, str) and event.category.value == "device":
            previous = state["devices"].get(device_id, DeviceProjection(device_id, "unknown"))
            state["devices"][device_id] = replace(
                previous,
                status=str(payload.get("status", previous.status)),
                name=payload.get("name", previous.name),
                capabilities=tuple(payload.get("capabilities", previous.capabilities) or ()),
                last_seen=event.timestamp,
            )
        goal_id = payload.get("goal_id")
        if isinstance(goal_id, str) and event.category.value == "goal":
            previous = state["goals"].get(goal_id, GoalProjection(goal_id, str(payload.get("title", goal_id)), "unknown"))
            state["goals"][goal_id] = replace(previous, status=str(payload.get("to", payload.get("status", previous.status))))
        notification_id = payload.get("notification_id")
        if isinstance(notification_id, str) and event.category.value == "ui":
            previous = state["notifications"].get(notification_id, NotificationProjection(notification_id, str(payload.get("title", "Notification")), str(payload.get("message", ""))))
            state["notifications"][notification_id] = replace(previous, dismissed=event_type.endswith("dismissed"))
        approval_id = payload.get("approval_id")
        if isinstance(approval_id, str) and event.category.value == "approval":
            previous = state["approvals"].get(approval_id, ApprovalProjection(approval_id, str(payload.get("action", "")), "pending"))
            state["approvals"][approval_id] = replace(previous, status=event_type.rsplit(".", 1)[-1], reason=payload.get("reason", previous.reason))
        research_id = payload.get("research_run_id", payload.get("run_id"))
        if isinstance(research_id, str) and event.category.value == "research":
            previous = state["research"].get(research_id, ResearchProjection(research_id, "queued"))
            state["research"][research_id] = replace(previous, status=event_type.rsplit(".", 1)[-1], query=payload.get("query", previous.query), evidence_count=int(payload.get("evidence_count", previous.evidence_count)))
        engineering_id = payload.get("session_id")
        if isinstance(engineering_id, str) and event.category.value == "engineering":
            previous = state["engineering"].get(engineering_id, EngineeringProjection(engineering_id, str(payload.get("provider", "unknown")), "active"))
            state["engineering"][engineering_id] = replace(previous, status=event_type.rsplit(".", 1)[-1], last_action=payload.get("action", previous.last_action), artifact_count=int(payload.get("artifact_count", previous.artifact_count)))

    @staticmethod
    def _status_from_event(event: Event) -> str:
        if event.state is EventState.FAILED or event.event_type.endswith("failed"):
            return "failed"
        if event.state is EventState.COMPLETED or event.event_type.endswith("completed"):
            return "completed"
        return event.event_type.rsplit(".", 1)[-1]

    @staticmethod
    def _state_for_event(event: Event) -> ExperienceState | None:
        name = event.event_type
        if name == "system.bootstrap.started":
            return ExperienceState.STARTING
        if name == "system.bootstrap.ready":
            return ExperienceState.IDLE
        if name.startswith("voice."):
            leaf = name.rsplit(".", 1)[-1]
            return {"listening": ExperienceState.LISTENING, "transcribing": ExperienceState.TRANSCRIBING, "speaking": ExperienceState.SPEAKING}.get(leaf, ExperienceState.PROCESSING)
        if name.startswith("tool."):
            return ExperienceState.APPROVAL_REQUIRED if "approval" in name else ExperienceState.TOOL_EXECUTING
        if name.startswith("worker."):
            return ExperienceState.WORKER_RUNNING
        if name.startswith("research."):
            return ExperienceState.RESEARCHING
        if name.startswith("engineering."):
            return ExperienceState.ENGINEERING_TASK
        if name.startswith("approval."):
            return ExperienceState.APPROVAL_REQUIRED if not name.endswith("approved") else ExperienceState.PROCESSING
        if name.startswith("proactive."):
            return ExperienceState.PROACTIVE_ALERT
        if event.state is EventState.FAILED or event.severity.value in {"error", "critical"}:
            return ExperienceState.ERROR
        if name.startswith(("run.", "model.")):
            return ExperienceState.PROCESSING
        return None

    @classmethod
    def _event_item(cls, event: Event) -> dict[str, object]:
        return {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "category": event.category.value,
            "timestamp": event.timestamp.isoformat(),
            "correlation_id": event.correlation_id,
            "state": event.state.value,
            "severity": event.severity.value,
            "payload": cls._redact(event.payload),
        }

    @classmethod
    def _redact(cls, value: object) -> object:
        return redact(value)

    async def state(self, owner_id: str) -> HudState:
        if not owner_id.strip():
            raise ValueError("owner_id is required")
        loaded: Mapping[str, object] = {}
        if self.state_loader is not None:
            value = self.state_loader(owner_id)
            loaded = await value if inspect.isawaitable(value) else value
        state = self._states[owner_id]
        system = self._system
        external_system = loaded.get("system")
        if isinstance(external_system, Mapping):
            system = replace(
                system,
                runtime_state=str(external_system.get("runtime_state", system.runtime_state)),
                offline=bool(external_system.get("offline", system.offline)),
                model_provider=external_system.get("model_provider", system.model_provider),
                model_available=bool(external_system.get("model_available", system.model_available)),
            )
            if system.offline and system.runtime_state == "ready" and system.state not in {ExperienceState.ERROR, ExperienceState.PROACTIVE_ALERT}:
                system = replace(system, state=ExperienceState.DEGRADED)
            elif system.runtime_state not in {"ready", "starting"}:
                system = replace(system, state=ExperienceState.OFFLINE)
        timeline = tuple(self._timelines[owner_id] or self._global_timeline)[-100:]
        return HudState(
            owner_id=owner_id,
            generated_at=datetime.now(UTC),
            state=system.state,
            system=system,
            conversation=loaded.get("conversation", state["conversation"]),
            runs=tuple(state["runs"].values()),
            voice=state["voice"],
            devices=tuple(loaded.get("devices", state["devices"].values())),
            goals=tuple(loaded.get("goals", state["goals"].values())),
            notifications=tuple(loaded.get("notifications", state["notifications"].values())),
            approvals=tuple(loaded.get("approvals", state["approvals"].values())),
            research=tuple(state["research"].values()),
            engineering=tuple(state["engineering"].values()),
            missions=tuple(loaded.get("missions", state["missions"].values())),
            skills=tuple(loaded.get("skills", state["skills"].values())),
            automations=tuple(loaded.get("automations", state["automations"].values())),
            briefings=tuple(loaded.get("briefings", state["briefings"].values())),
            intelligence=tuple(loaded.get("intelligence", state["intelligence"].values())),
            workspace=tuple(loaded.get("workspace", state["workspace"].values())),
            worker_delegations=tuple(loaded.get("worker_delegations", state["worker_delegations"].values())),
            evaluations=tuple(loaded.get("evaluations", state["evaluations"].values())),
            presence=dict(loaded.get("presence", state["presence"])),
            attention=dict(loaded.get("attention", state["attention"])),
            operations=dict(loaded.get("operations", state["operations"])),
            focus=loaded.get("focus", state["focus"]),
            follow_ups=tuple(loaded.get("follow_ups", state["follow_ups"].values())),
            home=dict(loaded.get("home", state["home"])),
            timeline=timeline,
        )

    async def system(self, owner_id: str) -> SystemStatusProjection:
        return (await self.state(owner_id)).system

    def timeline(self, owner_id: str, limit: int = 100) -> tuple[dict[str, object], ...]:
        if limit < 1 or limit > self.timeline_limit:
            raise ValueError("timeline limit must be between 1 and the configured maximum")
        return tuple((self._timelines[owner_id] or self._global_timeline)[-limit:])

    def close(self) -> None:
        for subscription in self._subscriptions:
            self.event_bus.unsubscribe(subscription)


def hud_dict(state: HudState) -> dict[str, object]:
    return asdict(state)
