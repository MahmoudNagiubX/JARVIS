"""Generic node descriptors for the future Venom server role."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class NodeRole(StrEnum):
    DESKTOP = "desktop"
    SERVER = "server"
    SATELLITE = "satellite"


class NodeStatus(StrEnum):
    NOT_CONFIGURED = "not_configured"
    CONNECTING = "connecting"
    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"


@dataclass(frozen=True, slots=True)
class NodeDescriptor:
    node_id: str
    role: NodeRole
    capabilities: frozenset[str] = field(default_factory=frozenset)
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NodeHealth:
    node_id: str
    available: bool
    checked_at: datetime
    reason: str


@dataclass(frozen=True, slots=True)
class VenomStorageHealth:
    total_bytes: int
    free_bytes: int
    used_bytes: int
    usage_percent: float
    status: str = "healthy"


@dataclass(frozen=True, slots=True)
class VenomServiceHealth:
    service_name: str
    active: bool
    status: str
    last_checked: datetime


@dataclass(frozen=True, slots=True)
class VenomDetailedHealth:
    node_id: str
    status: str
    available: bool
    checked_at: datetime
    reason: str
    version: str = "phase17"
    storage: VenomStorageHealth | None = None
    services: tuple[VenomServiceHealth, ...] = ()
    cpu_percent: float | None = None
    memory_percent: float | None = None
    mqtt_healthy: bool = False
    ha_bridge_healthy: bool = False
    backup_receive_healthy: bool = False


@dataclass(frozen=True, slots=True)
class VenomNodePlan:
    descriptor: NodeDescriptor
    services: tuple[str, ...]
    heavy_inference: bool = False
