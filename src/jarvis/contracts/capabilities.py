"""Unified registry metadata for currently usable capabilities."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CapabilityDescriptor:
    capability_id: str
    provider: str
    device_id: str | None
    available: bool
    risk: str
    requires_internet: bool = False
    requires_local_network: bool = False
    requires_device_online: bool = False
    permission: str = "owner"
    metadata: Mapping[str, object] = field(default_factory=dict)
