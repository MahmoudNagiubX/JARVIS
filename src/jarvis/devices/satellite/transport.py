"""Authenticated, bounded HTTP long-poll transport for typed satellites."""

from __future__ import annotations

import asyncio
import hashlib
import json
import queue
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from ...contracts import DeviceIdentity
from .contracts import (
    CommandObservation,
    CoreWelcome,
    SatelliteCommand,
    SatelliteHeartbeat,
    SatelliteHello,
    validate_command,
)
from .registry import WindowsSatelliteRegistry


@dataclass(slots=True)
class _PendingCommand:
    command: SatelliteCommand
    fingerprint: str
    expires_at: datetime
    completed: threading.Event = field(default_factory=threading.Event)
    result: CommandObservation | None = None


@dataclass(slots=True)
class _TransportSession:
    session_id: str
    owner_id: str
    device_id: str
    commands: queue.Queue[SatelliteCommand]
    pending: dict[str, _PendingCommand] = field(default_factory=dict)
    last_heartbeat: datetime = field(default_factory=lambda: datetime.now(UTC))
    online: bool = True


@dataclass(frozen=True, slots=True)
class ExpiredSatelliteSession:
    session_id: str
    owner_id: str
    device_id: str


@dataclass(frozen=True, slots=True)
class ResultSubmission:
    accepted: bool
    duplicate: bool = False
    reason: str | None = None
    observation: CommandObservation | None = None


