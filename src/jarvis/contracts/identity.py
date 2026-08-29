"""Identity and device contracts owned by the JARVIS product."""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Identity:
    identity_id: str
    display_name: str
    owner_id: str
    roles: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class DeviceIdentity:
    device_id: str
    owner_id: str
    device_kind: str
    platform: str
    capabilities: frozenset[str] = field(default_factory=frozenset)
    scopes: frozenset[str] = field(default_factory=frozenset)
    authenticated_at: datetime | None = None


class IdentityService(Protocol):
    def authenticate(
        self, credential: str, device_id: str
    ) -> Awaitable[DeviceIdentity | None]: ...

    def get_identity(self, identity_id: str) -> Awaitable[Identity | None]: ...
