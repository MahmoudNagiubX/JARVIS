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
    ENROLLING = "enrolling"
    ONLINE = "online"
    DEGRADED = "degraded"
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
    platform: str = "windows"
    scopes: frozenset[str] = field(default_factory=frozenset)
    enrolled_at: datetime | None = None
    revoked_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DeviceHeartbeat:
    device_id: str
    timestamp: datetime
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DeviceEnrollmentTicket:
    ticket_id: str
    code: str
    owner_id: str
    role: str
    name: str
    platform: str
    capabilities: frozenset[str]
    scopes: frozenset[str]
    expires_at: datetime
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DeviceEnrollmentRequest:
    code: str
    device_id: str
    name: str
    platform: str
    software_version: str = "phase17"
    capabilities: frozenset[str] = field(default_factory=frozenset)
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DeviceEnrollmentResult:
    accepted: bool
    device_id: str | None = None
    credential: str | None = None
    reason: str | None = None
    enrolled_at: datetime | None = None
