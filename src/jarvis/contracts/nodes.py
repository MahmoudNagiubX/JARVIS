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
class VenomNodePlan:
    descriptor: NodeDescriptor
    services: tuple[str, ...]
    heavy_inference: bool = False
