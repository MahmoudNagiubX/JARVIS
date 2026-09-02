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
    owner_id: str | None = None
    source_reference: str | None = None
    freshness_seconds: float | None = None
    expires_at: datetime | None = None
    authority_level: int = 0
    conflict_state: str = "clear"
    device_id: str | None = None
    scope: str = "owner"


@dataclass(frozen=True, slots=True)
class WorldStateFact:
    fact_id: str
    owner_id: str
    key: str
    value: object
    source: str
    source_reference: str | None
    observed_at: datetime
    freshness: float | None = None
    expires_at: datetime | None = None
    confidence: float = 1.0
    authority_level: int = 0
    conflict_state: str = "clear"
    device_id: str | None = None
    scope: str = "owner"


@dataclass(frozen=True, slots=True)
class WorldStateConflict:
    conflict_id: str
    owner_id: str
    key: str
    fact_ids: tuple[str, ...]
    reason: str
    detected_at: datetime
    resolved: bool = False


@dataclass(frozen=True, slots=True)
class WorldStateQuery:
    owner_id: str
    key_prefix: str | None = None
    include_expired: bool = False
    scope: str | None = None
    scopes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WorldStateSnapshot:
    snapshot_id: str
    created_at: datetime
    observations: tuple[Observation, ...] = ()
    facts: Mapping[str, object] = field(default_factory=dict)
    conflicts: tuple[WorldStateConflict, ...] = ()


class WorldState(Protocol):
    def observe(self, observation: Observation) -> Awaitable[None]: ...

    def snapshot(self) -> Awaitable[WorldStateSnapshot]: ...


class WorldStateService(WorldState, Protocol):
    def facts(self, query: WorldStateQuery) -> Awaitable[tuple[WorldStateFact, ...]]: ...

    def conflicts(self, owner_id: str) -> Awaitable[tuple[WorldStateConflict, ...]]: ...
