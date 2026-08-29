"""Goal and mission contracts for the future agent runtime."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class GoalStatus(StrEnum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    ACTIVE = "active"
    WAITING = "waiting"
    BLOCKED = "blocked"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class Goal:
    goal_id: str
    owner_id: str
    statement: str
    status: GoalStatus = GoalStatus.PROPOSED
    created_at: datetime | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    title: str | None = None
    description: str | None = None
    priority: int = 0
    target_date: datetime | None = None
    constraints: Mapping[str, object] = field(default_factory=dict)
    budget: Mapping[str, object] = field(default_factory=dict)
    plan: tuple[str, ...] = ()
    steps: tuple[Mapping[str, object], ...] = ()
    dependencies: tuple[str, ...] = ()
    checkpoints: tuple[Mapping[str, object], ...] = ()
    next_action: str | None = None
    last_reviewed_at: datetime | None = None
    completion_criteria: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GoalCheckpoint:
    checkpoint_id: str
    goal_id: str
    title: str
    status: str
    created_at: datetime
    completed_at: datetime | None = None
    evidence: Mapping[str, object] = field(default_factory=dict)


class GoalEngine(Protocol):
    def create(self, goal: Goal) -> Awaitable[Goal]: ...

    def transition(self, goal_id: str, status: GoalStatus) -> Awaitable[Goal | None]: ...
