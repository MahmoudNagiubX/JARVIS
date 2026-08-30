"""Typed computer-use controller with a safe UFO adapter boundary."""

from __future__ import annotations

from uuid import uuid4

from ..contracts import ComputerAction, ToolContext, ToolResult, ToolResultStatus
from ..devices.satellite.contracts import SatelliteCommand
from ..devices.satellite.registry import WindowsSatelliteRegistry


class WindowsComputerController:
    """Translate approved computer actions into typed satellite commands."""

    def __init__(self, registry: WindowsSatelliteRegistry) -> None:
        self.registry = registry

    async def execute(self, action: ComputerAction, context: ToolContext) -> ToolResult:
        if context.device is None:
            return ToolResult(ToolResultStatus.DENIED, error_code="device_missing")
        connection = self.registry.session_for_device(context.device.device_id)
        if connection is None:
            return ToolResult(ToolResultStatus.FAILED, error_code="satellite_offline")
        if action.action in {"observe", "input"}:
            transport_action = action.action
            transport_capability = f"computer.{action.action}"
            parameters = dict(action.parameters)
        elif action.action in {
            "list_processes",
            "inspect_file",
            "search_files",
            "open_file",
            "open_folder",
            "open_application",
            "stop_safe_process",
        }:
            transport_action = "observe" if action.action in {"list_processes", "inspect_file", "search_files"} else "input"
            transport_capability = f"computer.{transport_action}"
            parameters = {"operation": action.action, **dict(action.parameters)}
        else:
            return ToolResult(ToolResultStatus.DENIED, error_code="unsupported_computer_action")
        if transport_capability not in context.device.capabilities:
            return ToolResult(ToolResultStatus.DENIED, error_code="device_capability_missing")
        command = SatelliteCommand(
            f"command-{uuid4()}", transport_action, transport_capability, parameters, action.dry_run
        )
        observation = await self.registry.execute(connection.session_id, command)
        status = ToolResultStatus.SUCCEEDED if observation.status == "completed" else (
            ToolResultStatus.DENIED if observation.status == "denied" else ToolResultStatus.FAILED
        )
        return ToolResult(status, dict(observation.output), observation.error_code, verified=status is ToolResultStatus.SUCCEEDED)


class UFOComputerController:
    """Reserved adapter boundary; Microsoft UFO is not a Phase 02 dependency."""

    async def execute(self, action: ComputerAction, context: ToolContext) -> ToolResult:
        return ToolResult(ToolResultStatus.FAILED, error_code="ufo_adapter_not_configured")
