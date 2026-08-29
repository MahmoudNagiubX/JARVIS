"""Permission decisions are explicit data, never implicit tool behavior."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .identity import DeviceIdentity, Identity


class PermissionEffect(StrEnum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    effect: PermissionEffect
    reason_code: str
    policy_version: str = "foundation-1"


class PermissionEngine(Protocol):
    def evaluate(
        self,
        identity: Identity | None,
        device: DeviceIdentity | None,
        action: str,
        resource: Mapping[str, object] | None = None,
    ) -> Awaitable[PermissionDecision]: ...
