"""Versioned, typed messages for the Windows satellite boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Mapping

PROTOCOL_VERSION = "1"
PERCEPTION_PROTOCOL_VERSION = "2"
SUPPORTED_PROTOCOL_VERSIONS = frozenset({PROTOCOL_VERSION, PERCEPTION_PROTOCOL_VERSION})


@dataclass(frozen=True, slots=True)
class SatelliteHello:
    device_id: str
    owner_id: str
    platform: str
    software_version: str
    capabilities: frozenset[str] = field(default_factory=frozenset)
    protocol_version: str = PROTOCOL_VERSION


@dataclass(frozen=True, slots=True)
class CoreWelcome:
    accepted: bool
    session_id: str | None
    reason: str | None = None
    heartbeat_interval_seconds: int = 15


@dataclass(frozen=True, slots=True)
class SatelliteHeartbeat:
    session_id: str
    device_id: str
    sequence: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class SatelliteCommand:
    command_id: str
    action: str
    capability: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    dry_run: bool = True
    protocol_version: str = PROTOCOL_VERSION


@dataclass(frozen=True, slots=True)
class CommandObservation:
    command_id: str
    status: str
    output: Mapping[str, Any] = field(default_factory=dict)
    error_code: str | None = None


def validate_command(command: SatelliteCommand) -> None:
    if not command.command_id.strip() or not command.action.strip():
        raise ValueError("typed satellite command requires id and action")
    if command.capability not in {"computer.observe", "computer.input", "perception.screen"}:
        raise ValueError("unsupported satellite capability")
    if command.action not in {"observe", "input", "perception"}:
        raise ValueError("unsupported satellite action")
    if command.action == "observe" and command.capability != "computer.observe":
        raise ValueError("observe capability mismatch")
    if command.action == "input" and command.capability != "computer.input":
        raise ValueError("input capability mismatch")
    if command.action == "perception" and (command.capability != "perception.screen" or command.protocol_version != PERCEPTION_PROTOCOL_VERSION):
        raise ValueError("perception protocol v2 required")
    if command.protocol_version not in SUPPORTED_PROTOCOL_VERSIONS:
        raise ValueError("unsupported satellite protocol version")


def validate_perception_output(output: Mapping[str, Any]) -> None:
    """Reject raw image material from the normal structured result channel."""

    forbidden_keys = {"raw_pixels", "pixels", "image_bytes", "png", "jpeg", "bitmap", "screenshot", "base64"}
    def contains_forbidden(value: object) -> bool:
        if isinstance(value, Mapping):
            return any(str(key).casefold() in forbidden_keys or contains_forbidden(item) for key, item in value.items())
        if isinstance(value, (list, tuple)):
            return any(contains_forbidden(item) for item in value)
        return "data:image/" in str(value).casefold()
    encoded = str(output)
    if contains_forbidden(output) or len(encoded.encode("utf-8")) > 256_000:
        raise ValueError("raw_perception_payload_forbidden")
