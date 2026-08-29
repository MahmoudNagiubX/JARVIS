"""Offline/online state contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ConnectivityState:
    online: bool
    last_seen: datetime | None
    source: str


@dataclass(frozen=True, slots=True)
class OfflineCapabilityDecision:
    capability: str
    available: bool
    reason: str
