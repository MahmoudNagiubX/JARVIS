"""Windows satellite client using authenticated typed HTTP long polling."""

from __future__ import annotations

import asyncio
import json
import platform
import threading
import time
from dataclasses import dataclass
from http.client import HTTPException
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from ..computer.service import WindowsNativeComputerController
from ..contracts import ComputerAction, DeviceIdentity, Identity, ToolContext
from ..devices.satellite.contracts import CommandObservation, SatelliteCommand, validate_command


class SatelliteAgentTransportError(RuntimeError):
    """A transport failure that must not be reported as command success."""


@dataclass(frozen=True, slots=True)
class SatelliteAgentConfig:
    core_url: str
    owner_id: str
    identity_id: str
    device_id: str
    capabilities: frozenset[str]
    software_version: str = "phase09"
    poll_interval_seconds: float = 15.0
    heartbeat_interval_seconds: float = 15.0


class WindowsSatelliteAgent:
    """Execute only core-issued, typed computer operations on this machine."""

    ALLOWED_OPERATIONS = frozenset({
        "list_processes",
        "inspect_file",
        "search_files",
        "open_file",
        "open_folder",
        "open_application",
        "stop_safe_process",
    })

    def __init__(
        self,
        config: SatelliteAgentConfig,
        credential: str,
        *,
        controller: WindowsNativeComputerController | None = None,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        _validate_core_url(config.core_url)
        if not credential.strip():
            raise ValueError("satellite credential is required")
        if not config.owner_id.strip() or not config.identity_id.strip() or not config.device_id.strip():
            raise ValueError("satellite identity fields are required")
        if config.poll_interval_seconds <= 0 or config.heartbeat_interval_seconds <= 0:
            raise ValueError("satellite intervals must be positive")
        self.config = config
        self._credential = credential
        self._controller = controller or WindowsNativeComputerController()
        self._opener = opener
        self._session_id: str | None = None
        self._sequence = 0
        self._last_heartbeat = 0.0

    @property
    def session_id(self) -> str | None:
        return self._session_id

    async def connect(self) -> str:
        response = await asyncio.to_thread(
            self._request,
            "POST",
            "/v1/satellites/connect",
            {
                "owner_id": self.config.owner_id,
                "device_id": self.config.device_id,
                "platform": platform.system().casefold() or "windows",
                "software_version": self.config.software_version,
                "capabilities": sorted(self.config.capabilities),
                "protocol_version": "1",
                "name": self.config.device_id,
            },
        )
        if not bool(response.get("accepted")) or not isinstance(response.get("session_id"), str):
            raise SatelliteAgentTransportError(str(response.get("reason", "satellite_connection_rejected")))
        self._session_id = response["session_id"]
        self._last_heartbeat = 0.0
        return self._session_id

    async def heartbeat(self) -> bool:
        session_id = self._required_session()
        self._sequence += 1
        response = await asyncio.to_thread(
            self._request,
            "POST",
            "/v1/satellites/heartbeat",
            {"session_id": session_id, "sequence": self._sequence},
        )
        accepted = bool(response.get("accepted"))
        if accepted:
            self._last_heartbeat = time.monotonic()
        return accepted

    async def poll_once(self, *, wait_seconds: float | None = None) -> CommandObservation | None:
        session_id = self._required_session()
        wait = self.config.poll_interval_seconds if wait_seconds is None else max(0.0, min(wait_seconds, 25.0))
        query = urlencode({"session_id": session_id, "wait_seconds": str(wait)})
        response = await asyncio.to_thread(self._request, "GET", f"/v1/satellites/commands?{query}", None)
        raw = response.get("command")
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise SatelliteAgentTransportError("invalid_satellite_command_envelope")
        command = SatelliteCommand(
            str(raw.get("command_id", "")),
            str(raw.get("action", "")),
            str(raw.get("capability", "")),
            raw.get("parameters", {}) if isinstance(raw.get("parameters", {}), dict) else {},
            bool(raw.get("dry_run", True)),
        )
        observation = await self.execute_command(command)
        submission = await asyncio.to_thread(
            self._request,
            "POST",
            "/v1/satellites/results",
            {
                "session_id": session_id,
                "command_id": observation.command_id,
                "status": observation.status,
                "output": dict(observation.output),
                "error_code": observation.error_code,
            },
        )
        if not bool(submission.get("accepted")):
            raise SatelliteAgentTransportError(str(submission.get("reason", "satellite_result_rejected")))
        return observation

    async def execute_command(self, command: SatelliteCommand) -> CommandObservation:
        try:
            validate_command(command)
        except ValueError:
            return CommandObservation(command.command_id, "denied", error_code="invalid_typed_command")
        if command.capability not in self.config.capabilities:
            return CommandObservation(command.command_id, "denied", error_code="capability_not_declared")
        operation = command.parameters.get("operation")
        if not isinstance(operation, str) or operation not in self.ALLOWED_OPERATIONS:
            return CommandObservation(command.command_id, "denied", error_code="unsupported_typed_operation")
        parameters = {key: value for key, value in command.parameters.items() if key != "operation"}
        identity = Identity(self.config.identity_id, "JARVIS satellite", self.config.owner_id, frozenset({"owner"}))
        device = DeviceIdentity(
            self.config.device_id,
            self.config.owner_id,
            "desktop",
            "windows",
            self.config.capabilities,
            frozenset({"tool.request"}),
        )
        try:
            result = await self._controller.execute(
                ComputerAction(operation, parameters, command.dry_run),
                ToolContext(identity, device, f"satellite-{self.config.device_id}", command.command_id),
            )
        except Exception as exc:
            return CommandObservation(command.command_id, "failed", error_code=f"adapter_error:{exc.__class__.__name__}")
        status = "completed" if result.status == "succeeded" else "denied" if result.status == "denied" else "failed"
        output = dict(result.output) if isinstance(result.output, dict) else {"value": result.output}
        return CommandObservation(command.command_id, status, output, result.error_code)

    async def disconnect(self) -> bool:
        if self._session_id is None:
            return False
        response = await asyncio.to_thread(
            self._request,
            "POST",
            "/v1/satellites/disconnect",
            {"session_id": self._session_id},
        )
        accepted = bool(response.get("accepted"))
        self._session_id = None
        return accepted

    async def run_forever(self, stop_event: threading.Event | None = None) -> None:
        backoff = 1.0
        try:
            while stop_event is None or not stop_event.is_set():
                try:
                    if self._session_id is None:
                        await self.connect()
                    if time.monotonic() - self._last_heartbeat >= self.config.heartbeat_interval_seconds:
                        if not await self.heartbeat():
                            self._session_id = None
                            continue
                    await self.poll_once()
                    backoff = 1.0
                except (SatelliteAgentTransportError, HTTPError, HTTPException, OSError, URLError):
                    self._session_id = None
                    if stop_event is None:
                        await asyncio.sleep(backoff)
                    else:
                        await asyncio.to_thread(stop_event.wait, backoff)
                    backoff = min(60.0, backoff * 2)
        finally:
            if self._session_id is not None:
                try:
                    await self.disconnect()
                except (SatelliteAgentTransportError, HTTPException, OSError, URLError):
                    pass

    def _request(self, method: str, path: str, payload: dict[str, object] | None) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._credential}",
            "X-JARVIS-Device-ID": self.config.device_id,
            "X-JARVIS-Identity-ID": self.config.identity_id,
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = Request(f"{self.config.core_url.rstrip('/')}{path}", data=body, headers=headers, method=method)
        try:
            with self._opener(request, timeout=30.0) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except (HTTPError, HTTPException, OSError, URLError, ValueError, json.JSONDecodeError) as exc:
            raise SatelliteAgentTransportError(f"satellite_transport_error:{exc.__class__.__name__}") from exc
        if not isinstance(decoded, dict):
            raise SatelliteAgentTransportError("satellite_response_must_be_object")
        return decoded

    def _required_session(self) -> str:
        if self._session_id is None:
            raise SatelliteAgentTransportError("satellite_not_connected")
        return self._session_id


def _validate_core_url(value: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme != "http" or parsed.username or parsed.password or parsed.path not in ("", "/"):
        raise ValueError("satellite core URL must be a loopback HTTP origin")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.port is None:
        raise ValueError("satellite core URL must use an explicit loopback host and port")
