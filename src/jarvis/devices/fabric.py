"""Unified owner-scoped device capability fabric."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from ..authority.audit.service import DurableAuditService
from ..bus import InMemoryEventBus
from ..contracts import AuditRecord, DeviceHeartbeat, DeviceRecord, DeviceRole, DeviceStatus
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository


class DeviceFabricService:
    """Register, heartbeat, revoke, and inspect device capabilities."""

    def __init__(self, repository: RuntimeRepository, event_bus: InMemoryEventBus, audit: DurableAuditService | None = None) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.audit = audit

    async def register(self, device: DeviceRecord) -> DeviceRecord:
        if self.repository.owner(device.owner_id) is None:
            raise ValueError("device owner is unavailable")
        if not device.device_id.strip() or not device.name.strip():
            raise ValueError("device id and name are required")
        normalized = DeviceRecord(
            device.device_id, device.owner_id, device.name.strip(), device.role, device.transport,
            DeviceStatus.ONLINE.value if device.status == DeviceStatus.REGISTERED.value else device.status,
            frozenset(device.capabilities), device.trust_level, device.last_seen or datetime.now(UTC), device.room_id, dict(device.metadata),
        )
        self.repository.upsert_device_fabric(normalized)
        await self._audit(normalized, "device.registered", "registered")
        await self._emit("device.registered", normalized, {"capabilities": sorted(normalized.capabilities)}, EventState.COMPLETED)
        await self._emit("device.online", normalized, {"reason": "registered"}, EventState.COMPLETED)
        return normalized

    async def heartbeat(self, heartbeat: DeviceHeartbeat, owner_id: str) -> DeviceRecord:
        current = await self.get(owner_id, heartbeat.device_id)
        if current is None:
            raise KeyError(heartbeat.device_id)
        metadata = dict(current.metadata) | dict(heartbeat.metadata)
        updated = DeviceRecord(current.device_id, current.owner_id, current.name, current.role, current.transport, DeviceStatus.ONLINE.value, current.capabilities, current.trust_level, heartbeat.timestamp, current.room_id, metadata)
        self.repository.upsert_device_fabric(updated)
        await self._emit("device.online", updated, {"heartbeat": heartbeat.timestamp.isoformat()}, EventState.COMPLETED)
        return updated

    async def add_capability(self, owner_id: str, device_id: str, capability: str) -> DeviceRecord:
        if not capability.strip():
            raise ValueError("device capability is required")
        current = await self.get(owner_id, device_id)
        if current is None:
            raise KeyError(device_id)
        if capability in current.capabilities:
            return current
        updated = DeviceRecord(
            current.device_id, current.owner_id, current.name, current.role, current.transport,
            current.status, current.capabilities | {capability}, current.trust_level,
            current.last_seen, current.room_id, current.metadata,
        )
        self.repository.upsert_device_fabric(updated)
        await self._emit("device.capability_added", updated, {"capability": capability}, EventState.COMPLETED)
        return updated

    async def remove_capability(self, owner_id: str, device_id: str, capability: str) -> DeviceRecord:
        current = await self.get(owner_id, device_id)
        if current is None:
            raise KeyError(device_id)
        if capability not in current.capabilities:
            return current
        updated = DeviceRecord(
            current.device_id, current.owner_id, current.name, current.role, current.transport,
            current.status, current.capabilities - {capability}, current.trust_level,
            current.last_seen, current.room_id, current.metadata,
        )
        self.repository.upsert_device_fabric(updated)
        await self._emit("device.capability_removed", updated, {"capability": capability}, EventState.COMPLETED)
        return updated

    async def mark_stale_offline(self, owner_id: str, max_age_seconds: int = 60) -> tuple[DeviceRecord, ...]:
        cutoff = datetime.now(UTC) - timedelta(seconds=max(1, max_age_seconds))
        changed: list[DeviceRecord] = []
        for device in await self.list(owner_id):
            if device.status == DeviceStatus.ONLINE.value and device.last_seen and device.last_seen < cutoff:
                updated = DeviceRecord(device.device_id, device.owner_id, device.name, device.role, device.transport, DeviceStatus.OFFLINE.value, device.capabilities, device.trust_level, device.last_seen, device.room_id, device.metadata)
                self.repository.upsert_device_fabric(updated)
                changed.append(updated)
                await self._emit("device.offline", updated, {"reason": "heartbeat_stale"}, EventState.COMPLETED)
        return tuple(changed)

    async def revoke(self, owner_id: str, device_id: str) -> DeviceRecord:
        current = await self.get(owner_id, device_id)
        if current is None:
            raise KeyError(device_id)
        updated = DeviceRecord(current.device_id, current.owner_id, current.name, current.role, current.transport, DeviceStatus.REVOKED.value, current.capabilities, current.trust_level, current.last_seen, current.room_id, current.metadata)
        self.repository.upsert_device_fabric(updated)
        await self._audit(updated, "device.revoked", "revoked")
        await self._emit("device.offline", updated, {"reason": "revoked"}, EventState.COMPLETED)
        return updated

    async def get(self, owner_id: str, device_id: str) -> DeviceRecord | None:
        row = self.repository.fabric_device(owner_id, device_id)
        if row:
            return self._record(row)
        for row in self.repository.devices(owner_id):
            if row["id"] == device_id:
                return DeviceRecord(row["id"], row["owner_id"], row["display_name"], self._role(row["device_kind"]), "identity", row["status"], frozenset(json.loads(row["capabilities_json"])), row["trust_state"], datetime.fromisoformat(row["last_seen_at"]) if row["last_seen_at"] else None)
        return None

    async def list(self, owner_id: str) -> tuple[DeviceRecord, ...]:
        records = {row["id"]: self._record(row) for row in self.repository.fabric_devices(owner_id)}
        for row in self.repository.devices(owner_id):
            records.setdefault(row["id"], DeviceRecord(row["id"], row["owner_id"], row["display_name"], self._role(row["device_kind"]), "identity", row["status"], frozenset(json.loads(row["capabilities_json"])), row["trust_state"], datetime.fromisoformat(row["last_seen_at"]) if row["last_seen_at"] else None))
        return tuple(sorted(records.values(), key=lambda item: (item.name, item.device_id)))

    async def capabilities(self, owner_id: str, device_id: str) -> tuple[str, ...]:
        device = await self.get(owner_id, device_id)
        if device is None:
            raise KeyError(device_id)
        if device.status in {DeviceStatus.OFFLINE.value, DeviceStatus.REVOKED.value}:
            return ()
        return tuple(sorted(device.capabilities))

    @staticmethod
    def _role(device_kind: str) -> str:
        return device_kind if device_kind in {item.value for item in DeviceRole} else DeviceRole.PRIMARY_PC.value

    @staticmethod
    def _record(row: Mapping[str, object]) -> DeviceRecord:
        return DeviceRecord(row["id"], row["owner_id"], row["name"], row["role"], row["transport"], row["status"], frozenset(json.loads(row["capabilities_json"])), row["trust_level"], datetime.fromisoformat(row["last_seen"]) if row["last_seen"] else None, row["room_id"], json.loads(row["metadata_json"]))

    async def _audit(self, device: DeviceRecord, event_type: str, outcome: str) -> None:
        if self.audit:
            await self.audit.record(AuditRecord(f"audit-{uuid4()}", event_type, datetime.now(UTC), device.owner_id, device.device_id, f"device-{device.device_id}", outcome, None, {"device_id": device.device_id}))

    async def _emit(self, event_type: str, device: DeviceRecord, payload: dict[str, object], state: EventState) -> None:
        event = Event.create(event_type, EventCategory.DEVICE, correlation_id=f"device-{device.device_id}", actor_id=device.owner_id, payload={"device_id": device.device_id, **payload}, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)
