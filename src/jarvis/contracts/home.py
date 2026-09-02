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


@dataclass(frozen=True, slots=True)
class HomeEntityMapping:
    entity_id: str
    display_name: str = ""
    room_id: str | None = None
    domain: str = "light"
    read_caps: frozenset[str] = field(default_factory=lambda: frozenset({"home.read"}))
    write_caps: frozenset[str] = field(default_factory=lambda: frozenset({"home.control"}))
    risk_level: str = "safe"
    provider_locator: str | None = None
    enabled: bool = True
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __init__(
        self,
        entity_id: str,
        display_name: str = "",
        room_id: str | None = None,
        domain: str = "light",
        read_caps: frozenset[str] | Sequence[str] | None = None,
        write_caps: frozenset[str] | Sequence[str] | None = None,
        risk_level: str = "safe",
        provider_locator: str | None = None,
        enabled: bool = True,
        metadata: Mapping[str, object] | None = None,
        *,
        read_capabilities: frozenset[str] | Sequence[str] | None = None,
        write_capabilities: frozenset[str] | Sequence[str] | None = None,
    ) -> None:
        object.__setattr__(self, "entity_id", entity_id)
        object.__setattr__(self, "display_name", display_name or entity_id)
        object.__setattr__(self, "room_id", room_id)
        object.__setattr__(self, "domain", domain)
        rc = read_caps if read_caps is not None else read_capabilities
        wc = write_caps if write_caps is not None else write_capabilities
        object.__setattr__(self, "read_caps", frozenset(rc) if rc is not None else frozenset({"home.read"}))
        object.__setattr__(self, "write_caps", frozenset(wc) if wc is not None else frozenset({"home.control"}))
        object.__setattr__(self, "risk_level", risk_level)
        object.__setattr__(self, "provider_locator", provider_locator)
        object.__setattr__(self, "enabled", enabled)
        object.__setattr__(self, "metadata", metadata or {})

    @property
    def read_capabilities(self) -> frozenset[str]:
        return self.read_caps

    @property
    def write_capabilities(self) -> frozenset[str]:
        return self.write_caps


@dataclass(frozen=True, slots=True)
class ESP32DeviceManifest:
    device_id: str
    name: str
    hardware: str = "esp32"
    firmware_version: str = "1.0.0"
    sensors: tuple[str, ...] = ()
    actuators: tuple[str, ...] = ()
    capabilities: frozenset[str] = field(default_factory=frozenset)
    room_id: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ESP32CommandEnvelope:
    command_id: str
    device_id: str
    target: str
    action: str
    parameters: Mapping[str, object] = field(default_factory=dict)
    expires_at: datetime | None = None
    dry_run: bool = False


@dataclass(frozen=True, slots=True)
class ESP32StateEnvelope:
    device_id: str
    target: str
    state: Mapping[str, object]
    timestamp: datetime
    online: bool = True


@dataclass(frozen=True, slots=True)
class ESP32Ack:
    command_id: str
    device_id: str
    status: str
    error_code: str | None = None
    result: Mapping[str, object] = field(default_factory=dict)


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
