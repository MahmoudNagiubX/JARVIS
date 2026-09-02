"""Bounded room fabric contracts."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class RoomRecord:
    room_id: str
    owner_id: str
    name: str
    devices: tuple[str, ...] = ()
    voice_endpoints: tuple[str, ...] = ()
    home_entities: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RoomSnapshot:
    room_id: str
    owner_id: str
    name: str
    active_endpoint_id: str | None = None
    presence_confidence: float = 0.0
    presence_source: str | None = None
    last_activity: datetime | None = None
    device_count: int = 0
    entity_count: int = 0
    metadata: Mapping[str, object] = field(default_factory=dict)
