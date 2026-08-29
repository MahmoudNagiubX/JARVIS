"""Observation and world-state contracts."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Observation:
    observation_id: str
    source: str
    observed_at: datetime
    subject: str
    value: Mapping[str, object] = field(default_factory=dict)
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class WorldStateSnapshot:
    snapshot_id: str
    created_at: datetime
    observations: tuple[Observation, ...] = ()
    facts: Mapping[str, object] = field(default_factory=dict)


class WorldState(Protocol):
    def observe(self, observation: Observation) -> Awaitable[None]: ...

    def snapshot(self) -> Awaitable[WorldStateSnapshot]: ...
