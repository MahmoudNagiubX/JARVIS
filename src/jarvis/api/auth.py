"""Short-lived credentials for browser-compatible event streams."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Any


@dataclass(frozen=True, slots=True)
class StreamTicket:
    token: str
    owner_id: str
    identity_id: str
    device_id: str
    scope: str
    expires_at: datetime


class StreamTicketService:
    """Opaque, one-use, owner/device-bound tickets with a short TTL."""

    def __init__(self, *, ttl_seconds: int = 30) -> None:
        self.ttl_seconds = max(5, min(ttl_seconds, 120))
        self._tickets: dict[str, StreamTicket] = {}
        self._lock = RLock()

    def issue(self, principal: Any, scope: str) -> StreamTicket:
        if not scope or scope not in {"events", "experience.events", "experience.events.ws"}:
            raise ValueError("unsupported_stream_scope")
        now = datetime.now(UTC)
        ticket = StreamTicket(
            secrets.token_urlsafe(32), principal.identity.owner_id, principal.identity.identity_id,
            principal.device.device_id, scope, now + timedelta(seconds=self.ttl_seconds),
        )
        with self._lock:
            self._tickets[ticket.token] = ticket
        return ticket

    def consume(self, token: str, scope: str) -> StreamTicket | None:
        now = datetime.now(UTC)
        with self._lock:
            ticket = self._tickets.get(token)
            if ticket is None or ticket.scope != scope or ticket.expires_at <= now:
                if ticket is not None and ticket.expires_at <= now:
                    self._tickets.pop(token, None)
                return None
            self._tickets.pop(token, None)
            return ticket
