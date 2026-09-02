from __future__ import annotations

import unittest

from jarvis.computer.controller import WindowsComputerController
from jarvis.contracts import ComputerAction, DeviceIdentity, Identity, ToolContext, ToolResult, ToolResultStatus
from jarvis.devices.satellite.contracts import SatelliteCommand, SatelliteHello
from jarvis.devices.satellite.registry import WindowsSatelliteRegistry
from jarvis.satellite_agent.agent import SatelliteAgentConfig, WindowsSatelliteAgent


class _Controller:
    def __init__(self) -> None:
        self.actions = []

    async def execute(self, action, context):
        self.actions.append((action, context))
        return ToolResult(ToolResultStatus.SUCCEEDED, {"bounded": True}, verified=True)


class PhaseElevenSatelliteInteractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_operations_use_existing_typed_satellite_registry(self) -> None:
        registry = WindowsSatelliteRegistry()
        owner = "owner-phase11"
        device = DeviceIdentity("satellite-phase11", owner, "desktop", "windows", frozenset({"computer.input", "computer.observe"}), frozenset({"tool.request"}))
        received = []

        async def handler(command):
            received.append(command)
            from jarvis.devices.satellite.contracts import CommandObservation
            return CommandObservation(command.command_id, "completed", {"bounded": True})

        welcome = registry.register(
            SatelliteHello(device.device_id, owner, "windows", "phase11", device.capabilities), device, handler
        )
        self.assertTrue(welcome.accepted)
        controller = WindowsComputerController(registry)
        context = ToolContext(Identity("identity", "Owner", owner, frozenset({"owner"})), device, "session", "correlation")
        for action_name, capability in (("window_action", "computer.input"), ("clipboard_read", "computer.observe"), ("clipboard_write", "computer.input"), ("keyboard_action", "computer.input")):
            parameters = {"operation": "type_text", "window_ref": "window-good", "text": "safe"} if action_name == "keyboard_action" else ({"text": "safe"} if action_name == "clipboard_write" else {})
            result = await controller.execute(ComputerAction(action_name, parameters, False), context)
            self.assertEqual(result.status, "succeeded")
            self.assertEqual(received[-1].action, "observe" if capability == "computer.observe" else "input")
            self.assertEqual(received[-1].parameters["operation"], action_name)

    async def test_satellite_agent_allowlist_accepts_phase_eleven_operations_only(self) -> None:
        fake = _Controller()
        config = SatelliteAgentConfig(
            "http://127.0.0.1:8787", "owner-phase11", "identity-phase11", "device-phase11",
            frozenset({"computer.input", "computer.observe"}),
        )
        agent = WindowsSatelliteAgent(config, "credential", network_mode="test", controller=fake)
        accepted = await agent.execute_command(SatelliteCommand(
            "command-keyboard", "input", "computer.input",
            {"operation": "keyboard_action", "window_ref": "window-good", "text": "safe"}, False,
        ))
        self.assertEqual(accepted.status, "completed")
        self.assertEqual(fake.actions[0][0].action, "keyboard_action")
        rejected = await agent.execute_command(SatelliteCommand(
            "command-mouse", "input", "computer.input", {"operation": "mouse_click", "x": 1, "y": 1}, False,
        ))
        self.assertEqual(rejected.status, "denied")
        self.assertEqual(rejected.error_code, "unsupported_typed_operation")
