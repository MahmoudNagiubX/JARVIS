"""Room-aware voice endpoint registration and deterministic routing."""

from __future__ import annotations

import json
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
        self._loaded_owners: set[str] = set()

    def _ensure_loaded(self, owner_id: str) -> None:
        if owner_id in self._loaded_owners:
            return
        self._loaded_owners.add(owner_id)
        for row in self.repository.personalization(owner_id):
            key = str(row.get("key", ""))
            if key.startswith("voice_endpoint:"):
                val = row.get("value_json")
                if isinstance(val, str):
                    try:
                        val = json.loads(val)
                    except Exception:
                        continue
                if isinstance(val, dict):
                    ep_id = val.get("endpoint_id") or key.split("voice_endpoint:", 1)[1]
                    last_seen = datetime.fromisoformat(val["last_seen"]) if val.get("last_seen") else None
                    self._endpoints[ep_id] = VoiceEndpoint(
                        endpoint_id=ep_id,
                        device_id=val.get("device_id", ""),
                        room_id=val.get("room_id", ""),
                        input_enabled=bool(val.get("input_enabled", True)),
                        output_enabled=bool(val.get("output_enabled", True)),
                        online=bool(val.get("online", False)),
                        last_seen=last_seen,
                        owner_id=val.get("owner_id", owner_id),
                    )

    def _save_endpoint(self, endpoint: VoiceEndpoint) -> None:
        if not endpoint.owner_id:
            return
        data = {
            "endpoint_id": endpoint.endpoint_id,
            "device_id": endpoint.device_id,
            "room_id": endpoint.room_id,
            "input_enabled": endpoint.input_enabled,
            "output_enabled": endpoint.output_enabled,
            "online": endpoint.online,
            "last_seen": endpoint.last_seen.isoformat() if endpoint.last_seen else None,
            "owner_id": endpoint.owner_id,
        }
        self.repository.set_personalization(endpoint.owner_id, f"voice_endpoint:{endpoint.endpoint_id}", data, "voice_routing")

    async def register(self, owner_id: str, endpoint: VoiceEndpoint) -> VoiceEndpoint:
        self._ensure_loaded(owner_id)
        if endpoint.owner_id and endpoint.owner_id != owner_id:
            raise ValueError("voice endpoint owner mismatch")
        normalized = VoiceEndpoint(endpoint.endpoint_id, endpoint.device_id, endpoint.room_id, endpoint.input_enabled, endpoint.output_enabled, True, datetime.now(UTC), owner_id)
        self._endpoints[endpoint.endpoint_id] = normalized
        self._save_endpoint(normalized)
        await self._emit("voice.endpoint_online", owner_id, {"endpoint_id": endpoint.endpoint_id, "device_id": endpoint.device_id}, EventState.COMPLETED)
        return normalized

    async def set_online(self, owner_id: str, endpoint_id: str, online: bool) -> VoiceEndpoint:
        endpoint = self._required(owner_id, endpoint_id)
        updated = VoiceEndpoint(endpoint.endpoint_id, endpoint.device_id, endpoint.room_id, endpoint.input_enabled, endpoint.output_enabled, online, datetime.now(UTC) if online else endpoint.last_seen, endpoint.owner_id)
        self._endpoints[endpoint_id] = updated
        self._save_endpoint(updated)
        await self._emit("voice.endpoint_online" if online else "voice.endpoint_offline", owner_id, {"endpoint_id": endpoint_id}, EventState.COMPLETED)
        return updated

    async def mute(self, owner_id: str, endpoint_id: str, *, input_enabled: bool | None = None, output_enabled: bool | None = None) -> VoiceEndpoint:
        endpoint = self._required(owner_id, endpoint_id)
        updated = VoiceEndpoint(endpoint.endpoint_id, endpoint.device_id, endpoint.room_id, endpoint.input_enabled if input_enabled is None else input_enabled, endpoint.output_enabled if output_enabled is None else output_enabled, endpoint.online, endpoint.last_seen, endpoint.owner_id)
        self._endpoints[endpoint_id] = updated
        self._save_endpoint(updated)
        return updated

    async def revoke_endpoint(self, owner_id: str, endpoint_id: str) -> VoiceEndpoint:
        endpoint = self._required(owner_id, endpoint_id)
        updated = VoiceEndpoint(endpoint.endpoint_id, endpoint.device_id, endpoint.room_id, False, False, False, endpoint.last_seen, endpoint.owner_id)
        self._endpoints[endpoint_id] = updated
        self._save_endpoint(updated)
        await self._emit("voice.endpoint_revoked", owner_id, {"endpoint_id": endpoint_id, "device_id": endpoint.device_id}, EventState.COMPLETED)
        return updated

    async def revoke_device_endpoints(self, owner_id: str, device_id: str) -> tuple[VoiceEndpoint, ...]:
        self._ensure_loaded(owner_id)
        revoked: list[VoiceEndpoint] = []
        for ep in list(self._endpoints.values()):
            if ep.owner_id == owner_id and ep.device_id == device_id:
                updated = await self.revoke_endpoint(owner_id, ep.endpoint_id)
                revoked.append(updated)
        return tuple(revoked)

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
        self._ensure_loaded(owner_id)
        endpoint = self._endpoints.get(endpoint_id)
        return endpoint if endpoint and endpoint.owner_id == owner_id else None

    async def list(self, owner_id: str) -> tuple[VoiceEndpoint, ...]:
        self._ensure_loaded(owner_id)
        return tuple(endpoint for endpoint in self._endpoints.values() if endpoint.owner_id == owner_id)

    def _required(self, owner_id: str, endpoint_id: str) -> VoiceEndpoint:
        self._ensure_loaded(owner_id)
        endpoint = self._endpoints.get(endpoint_id)
        if endpoint is None or endpoint.owner_id != owner_id:
            raise KeyError(endpoint_id)
        return endpoint

    async def _emit(self, event_type: str, owner_id: str, payload: dict[str, object], state: EventState) -> None:
        event = Event.create(event_type, EventCategory.VOICE, correlation_id=f"voice-routing-{owner_id}", actor_id=owner_id, payload=payload, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)
