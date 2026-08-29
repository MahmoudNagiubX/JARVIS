"""Unified registered-device capability contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class DeviceRole(StrEnum):
    PRIMARY_PC = "primary_pc"
    SERVER = "server"
    ROOM_SATELLITE = "room_satellite"
    MOBILE = "mobile"
    HOME_DEVICE_GATEWAY = "home_device_gateway"
    MICROCONTROLLER = "microcontroller"
    SPEAKER = "speaker"
    MICROPHONE = "microphone"


class DeviceStatus(StrEnum):
    REGISTERED = "registered"
    ONLINE = "online"
    OFFLINE = "offline"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class DeviceRecord:
    device_id: str
    owner_id: str
    name: str
    role: str
    transport: str
    status: str
    capabilities: frozenset[str] = field(default_factory=frozenset)
    trust_level: str = "unverified"
    last_seen: datetime | None = None
    room_id: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DeviceHeartbeat:
    device_id: str
    timestamp: datetime
    metadata: Mapping[str, object] = field(default_factory=dict)
