"""Bounded room service and room context management."""
from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import uuid4

from ...bus import InMemoryEventBus
from ...contracts import PresenceSnapshot, RoomRecord, RoomSnapshot
from ...events import Event, EventCategory, EventState
from ...persistence.repositories import RuntimeRepository


class RoomService:
    """Manages room grouping, device/voice bindings, and room presence projections."""

    DEFAULT_ROOMS = (
        ("office", "Office"),
        ("living_room", "Living Room"),
        ("bedroom", "Bedroom"),
        ("kitchen", "Kitchen"),
        ("lab", "Hardware Lab"),
    )

    def __init__(self, repository: RuntimeRepository, event_bus: InMemoryEventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self._rooms: dict[str, dict[str, RoomRecord]] = {}

    def _ensure_loaded(self, owner_id: str) -> None:
        if owner_id in self._rooms:
            return
        loaded: dict[str, RoomRecord] = {}
        for row in self.repository.personalization(owner_id):
            key = str(row.get("key", ""))
            if key.startswith("room:"):
                val = row.get("value_json")
                if isinstance(val, str):
                    try:
                        val = json.loads(val)
                    except (ValueError, TypeError):
                        continue
                if isinstance(val, dict):
                    rid = val.get("room_id") or key.split("room:", 1)[1]
                    loaded[rid.casefold()] = RoomRecord(
                        room_id=rid,
                        owner_id=val.get("owner_id", owner_id),
                        name=val.get("name", rid),
                        devices=tuple(val.get("devices", ())),
                        voice_endpoints=tuple(val.get("voice_endpoints", ())),
                        home_entities=tuple(val.get("home_entities", ())),
                        metadata=val.get("metadata", {}),
                    )
        self._rooms[owner_id] = loaded

    def _save_room(self, record: RoomRecord) -> None:
        data = {
            "room_id": record.room_id,
            "owner_id": record.owner_id,
            "name": record.name,
            "devices": list(record.devices),
            "voice_endpoints": list(record.voice_endpoints),
            "home_entities": list(record.home_entities),
            "metadata": dict(record.metadata),
        }
        self.repository.set_personalization(record.owner_id, f"room:{record.room_id}", data, "room_service")

    async def initialize_defaults(self, owner_id: str) -> tuple[RoomRecord, ...]:
        """Bootstrap default room layout if none exist for owner."""
        existing = await self.list_rooms(owner_id)
        if existing:
            return existing
        created = []
        for room_id, name in self.DEFAULT_ROOMS:
            record = await self.create_room(owner_id, name, room_id=room_id)
            created.append(record)
        return tuple(created)

    async def create_room(
        self,
        owner_id: str,
        name: str,
        *,
        room_id: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> RoomRecord:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("room name cannot be empty")
        self._ensure_loaded(owner_id)
        rid = (room_id or f"room-{uuid4()}").strip().casefold()
        record = RoomRecord(
            room_id=rid,
            owner_id=owner_id,
            name=clean_name,
            devices=(),
            voice_endpoints=(),
            home_entities=(),
            metadata=dict(metadata or {}),
        )
        self._save_room(record)
        self._rooms[owner_id][rid] = record
        await self._emit("room.created", owner_id, {"room_id": rid, "name": clean_name})
        return record

    async def get_room(self, owner_id: str, room_id: str) -> RoomRecord | None:
        self._ensure_loaded(owner_id)
        return self._rooms.get(owner_id, {}).get(room_id.casefold())

    async def list_rooms(self, owner_id: str) -> tuple[RoomRecord, ...]:
        self._ensure_loaded(owner_id)
        rooms = list(self._rooms.get(owner_id, {}).values())
        return tuple(sorted(rooms, key=lambda r: (r.name, r.room_id)))

    async def bind_device(self, owner_id: str, room_id: str, device_id: str) -> RoomRecord:
        room = await self._require(owner_id, room_id)
        if device_id in room.devices:
            return room
        updated = RoomRecord(
            room_id=room.room_id,
            owner_id=room.owner_id,
            name=room.name,
            devices=tuple(sorted(set(room.devices) | {device_id})),
            voice_endpoints=room.voice_endpoints,
            home_entities=room.home_entities,
            metadata=room.metadata,
        )
        self._save_room(updated)
        self._rooms[owner_id][room.room_id] = updated
        await self._emit("room.device_bound", owner_id, {"room_id": room.room_id, "device_id": device_id})
        return updated

    async def bind_voice_endpoint(self, owner_id: str, room_id: str, endpoint_id: str) -> RoomRecord:
        room = await self._require(owner_id, room_id)
        if endpoint_id in room.voice_endpoints:
            return room
        updated = RoomRecord(
            room_id=room.room_id,
            owner_id=room.owner_id,
            name=room.name,
            devices=room.devices,
            voice_endpoints=tuple(sorted(set(room.voice_endpoints) | {endpoint_id})),
            home_entities=room.home_entities,
            metadata=room.metadata,
        )
        self._save_room(updated)
        self._rooms[owner_id][room.room_id] = updated
        await self._emit("room.endpoint_bound", owner_id, {"room_id": room.room_id, "endpoint_id": endpoint_id})
        return updated

    async def bind_home_entity(self, owner_id: str, room_id: str, entity_id: str) -> RoomRecord:
        room = await self._require(owner_id, room_id)
        if entity_id in room.home_entities:
            return room
        updated = RoomRecord(
            room_id=room.room_id,
            owner_id=room.owner_id,
            name=room.name,
            devices=room.devices,
            voice_endpoints=room.voice_endpoints,
            home_entities=tuple(sorted(set(room.home_entities) | {entity_id})),
            metadata=room.metadata,
        )
        self._save_room(updated)
        self._rooms[owner_id][room.room_id] = updated
        await self._emit("room.entity_bound", owner_id, {"room_id": room.room_id, "entity_id": entity_id})
        return updated

    async def snapshot(
        self,
        owner_id: str,
        room_id: str,
        presence: PresenceSnapshot | None = None,
    ) -> RoomSnapshot | None:
        room = await self.get_room(owner_id, room_id)
        if room is None:
            return None
        active_endpoint = None
        presence_conf = 0.0
        presence_src = None
        last_activity = None
        if presence and presence.room_id == room.room_id:
            active_endpoint = presence.voice_endpoint_id
            presence_conf = presence.confidence
            presence_src = presence.source
            last_activity = presence.observed_at
        return RoomSnapshot(
            room_id=room.room_id,
            owner_id=owner_id,
            name=room.name,
            active_endpoint_id=active_endpoint,
            presence_confidence=presence_conf,
            presence_source=presence_src,
            last_activity=last_activity,
            device_count=len(room.devices),
            entity_count=len(room.home_entities),
            metadata=dict(room.metadata),
        )

    async def list_snapshots(
        self,
        owner_id: str,
        presence: PresenceSnapshot | None = None,
    ) -> tuple[RoomSnapshot, ...]:
        rooms = await self.list_rooms(owner_id)
        if not rooms:
            rooms = await self.initialize_defaults(owner_id)
        snapshots = []
        for room in rooms:
            snap = await self.snapshot(owner_id, room.room_id, presence=presence)
            if snap:
                snapshots.append(snap)
        return tuple(snapshots)

    async def _require(self, owner_id: str, room_id: str) -> RoomRecord:
        room = await self.get_room(owner_id, room_id)
        if room is None:
            raise KeyError(f"room_not_found:{room_id}")
        return room

    async def _emit(self, event_type: str, owner_id: str, payload: dict[str, object]) -> None:
        event = Event.create(
            event_type,
            EventCategory.DEVICE,
            correlation_id=f"room-{payload.get('room_id', owner_id)}",
            actor_id=owner_id,
            payload={"owner_id": owner_id, **payload},
            state=EventState.COMPLETED,
        )
        self.repository.append_event(event)
        await self.event_bus.publish(event)
