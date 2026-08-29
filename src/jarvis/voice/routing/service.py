"""Room-aware voice endpoint registration and deterministic routing."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from ...bus import InMemoryEventBus
from ...contracts import VoiceEndpoint, VoiceRoute
from ...events import Event, EventCategory, EventState
from ...persistence.repositories import RuntimeRepository


class VoiceRoutingService:
    """Keep replies on the originating endpoint unless an explicit handoff occurs."""

    def __init__(self, repository: RuntimeRepository, event_bus: InMemoryEventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self._endpoints: dict[str, VoiceEndpoint] = {}

    async def register(self, owner_id: str, endpoint: VoiceEndpoint) -> VoiceEndpoint:
        if endpoint.owner_id and endpoint.owner_id != owner_id:
            raise ValueError("voice endpoint owner mismatch")
        normalized = VoiceEndpoint(endpoint.endpoint_id, endpoint.device_id, endpoint.room_id, endpoint.input_enabled, endpoint.output_enabled, True, datetime.now(UTC), owner_id)
        self._endpoints[endpoint.endpoint_id] = normalized
        await self._emit("voice.endpoint_online", owner_id, {"endpoint_id": endpoint.endpoint_id, "device_id": endpoint.device_id}, EventState.COMPLETED)
        return normalized

    async def set_online(self, owner_id: str, endpoint_id: str, online: bool) -> VoiceEndpoint:
        endpoint = self._required(owner_id, endpoint_id)
        updated = VoiceEndpoint(endpoint.endpoint_id, endpoint.device_id, endpoint.room_id, endpoint.input_enabled, endpoint.output_enabled, online, datetime.now(UTC) if online else endpoint.last_seen, endpoint.owner_id)
        self._endpoints[endpoint_id] = updated
        await self._emit("voice.endpoint_online" if online else "voice.endpoint_offline", owner_id, {"endpoint_id": endpoint_id}, EventState.COMPLETED)
        return updated

    async def mute(self, owner_id: str, endpoint_id: str, *, input_enabled: bool | None = None, output_enabled: bool | None = None) -> VoiceEndpoint:
        endpoint = self._required(owner_id, endpoint_id)
        updated = VoiceEndpoint(endpoint.endpoint_id, endpoint.device_id, endpoint.room_id, endpoint.input_enabled if input_enabled is None else input_enabled, endpoint.output_enabled if output_enabled is None else output_enabled, endpoint.online, endpoint.last_seen, endpoint.owner_id)
        self._endpoints[endpoint_id] = updated
        return updated

    async def select(
        self,
        owner_id: str,
        session_id: str,
        source_endpoint_id: str,
        room_id: str | None = None,
        *,
        conversation_id: str | None = None,
        priority: int = 0,
        active_speaker: str | None = None,
    ) -> VoiceRoute:
        source = self._required(owner_id, source_endpoint_id)
        if not source.online or not source.input_enabled:
            raise ValueError("voice_source_endpoint_offline_or_muted")
        target = source
        if not source.output_enabled:
            target = next((item for item in self._endpoints.values() if item.owner_id == owner_id and item.online and item.output_enabled and item.room_id == (room_id or source.room_id)), None)
        if target is None:
            raise ValueError("voice_output_endpoint_unavailable")
        route = VoiceRoute(
            session_id, source.endpoint_id, target.endpoint_id, room_id or source.room_id,
            target.endpoint_id != source.endpoint_id, conversation_id, priority, active_speaker,
        )
        await self._emit("voice.route_selected", owner_id, {"session_id": session_id, "source_endpoint_id": source.endpoint_id, "output_endpoint_id": target.endpoint_id, "handoff": route.handoff}, EventState.COMPLETED)
        if route.handoff:
            await self._emit("voice.handoff", owner_id, {"session_id": session_id, "from": source.endpoint_id, "to": target.endpoint_id}, EventState.ACCEPTED)
        return route

    async def get(self, owner_id: str, endpoint_id: str) -> VoiceEndpoint | None:
        endpoint = self._endpoints.get(endpoint_id)
        return endpoint if endpoint and endpoint.owner_id == owner_id else None

    async def list(self, owner_id: str) -> tuple[VoiceEndpoint, ...]:
        return tuple(endpoint for endpoint in self._endpoints.values() if endpoint.owner_id == owner_id)

    def _required(self, owner_id: str, endpoint_id: str) -> VoiceEndpoint:
        endpoint = self._endpoints.get(endpoint_id)
        if endpoint is None or endpoint.owner_id != owner_id:
            raise KeyError(endpoint_id)
        return endpoint

    async def _emit(self, event_type: str, owner_id: str, payload: dict[str, object], state: EventState) -> None:
        event = Event.create(event_type, EventCategory.VOICE, correlation_id=f"voice-routing-{owner_id}", actor_id=owner_id, payload=payload, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)
