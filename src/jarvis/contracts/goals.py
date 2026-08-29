"""Goal and mission contracts for the future agent runtime."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class GoalStatus(StrEnum):
    PROPOSED = "proposed"
    ACTIVE = "active"
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


class GoalEngine(Protocol):
    def create(self, goal: Goal) -> Awaitable[Goal]: ...

    def transition(self, goal_id: str, status: GoalStatus) -> Awaitable[Goal | None]: ...
