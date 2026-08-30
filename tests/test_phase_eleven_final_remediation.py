from __future__ import annotations

import asyncio
import json
import threading
import unittest
from collections import deque
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from jarvis.api.core import CoreApplication
from jarvis.api.http import CoreHttpServer
from jarvis.authority.identity.service import EnrollmentGrant
from jarvis.authority.permissions.engine import PermissionRule
from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.contracts import (
    ApprovalRequest,
    ComputerAction,
    ComputerResult,
    DeviceIdentity,
    Identity,
    LLMResponse,
    PermissionEffect,
    ToolContext,
    ToolResult,
    ToolResultStatus,
)
from jarvis.satellite_agent.agent import SatelliteAgentConfig, WindowsSatelliteAgent
from jarvis.tools.registry import ToolSpec
from jarvis.tools.service import ToolExecutionStatus


AGENT_SENTINEL = "PHASE11_AGENT_PRIVATE_TYPED_SENTINEL_68142"


class _RecordingController:
    def __init__(self) -> None:
        self.actions: list[tuple[ComputerAction, ToolContext]] = []

    async def execute(self, action: ComputerAction, context: ToolContext) -> ComputerResult:
        self.actions.append((action, context))
        return ComputerResult("succeeded", {"accepted": True, "action": action.action}, verified=True)


class _TwoStepModel:
    def __init__(self, sentinel: str) -> None:
        self.sentinel = sentinel
        self.calls = 0
        self.requests = []

    async def generate(self, request, route):
        del route
        self.calls += 1
        self.requests.append(request)
        if self.calls == 1:
            return LLMResponse(
                request.request_id,
                "",
                "phase11-test-model",
                "tool_calls",
                ({"function": {"name": "computer.keyboard.type", "arguments": {"window_ref": "window-good", "text": self.sentinel}}},),
                {},
                "test",
            )
        return LLMResponse(request.request_id, "The prepared input completed.", "phase11-test-model", "stop", (), {}, "test")


class PhaseElevenFinalRemediationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        self.identity = await self.runtime.identity.bootstrap_owner("Phase Eleven Remediation Owner")
        grant = await self.runtime.identity.create_enrollment(
            EnrollmentGrant(
                self.identity.owner_id,
                "Phase Eleven Remediation Desktop",
                "desktop",
                "windows",
                ("tool.request",),
                ("computer.observe", "computer.input"),
            )
        )
        issued = await self.runtime.identity.redeem_enrollment(grant.code)
        self.credential = issued.raw
        self.device = await self.runtime.identity.authenticate(issued.raw, issued.device_id)
        assert self.device is not None
        self.context = ToolContext(self.identity, self.device, "phase11-remediation", "phase11-remediation-correlation")
        self.controller = _RecordingController()
        self.runtime.computer_actions.controller.local = self.controller
        self.application = CoreApplication(self.runtime)
        self.server: CoreHttpServer | None = None
        self.server_thread: threading.Thread | None = None

    async def asyncTearDown(self) -> None:
        if self.server is not None:
            await asyncio.to_thread(self.server.shutdown)
        if self.server_thread is not None:
            self.server_thread.join(timeout=2)
        await self.runtime.shutdown()

    def _db_text(self) -> str:
        tables = self.runtime.repository.database.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        values: list[str] = []
        for table in tables:
            name = str(table[0])
            rows = self.runtime.repository.database.connection.execute(f'SELECT * FROM "{name}"').fetchall()
            values.extend(str(tuple(row)) for row in rows)
        return "\n".join(values)

    async def _approval(self, approval_id: str, *, expires_at: datetime | None = None) -> str:
        now = datetime.now(UTC)
        await self.runtime.approval.request(
            ApprovalRequest(
                approval_id,
                "tool.phase11.delegated",
                self.identity.owner_id,
                self.device.device_id,
                "phase 11 remediation fixture",
                now,
                expires_at or now + timedelta(minutes=10),
                {},
            )
        )
        return approval_id

    def _register_delegated_fixture(self, approval_ids: list[str]) -> None:
        self._delegated_queue = deque(approval_ids)
        self.runtime.permission.rules = (
            PermissionRule("tool.phase11.delegated", PermissionEffect.ALLOW, "remediation_fixture"),
            *self.runtime.permission.rules,
        )

        async def handler(arguments, context):
            del arguments, context
            return ToolResult(ToolResultStatus.APPROVAL_REQUIRED, approval_id=self._delegated_queue.popleft())

        self.runtime.tools.register(
            ToolSpec(
                "phase11-delegated-v1",
                "phase11.delegated",
                "1",
                "delegated approval lifecycle fixture",
                "safe",
                "tool.request",
                frozenset(),
                10.0,
                False,
                handler,
                parameters_schema={"type": "object", "properties": {}, "additionalProperties": False},
            )
        )

    async def _delegated_batch(self, count: int) -> tuple[list[str], list[object]]:
        approval_ids = [f"approval-remediation-{index}" for index in range(count)]
        for approval_id in approval_ids:
            await self._approval(approval_id)
        self._register_delegated_fixture(approval_ids)
        results = [
            await self.runtime.tool_service.execute("phase11.delegated", {}, self.context)
            for _ in approval_ids
        ]
        return approval_ids, results

    def _expire_approvals(self, approval_ids: list[str]) -> None:
        expired = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        placeholders = ",".join("?" for _ in approval_ids)
        with self.runtime.repository.database.transaction() as db:
            db.execute(
                f"UPDATE approvals SET expires_at = ? WHERE id IN ({placeholders})",
                (expired, *approval_ids),
            )

    async def test_expired_delegated_approvals_prune_and_recover_capacity(self) -> None:
        approval_ids, results = await self._delegated_batch(32)
        self.assertTrue(all(result.status is ToolExecutionStatus.APPROVAL_REQUIRED for result in results))
        self.assertEqual(len(self.runtime.tool_service._delegated_approvals), 32)
        delegated = self.runtime.tool_service._delegated_approvals[approval_ids[0]]
        row = self.runtime.repository.approval(approval_ids[0])
        assert row is not None
        self.assertEqual(delegated.expires_at, datetime.fromisoformat(str(row["expires_at"])))
        self._expire_approvals(approval_ids)
        new_approval = await self._approval("approval-remediation-new")
        # The fixture queue must provide the new canonical approval after the expired batch.
        self._delegated_queue.append(new_approval)
        replacement = await self.runtime.tool_service.execute("phase11.delegated", {}, self.context)
        self.assertEqual(replacement.status, ToolExecutionStatus.APPROVAL_REQUIRED)
        self.assertEqual(replacement.approval_id, new_approval)
        self.assertEqual(len(self.runtime.tool_service._delegated_approvals), 1)
        self.assertTrue(all(approval_id not in self.runtime.tool_service._delegated_approvals for approval_id in approval_ids))
        self.assertTrue(all(self.runtime.repository.approval(approval_id)["status"] == "expired" for approval_id in approval_ids))

    async def test_live_delegated_capacity_is_bounded_without_eviction(self) -> None:
        approval_ids, results = await self._delegated_batch(33)
        self.assertTrue(all(result.status is ToolExecutionStatus.APPROVAL_REQUIRED for result in results[:32]))
        self.assertEqual(results[32].error_code, "delegated_approval_store_full")
        self.assertEqual(len(self.runtime.tool_service._delegated_approvals), 32)
        self.assertEqual(
            set(self.runtime.tool_service._delegated_approvals),
            set(approval_ids[:32]),
        )

    async def test_expired_delegated_paused_run_reconciles(self) -> None:
        session = self.runtime.repository.create_session(self.identity.owner_id, self.device.device_id)
        conversation = self.runtime.repository.create_conversation(self.identity.owner_id, self.device.device_id, None)
        message = self.runtime.repository.create_message(
            conversation.id, session.id, None, self.device.device_id, "user", "prepare the approved action"
        )
        run = self.runtime.repository.create_run(
            conversation.id, session.id, self.device.device_id, message.id, "phase11-remediation-run"
        )
        approval_id = [await self._approval("approval-remediation-run")]
        self._register_delegated_fixture(approval_id)
        result = await self.runtime.tool_service.execute(
            "phase11.delegated", {}, self.context, run_id=run.id
        )
        self.runtime.repository.update_run(run.id, status="paused", pending_approval_id=result.approval_id)
        self._expire_approvals(approval_id)
        removed = await self.runtime.tool_service._prune_delegated_approvals()
        self.assertEqual(removed, 1)
        reconciled = self.runtime.repository.run(run.id)
        assert reconciled is not None
        self.assertEqual(reconciled.status, "failed")
        self.assertEqual(reconciled.failure_code, "approval_expired")
        self.assertIsNone(reconciled.pending_approval_id)
        tool_call = self.runtime.repository.tool_call(result.tool_call_id)
        assert tool_call is not None
        self.assertEqual(tool_call["status"], "failed")
        self.assertIn("approval_expired", str(tool_call["output_json"]))
        self.assertEqual(self.controller.actions, [])

    async def test_domain_pending_capacity_does_not_create_orphan_approval(self) -> None:
        pending = [
            await self.runtime.computer_actions.execute(
                ComputerAction("keyboard_action", {"operation": "type_text", "window_ref": "window-good", "text": f"safe-{index}"}),
                self.identity,
                self.device,
            )
            for index in range(32)
        ]
        self.assertTrue(all(result.status == "approval_required" for result in pending))
        self.assertEqual(len(self.runtime.computer_actions._pending), 32)
        before = self.runtime.repository.database.connection.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]
        overflow = await self.runtime.computer_actions.execute(
            ComputerAction("keyboard_action", {"operation": "type_text", "window_ref": "window-good", "text": "overflow"}),
            self.identity,
            self.device,
        )
        after = self.runtime.repository.database.connection.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]
        self.assertEqual(overflow.status, "failed")
        self.assertEqual(overflow.error_code, "computer_pending_store_full")
        self.assertEqual(before, after)
        self.assertEqual(len(self.runtime.computer_actions._pending), 32)
        self.assertTrue(all(result.approval_id in self.runtime.computer_actions._pending for result in pending))

    async def test_expired_domain_approval_never_executes_and_reports_canonical_code(self) -> None:
        requested = await self.runtime.computer_actions.execute(
            ComputerAction("keyboard_action", {"operation": "type_text", "window_ref": "window-good", "text": "expires"}),
            self.identity,
            self.device,
        )
        assert requested.approval_id is not None
        self._expire_approvals([requested.approval_id])
        expired = await self.runtime.computer_actions.decide(
            requested.approval_id,
            True,
            self.identity.identity_id,
            identity=self.identity,
            device=self.device,
        )
        self.assertEqual(expired.status, "denied")
        self.assertEqual(expired.error_code, "approval_expired")
        self.assertEqual(self.controller.actions, [])
        self.assertNotIn(requested.approval_id, self.runtime.computer_actions._pending)

    async def _prepare_agent_pause(self) -> object:
        self.runtime.agent.models = _TwoStepModel(AGENT_SENTINEL)
        return await self.runtime.agent.process_text(
            "perform the prepared grounded input test",
            self.identity,
            self.device,
        )

    async def test_agent_delegated_approval_rejects_standalone_decision_and_resumes_once(self) -> None:
        paused = await self._prepare_agent_pause()
        self.assertEqual(paused.state.value, "paused")
        assert paused.pending_approval_id is not None
        denied = await self.application.decide_computer_action(
            paused.pending_approval_id,
            True,
            self.identity.identity_id,
            self.identity,
            self.device,
        )
        self.assertEqual(denied["error_code"], "delegated_approval_requires_run_resume")
        self.assertEqual(self.controller.actions, [])
        still_paused = self.runtime.repository.run(paused.run_id)
        assert still_paused is not None
        self.assertEqual(still_paused.status, "paused")
        self.assertIn(paused.pending_approval_id, self.runtime.computer_actions._pending)
        resumed = await self.runtime.agent.resume(
            paused.run_id,
            self.identity,
            self.device,
            self.identity.identity_id,
            approved=True,
        )
        self.assertEqual(resumed.state.value, "succeeded")
        self.assertEqual(len(self.controller.actions), 1)
        self.assertEqual(self.controller.actions[0][0].parameters["text"], AGENT_SENTINEL)
        with self.assertRaisesRegex(ValueError, "not awaiting approval"):
            await self.runtime.agent.resume(
                paused.run_id,
                self.identity,
                self.device,
                self.identity.identity_id,
                approved=True,
            )
        self.assertEqual(len(self.controller.actions), 1)

    async def test_standalone_direct_computer_approval_still_works(self) -> None:
        requested = await self.application.computer_action(
            self.identity,
            self.device,
            "keyboard_action",
            {"operation": "type_text", "window_ref": "window-good", "text": "standalone"},
            dry_run=False,
        )
        self.assertEqual(requested["status"], "approval_required")
        completed = await self.application.decide_computer_action(
            str(requested["approval_id"]),
            True,
            self.identity.identity_id,
            self.identity,
            self.device,
        )
        self.assertEqual(completed["status"], "succeeded")
        self.assertEqual(len(self.controller.actions), 1)

    def _start_http(self) -> None:
        self.server = CoreHttpServer(self.application, port=0)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

    def _http_request(self, path: str, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
        assert self.server is not None
        request = Request(
            f"http://127.0.0.1:{self.server.address[1]}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read().decode("utf-8"))
            finally:
                exc.close()

    async def test_http_phase_eleven_decisions_use_authenticated_principal_attribution(self) -> None:
        self._start_http()
        paused = await self._prepare_agent_pause()
        assert paused.pending_approval_id is not None
        status, resumed = await asyncio.to_thread(
            self._http_request,
            f"/v1/approvals/{paused.pending_approval_id}",
            {
                "credential": self.credential,
                "device_id": self.device.device_id,
                "identity_id": self.identity.identity_id,
                "run_id": paused.run_id,
                "approved": True,
                "decided_by": "forged-client-attribution",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(resumed["state"], "succeeded")
        row = self.runtime.repository.approval(paused.pending_approval_id)
        assert row is not None
        self.assertEqual(row["decided_by"], self.identity.identity_id)

        direct = await self.application.computer_action(
            self.identity,
            self.device,
            "keyboard_action",
            {"operation": "type_text", "window_ref": "window-good", "text": "http-direct"},
            dry_run=False,
        )
        direct_id = str(direct["approval_id"])
        status, completed = await asyncio.to_thread(
            self._http_request,
            f"/v1/computer/approvals/{direct_id}",
            {
                "credential": self.credential,
                "device_id": self.device.device_id,
                "identity_id": self.identity.identity_id,
                "approved": True,
                "decided_by": "forged-client-attribution",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(completed["status"], "succeeded")
        direct_row = self.runtime.repository.approval(direct_id)
        assert direct_row is not None
        self.assertEqual(direct_row["decided_by"], self.identity.identity_id)

    async def test_full_agent_approval_resume_has_no_durable_sentinel_and_is_exactly_once(self) -> None:
        paused = await self._prepare_agent_pause()
        assert paused.pending_approval_id is not None
        self.assertEqual(paused.state.value, "paused")
        self.assertEqual(len(self.runtime.repository.pending_approvals(self.identity.owner_id)), 1)
        self.assertEqual(len(self.controller.actions), 0)
        self.assertNotIn(AGENT_SENTINEL, self._db_text())
        durable_before = self._db_text()
        self.assertNotIn(AGENT_SENTINEL, durable_before)

        resumed = await self.runtime.agent.resume(
            paused.run_id,
            self.identity,
            self.device,
            self.identity.identity_id,
            approved=True,
        )
        self.assertEqual(resumed.state.value, "succeeded")
        self.assertEqual(self.runtime.agent.models.calls, 2)
        self.assertEqual(len(self.controller.actions), 1)
        self.assertEqual(self.controller.actions[0][0].parameters["text"], AGENT_SENTINEL)
        self.assertNotIn(AGENT_SENTINEL, self._db_text())
        self.assertEqual(self.runtime.repository.run(paused.run_id).status, "succeeded")


if __name__ == "__main__":
    unittest.main()
