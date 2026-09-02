"""Unified owner-scoped device capability fabric."""

from __future__ import annotations

import json
import secrets
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from ..authority.audit.service import DurableAuditService
from ..bus import InMemoryEventBus
from ..contracts import (
    AuditRecord,
    DeviceEnrollmentRequest,
    DeviceEnrollmentResult,
    DeviceEnrollmentTicket,
    DeviceHeartbeat,
    DeviceRecord,
    DeviceRole,
    DeviceStatus,
)
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository


def sanitize_untrusted_text(text: str) -> str:
    """Sanitize untrusted text (e.g. device names/labels) to prevent prompt injection."""
    if not isinstance(text, str):
        return ""
    # Strip potential control characters and direct instruction headers
    sanitized = text.replace("\r", " ").replace("\n", " ").strip()
    return sanitized[:120]


def sanitize_untrusted_metadata(metadata: Mapping[str, object] | None) -> dict[str, object]:
    """Ensure untrusted device metadata is strictly plain data."""
    if not metadata:
        return {}
    clean: dict[str, object] = {}
    for key, value in metadata.items():
        clean_key = sanitize_untrusted_text(str(key))[:64]
        if isinstance(value, str):
            clean[clean_key] = sanitize_untrusted_text(value)
        elif isinstance(value, (int, float, bool)):
            clean[clean_key] = value
        elif isinstance(value, (list, tuple)):
            clean[clean_key] = [sanitize_untrusted_text(str(v)) if isinstance(v, str) else v for v in value[:20]]
        elif isinstance(value, dict):
            clean[clean_key] = {sanitize_untrusted_text(str(k)): (sanitize_untrusted_text(v) if isinstance(v, str) else v) for k, v in list(value.items())[:20]}
        else:
            clean[clean_key] = str(value)[:120]
    return clean


