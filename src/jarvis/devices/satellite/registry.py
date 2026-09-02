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
    SUPPORTED_PROTOCOL_VERSIONS,
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
        self._current_sessions: dict[str, str] = {}
        self._last_status: dict[str, str] = {}
        self._last_capabilities: dict[str, frozenset[str]] = {}

    def register(
        self,
        hello: SatelliteHello,
        device: DeviceIdentity,
        handler: SatelliteHandler,
    ) -> CoreWelcome:
        if hello.protocol_version not in SUPPORTED_PROTOCOL_VERSIONS:
            return CoreWelcome(False, None, "protocol_version_unsupported")
        if "perception.screen" in hello.capabilities and hello.protocol_version != "2":
            return CoreWelcome(False, None, "perception_protocol_v2_required")
        if hello.platform.casefold() not in {"windows", "linux", "ubuntu", "darwin", "satellite", "esp32", "posix", "android", "ios"}:
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
        self._current_sessions[device.device_id] = session_id
        self._last_status[device.device_id] = "online"
        self._last_capabilities[device.device_id] = hello.capabilities
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
        if connection is None or connection.hello.device_id != heartbeat.device_id or connection.revoked or not connection.online:
            return False
        connection.last_heartbeat = heartbeat.timestamp
        connection.online = True
        self._current_sessions[connection.device.device_id] = connection.session_id
        self._last_status[connection.device.device_id] = "online"
        return True

    def session_for_device(self, device_id: str) -> SatelliteConnection | None:
        current_id = self._current_sessions.get(device_id)
        current = self._connections.get(current_id) if current_id else None
        if current is not None and current.online and not current.revoked:
            return current
        active = [
            connection
            for connection in self._connections.values()
            if connection.device.device_id == device_id and connection.online and not connection.revoked
        ]
        if not active:
            return None
        current = max(active, key=lambda connection: connection.last_heartbeat)
        self._current_sessions[device_id] = current.session_id
        return current

    def capabilities(self, device_id: str) -> frozenset[str]:
        connection = self.session_for_device(device_id)
        return connection.hello.capabilities if connection else self._last_capabilities.get(device_id, frozenset())

    def status(self, device_id: str) -> str:
        connection = self.session_for_device(device_id)
        if connection is not None:
            return "online"
        if device_id in self._revoked_devices or self._last_status.get(device_id) == "revoked":
            return "revoked"
        return self._last_status.get(device_id, "unknown")

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
        if not connection.revoked:
            self._last_status[connection.device.device_id] = "offline"
        return True

    def retire(self, session_id: str) -> bool:
        """Forget an inactive transport session after its pending work is settled."""
        connection = self._connections.pop(session_id, None)
        if connection is None:
            return False
        if self._current_sessions.get(connection.device.device_id) == session_id:
            self._current_sessions.pop(connection.device.device_id, None)
        return True

    def revoke(self, device_id: str) -> bool:
        changed = device_id not in self._revoked_devices
        self._revoked_devices.add(device_id)
        for connection in self._connections.values():
            if connection.device.device_id == device_id:
                connection.online = False
                connection.revoked = True
                changed = True
        self._current_sessions.pop(device_id, None)
        self._last_status[device_id] = "revoked"
        return changed
