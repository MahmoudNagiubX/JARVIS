"""Authenticated logical client-session contracts for multi-device UX."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ClientSession:
    client_session_id: str
    owner_id: str
    identity_id: str
    device_id: str | None
    capabilities: frozenset[str] = field(default_factory=frozenset)
    subscriptions: frozenset[str] = field(default_factory=frozenset)
    ui_profile: str = "hud"
    connection: str = "connected"
    last_seen: datetime | None = None


ALLOWED_CLIENT_TOPICS = frozenset({
    "conversation", "voice", "runs", "tools", "approvals", "notifications",
    "devices", "goals", "research", "engineering", "world_state", "system_health",
})
