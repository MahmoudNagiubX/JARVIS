"""Authenticated logical client sessions with topic allowlisting."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import uuid4

from ..bus import InMemoryEventBus
from ..contracts import ALLOWED_CLIENT_TOPICS, ClientSession, DeviceIdentity, Identity
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository


class ClientSessionService:
    """Keep connection metadata only; the client cannot become an authority."""

    def __init__(self, repository: RuntimeRepository, event_bus: InMemoryEventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self._sessions: dict[str, ClientSession] = {}
        self.max_sessions = 64

    async def connect(
        self,
        identity: Identity,
        device: DeviceIdentity | None,
        subscriptions: Iterable[str] = (),
        *,
        ui_profile: str = "hud",
    ) -> ClientSession:
        topics = frozenset(subscriptions)
        unknown = topics - ALLOWED_CLIENT_TOPICS
        if unknown:
            raise ValueError(f"unsupported client topics: {sorted(unknown)}")
        active = sum(1 for item in self._sessions.values() if item.connection == "connected")
        if active >= self.max_sessions:
            raise ValueError("client session limit reached")
        if device is not None and device.owner_id != identity.owner_id:
            raise PermissionError("owner_binding_mismatch")
        session = ClientSession(
            client_session_id=f"client-{uuid4()}", owner_id=identity.owner_id,
            identity_id=identity.identity_id, device_id=device.device_id if device else None,
            capabilities=device.capabilities if device else frozenset(), subscriptions=topics,
            ui_profile=ui_profile, last_seen=datetime.now(UTC),
        )
        self._sessions[session.client_session_id] = session
        await self._emit("experience.client.connected", identity, session, EventState.COMPLETED)
        return session

    async def heartbeat(self, client_session_id: str, identity: Identity) -> ClientSession:
        current = self._required(client_session_id, identity.owner_id)
        current = ClientSession(
            current.client_session_id, current.owner_id, current.identity_id, current.device_id,
            current.capabilities, current.subscriptions, current.ui_profile, "connected", datetime.now(UTC),
        )
        self._sessions[client_session_id] = current
        return current

    async def disconnect(self, client_session_id: str, identity: Identity) -> None:
        current = self._required(client_session_id, identity.owner_id)
        self._sessions[client_session_id] = ClientSession(
            current.client_session_id, current.owner_id, current.identity_id, current.device_id,
            current.capabilities, current.subscriptions, current.ui_profile, "disconnected", datetime.now(UTC),
        )
        await self._emit("experience.client.disconnected", identity, self._sessions[client_session_id], EventState.COMPLETED)

    def list(self, owner_id: str) -> tuple[ClientSession, ...]:
        return tuple(session for session in self._sessions.values() if session.owner_id == owner_id)

    def get(self, client_session_id: str, owner_id: str) -> ClientSession | None:
        session = self._sessions.get(client_session_id)
        return session if session and session.owner_id == owner_id else None

    def _required(self, client_session_id: str, owner_id: str) -> ClientSession:
        current = self._sessions.get(client_session_id)
        if current is None or current.owner_id != owner_id:
            raise KeyError(client_session_id)
        return current

    async def _emit(self, event_type: str, identity: Identity, session: ClientSession, state: EventState) -> None:
        event = Event.create(
            event_type, EventCategory.EXPERIENCE, actor_id=identity.identity_id,
            payload={"owner_id": identity.owner_id, "client_session_id": session.client_session_id,
                     "device_id": session.device_id, "subscriptions": sorted(session.subscriptions)}, state=state,
        )
        self.repository.append_event(event)
        await self.event_bus.publish(event)
