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


@dataclass(frozen=True, slots=True)
class DesktopBootstrap:
    token: str
    credential: str
    device_id: str
    identity_id: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class DesktopSession:
    token: str
    owner_id: str
    identity_id: str
    device_id: str
    csrf_token: str
    expires_at: datetime


class DesktopSessionService:
    """Keep browser bootstrap material and sessions in process memory only."""

    def __init__(self, *, bootstrap_ttl_seconds: int = 30, session_ttl_seconds: int = 900) -> None:
        self.bootstrap_ttl_seconds = max(5, min(bootstrap_ttl_seconds, 120))
        self.session_ttl_seconds = max(60, min(session_ttl_seconds, 3600))
        self._bootstraps: dict[str, DesktopBootstrap] = {}
        self._sessions: dict[str, DesktopSession] = {}
        self._lock = RLock()

    def issue_bootstrap(self, credential: str, device_id: str, identity_id: str) -> str:
        if not credential or not device_id or not identity_id:
            raise ValueError("desktop bootstrap requires credential, device, and identity")
        now = datetime.now(UTC)
        item = DesktopBootstrap(
            secrets.token_urlsafe(32), credential, device_id, identity_id,
            now + timedelta(seconds=self.bootstrap_ttl_seconds),
        )
        with self._lock:
            self._prune(now)
            self._bootstraps[item.token] = item
        return item.token

    def consume_bootstrap(self, token: str) -> DesktopBootstrap | None:
        now = datetime.now(UTC)
        with self._lock:
            item = self._bootstraps.pop(token, None)
            self._prune(now)
            if item is None or item.expires_at <= now:
                return None
            return item

    def create_session(self, principal: Any) -> DesktopSession:
        now = datetime.now(UTC)
        session = DesktopSession(
            secrets.token_urlsafe(32), principal.identity.owner_id,
            principal.identity.identity_id, principal.device.device_id,
            secrets.token_urlsafe(24), now + timedelta(seconds=self.session_ttl_seconds),
        )
        with self._lock:
            self._prune(now)
            self._sessions[session.token] = session
        return session

    def get_session(self, token: str | None) -> DesktopSession | None:
        if not token:
            return None
        now = datetime.now(UTC)
        with self._lock:
            session = self._sessions.get(token)
            self._prune(now)
            if session is None or session.expires_at <= now:
                return None
            return session

    def revoke_session(self, token: str | None) -> None:
        if token:
            with self._lock:
                self._sessions.pop(token, None)

    def _prune(self, now: datetime) -> None:
        self._bootstraps = {key: item for key, item in self._bootstraps.items() if item.expires_at > now}
        self._sessions = {key: item for key, item in self._sessions.items() if item.expires_at > now}
