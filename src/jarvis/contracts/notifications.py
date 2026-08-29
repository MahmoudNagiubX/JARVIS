"""Local/device notification contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Notification:
    notification_id: str
    title: str
    message: str
    severity: str
    source: str
    action_options: tuple[str, ...] = ()
    target_device: str | None = None
    expires_at: datetime | None = None
    dedup_key: str | None = None
    created_at: datetime | None = None
    delivered_at: datetime | None = None
    dismissed_at: datetime | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    owner_id: str | None = None
