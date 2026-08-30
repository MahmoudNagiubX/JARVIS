"""JARVIS-owned identity and device enrollment service.

The implementation adapts the BMO Phase 06 security shape while keeping the
domain independent from Pydantic and SQLAlchemy. Raw credentials and one-time
enrollment codes are returned only to the caller; only salted hashes and public
credential ids are persisted.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ...bus import InMemoryEventBus
from ...contracts import DeviceIdentity, Identity
from ...events import Event, EventCategory, EventState
from ...persistence.repositories import RuntimeRepository


@dataclass(frozen=True, slots=True)
class EnrollmentGrant:
    owner_id: str
    display_name: str
    device_kind: str
    platform: str
    scopes: tuple[str, ...]
    capabilities: tuple[str, ...] = ()
    software_version: str | None = None
    ttl_minutes: int = 10


@dataclass(frozen=True, slots=True)
class IssuedEnrollment:
    enrollment_id: str
    code: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class IssuedCredential:
    device_id: str
    credential_id: str
    raw: str


def _hash_secret(secret: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt, 240_000)
    return f"{salt.hex()}${digest.hex()}"


def _verify_secret(secret: str, encoded: str) -> bool:
    try:
        salt_hex, digest_hex = encoded.split("$", 1)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac("sha256", secret.encode(), bytes.fromhex(salt_hex), 240_000)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def _credential_parts(raw: str) -> tuple[str, str] | None:
    public_id, separator, secret = raw.partition(".")
    if not separator or not public_id or not secret:
        return None
    return public_id, secret


class IdentityService:
    """Fail-closed owner, agent, device, enrollment, and credential service."""

    def __init__(self, repository: RuntimeRepository, event_bus: InMemoryEventBus | None = None) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def bootstrap_owner(self, display_name: str) -> Identity:
        name = display_name.strip()
        if not 1 <= len(name) <= 100:
            raise ValueError("owner display name must be between 1 and 100 characters")
        if self.repository.owner_count() != 0:
            raise ValueError("owner bootstrap is already complete")
        owner_id = self.repository.create_owner(name)
        identity_id = self.repository.create_identity(owner_id, name, "owner", ("owner",))
        return Identity(identity_id, name, owner_id, frozenset({"owner"}))

    async def create_agent(self, owner_id: str, display_name: str) -> Identity:
        if self.repository.owner(owner_id) is None:
            raise ValueError("owner is unavailable")
        name = display_name.strip()
        if not name:
            raise ValueError("agent display name cannot be empty")
        identity_id = self.repository.create_identity(owner_id, name, "agent", ("agent",))
        return Identity(identity_id, name, owner_id, frozenset({"agent"}))

    async def get_identity(self, identity_id: str) -> Identity | None:
        row = self.repository.identity(identity_id)
        if row is None:
            return None
        return Identity(row["id"], row["display_name"], row["owner_id"], frozenset(json.loads(row["roles_json"])))

    async def create_enrollment(self, grant: EnrollmentGrant) -> IssuedEnrollment:
        if self.repository.owner(grant.owner_id) is None:
            raise ValueError("owner is unavailable")
        if not grant.scopes:
            raise ValueError("enrollment requires at least one scope")
        if len(set(grant.scopes)) != len(grant.scopes):
            raise ValueError("enrollment scopes must be unique")
        if not 1 <= grant.ttl_minutes <= 30:
            raise ValueError("enrollment ttl must be between 1 and 30 minutes")
        code = secrets.token_urlsafe(24)
        expires_at = datetime.now(UTC) + timedelta(minutes=grant.ttl_minutes)
        enrollment_id, _ = self.repository.create_enrollment(
            grant.owner_id,
            grant.display_name.strip(),
            grant.device_kind,
            grant.platform,
            grant.software_version,
            _hash_secret(code),
            grant.scopes,
            grant.capabilities,
            expires_at,
        )
        return IssuedEnrollment(enrollment_id, code, expires_at)

    async def redeem_enrollment(self, code: str) -> IssuedCredential:
        # Enrollment hashes are salted, so verification is intentionally a
        # bounded scan through the repository boundary.
        row = next((candidate for candidate in self.repository.enrollments() if _verify_secret(code, candidate["code_hash"])), None)
        if row is None or row["consumed_at"] is not None:
            raise ValueError("invalid enrollment")
        now = datetime.now(UTC)
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at <= now:
            raise ValueError("enrollment expired")
        device_id = self.repository.create_device(
            row["owner_id"],
            row["display_name"],
            row["device_kind"],
            row["platform"],
            json.loads(row["capabilities_json"]),
            json.loads(row["scopes_json"]),
        )
        public_id = secrets.token_urlsafe(12)
        secret = secrets.token_urlsafe(32)
        credential_id = self.repository.create_credential(device_id, public_id, _hash_secret(secret))
        self.repository.consume_enrollment(row["id"], now)
        return IssuedCredential(device_id, credential_id, f"{public_id}.{secret}")

    async def authenticate(self, credential: str, device_id: str | None = None) -> DeviceIdentity | None:
        parts = _credential_parts(credential)
        if parts is None:
            return None
        public_id, secret = parts
        stored = self.repository.credential(public_id)
        if stored is None or stored["revoked_at"] is not None or not _verify_secret(secret, stored["secret_hash"]):
            return None
        device = self.repository.device(stored["device_id"])
        if device is None or device["status"] != "active" or (device_id and device_id != device["id"]):
            return None
        owner = self.repository.owner(device["owner_id"])
        if owner is None or owner["status"] != "active":
            return None
        now = datetime.now(UTC)
        self.repository.touch_device(device["id"], stored["id"], now)
        return DeviceIdentity(
            device_id=device["id"],
            owner_id=device["owner_id"],
            device_kind=device["device_kind"],
            platform=device["platform"],
            capabilities=frozenset(json.loads(device["capabilities_json"])),
            scopes=frozenset(json.loads(device["scopes_json"])),
            authenticated_at=now,
            credential_id=stored["id"],
        )

    async def device(self, device_id: str) -> DeviceIdentity | None:
        row = self.repository.device(device_id)
        if row is None:
            return None
        return DeviceIdentity(
            row["id"], row["owner_id"], row["device_kind"], row["platform"],
            frozenset(json.loads(row["capabilities_json"])), frozenset(json.loads(row["scopes_json"])),
            datetime.fromisoformat(row["last_seen_at"]) if row["last_seen_at"] else None,
        )

    async def list_devices(self, owner_id: str) -> tuple[DeviceIdentity, ...]:
        result = []
        for row in self.repository.devices(owner_id):
            result.append(
                DeviceIdentity(
                    row["id"], row["owner_id"], row["device_kind"], row["platform"],
                    frozenset(json.loads(row["capabilities_json"])), frozenset(json.loads(row["scopes_json"])),
                    datetime.fromisoformat(row["last_seen_at"]) if row["last_seen_at"] else None,
                )
            )
        return tuple(result)

    async def revoke_device(self, device_id: str) -> None:
        row = self.repository.device(device_id)
        if row is None:
            raise KeyError(device_id)
        revoked_at = datetime.now(UTC)
        self.repository.revoke_device(device_id, revoked_at)
        if self.event_bus is None:
            return
        event = Event.create(
            "device.revoked",
            EventCategory.DEVICE,
            correlation_id=f"device-{device_id}",
            actor_id=row["owner_id"],
            payload={"owner_id": row["owner_id"], "device_id": device_id},
            state=EventState.COMPLETED,
        )
        self.repository.append_event(event)
        await self.event_bus.publish(event)