class SatelliteTransportService:
    """Outer transport adapter around the canonical satellite registry.

    The HTTP server creates one asyncio loop per request, so the transport
    deliberately uses thread-safe queues/events internally and exposes async
    wrappers for the application boundary. No authority or approval policy is
    created here; the core enqueues only commands already admitted by its
    existing typed computer boundary.
    """

    MAX_COMMAND_BYTES = 64 * 1024
    MAX_RESULT_BYTES = 256 * 1024
    MAX_COMPLETED = 4096
    MAX_INACTIVE_SESSIONS = 32
    ALLOWED_RESULT_STATUSES = frozenset({"completed", "failed", "denied"})

    def __init__(
        self,
        registry: WindowsSatelliteRegistry,
        *,
        heartbeat_interval_seconds: float = 15.0,
        command_ttl_seconds: float = 30.0,
        max_queue_per_device: int = 64,
    ) -> None:
        if heartbeat_interval_seconds <= 0 or command_ttl_seconds <= 0:
            raise ValueError("transport intervals must be positive")
        if not 1 <= max_queue_per_device <= 64:
            raise ValueError("transport queue bound must be between 1 and 64")
        self.registry = registry
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.command_ttl_seconds = command_ttl_seconds
        self.max_queue_per_device = max_queue_per_device
        self._lock = threading.RLock()
        self._sessions: dict[str, _TransportSession] = {}
        self._device_sessions: dict[str, str] = {}
        self._completed: OrderedDict[tuple[str, str], tuple[str, CommandObservation]] = OrderedDict()

    async def connect(self, principal: Any, hello: SatelliteHello) -> CoreWelcome:
        return await asyncio.to_thread(self._connect, principal, hello)

    async def heartbeat(self, owner_id: str, device_id: str, heartbeat: SatelliteHeartbeat) -> bool:
        return await asyncio.to_thread(self._heartbeat, owner_id, device_id, heartbeat)

    async def poll(self, owner_id: str, device_id: str, session_id: str, wait_seconds: float = 20.0) -> SatelliteCommand | None:
        return await asyncio.to_thread(self._poll, owner_id, device_id, session_id, wait_seconds)

    async def submit_result(
        self,
        owner_id: str,
        device_id: str,
        session_id: str,
        observation: CommandObservation,
    ) -> ResultSubmission:
        return await asyncio.to_thread(self._submit_result, owner_id, device_id, session_id, observation)

    async def disconnect(self, owner_id: str, device_id: str, session_id: str) -> bool:
        return await asyncio.to_thread(self._disconnect, owner_id, device_id, session_id)

    async def revoke(self, device_id: str) -> bool:
        return await asyncio.to_thread(self._revoke, device_id)

    async def expire_stale_sessions(self, now: datetime | None = None) -> tuple[ExpiredSatelliteSession, ...]:
        return await asyncio.to_thread(self._expire_stale_sessions, now)

    def public_health(self) -> dict[str, object]:
        with self._lock:
            online = sum(1 for session in self._sessions.values() if session.online)
            total = len(self._sessions)
            return {
                "transport": "http-long-poll",
                "available": online > 0,
                "online_sessions": online,
                "degraded": total > online,
            }

    def health(self, *, include_owner: bool = False) -> dict[str, object]:
        with self._lock:
            sessions = []
            for session in self._sessions.values():
                item: dict[str, object] = {
                    "session_id": session.session_id,
                    "device_id": session.device_id,
                    "status": "online" if session.online else "offline",
                    "queued": session.commands.qsize(),
                    "in_flight": len(session.pending),
                    "last_heartbeat": session.last_heartbeat.isoformat(),
                    "heartbeat_interval_seconds": self.heartbeat_interval_seconds,
                }
                if include_owner:
                    item["owner_id"] = session.owner_id
                sessions.append(item)
            return {
                "transport": "http-long-poll",
                "max_queued_per_device": self.max_queue_per_device,
                "command_ttl_seconds": self.command_ttl_seconds,
                "sessions": sessions,
            }

    def close(self) -> None:
        with self._lock:
            for session in tuple(self._sessions.values()):
                self._fail_pending(session, "transport_closed")
                session.online = False
                self.registry.disconnect(session.session_id)

    def _connect(self, principal: Any, hello: SatelliteHello) -> CoreWelcome:
        device: DeviceIdentity = principal.device
        if hello.owner_id != principal.identity.owner_id:
            return CoreWelcome(False, None, "owner_identity_mismatch", int(self.heartbeat_interval_seconds))
        if len(hello.capabilities) > 32:
            return CoreWelcome(False, None, "capability_declaration_too_large", int(self.heartbeat_interval_seconds))
        with self._lock:
            previous_id = self._device_sessions.get(device.device_id)
            if previous_id:
                previous = self._sessions.get(previous_id)
                if previous:
                    self._fail_pending(previous, "satellite_reconnected")
                    previous.online = False
                self.registry.disconnect(previous_id)
                self.registry.retire(previous_id)
            session_ref: dict[str, str] = {}

            async def handler(command: SatelliteCommand) -> CommandObservation:
                return await self._dispatch(session_ref["session_id"], command)

            welcome = self.registry.register(hello, device, handler)
            if not welcome.accepted or welcome.session_id is None:
                return welcome
            session_ref["session_id"] = welcome.session_id
            self._sessions[welcome.session_id] = _TransportSession(
                welcome.session_id,
                principal.identity.owner_id,
                device.device_id,
                queue.Queue(maxsize=self.max_queue_per_device),
            )
            self._device_sessions[device.device_id] = welcome.session_id
            self._prune_inactive_sessions()
            return CoreWelcome(True, welcome.session_id, None, int(self.heartbeat_interval_seconds))

    async def _dispatch(self, session_id: str, command: SatelliteCommand) -> CommandObservation:
        try:
            validate_command(command)
            fingerprint = _fingerprint(command)
            if _encoded_size(command.parameters) > self.MAX_COMMAND_BYTES:
                return CommandObservation(command.command_id, "denied", error_code="command_payload_too_large")
        except (TypeError, ValueError):
            return CommandObservation(command.command_id, "denied", error_code="invalid_typed_command")
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or not session.online:
                return CommandObservation(command.command_id, "failed", error_code="satellite_offline")
            cached = self._completed.get((session.device_id, command.command_id))
            if cached:
                cached_fingerprint, observation = cached
                if cached_fingerprint != fingerprint:
                    return CommandObservation(command.command_id, "denied", error_code="command_id_reuse")
                return observation
            pending = session.pending.get(command.command_id)
            if pending is not None:
                if pending.fingerprint != fingerprint:
                    return CommandObservation(command.command_id, "denied", error_code="command_id_reuse")
            else:
                pending = _PendingCommand(
                    command,
                    fingerprint,
                    datetime.now(UTC) + timedelta(seconds=self.command_ttl_seconds),
                )
                try:
                    session.commands.put_nowait(command)
                except queue.Full:
                    return CommandObservation(command.command_id, "failed", error_code="transport_queue_overflow")
                session.pending[command.command_id] = pending
        if not await asyncio.to_thread(pending.completed.wait, self.command_ttl_seconds):
            with self._lock:
                current = session.pending.get(command.command_id)
                if current is pending:
                    observation = CommandObservation(command.command_id, "failed", error_code="command_expired")
                    self._complete(session, pending, observation)
        return pending.result or CommandObservation(command.command_id, "failed", error_code="command_expired")

    def _poll(self, owner_id: str, device_id: str, session_id: str, wait_seconds: float) -> SatelliteCommand | None:
        wait = max(0.0, min(wait_seconds, 25.0))
        with self._lock:
            session = self._session_for(session_id, owner_id, device_id)
            if session is None or not session.online:
                return None
            commands = session.commands
        end = datetime.now(UTC).timestamp() + wait
        while True:
            remaining = max(0.0, end - datetime.now(UTC).timestamp())
            try:
                command = commands.get(timeout=remaining)
            except queue.Empty:
                return None
            with self._lock:
                current = session.pending.get(command.command_id)
                if current is None:
                    continue
                if current.expires_at <= datetime.now(UTC):
                    self._complete(session, current, CommandObservation(command.command_id, "failed", error_code="command_expired"))
                    continue
                return command

    def _heartbeat(self, owner_id: str, device_id: str, heartbeat: SatelliteHeartbeat) -> bool:
        with self._lock:
            session = self._session_for(heartbeat.session_id, owner_id, device_id)
            if session is None or not session.online:
                return False
            if not self.registry.heartbeat(heartbeat):
                return False
            session.last_heartbeat = heartbeat.timestamp
            return True

    def _expire_stale_sessions(self, now: datetime | None = None) -> tuple[ExpiredSatelliteSession, ...]:
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            raise ValueError("stale-session time must be timezone-aware")
        cutoff = current.astimezone(UTC) - timedelta(seconds=max(30.0, self.heartbeat_interval_seconds * 3))
        expired: list[ExpiredSatelliteSession] = []
        with self._lock:
            for session in tuple(self._sessions.values()):
                if not session.online or session.last_heartbeat >= cutoff:
                    continue
                self._fail_pending(session, "satellite_stale")
                session.online = False
                self.registry.disconnect(session.session_id)
                if self._device_sessions.get(session.device_id) == session.session_id:
                    self._device_sessions.pop(session.device_id, None)
                expired.append(ExpiredSatelliteSession(session.session_id, session.owner_id, session.device_id))
            self._prune_inactive_sessions()
        return tuple(expired)

    def _submit_result(self, owner_id: str, device_id: str, session_id: str, observation: CommandObservation) -> ResultSubmission:
        try:
            if not observation.command_id.strip() or observation.status not in self.ALLOWED_RESULT_STATUSES:
                return ResultSubmission(False, reason="invalid_command_result", observation=observation)
            if _encoded_size(observation.output) > self.MAX_RESULT_BYTES:
                return ResultSubmission(False, reason="result_payload_too_large", observation=observation)
        except (TypeError, ValueError):
            return ResultSubmission(False, reason="invalid_command_result", observation=observation)
        with self._lock:
            session = self._session_for(session_id, owner_id, device_id)
            if session is None or not session.online:
                return ResultSubmission(False, reason="satellite_session_invalid", observation=observation)
            cached = self._completed.get((device_id, observation.command_id))
            if cached:
                return ResultSubmission(True, duplicate=True, observation=cached[1])
            pending = session.pending.get(observation.command_id)
            if pending is None:
                return ResultSubmission(False, reason="unknown_command", observation=observation)
            if pending.expires_at <= datetime.now(UTC):
                expired = CommandObservation(observation.command_id, "failed", error_code="command_expired")
                self._complete(session, pending, expired)
                return ResultSubmission(False, reason="command_expired", observation=expired)
            self._complete(session, pending, observation)
            return ResultSubmission(True, observation=observation)

    def _disconnect(self, owner_id: str, device_id: str, session_id: str) -> bool:
        with self._lock:
            session = self._session_for(session_id, owner_id, device_id)
            if session is None:
                return False
            self._fail_pending(session, "satellite_disconnected")
            session.online = False
            self.registry.disconnect(session_id)
            if self._device_sessions.get(device_id) == session_id:
                self._device_sessions.pop(device_id, None)
            return True

    def _revoke(self, device_id: str) -> bool:
        with self._lock:
            changed = self.registry.revoke(device_id)
            session_id = self._device_sessions.get(device_id)
            session = self._sessions.get(session_id) if session_id else None
            if session:
                self._fail_pending(session, "device_revoked")
                session.online = False
            self._device_sessions.pop(device_id, None)
            self._prune_inactive_sessions()
            return changed or session is not None

    def _session_for(self, session_id: str, owner_id: str, device_id: str) -> _TransportSession | None:
        session = self._sessions.get(session_id)
        if session is None or session.owner_id != owner_id or session.device_id != device_id:
            return None
        return session

    def _complete(self, session: _TransportSession, pending: _PendingCommand, observation: CommandObservation) -> None:
        pending.result = observation
        pending.completed.set()
        session.pending.pop(pending.command.command_id, None)
        self._completed[(session.device_id, pending.command.command_id)] = (pending.fingerprint, observation)
        self._completed.move_to_end((session.device_id, pending.command.command_id))
        while len(self._completed) > self.MAX_COMPLETED:
            self._completed.popitem(last=False)

    def _fail_pending(self, session: _TransportSession, error_code: str) -> None:
        for pending in tuple(session.pending.values()):
            self._complete(session, pending, CommandObservation(pending.command.command_id, "failed", error_code=error_code))

    def _prune_inactive_sessions(self) -> None:
        inactive = [session for session in self._sessions.values() if not session.online]
        inactive.sort(key=lambda session: session.last_heartbeat)
        for session in inactive[:-self.MAX_INACTIVE_SESSIONS]:
            self._sessions.pop(session.session_id, None)


def _encoded_size(value: object) -> int:
    return len(json.dumps(value, default=str, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _fingerprint(command: SatelliteCommand) -> str:
    encoded = json.dumps(
        {
            "action": command.action,
            "capability": command.capability,
            "parameters": dict(command.parameters),
            "dry_run": command.dry_run,
        },
        default=str,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
