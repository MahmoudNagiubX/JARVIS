"""Product-owned contracts for the experience projection layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class ExperienceState(StrEnum):
    OFFLINE = "offline"
    STARTING = "starting"
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    PROCESSING = "processing"
    TOOL_EXECUTING = "tool_executing"
    WORKER_RUNNING = "worker_running"
    APPROVAL_REQUIRED = "approval_required"
    RESEARCHING = "researching"
    ENGINEERING_TASK = "engineering_task"
    SPEAKING = "speaking"
    PROACTIVE_ALERT = "proactive_alert"
    DEGRADED = "degraded"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class SystemStatusProjection:
    state: ExperienceState = ExperienceState.OFFLINE
    runtime_state: str = "created"
    offline: bool = True
    model_provider: str | None = None
    model_available: bool = False
    event_count: int = 0
    active_runs: int = 0
    active_workers: int = 0
    error_count: int = 0
    generated_at: datetime | None = None
    topology: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConversationProjection:
    conversation_id: str | None = None
    session_id: str | None = None
    state: str = "idle"
    last_message: str | None = None
    response: str | None = None


@dataclass(frozen=True, slots=True)
class RunProjection:
    run_id: str
    status: str
    correlation_id: str | None = None
    pending_approval_id: str | None = None
    error_code: str | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class VoiceProjection:
    state: str = "idle"
    route: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DeviceProjection:
    device_id: str
    status: str
    name: str | None = None
    capabilities: tuple[str, ...] = ()
    last_seen: datetime | None = None


@dataclass(frozen=True, slots=True)
class GoalProjection:
    goal_id: str
    title: str
    status: str
    priority: int = 0


@dataclass(frozen=True, slots=True)
class NotificationProjection:
    notification_id: str
    title: str
    message: str
    severity: str = "info"
    dismissed: bool = False


@dataclass(frozen=True, slots=True)
class ApprovalProjection:
    approval_id: str
    action: str
    status: str
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ResearchProjection:
    run_id: str
    status: str
    query: str | None = None
    evidence_count: int = 0


@dataclass(frozen=True, slots=True)
class EngineeringProjection:
    session_id: str
    provider: str
    status: str
    last_action: str | None = None
    artifact_count: int = 0


@dataclass(frozen=True, slots=True)
class HudState:
    """A serializable read model; never a source of business truth."""

    owner_id: str
    generated_at: datetime
    state: ExperienceState
    system: SystemStatusProjection
    conversation: ConversationProjection
    runs: tuple[RunProjection, ...] = ()
    voice: VoiceProjection = field(default_factory=VoiceProjection)
    devices: tuple[DeviceProjection, ...] = ()
    goals: tuple[GoalProjection, ...] = ()
    notifications: tuple[NotificationProjection, ...] = ()
    approvals: tuple[ApprovalProjection, ...] = ()
    research: tuple[ResearchProjection, ...] = ()
    engineering: tuple[EngineeringProjection, ...] = ()
    missions: tuple[dict[str, object], ...] = ()
    skills: tuple[dict[str, object], ...] = ()
    automations: tuple[dict[str, object], ...] = ()
    briefings: tuple[dict[str, object], ...] = ()
    intelligence: tuple[dict[str, object], ...] = ()
    workspace: tuple[dict[str, object], ...] = ()
    worker_delegations: tuple[dict[str, object], ...] = ()
    evaluations: tuple[dict[str, object], ...] = ()
    presence: dict[str, object] = field(default_factory=dict)
    attention: dict[str, object] = field(default_factory=dict)
    operations: dict[str, object] = field(default_factory=dict)
    focus: dict[str, object] | None = None
    follow_ups: tuple[dict[str, object], ...] = ()
    home: dict[str, object] = field(default_factory=dict)
    timeline: tuple[dict[str, object], ...] = ()


class ExperienceGateway(Protocol):
    async def state(self, owner_id: str) -> HudState: ...

    async def system(self, owner_id: str) -> SystemStatusProjection: ...

    def timeline(self, owner_id: str, limit: int = 100) -> tuple[dict[str, object], ...]: ...
