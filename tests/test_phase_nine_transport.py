from __future__ import annotations

import asyncio
import unittest

from jarvis.api.core import CoreApplication, DemoPrincipal
from jarvis.authority.identity.service import EnrollmentGrant
from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.contracts import ComputerAction, ToolContext
from jarvis.devices.satellite.contracts import CommandObservation, SatelliteCommand, SatelliteHeartbeat, SatelliteHello
from jarvis.devices.satellite.transport import SatelliteTransportService


class PhaseNineTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        self.identity = await self.runtime.identity.bootstrap_owner("Phase Nine Owner")
        enrollment = await self.runtime.identity.create_enrollment(
            EnrollmentGrant(
                self.identity.owner_id,
                "Phase Nine Windows Satellite",
                "desktop",
                "windows",
                ("tool.request",),
                ("computer.observe", "computer.input"),
            )
        )
        issued = await self.runtime.identity.redeem_enrollment(enrollment.code)
        self.device = await self.runtime.identity.authenticate(issued.raw, issued.device_id)
        assert self.device is not None
        self.principal = DemoPrincipal(self.identity, self.device, issued.raw)
        self.application = CoreApplication(self.runtime)
        self.welcome = await self.application.satellite_connect(
            self.principal,
            {
                "device_id": self.device.device_id,
                "owner_id": self.identity.owner_id,
                "platform": "windows",
                "capabilities": ["computer.observe", "computer.input"],
            },
        )
        self.session_id = str(self.welcome["session_id"])

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    async def test_typed_command_round_trip_is_nonblocking_and_idempotent(self) -> None:
        task = asyncio.create_task(
            self.runtime.computer.execute(
                ComputerAction("list_processes", dry_run=True),
                ToolContext(self.identity, self.device, "satellite-test", "command-test"),
            )
        )
        command = await asyncio.wait_for(
            self.runtime.satellite_transport.poll(
                self.identity.owner_id, self.device.device_id, self.session_id, wait_seconds=2
            ),
            timeout=3,
        )
        self.assertIsNotNone(command)
        assert command is not None
        self.assertEqual(command.action, "observe")
        self.assertEqual(command.capability, "computer.observe")
        self.assertEqual(command.parameters["operation"], "list_processes")

        first = await self.application.satellite_result(
            self.principal,
            {
                "session_id": self.session_id,
                "command_id": command.command_id,
                "status": "completed",
                "output": {"dry_run": True},
            },
        )
        duplicate = await self.application.satellite_result(
            self.principal,
            {
                "session_id": self.session_id,
                "command_id": command.command_id,
                "status": "completed",
                "output": {"dry_run": True},
            },
        )
        result = await asyncio.wait_for(task, timeout=2)
        self.assertTrue(first["accepted"])
        self.assertFalse(first["duplicate"])
        self.assertTrue(duplicate["accepted"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(result.status.value, "succeeded")
        self.assertTrue(result.verified)

        reused = await self.runtime.satellite_transport._dispatch(
            self.session_id,
            SatelliteCommand(command.command_id, "observe", "computer.observe", {"operation": "search_files"}),
        )
        self.assertEqual(reused.status, "denied")
        self.assertEqual(reused.error_code, "command_id_reuse")

    async def test_owner_device_and_session_binding_fail_closed(self) -> None:
        self.assertIsNone(
            await self.runtime.satellite_transport.poll(
                "owner-not-mine", self.device.device_id, self.session_id, wait_seconds=0
            )
        )
        self.assertIsNone(
            await self.runtime.satellite_transport.poll(
                self.identity.owner_id, "device-not-mine", self.session_id, wait_seconds=0
            )
        )
        invalid_result = await self.runtime.satellite_transport.submit_result(
            "owner-not-mine",
            self.device.device_id,
            self.session_id,
            CommandObservation("unknown", "completed"),
        )
        self.assertFalse(invalid_result.accepted)
        self.assertEqual(invalid_result.reason, "satellite_session_invalid")

        disconnected = await self.application.satellite_disconnect(self.principal, self.session_id)
        self.assertTrue(disconnected["accepted"])
        self.assertFalse(
            await self.runtime.satellite_transport.heartbeat(
                self.identity.owner_id,
                self.device.device_id,
                SatelliteHeartbeat(self.session_id, self.device.device_id, 1),
            )
        )
        self.assertEqual(self.runtime.satellite_transport.health()["sessions"][0]["status"], "offline")

    async def test_command_and_result_payload_limits_are_bounded(self) -> None:
        oversized_command = await self.runtime.satellite_transport._dispatch(
            self.session_id,
            SatelliteCommand(
                "oversized-command",
                "observe",
                "computer.observe",
                {"operation": "inspect_file", "path": "x" * (self.runtime.satellite_transport.MAX_COMMAND_BYTES + 1)},
            ),
        )
        self.assertEqual(oversized_command.status, "denied")
        self.assertEqual(oversized_command.error_code, "command_payload_too_large")

        result_task = asyncio.create_task(
            self.runtime.satellite_transport._dispatch(
                self.session_id,
                SatelliteCommand("result-limit", "observe", "computer.observe", {"operation": "list_processes"}),
            )
        )
        command = await self.runtime.satellite_transport.poll(
            self.identity.owner_id, self.device.device_id, self.session_id, wait_seconds=1
        )
        self.assertIsNotNone(command)
        assert command is not None
        oversized_result = await self.runtime.satellite_transport.submit_result(
            self.identity.owner_id,
            self.device.device_id,
            self.session_id,
            CommandObservation(command.command_id, "completed", {"output": "x" * (self.runtime.satellite_transport.MAX_RESULT_BYTES + 1)}),
        )
        self.assertFalse(oversized_result.accepted)
        self.assertEqual(oversized_result.reason, "result_payload_too_large")
        await self.runtime.satellite_transport.submit_result(
            self.identity.owner_id,
            self.device.device_id,
            self.session_id,
            CommandObservation(command.command_id, "failed", error_code="test_cleanup"),
        )
        self.assertEqual((await result_task).status, "failed")

    async def test_reconnect_replaces_session_and_preserves_one_registry_authority(self) -> None:
        replacement = await self.application.satellite_connect(
            self.principal,
            {
                "device_id": self.device.device_id,
                "owner_id": self.identity.owner_id,
                "platform": "windows",
                "capabilities": ["computer.observe"],
            },
        )
        self.assertTrue(replacement["accepted"])
        self.assertNotEqual(replacement["session_id"], self.session_id)
        self.assertEqual(len(self.runtime.satellite_transport.health()["sessions"]), 2)
        self.assertEqual(sum(item["status"] == "online" for item in self.runtime.satellite_transport.health()["sessions"]), 1)
        self.assertIsNone(
            await self.runtime.satellite_transport.poll(
                self.identity.owner_id, self.device.device_id, self.session_id, wait_seconds=0
            )
        )

    async def test_revocation_denies_existing_and_new_sessions(self) -> None:
        self.assertTrue(await self.runtime.satellite_transport.revoke(self.device.device_id))
        self.assertFalse(
            await self.runtime.satellite_transport.heartbeat(
                self.identity.owner_id,
                self.device.device_id,
                SatelliteHeartbeat(self.session_id, self.device.device_id, 1),
            )
        )
        replacement = await self.application.satellite_connect(
            self.principal,
            {
                "device_id": self.device.device_id,
                "owner_id": self.identity.owner_id,
                "platform": "windows",
                "capabilities": ["computer.observe"],
            },
        )
        self.assertFalse(replacement["accepted"])
        self.assertEqual(replacement["reason"], "device_revoked")

    async def test_queue_overflow_and_command_ttl_fail_closed(self) -> None:
        limited = SatelliteTransportService(
            self.runtime.satellite,
            command_ttl_seconds=0.1,
            max_queue_per_device=1,
        )
        try:
            welcome = await limited.connect(
                self.principal,
                SatelliteHello(
                    self.device.device_id,
                    self.identity.owner_id,
                    "windows",
                    "test",
                    frozenset({"computer.observe"}),
                ),
            )
            self.assertTrue(welcome.accepted)
            assert welcome.session_id is not None
            first_task = asyncio.create_task(
                limited._dispatch(
                    welcome.session_id,
                    SatelliteCommand("bounded-1", "observe", "computer.observe", {"operation": "list_processes"}),
                )
            )
            await asyncio.sleep(0)
            overflow = await limited._dispatch(
                welcome.session_id,
                SatelliteCommand("bounded-2", "observe", "computer.observe", {"operation": "list_processes"}),
            )
            self.assertEqual(overflow.error_code, "transport_queue_overflow")
            command = await limited.poll(
                self.identity.owner_id, self.device.device_id, welcome.session_id, wait_seconds=0
            )
            self.assertIsNotNone(command)
            assert command is not None
            self.assertEqual(command.command_id, "bounded-1")
            await limited.submit_result(
                self.identity.owner_id,
                self.device.device_id,
                welcome.session_id,
                CommandObservation("bounded-1", "completed", {"dry_run": True}),
            )
            self.assertEqual((await first_task).status, "completed")

            expired = await limited._dispatch(
                welcome.session_id,
                SatelliteCommand("bounded-expiry", "observe", "computer.observe", {"operation": "list_processes"}),
            )
            self.assertEqual(expired.error_code, "command_expired")
        finally:
            limited.close()


if __name__ == "__main__":
    unittest.main()
