from __future__ import annotations

import asyncio
import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jarvis.api.core import CoreApplication, DemoPrincipal
from jarvis.authority.identity.service import EnrollmentGrant
from jarvis.authority.permissions.engine import PermissionRule, PolicyPermissionEngine
from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.contracts import DeviceIdentity, PermissionEffect, ToolResult, ToolResultStatus, WorldStateQuery


ROOT = Path(__file__).resolve().parents[1]


class _CountingLocalController:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, action, context):
        self.calls += 1
        return ToolResult(ToolResultStatus.SUCCEEDED, {"action": action.action}, verified=True)


class PhaseNineAuthorityIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        self.identity = await self.runtime.identity.bootstrap_owner("Phase Nine Authority Owner")
        self.actor = await self._enroll("Request Desktop", {"computer.observe", "computer.input"})
        self.target = await self._enroll("Windows Satellite", {"computer.observe", "computer.input"})
        self.limited = await self._enroll("Limited Desktop", set())
        self.actor_principal = DemoPrincipal(self.identity, self.actor)
        self.target_principal = DemoPrincipal(self.identity, self.target)
        self.application = CoreApplication(self.runtime)
        welcome = await self.application.satellite_connect(
            self.target_principal,
            {
                "device_id": self.target.device_id,
                "owner_id": self.identity.owner_id,
                "platform": "windows",
                "capabilities": ["computer.observe", "computer.input"],
            },
        )
        self.assertTrue(welcome["accepted"])
        self.session_id = str(welcome["session_id"])

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    async def _enroll(self, name: str, capabilities: set[str]) -> DeviceIdentity:
        enrollment = await self.runtime.identity.create_enrollment(
            EnrollmentGrant(
                self.identity.owner_id,
                name,
                "desktop",
                "windows",
                ("tool.request",),
                tuple(sorted(capabilities)),
            )
        )
        issued = await self.runtime.identity.redeem_enrollment(enrollment.code)
        device = await self.runtime.identity.authenticate(issued.raw, issued.device_id)
        assert device is not None
        return device

    async def _poll(self, session_id: str | None = None):
        return await self.runtime.satellite_transport.poll(
            self.identity.owner_id,
            self.target.device_id,
            session_id or self.session_id,
            wait_seconds=1,
        )

    async def _run_satellite_command(self, task, session_id: str | None = None):
        command = await self._poll(session_id)
        self.assertIsNotNone(command)
        assert command is not None
        result = await self.application.satellite_result(
            self.target_principal,
            {
                "session_id": session_id or self.session_id,
                "command_id": command.command_id,
                "status": "completed",
                "output": {"bounded": True},
            },
        )
        self.assertTrue(result["accepted"])
        return command, await task

    def _queued(self) -> int:
        return sum(item["queued"] for item in self.runtime.satellite_transport.health()["sessions"])

    async def test_product_computer_action_routes_explicit_target_through_satellite(self) -> None:
        task = self.application.computer_action(
            self.identity,
            self.actor,
            "list_processes",
            dry_run=True,
            target_device_id=self.target.device_id,
        )
        command, result = await self._run_satellite_command(asyncio.create_task(task))
        self.assertEqual(command.parameters["operation"], "list_processes")
        self.assertEqual(result["status"], "succeeded")
        self.assertTrue(result["verified"])

    async def test_permission_failure_queues_nothing(self) -> None:
        before = self._queued()
        result = await self.application.computer_action(
            self.identity,
            self.limited,
            "list_processes",
            dry_run=True,
            target_device_id=self.target.device_id,
        )
        self.assertEqual(result["status"], "denied")
        self.assertEqual(result["error_code"], "device_capability_missing")
        self.assertEqual(self._queued(), before)

    async def test_approval_blocks_remote_execution_then_executes_once_after_approval(self) -> None:
        self.runtime.computer_actions.permission = PolicyPermissionEngine(
            (PermissionRule("computer.open_application", PermissionEffect.REQUIRE_APPROVAL, "review_required"),)
        )
        before = self._queued()
        pending = await self.application.computer_action(
            self.identity,
            self.actor,
            "open_application",
            {"application": "notepad"},
            dry_run=True,
            target_device_id=self.target.device_id,
        )
        self.assertEqual(pending["status"], "approval_required")
        self.assertIsNotNone(pending["approval_id"])
        self.assertEqual(self._queued(), before)

        approval_task = asyncio.create_task(
            self.application.decide_computer_action(str(pending["approval_id"]), True, self.identity.identity_id)
        )
        command = await self._poll()
        self.assertIsNotNone(command)
        assert command is not None
        self.assertEqual(command.parameters["operation"], "open_application")
        await self.application.satellite_result(
            self.target_principal,
            {
                "session_id": self.session_id,
                "command_id": command.command_id,
                "status": "completed",
                "output": {"bounded": True},
            },
        )
        approved = await approval_task
        self.assertEqual(approved["status"], "succeeded")

    async def test_cross_owner_target_is_rejected_without_queueing(self) -> None:
        other_owner = self.runtime.repository.create_owner("Other Owner")
        other_device = self.runtime.repository.create_device(
            other_owner,
            "Other Windows",
            "desktop",
            "windows",
            ("computer.observe",),
            ("tool.request",),
        )
        before = self._queued()
        result = await self.application.computer_action(
            self.identity,
            self.actor,
            "list_processes",
            dry_run=True,
            target_device_id=other_device,
        )
        self.assertEqual(result["status"], "denied")
        self.assertEqual(result["error_code"], "target_owner_mismatch")
        self.assertEqual(self._queued(), before)

    async def test_explicit_offline_target_never_falls_back_to_local(self) -> None:
        local = _CountingLocalController()
        self.runtime.computer_actions.controller.local = local
        disconnected = await self.application.satellite_disconnect(self.target_principal, self.session_id)
        self.assertTrue(disconnected["accepted"])
        result = await self.application.computer_action(
            self.identity,
            self.actor,
            "list_processes",
            dry_run=False,
            target_device_id=self.target.device_id,
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "satellite_offline")
        self.assertEqual(local.calls, 0)

    async def test_remote_audit_contains_actor_target_and_adapter_without_secrets(self) -> None:
        task = asyncio.create_task(
            self.application.computer_action(
                self.identity,
                self.actor,
                "list_processes",
                {"path": "safe-path"},
                dry_run=True,
                target_device_id=self.target.device_id,
            )
        )
        command, result = await self._run_satellite_command(task)
        self.assertEqual(result["status"], "succeeded")
        del command
        rows = self.runtime.repository.audit()
        metadata = [json.loads(row["metadata_json"]) for row in rows if row["device_id"] == self.actor.device_id]
        remote = [item for item in metadata if item.get("target_device_id") == self.target.device_id]
        self.assertTrue(remote)
        self.assertEqual(remote[-1]["request_device_id"], self.actor.device_id)
        self.assertEqual(remote[-1]["execution_adapter"], "satellite")
        self.assertNotIn("safe-path", json.dumps(remote))

    async def test_stale_maintenance_invalidates_transport_registry_fabric_and_world_state(self) -> None:
        session = self.runtime.satellite_transport._sessions[self.session_id]
        session.last_heartbeat = datetime.now(UTC) - timedelta(minutes=5)
        job = next(item for item in self.runtime.scheduler.jobs.values() if item.name == "satellite-health")
        self.assertEqual(await self.runtime.scheduler.run_once(job.job_id), 1)
        self.assertEqual(self.runtime.satellite_transport.health()["sessions"][0]["status"], "offline")
        self.assertEqual(self.runtime.satellite.status(self.target.device_id), "offline")
        device = await self.runtime.device_fabric.get(self.identity.owner_id, self.target.device_id)
        self.assertIsNotNone(device)
        assert device is not None
        self.assertEqual(device.status, "offline")
        facts = await self.runtime.world_state.facts(
            WorldStateQuery(self.identity.owner_id, f"device.{self.target.device_id}.online")
        )
        self.assertEqual(facts[0].value, False)

    async def test_action_after_stale_expiration_fails_without_queueing(self) -> None:
        session = self.runtime.satellite_transport._sessions[self.session_id]
        session.last_heartbeat = datetime.now(UTC) - timedelta(minutes=5)
        job = next(item for item in self.runtime.scheduler.jobs.values() if item.name == "satellite-health")
        await self.runtime.scheduler.run_once(job.job_id)
        before = self._queued()
        result = await self.application.computer_action(
            self.identity,
            self.actor,
            "list_processes",
            dry_run=True,
            target_device_id=self.target.device_id,
        )
        self.assertEqual(result["error_code"], "satellite_offline")
        self.assertEqual(self._queued(), before)

    async def test_pending_command_fails_as_satellite_stale(self) -> None:
        task = asyncio.create_task(
            self.application.computer_action(
                self.identity,
                self.actor,
                "list_processes",
                dry_run=True,
                target_device_id=self.target.device_id,
            )
        )
        command = await self._poll()
        self.assertIsNotNone(command)
        session = self.runtime.satellite_transport._sessions[self.session_id]
        session.last_heartbeat = datetime.now(UTC) - timedelta(minutes=5)
        expired = await self.runtime.satellite_transport.expire_stale_sessions()
        self.assertEqual(len(expired), 1)
        result = await task
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "satellite_stale")

    async def test_canonical_identity_revoke_invalidates_pending_and_reconnect(self) -> None:
        task = asyncio.create_task(
            self.application.computer_action(
                self.identity,
                self.actor,
                "list_processes",
                dry_run=True,
                target_device_id=self.target.device_id,
            )
        )
        command = await self._poll()
        self.assertIsNotNone(command)
        await self.runtime.identity.revoke_device(self.target.device_id)
        result = await task
        self.assertEqual(result["error_code"], "device_revoked")
        self.assertEqual(self.runtime.satellite.status(self.target.device_id), "revoked")
        replacement = await self.application.satellite_connect(
            self.target_principal,
            {
                "device_id": self.target.device_id,
                "owner_id": self.identity.owner_id,
                "platform": "windows",
                "capabilities": ["computer.observe"],
            },
        )
        self.assertFalse(replacement["accepted"])
        self.assertEqual(replacement["reason"], "device_revoked")

    async def test_revoke_without_live_session_persists_against_future_connect(self) -> None:
        dormant = await self._enroll("Dormant Satellite", {"computer.observe"})
        dormant_principal = DemoPrincipal(self.identity, dormant)
        self.assertTrue(await self.runtime.satellite_transport.revoke(dormant.device_id))
        replacement = await self.application.satellite_connect(
            dormant_principal,
            {
                "device_id": dormant.device_id,
                "owner_id": self.identity.owner_id,
                "platform": "windows",
                "capabilities": ["computer.observe"],
            },
        )
        self.assertFalse(replacement["accepted"])
        self.assertEqual(replacement["reason"], "device_revoked")

    async def test_heartbeats_refresh_freshness_without_lifecycle_storm_and_transition_once(self) -> None:
        initial_events = len([row for row in self.runtime.repository.events() if row["event_type"] == "device.online"])
        initial_observations = self.runtime.repository.database.connection.execute(
            "SELECT COUNT(*) AS count FROM world_observations WHERE subject = ?",
            (f"device.{self.target.device_id}.online",),
        ).fetchone()["count"]
        last_seen = None
        for sequence in range(1, 21):
            response = await self.application.satellite_heartbeat(
                self.target_principal,
                {"session_id": self.session_id, "sequence": sequence},
            )
            self.assertTrue(response["accepted"])
            current = await self.runtime.device_fabric.get(self.identity.owner_id, self.target.device_id)
            assert current is not None
            last_seen = current.last_seen
        self.assertIsNotNone(last_seen)
        self.assertEqual(
            len([row for row in self.runtime.repository.events() if row["event_type"] == "device.online"]),
            initial_events,
        )
        self.assertEqual(
            self.runtime.repository.database.connection.execute(
                "SELECT COUNT(*) AS count FROM world_observations WHERE subject = ?",
                (f"device.{self.target.device_id}.online",),
            ).fetchone()["count"],
            initial_observations,
        )
        await self.runtime.device_fabric.mark_offline(self.identity.owner_id, self.target.device_id, reason="test_transition")
        await self.application.satellite_heartbeat(self.target_principal, {"session_id": self.session_id, "sequence": 21})
        self.assertEqual(
            len([row for row in self.runtime.repository.events() if row["event_type"] == "device.online"]),
            initial_events + 1,
        )

    async def test_reconnect_history_is_bounded_and_only_one_session_is_active(self) -> None:
        old_session = self.session_id
        for _ in range(100):
            welcome = await self.application.satellite_connect(
                self.target_principal,
                {
                    "device_id": self.target.device_id,
                    "owner_id": self.identity.owner_id,
                    "platform": "windows",
                    "capabilities": ["computer.observe"],
                },
            )
            self.assertTrue(welcome["accepted"])
        sessions = self.runtime.satellite_transport.health()["sessions"]
        self.assertEqual(sum(item["status"] == "online" for item in sessions), 1)
        self.assertLessEqual(len(sessions), self.runtime.satellite_transport.MAX_INACTIVE_SESSIONS + 1)
        self.assertIsNone(await self.runtime.satellite_transport.poll(self.identity.owner_id, self.target.device_id, old_session, 0))

    async def test_public_health_is_aggregate_only(self) -> None:
        health = await self.application.health()
        transport = health["node_transport"]
        self.assertEqual(set(transport), {"transport", "available", "online_sessions", "degraded"})
        self.assertNotIn("session_id", json.dumps(transport))
        self.assertNotIn(self.target.device_id, json.dumps(transport))
        self.assertNotIn(self.identity.owner_id, json.dumps(transport))

    async def test_satellite_role_cannot_compose_core_and_credential_cli_is_unavailable(self) -> None:
        with self.assertRaisesRegex(ValueError, "satellite role must use python -m jarvis.satellite_agent"):
            create_runtime(
                JarvisConfig(
                    environment="test",
                    database_path=":memory:",
                    runtime_role="satellite",
                    core_url="http://127.0.0.1:8787",
                )
            )
        entrypoint = (ROOT / "src/jarvis/satellite_agent/__main__.py").read_text(encoding="utf-8")
        launcher = (ROOT / "scripts/phase09/run_windows_satellite.ps1").read_text(encoding="utf-8")
        self.assertNotIn("--credential", entrypoint)
        self.assertNotIn("[string]$Credential", launcher)
        self.assertIn("JARVIS_SATELLITE_CREDENTIAL", entrypoint)
        self.assertIn("JARVIS_SATELLITE_CREDENTIAL", launcher)


if __name__ == "__main__":
    unittest.main()
