"""Bounded mission contracts layered above the existing GoalEngine."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class MissionStatus(StrEnum):
    DRAFT = "draft"
    PLANNED = "planned"
    READY = "ready"
    RUNNING = "running"
    WAITING = "waiting"
    WAITING_APPROVAL = "waiting_approval"
    BLOCKED = "blocked"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class MissionBudget:
    max_steps: int = 20
    max_duration: float = 900.0
    max_tool_calls: int = 20
    max_worker_runs: int = 5
    max_replans: int = 3
    max_external_actions: int = 0

    def validate(self) -> None:
        if not 1 <= self.max_steps <= 100:
            raise ValueError("mission max_steps must be between 1 and 100")
        if not 1 <= self.max_duration <= 3_600:
            raise ValueError("mission max_duration must be between 1 and 3600 seconds")
        if not 0 <= self.max_tool_calls <= 100 or not 0 <= self.max_worker_runs <= 20:
            raise ValueError("mission execution budgets are invalid")
        if not 0 <= self.max_replans <= 5 or not 0 <= self.max_external_actions <= 20:
            raise ValueError("mission recovery budgets are invalid")


@dataclass(frozen=True, slots=True)
class MissionDependency:
    mission_id: str
    required_status: str = MissionStatus.COMPLETED.value


@dataclass(frozen=True, slots=True)
class MissionStep:
    step_id: str
    title: str
    status: str = "pending"
    dependencies: tuple[str, ...] = ()
    required_capability: str | None = None
    risk_level: str = "read"
    approval_required: bool = False
    expected_evidence: tuple[str, ...] = ()
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class MissionPlan:
    steps: tuple[MissionStep, ...]
    dependencies: tuple[MissionDependency, ...] = ()
    risk_level: str = "read"
    expected_evidence: tuple[str, ...] = ()
    completion_criteria: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MissionCheckpoint:
    checkpoint_id: str
    mission_id: str
    title: str
    status: str
    created_at: datetime
    completed_at: datetime | None = None
    evidence: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MissionEvidence:
    evidence_id: str
    mission_id: str
    kind: str
    locator: str
    details: Mapping[str, object] = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class MissionResult:
    status: str
    summary: str
    evidence_ids: tuple[str, ...] = ()
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class Mission:
    mission_id: str
    owner_id: str
    request: str
    title: str
    status: MissionStatus = MissionStatus.DRAFT
    goal_id: str | None = None
    plan: MissionPlan | None = None
    budget: MissionBudget = field(default_factory=MissionBudget)
    checkpoints: tuple[MissionCheckpoint, ...] = ()
    evidence: tuple[MissionEvidence, ...] = ()
    current_step: int = 0
    tool_calls: int = 0
    worker_runs: int = 0
    external_actions: int = 0
    replan_count: int = 0
    blocked_reason: str | None = None
    approval_id: str | None = None
    result: MissionResult | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None
