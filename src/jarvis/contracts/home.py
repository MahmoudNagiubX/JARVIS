"""Local Home Assistant and MQTT capability contracts."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from .identity import DeviceIdentity, Identity


@dataclass(frozen=True, slots=True)
class HomeEntity:
    entity_id: str
    name: str
    domain: str
    state: str
    attributes: Mapping[str, object] = field(default_factory=dict)
    room_id: str | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class HomeAction:
    entity_id: str
    action: str
    parameters: Mapping[str, object] = field(default_factory=dict)
    dry_run: bool = True


@dataclass(frozen=True, slots=True)
class HomeResult:
    status: str
    output: Mapping[str, object] = field(default_factory=dict)
    error_code: str | None = None
    verified: bool = False
    approval_id: str | None = None


class HomeTransport(Protocol):
    name: str

    def list_entities(self) -> Awaitable[tuple[HomeEntity, ...]]: ...

    def execute(self, action: HomeAction) -> Awaitable[HomeResult]: ...


class MQTTTransport(Protocol):
    name: str

    def publish(self, topic: str, payload: str) -> Awaitable[bool]: ...

    def subscribe(self, topic: str) -> Awaitable[bool]: ...


class HomeController(Protocol):
    def list_entities(self, identity: Identity, device: DeviceIdentity) -> Awaitable[tuple[HomeEntity, ...]]: ...

    def execute(self, action: HomeAction, identity: Identity, device: DeviceIdentity) -> Awaitable[HomeResult]: ...
