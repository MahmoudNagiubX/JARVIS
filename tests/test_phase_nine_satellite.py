from __future__ import annotations

import json
import unittest

from jarvis.contracts import ComputerResult
from jarvis.devices.satellite.contracts import SatelliteCommand
from jarvis.satellite_agent import SatelliteAgentConfig, SatelliteAgentTransportError, WindowsSatelliteAgent


class _FakeController:
    async def execute(self, action, context):
        return ComputerResult("succeeded", {"action": action.action, "dry_run": action.dry_run}, verified=True)


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class PhaseNineSatelliteAgentTests(unittest.IsolatedAsyncioTestCase):
    def _config(self) -> SatelliteAgentConfig:
        return SatelliteAgentConfig(
            "http://127.0.0.1:8787",
            "owner-1",
            "identity-1",
            "device-1",
            frozenset({"computer.observe", "computer.input"}),
        )

    async def test_agent_executes_only_declared_typed_operations(self) -> None:
        agent = WindowsSatelliteAgent(self._config(), "secret", network_mode="test", controller=_FakeController())
        result = await agent.execute_command(
            SatelliteCommand("command-1", "observe", "computer.observe", {"operation": "list_processes"})
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.output["action"], "list_processes")

        denied = await agent.execute_command(
            SatelliteCommand("command-2", "input", "computer.input", {"operation": "shell"}, False)
        )
        self.assertEqual(denied.status, "denied")
        self.assertEqual(denied.error_code, "unsupported_typed_operation")

        mismatch = await agent.execute_command(
            SatelliteCommand("command-3", "input", "computer.observe", {"operation": "list_processes"})
        )
        self.assertEqual(mismatch.error_code, "invalid_typed_command")

    async def test_agent_keeps_credential_in_header_and_rejects_result_failure(self) -> None:
        requests = []
        responses = [
            {"accepted": True, "session_id": "session-1"},
            {"command": {"command_id": "command-1", "action": "observe", "capability": "computer.observe", "parameters": {"operation": "list_processes"}, "dry_run": True}},
            {"accepted": False, "reason": "satellite_session_invalid"},
        ]

        def opener(request, timeout=30.0):
            requests.append(request)
            return _Response(responses.pop(0))

        agent = WindowsSatelliteAgent(self._config(), "credential-not-in-body", network_mode="test", controller=_FakeController(), opener=opener)
        await agent.connect()
        with self.assertRaisesRegex(SatelliteAgentTransportError, "satellite_session_invalid"):
            await agent.poll_once(wait_seconds=0)
        self.assertEqual(len(requests), 3)
        self.assertTrue(requests[0].get_header("Authorization").startswith("Bearer "))
        self.assertNotIn(b"credential-not-in-body", requests[0].data)
        self.assertNotIn("credential-not-in-body", requests[0].full_url)

    def test_agent_rejects_non_loopback_core(self) -> None:
        with self.assertRaisesRegex(ValueError, "public_or_unauthorized"):
            WindowsSatelliteAgent(
                SatelliteAgentConfig("http://203.0.113.5:8787", "o", "i", "d", frozenset()),
                "secret",
            )
if __name__ == "__main__":
    unittest.main()