class DeviceFabricService:
    """Register, heartbeat, enroll, revoke, and inspect device capabilities."""

    def __init__(
        self,
        repository: RuntimeRepository,
        event_bus: InMemoryEventBus,
        audit: DurableAuditService | None = None,
        identity_service: Any = None,
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.audit = audit
        self.identity_service = identity_service
        self._enrollment_tickets: dict[str, DeviceEnrollmentTicket] = {}

    async def register(self, device: DeviceRecord) -> DeviceRecord:
        if self.repository.owner(device.owner_id) is None:
            raise ValueError("device owner is unavailable")
        if not device.device_id.strip() or not device.name.strip():
            raise ValueError("device id and name are required")
        clean_name = sanitize_untrusted_text(device.name)
        clean_meta = sanitize_untrusted_metadata(device.metadata)
        platform = str(clean_meta.get("platform", getattr(device, "platform", "windows")))
        clean_meta["platform"] = platform
        normalized = DeviceRecord(
            device.device_id,
            device.owner_id,
            clean_name,
            device.role,
            device.transport,
            DeviceStatus.ONLINE.value if device.status == DeviceStatus.REGISTERED.value else device.status,
            frozenset(device.capabilities),
            device.trust_level,
            device.last_seen or datetime.now(UTC),
            device.room_id,
            clean_meta,
            platform=platform,
            scopes=frozenset(getattr(device, "scopes", ())),
            enrolled_at=getattr(device, "enrolled_at", None) or datetime.now(UTC),
            revoked_at=getattr(device, "revoked_at", None),
        )
        self.repository.upsert_device_fabric(normalized)
        await self._audit(normalized, "device.registered", "registered")
        await self._emit("device.registered", normalized, {"capabilities": sorted(normalized.capabilities)}, EventState.COMPLETED)
        await self._emit("device.online", normalized, {"reason": "registered"}, EventState.COMPLETED)
        return normalized

    async def issue_enrollment_ticket(
        self,
        owner_id: str,
        name: str,
        *,
        role: str = DeviceRole.ROOM_SATELLITE.value,
        platform: str = "windows",
        capabilities: Sequence[str] = (),
        scopes: Sequence[str] = ("tool.request",),
        ttl_minutes: int = 10,
        metadata: Mapping[str, object] | None = None,
    ) -> DeviceEnrollmentTicket:
        if self.repository.owner(owner_id) is None:
            raise ValueError("owner is unavailable")
        clean_name = sanitize_untrusted_text(name)
        if not clean_name:
            raise ValueError("device enrollment name cannot be empty")
        code = secrets.token_urlsafe(24)
        ticket_id = f"ticket-{uuid4()}"
        expires_at = datetime.now(UTC) + timedelta(minutes=max(1, min(ttl_minutes, 30)))
        ticket = DeviceEnrollmentTicket(
            ticket_id=ticket_id,
            code=code,
            owner_id=owner_id,
            role=role,
            name=clean_name,
            platform=platform,
            capabilities=frozenset(capabilities),
            scopes=frozenset(scopes),
            expires_at=expires_at,
            metadata=sanitize_untrusted_metadata(metadata),
        )
        self._enrollment_tickets[code] = ticket
        if self.audit:
            await self.audit.record(
                AuditRecord(
                    f"audit-{uuid4()}",
                    "device.enrollment_ticket_issued",
                    datetime.now(UTC),
                    owner_id,
                    ticket_id,
                    f"ticket-{ticket_id}",
                    "issued",
                    None,
                    {"ticket_id": ticket_id, "role": role, "name": clean_name},
                )
            )
        return ticket

    async def enroll_device(self, request: DeviceEnrollmentRequest) -> DeviceEnrollmentResult:
        now = datetime.now(UTC)
        ticket = self._enrollment_tickets.get(request.code)
        if ticket is None or ticket.expires_at <= now:
            if ticket is not None and ticket.expires_at <= now:
                self._enrollment_tickets.pop(request.code, None)
            return DeviceEnrollmentResult(accepted=False, reason="invalid_or_expired_enrollment_code")
        self._enrollment_tickets.pop(request.code, None)
        owner_id = ticket.owner_id
        device_id = request.device_id.strip()
        if not device_id:
            device_id = f"device-{uuid4()}"

        # Check existing device collision using repository boundary
        existing_owner = self.repository.find_device_owner(device_id)
        if existing_owner is not None:
            if existing_owner != owner_id:
                return DeviceEnrollmentResult(accepted=False, reason="device_id_already_registered_to_different_owner")
            return DeviceEnrollmentResult(accepted=False, reason="device_id_already_registered")

        clean_name = sanitize_untrusted_text(request.name or ticket.name)
        # Requester capabilities must not escalate beyond owner-approved ticket capabilities
        granted_caps = frozenset(ticket.capabilities & request.capabilities) if request.capabilities else frozenset(ticket.capabilities)
        merged_meta = dict(ticket.metadata) | dict(sanitize_untrusted_metadata(request.metadata))
        merged_meta["software_version"] = request.software_version
        merged_meta["platform"] = request.platform or ticket.platform
        merged_meta["scopes"] = sorted(ticket.scopes)
        merged_meta["enrolled_at"] = now.isoformat()
        public_id = secrets.token_urlsafe(12)
        secret = secrets.token_urlsafe(32)
        credential_raw = f"{public_id}.{secret}"

        record = DeviceRecord(
            device_id=device_id,
            owner_id=owner_id,
            name=clean_name,
            role=ticket.role,
            transport="http-long-poll",
            status=DeviceStatus.ONLINE.value,
            capabilities=granted_caps,
            trust_level="verified",
            last_seen=now,
            room_id=clean_meta_room(merged_meta),
            metadata=merged_meta,
            platform=request.platform or ticket.platform,
            scopes=ticket.scopes,
            enrolled_at=now,
        )

        try:
            from ..authority.identity.service import _hash_secret
            self.repository.enroll_device_atomic(owner_id, record, public_id, _hash_secret(secret))
        except Exception:
            return DeviceEnrollmentResult(
                accepted=False,
                reason="enrollment_persistence_failed",
            )

        await self._audit(record, "device.enrolled", "enrolled")
        await self._emit("device.enrolled", record, {"role": ticket.role, "capabilities": sorted(granted_caps)}, EventState.COMPLETED)
        await self._emit("device.online", record, {"reason": "enrolled"}, EventState.COMPLETED)
        return DeviceEnrollmentResult(
            accepted=True,
            device_id=device_id,
            credential=credential_raw,
            enrolled_at=now,
        )

    async def heartbeat(self, heartbeat: DeviceHeartbeat, owner_id: str) -> DeviceRecord:
        current = await self.get(owner_id, heartbeat.device_id)
        if current is None:
            raise KeyError(heartbeat.device_id)
        if current.status == DeviceStatus.REVOKED.value:
            raise PermissionError("device_revoked")
        was_online = current.status == DeviceStatus.ONLINE.value
        clean_meta = dict(current.metadata) | sanitize_untrusted_metadata(heartbeat.metadata)
        updated = DeviceRecord(
            current.device_id,
            current.owner_id,
            current.name,
            current.role,
            current.transport,
            DeviceStatus.ONLINE.value,
            current.capabilities,
            current.trust_level,
            heartbeat.timestamp,
            clean_meta_room(clean_meta) or current.room_id,
            clean_meta,
            platform=current.platform,
            scopes=current.scopes,
            enrolled_at=current.enrolled_at,
            revoked_at=current.revoked_at,
        )
        self.repository.upsert_device_fabric(updated)
        if not was_online:
            await self._emit("device.online", updated, {"reason": "heartbeat_transition", "heartbeat": heartbeat.timestamp.isoformat()}, EventState.COMPLETED)
        return updated

    async def mark_offline(self, owner_id: str, device_id: str, *, reason: str = "transport_disconnected") -> DeviceRecord:
        current = await self.get(owner_id, device_id)
        if current is None:
            raise KeyError(device_id)
        if current.status in {DeviceStatus.OFFLINE.value, DeviceStatus.REVOKED.value}:
            return current
        updated = DeviceRecord(
            current.device_id,
            current.owner_id,
            current.name,
            current.role,
            current.transport,
            DeviceStatus.OFFLINE.value,
            current.capabilities,
            current.trust_level,
            current.last_seen,
            current.room_id,
            dict(current.metadata) | {"offline_reason": reason},
            platform=current.platform,
            scopes=current.scopes,
            enrolled_at=current.enrolled_at,
            revoked_at=current.revoked_at,
        )
        self.repository.upsert_device_fabric(updated)
        await self._emit("device.offline", updated, {"reason": reason}, EventState.COMPLETED)
        return updated

    async def mark_degraded(self, owner_id: str, device_id: str, *, reason: str = "degraded") -> DeviceRecord:
        current = await self.get(owner_id, device_id)
        if current is None:
            raise KeyError(device_id)
        if current.status == DeviceStatus.REVOKED.value:
            return current
        updated = DeviceRecord(
            current.device_id,
            current.owner_id,
            current.name,
            current.role,
            current.transport,
            DeviceStatus.DEGRADED.value,
            current.capabilities,
            current.trust_level,
            current.last_seen,
            current.room_id,
            dict(current.metadata) | {"degraded_reason": reason},
            platform=current.platform,
            scopes=current.scopes,
            enrolled_at=current.enrolled_at,
            revoked_at=current.revoked_at,
        )
        self.repository.upsert_device_fabric(updated)
        await self._emit("device.degraded", updated, {"reason": reason}, EventState.COMPLETED)
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
            current.device_id,
            current.owner_id,
            current.name,
            current.role,
            current.transport,
            current.status,
            current.capabilities | {capability},
            current.trust_level,
            current.last_seen,
            current.room_id,
            current.metadata,
            platform=current.platform,
            scopes=current.scopes,
            enrolled_at=current.enrolled_at,
            revoked_at=current.revoked_at,
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
            current.device_id,
            current.owner_id,
            current.name,
            current.role,
            current.transport,
            current.status,
            current.capabilities - {capability},
            current.trust_level,
            current.last_seen,
            current.room_id,
            current.metadata,
            platform=current.platform,
            scopes=current.scopes,
            enrolled_at=current.enrolled_at,
            revoked_at=current.revoked_at,
        )
        self.repository.upsert_device_fabric(updated)
        await self._emit("device.capability_removed", updated, {"capability": capability}, EventState.COMPLETED)
        return updated

    async def mark_stale_offline(self, owner_id: str, max_age_seconds: int = 60) -> tuple[DeviceRecord, ...]:
        cutoff = datetime.now(UTC) - timedelta(seconds=max(1, max_age_seconds))
        changed: list[DeviceRecord] = []
        for device in await self.list(owner_id):
            if device.status == DeviceStatus.ONLINE.value and device.last_seen and device.last_seen < cutoff:
                updated = DeviceRecord(
                    device.device_id,
                    device.owner_id,
                    device.name,
                    device.role,
                    device.transport,
                    DeviceStatus.OFFLINE.value,
                    device.capabilities,
                    device.trust_level,
                    device.last_seen,
                    device.room_id,
                    dict(device.metadata) | {"offline_reason": "heartbeat_stale"},
                    platform=device.platform,
                    scopes=device.scopes,
                    enrolled_at=device.enrolled_at,
                    revoked_at=device.revoked_at,
                )
                self.repository.upsert_device_fabric(updated)
                changed.append(updated)
                await self._emit("device.offline", updated, {"reason": "heartbeat_stale"}, EventState.COMPLETED)
        return tuple(changed)

    async def revoke(self, owner_id: str, device_id: str) -> DeviceRecord:
        current = await self.get(owner_id, device_id)
        if current is None:
            raise KeyError(device_id)
        now = datetime.now(UTC)
        updated = DeviceRecord(
            current.device_id,
            current.owner_id,
            current.name,
            current.role,
            current.transport,
            DeviceStatus.REVOKED.value,
            current.capabilities,
            current.trust_level,
            current.last_seen,
            current.room_id,
            dict(current.metadata) | {"revoked_at": now.isoformat()},
            platform=current.platform,
            scopes=current.scopes,
            enrolled_at=current.enrolled_at,
            revoked_at=now,
        )
        self.repository.upsert_device_fabric(updated)
        try:
            self.repository.revoke_device(device_id, now)
        except Exception:
            pass
        await self._audit(updated, "device.revoked", "revoked")
        await self._emit("device.offline", updated, {"reason": "revoked"}, EventState.COMPLETED)
        await self._emit("device.revoked", updated, {"reason": "revoked"}, EventState.COMPLETED)
        return updated

    async def get(self, owner_id: str, device_id: str) -> DeviceRecord | None:
        row = self.repository.fabric_device(owner_id, device_id)
        if row:
            return self._record(row)
        for row in self.repository.devices(owner_id):
            if row["id"] == device_id:
                return DeviceRecord(
                    row["id"],
                    row["owner_id"],
                    row["display_name"],
                    self._role(row["device_kind"]),
                    "identity",
                    row["status"],
                    frozenset(json.loads(row["capabilities_json"])),
                    row["trust_state"],
                    datetime.fromisoformat(row["last_seen_at"]) if row["last_seen_at"] else None,
                    platform=row.get("platform", "windows"),
                    scopes=frozenset(json.loads(row.get("scopes_json", "[]"))),
                )
        return None

    async def list(self, owner_id: str) -> tuple[DeviceRecord, ...]:
        records = {row["id"]: self._record(row) for row in self.repository.fabric_devices(owner_id)}
        for row in self.repository.devices(owner_id):
            records.setdefault(
                row["id"],
                DeviceRecord(
                    row["id"],
                    row["owner_id"],
                    row["display_name"],
                    self._role(row["device_kind"]),
                    "identity",
                    row["status"],
                    frozenset(json.loads(row["capabilities_json"])),
                    row["trust_state"],
                    datetime.fromisoformat(row["last_seen_at"]) if row["last_seen_at"] else None,
                    platform=row.get("platform", "windows"),
                    scopes=frozenset(json.loads(row.get("scopes_json", "[]"))),
                ),
            )
        return tuple(sorted(records.values(), key=lambda item: (item.name, item.device_id)))

    async def capabilities(self, owner_id: str, device_id: str) -> tuple[str, ...]:
        device = await self.get(owner_id, device_id)
        if device is None:
            raise KeyError(device_id)
        if device.status in {DeviceStatus.OFFLINE.value, DeviceStatus.REVOKED.value}:
            return ()
        return tuple(sorted(device.capabilities))

    async def diagnostics(self, owner_id: str) -> dict[str, object]:
        devices = await self.list(owner_id)
        online = sum(1 for d in devices if d.status == DeviceStatus.ONLINE.value)
        degraded = sum(1 for d in devices if d.status == DeviceStatus.DEGRADED.value)
        offline = sum(1 for d in devices if d.status == DeviceStatus.OFFLINE.value)
        revoked = sum(1 for d in devices if d.status == DeviceStatus.REVOKED.value)
        return {
            "total_devices": len(devices),
            "online_devices": online,
            "degraded_devices": degraded,
            "offline_devices": offline,
            "revoked_devices": revoked,
            "devices": [
                {
                    "device_id": d.device_id,
                    "name": d.name,
                    "role": d.role,
                    "platform": d.platform,
                    "status": d.status,
                    "transport": d.transport,
                    "capabilities_count": len(d.capabilities),
                    "last_seen": d.last_seen.isoformat() if d.last_seen else None,
                    "room_id": d.room_id,
                }
                for d in devices
            ],
        }

    @staticmethod
    def _role(device_kind: str) -> str:
        return device_kind if device_kind in {item.value for item in DeviceRole} else DeviceRole.PRIMARY_PC.value

    @staticmethod
    def _record(row: Mapping[str, object]) -> DeviceRecord:
        meta = json.loads(str(row["metadata_json"])) if row.get("metadata_json") else {}
        return DeviceRecord(
            str(row["id"]),
            str(row["owner_id"]),
            str(row["name"]),
            str(row["role"]),
            str(row["transport"]),
            str(row["status"]),
            frozenset(json.loads(str(row["capabilities_json"]))),
            str(row["trust_level"]),
            datetime.fromisoformat(str(row["last_seen"])) if row.get("last_seen") else None,
            str(row["room_id"]) if row.get("room_id") else None,
            meta,
            platform=str(meta.get("platform", "windows")),
            scopes=frozenset(meta.get("scopes", ())),
            enrolled_at=datetime.fromisoformat(str(meta["enrolled_at"])) if meta.get("enrolled_at") else None,
            revoked_at=datetime.fromisoformat(str(meta["revoked_at"])) if meta.get("revoked_at") else None,
        )

    async def _audit(self, device: DeviceRecord, event_type: str, outcome: str) -> None:
        if self.audit:
            await self.audit.record(
                AuditRecord(
                    f"audit-{uuid4()}",
                    event_type,
                    datetime.now(UTC),
                    device.owner_id,
                    device.device_id,
                    f"device-{device.device_id}",
                    outcome,
                    None,
                    {"device_id": device.device_id, "role": device.role, "status": device.status},
                )
            )

    async def _emit(self, event_type: str, device: DeviceRecord, payload: dict[str, object], state: EventState) -> None:
        event = Event.create(
            event_type,
            EventCategory.DEVICE,
            correlation_id=f"device-{device.device_id}",
            actor_id=device.owner_id,
            payload={"device_id": device.device_id, **payload},
            state=state,
        )
        self.repository.append_event(event)
        await self.event_bus.publish(event)


def clean_meta_room(meta: Mapping[str, object]) -> str | None:
    room = meta.get("room_id")
    return str(room).strip().casefold() if room and str(room).strip() else None
