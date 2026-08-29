"""Deterministic presence context over existing device/session authorities."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from uuid import uuid4

from ..bus import InMemoryEventBus
from ..clients.service import ClientSessionService
from ..contracts import Observation, WorldStateQuery
from ..contracts.presence import PresenceObservation, PresenceSnapshot, PresenceSource
from ..devices.fabric import DeviceFabricService
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository
from ..voice.routing.service import VoiceRoutingService
from ..world_state.service import DurableWorldStateService


class PresenceService:
    """Owns only a transient view; facts are written to World State with TTL."""

    _priority = {
        PresenceSource.ORIGINATING_DEVICE.value: 5,
        PresenceSource.CLIENT_SESSION.value: 4,
        PresenceSource.DEVICE_HEARTBEAT.value: 3,
        # An online microphone is availability evidence, not proof of room presence.
        PresenceSource.VOICE_ENDPOINT.value: 2,
        PresenceSource.EXPLICIT_ROOM.value: 1,
    }

    def __init__(
        self,
        world_state: DurableWorldStateService,
        voice_routing: VoiceRoutingService,
        clients: ClientSessionService,
        device_fabric: DeviceFabricService,
        repository: RuntimeRepository,
        event_bus: InMemoryEventBus,
    ) -> None:
        self.world_state = world_state
        self.voice_routing = voice_routing
        self.clients = clients
        self.device_fabric = device_fabric
        self.repository = repository
        self.event_bus = event_bus
        self._observations: dict[str, dict[str, PresenceObservation]] = {}

    async def observe(self, observation: PresenceObservation) -> PresenceSnapshot:
        if not observation.owner_id.strip() or not observation.observation_id.strip():
            raise ValueError("presence observation requires owner and observation identifiers")
        if observation.source not in {item.value for item in PresenceSource}:
            raise ValueError("unsupported presence source")
        if not 0.0 <= observation.confidence <= 1.0:
            raise ValueError("presence confidence must be between 0 and 1")
        existing = self._observations.setdefault(observation.owner_id, {}).get(observation.observation_id)
        if existing is not None and self._materially_equal(existing, observation):
            return await self.snapshot(observation.owner_id, now=observation.observed_at)
        self._observations[observation.owner_id][observation.observation_id] = observation
        await self.world_state.observe(Observation(
            observation.observation_id,
            "presence",
            observation.observed_at,
            f"presence.observation.{observation.observation_id}",
            {"value": asdict(observation)},
            observation.confidence,
            observation.owner_id,
            observation.source,
            observation.freshness_seconds,
            observation.expires_at,
            35,
            "clear",
            observation.device_id,
            "owner",
        ))
        await self._emit("presence.updated", observation.owner_id, {"observation_id": observation.observation_id, "source": observation.source, "device_id": observation.device_id, "room_id": observation.room_id})
        return await self.snapshot(observation.owner_id, now=observation.observed_at)

    async def refresh(self, owner_id: str) -> PresenceSnapshot:
        """Collect only explicit runtime evidence; no polling or surveillance."""
        active_generated: set[str] = set()
        for endpoint in await self.voice_routing.list(owner_id):
            if endpoint.online and endpoint.input_enabled:
                active_generated.add(f"voice-{endpoint.endpoint_id}")
                await self.observe(PresenceObservation(
                    f"voice-{endpoint.endpoint_id}", owner_id, PresenceSource.VOICE_ENDPOINT.value,
                    endpoint.last_seen or datetime.now(UTC), endpoint.device_id, endpoint.room_id,
                    endpoint.endpoint_id, 0.35, 120.0,
                ))
        for session in self.clients.list(owner_id):
            if session.connection == "connected" and session.device_id:
                active_generated.add(f"client-{session.client_session_id}")
                await self.observe(PresenceObservation(
                    f"client-{session.client_session_id}", owner_id, PresenceSource.CLIENT_SESSION.value,
                    session.last_seen, session.device_id, None, None, 0.8, 180.0,
                ))
        for device in await self.device_fabric.list(owner_id):
            if device.status == "online" and device.last_seen:
                active_generated.add(f"device-{device.device_id}")
                await self.observe(PresenceObservation(
                    f"device-{device.device_id}", owner_id, PresenceSource.DEVICE_HEARTBEAT.value,
                    device.last_seen, device.device_id, device.room_id, None, 0.7, 120.0,
                ))
        generated = self._observations.get(owner_id, {})
        for key in tuple(generated):
            if (key.startswith("voice-") or key.startswith("client-") or key.startswith("device-")) and key not in active_generated:
                del generated[key]
        return await self.snapshot(owner_id)

    async def snapshot(self, owner_id: str, *, now: datetime | None = None) -> PresenceSnapshot:
        current = now or datetime.now(UTC)
        observations = list(self._observations.get(owner_id, {}).values())
        if not observations:
            rows = await self.world_state.facts(WorldStateQuery(owner_id, "presence.observation."))
            for fact in rows:
                if isinstance(fact.value, dict):
                    value = dict(fact.value)
                    value["metadata"] = value.get("metadata") or {}
                    try:
                        for key in ("observed_at",):
                            if isinstance(value.get(key), str):
                                value[key] = datetime.fromisoformat(value[key].replace("Z", "+00:00"))
                        item = PresenceObservation(**value)
                    except (TypeError, ValueError):
                        continue
                    self._observations.setdefault(owner_id, {})[item.observation_id] = item
                    observations.append(item)
        fresh = [item for item in observations if item.expires_at > current]
        fresh.sort(key=lambda item: (self._priority.get(item.source, 0), item.confidence, item.observed_at), reverse=True)
        chosen = fresh[0] if fresh else None
        return PresenceSnapshot(
            owner_id,
            chosen.device_id if chosen else None,
            chosen.room_id if chosen else None,
            chosen.voice_endpoint_id if chosen else None,
            chosen.source if chosen else None,
            chosen.confidence if chosen else 0.0,
            chosen.observed_at if chosen else None,
            chosen.expires_at if chosen else None,
            tuple(sorted(fresh, key=lambda item: item.observed_at, reverse=True)),
        )

    async def expire(self, owner_id: str, *, now: datetime | None = None) -> int:
        current = now or datetime.now(UTC)
        items = self._observations.get(owner_id, {})
        expired = [key for key, item in items.items() if item.expires_at <= current]
        for key in expired:
            del items[key]
            await self._emit("presence.expired", owner_id, {"observation_id": key}, EventState.COMPLETED)
        return len(expired)

    async def current(self, owner_id: str, *, now: datetime | None = None) -> PresenceSnapshot:
        return await self.snapshot(owner_id, now=now)

    async def _emit(self, event_type: str, owner_id: str, payload: dict[str, object], state: EventState = EventState.EMITTED) -> None:
        event = Event.create(event_type, EventCategory.EXPERIENCE, correlation_id=f"presence-{owner_id}", actor_id=owner_id, payload={"owner_id": owner_id, **payload}, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)

    @staticmethod
    def _materially_equal(left: PresenceObservation, right: PresenceObservation) -> bool:
        return (
            left.source == right.source
            and left.device_id == right.device_id
            and left.room_id == right.room_id
            and left.voice_endpoint_id == right.voice_endpoint_id
            and left.confidence == right.confidence
            and left.observed_at == right.observed_at
            and left.freshness_seconds == right.freshness_seconds
        )
