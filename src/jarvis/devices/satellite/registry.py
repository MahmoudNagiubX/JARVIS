"""In-process satellite registry; transport is deliberately an outer adapter."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Awaitable, Callable
from uuid import uuid4

from ...contracts import DeviceIdentity
from .contracts import (
    CommandObservation,
    CoreWelcome,
    SatelliteCommand,
    SatelliteHeartbeat,
    SatelliteHello,
    validate_command,
)

SatelliteHandler = Callable[[SatelliteCommand], CommandObservation | Awaitable[CommandObservation]]


@dataclass(slots=True)
class SatelliteConnection:
    session_id: str
    hello: SatelliteHello
    device: DeviceIdentity
    handler: SatelliteHandler
    last_heartbeat: datetime
    online: bool = True
    revoked: bool = False


class WindowsSatelliteRegistry:
    """Tracks typed Windows connections without executing arbitrary commands."""

    def __init__(self) -> None:
        self._connections: dict[str, SatelliteConnection] = {}
        self._revoked_devices: set[str] = set()

    def register(
        self,
        hello: SatelliteHello,
        device: DeviceIdentity,
        handler: SatelliteHandler,
    ) -> CoreWelcome:
        if hello.protocol_version != "1":
            return CoreWelcome(False, None, "protocol_version_unsupported")
        if hello.platform.casefold() != "windows":
            return CoreWelcome(False, None, "windows_satellite_required")
        if hello.device_id != device.device_id or hello.owner_id != device.owner_id:
            return CoreWelcome(False, None, "device_identity_mismatch")
        if not hello.capabilities.issubset(device.capabilities):
            return CoreWelcome(False, None, "unregistered_capability")
        if device.device_id in self._revoked_devices:
            return CoreWelcome(False, None, "device_revoked")
        session_id = f"satellite-session-{uuid4()}"
        self._connections[session_id] = SatelliteConnection(
            session_id, hello, device, handler, datetime.now(UTC)
        )
        return CoreWelcome(True, session_id)

    def reconnect(
        self,
        hello: SatelliteHello,
        device: DeviceIdentity,
        handler: SatelliteHandler,
    ) -> CoreWelcome:
        """Re-establish a typed session after a transport interruption."""
        return self.register(hello, device, handler)

    def heartbeat(self, heartbeat: SatelliteHeartbeat) -> bool:
        connection = self._connections.get(heartbeat.session_id)
        if connection is None or connection.hello.device_id != heartbeat.device_id:
            return False
        connection.last_heartbeat = heartbeat.timestamp
        connection.online = True
        return True

    def session_for_device(self, device_id: str) -> SatelliteConnection | None:
        for connection in self._connections.values():
            if connection.device.device_id == device_id and connection.online and not connection.revoked:
                return connection
        return None

    def capabilities(self, device_id: str) -> frozenset[str]:
        connection = next((item for item in self._connections.values() if item.device.device_id == device_id), None)
        return connection.hello.capabilities if connection else frozenset()

    def status(self, device_id: str) -> str:
        connection = next((item for item in self._connections.values() if item.device.device_id == device_id), None)
        if connection is None:
            return "unknown"
        if connection.revoked:
            return "revoked"
        return "online" if connection.online else "offline"

    async def execute(self, session_id: str, command: SatelliteCommand) -> CommandObservation:
        validate_command(command)
        connection = self._connections.get(session_id)
        if connection is None or not connection.online or connection.revoked:
            return CommandObservation(command.command_id, "failed", error_code="satellite_offline")
        if command.capability not in connection.device.capabilities:
            return CommandObservation(command.command_id, "denied", error_code="device_capability_missing")
        result = connection.handler(command)
        if inspect.isawaitable(result):
            result = await result
        return result

    def disconnect(self, session_id: str) -> bool:
        connection = self._connections.get(session_id)
        if connection is None:
            return False
        connection.online = False
        return True

    def revoke(self, device_id: str) -> bool:
        changed = False
        for connection in self._connections.values():
            if connection.device.device_id == device_id:
                connection.online = False
                connection.revoked = True
                changed = True
        if changed:
            self._revoked_devices.add(device_id)
        return changed
