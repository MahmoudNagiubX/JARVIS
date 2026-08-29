"""Transient presence contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum


class PresenceSource(StrEnum):
    VOICE_ENDPOINT = "voice_endpoint"
    CLIENT_SESSION = "client_session"
    DEVICE_HEARTBEAT = "device_heartbeat"
    ORIGINATING_DEVICE = "originating_device"
    EXPLICIT_ROOM = "explicit_room"


@dataclass(frozen=True, slots=True)
class PresenceObservation:
    observation_id: str
    owner_id: str
    source: str
    observed_at: datetime
    device_id: str | None = None
    room_id: str | None = None
    voice_endpoint_id: str | None = None
    confidence: float = 1.0
    freshness_seconds: float = 300.0
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def expires_at(self) -> datetime:
        return self.observed_at + timedelta(seconds=max(1.0, self.freshness_seconds))


@dataclass(frozen=True, slots=True)
class PresenceSnapshot:
    owner_id: str
    active_device_id: str | None = None
    room_id: str | None = None
    voice_endpoint_id: str | None = None
    source: str | None = None
    confidence: float = 0.0
    observed_at: datetime | None = None
    expires_at: datetime | None = None
    observations: tuple[PresenceObservation, ...] = ()
