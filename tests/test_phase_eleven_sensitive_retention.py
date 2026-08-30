from __future__ import annotations

import json
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from jarvis.authority.identity.service import EnrollmentGrant
from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.contracts import ToolContext, ToolResult, ToolResultRetention, ToolResultStatus
from jarvis.tools.registry import ToolSpec
from jarvis.tools.service import ToolExecutionService, ToolExecutionStatus


SECRET = "PHASE11_EPHEMERAL_SENTINEL"


class _RecordingController:
    def __init__(self) -> None:
        self.actions = []

    async def execute(self, action, context):
        self.actions.append((action, context))
        return ToolResult(ToolResultStatus.SUCCEEDED, {"accepted": True}, verified=True)


class PhaseElevenSensitiveRetentionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        self.identity = await self.runtime.identity.bootstrap_owner("Phase Eleven Owner")
        self.device = await self._enroll("Phase Eleven Desktop", {"computer.observe", "computer.input"})
        self.context = ToolContext(self.identity, self.device, "phase11-session", "phase11-correlation")

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    async def _enroll(self, name: str, capabilities: set[str]):
        grant = await self.runtime.identity.create_enrollment(
            EnrollmentGrant(self.identity.owner_id, name, "desktop", "windows", ("tool.request",), tuple(sorted(capabilities)))
        )
        issued = await self.runtime.identity.redeem_enrollment(grant.code)
        device = await self.runtime.identity.authenticate(issued.raw, issued.device_id)
        assert device is not None
        return device

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

    async def test_generic_ephemeral_arguments_are_redacted_and_resume_from_memory(self) -> None:
        observed: list[dict[str, object]] = []

        async def handler(arguments, context):
            del context
            observed.append(dict(arguments))
            return ToolResult(ToolResultStatus.SUCCEEDED, {"ok": True}, verified=True)

        self.runtime.tools.register(ToolSpec(
            "phase11-sensitive-v1", "phase11.sensitive", "1", "bounded sensitive fixture",
            "safe", "tool.request", frozenset(), 10.0, False, handler,
            parameters_schema={"type": "object", "properties": {"text": {"type": "string"}, "target_device_id": {"type": "string"}}, "required": ["text"], "additionalProperties": False},
            argument_retention=ToolResultRetention.EPHEMERAL,
        ))
        pending = await self.runtime.tool_service.execute(
            "phase11.sensitive", {"text": SECRET, "target_device_id": "device-phase11"}, self.context
        )
        self.assertEqual(pending.status, ToolExecutionStatus.APPROVAL_REQUIRED)
        row = self.runtime.repository.tool_call(pending.tool_call_id)
        assert row is not None
        self.assertNotIn(SECRET, str(row["arguments_json"]))
        approval = self.runtime.repository.approval(str(pending.approval_id))
        assert approval is not None
        self.assertNotIn(SECRET, str(approval["preview_json"]))
        self.assertIn("argument_digest", str(approval["preview_json"]))
        self.assertNotIn(SECRET, self._db_text())

        wrong_device = await self._enroll("Wrong Thread Desktop", {"computer.observe", "computer.input"})
        with self.assertRaisesRegex(PermissionError, "approval_device_mismatch"):
            await self.runtime.tool_service.decide_and_resume(
                str(pending.approval_id), True, self.identity.identity_id,
                replace(self.context, device=wrong_device),
            )
        resumed = await self.runtime.tool_service.decide_and_resume(
            str(pending.approval_id), True, self.identity.identity_id, self.context
        )
        self.assertEqual(resumed.status, ToolExecutionStatus.COMPLETED)
        self.assertEqual(observed, [{"text": SECRET, "target_device_id": "device-phase11"}])
        self.assertNotIn(SECRET, self._db_text())

    async def test_restart_loses_ephemeral_arguments_fail_closed(self) -> None:
        async def handler(arguments, context):
            del arguments, context
            return ToolResult(ToolResultStatus.SUCCEEDED, {"ok": True})

        self.runtime.tools.register(ToolSpec(
            "phase11-restart-v1", "phase11.restart", "1", "restart fixture",
            "safe", "tool.request", frozenset(), 10.0, False, handler,
            parameters_schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"], "additionalProperties": False},
            argument_retention=ToolResultRetention.EPHEMERAL,
        ))
        pending = await self.runtime.tool_service.execute("phase11.restart", {"text": SECRET}, self.context)
        replacement = ToolExecutionService(
            self.runtime.repository, self.runtime.event_bus, self.runtime.tools,
            self.runtime.permission, self.runtime.approval, self.runtime.audit,
        )
        failed = await replacement.decide_and_resume(str(pending.approval_id), True, self.identity.identity_id, self.context)
        self.assertEqual(failed.status, ToolExecutionStatus.FAILED)
        self.assertEqual(failed.error_code, "ephemeral_arguments_unavailable")
        self.assertNotIn(SECRET, self._db_text())

    async def test_computer_tool_bridges_one_domain_approval_and_redacts_text(self) -> None:
        fake = _RecordingController()
        self.runtime.computer_actions.controller.local = fake
        pending = await self.runtime.tool_service.execute(
            "computer.clipboard.write", {"text": SECRET}, self.context
        )
        self.assertEqual(pending.status, ToolExecutionStatus.APPROVAL_REQUIRED)
        self.assertEqual(len(self.runtime.repository.database.connection.execute("SELECT id FROM approvals").fetchall()), 1)
        row = self.runtime.repository.tool_call(pending.tool_call_id)
        assert row is not None
        self.assertNotIn(SECRET, str(row["arguments_json"]))
        approval = self.runtime.repository.approval(str(pending.approval_id))
        assert approval is not None
        preview = json.loads(str(approval["preview_json"]))
        self.assertNotIn(SECRET, json.dumps(preview))
        self.assertEqual(preview["action"], "clipboard_write")
        self.assertEqual(preview["text_length"], len(SECRET))
        self.assertIn("parameter_digest", preview)

        completed = await self.runtime.tool_service.decide_and_resume(
            str(pending.approval_id), True, self.identity.identity_id, self.context
        )
        self.assertEqual(completed.status, ToolExecutionStatus.COMPLETED)
        self.assertEqual(len(fake.actions), 1)
        self.assertEqual(fake.actions[0][0].action, "clipboard_write")
        self.assertEqual(fake.actions[0][0].parameters["text"], SECRET)
        self.assertNotIn(SECRET, self._db_text())

    async def test_ephemeral_approval_store_is_bounded_and_cleans_denied_or_expired_entries(self) -> None:
        async def handler(arguments, context):
            del arguments, context
            return ToolResult(ToolResultStatus.SUCCEEDED, {"ok": True})

        self.runtime.tools.register(ToolSpec(
            "phase11-bound-v1", "phase11.bound", "1", "bounded fixture",
            "safe", "tool.request", frozenset(), 10.0, False, handler,
            parameters_schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"], "additionalProperties": False},
            argument_retention=ToolResultRetention.EPHEMERAL,
        ))
        pending = []
        for index in range(32):
            pending.append(await self.runtime.tool_service.execute("phase11.bound", {"text": f"{SECRET}-{index}"}, self.context))
        self.assertEqual(len(self.runtime.tool_service._pending_arguments), 32)
        overflow = await self.runtime.tool_service.execute("phase11.bound", {"text": f"{SECRET}-overflow"}, self.context)
        self.assertEqual(overflow.status, ToolExecutionStatus.FAILED)
        self.assertEqual(overflow.error_code, "ephemeral_argument_store_full")
        denied = await self.runtime.tool_service.decide_and_resume(str(pending[0].approval_id), False, self.identity.identity_id, self.context)
        self.assertEqual(denied.status, ToolExecutionStatus.DENIED)
        self.assertNotIn(str(pending[0].approval_id), self.runtime.tool_service._pending_arguments)

        expired = pending[1]
        self.runtime.tool_service._pending_arguments[str(expired.approval_id)].expires_at = datetime.now(UTC) - timedelta(seconds=1)
        unavailable = await self.runtime.tool_service.decide_and_resume(str(expired.approval_id), True, self.identity.identity_id, self.context)
        self.assertEqual(unavailable.error_code, "ephemeral_arguments_unavailable")
        self.assertNotIn(SECRET, self._db_text())
