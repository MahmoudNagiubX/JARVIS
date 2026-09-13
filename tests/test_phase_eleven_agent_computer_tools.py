from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime, timedelta

from jarvis.agents.runtime.runtime import AgentRuntime
from jarvis.authority.identity.service import EnrollmentGrant
from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.contracts import Identity, LLMMessage, LLMRole, ToolContext, ToolResult, ToolResultRetention, ToolResultStatus
from jarvis.tools.service import ToolCallResult, ToolExecutionStatus


CLIPBOARD_SENTINEL = "PHASE11_CLIPBOARD_OUTPUT_SENTINEL"


class _ToolController:
    def __init__(self) -> None:
        self.actions = []

    async def execute(self, action, context):
        # Internal-only target-descriptor resolution (R18B02-001/003) is a
        # read-only pre-check ComputerActionService performs before/around
        # every element- or window-targeted approval - not itself the
        # "action executed" tests here assert an exact count for.
        if action.action == "resolve_window_target":
            return ToolResult(ToolResultStatus.SUCCEEDED, {
                "window_ref": action.parameters.get("window_ref"),
                "title": "Recording Fixture Window",
                "process_name": "python.exe",
                "expires_at": datetime.now(UTC) + timedelta(minutes=10),
                "identity_digest": f"digest-{action.parameters.get('window_ref')}",
            }, verified=True)
        if action.action == "resolve_element_target":
            return ToolResult(ToolResultStatus.SUCCEEDED, {
                "element": {
                    "element_ref": action.parameters.get("element_ref"), "window_ref": "window-good",
                    "name": "Target", "control_type": "ButtonControl", "automation_id": None, "actionable": True,
                },
                "reference_expires_at": datetime.now(UTC) + timedelta(minutes=10),
            }, verified=True)
        self.actions.append((action, context))
        if action.action == "clipboard_read":
            return ToolResult(ToolResultStatus.SUCCEEDED, {"text": CLIPBOARD_SENTINEL, "length": len(CLIPBOARD_SENTINEL), "digest": "digest", "format": "CF_UNICODETEXT"}, verified=True)
        return ToolResult(ToolResultStatus.SUCCEEDED, {"action": action.action, "parameters": dict(action.parameters)}, verified=False)


class PhaseElevenAgentComputerToolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        self.identity = await self.runtime.identity.bootstrap_owner("Phase Eleven Agent Owner")
        grant = await self.runtime.identity.create_enrollment(
            EnrollmentGrant(self.identity.owner_id, "Phase Eleven Agent Desktop", "desktop", "windows", ("tool.request",), ("computer.observe", "computer.input"))
        )
        issued = await self.runtime.identity.redeem_enrollment(grant.code)
        self.device = await self.runtime.identity.authenticate(issued.raw, issued.device_id)
        assert self.device is not None
        self.context = ToolContext(self.identity, self.device, "agent-session", "agent-correlation")
        self.fake = _ToolController()
        self.runtime.computer_actions.controller.local = self.fake

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    def test_registry_contains_only_narrow_phase_eleven_tools(self) -> None:
        expected = {
            "computer.audio.adjust", "computer.window.control", "computer.clipboard.read",
            "computer.clipboard.write", "computer.keyboard.type",
        }
        actual = {spec.name for spec in self.runtime.tools.list()}
        self.assertTrue(expected.issubset(actual))
        self.assertEqual(self.runtime.tools.get("computer.clipboard.read").retention, ToolResultRetention.EPHEMERAL)
        self.assertEqual(self.runtime.tools.get("computer.clipboard.write").argument_retention, ToolResultRetention.EPHEMERAL)
        self.assertEqual(self.runtime.tools.get("computer.keyboard.type").argument_retention, ToolResultRetention.EPHEMERAL)
        self.assertNotIn("computer.mouse.click", actual)

    async def test_clipboard_read_is_direct_and_ephemeral_to_agent(self) -> None:
        # clipboard_read is classified as a read action
        # (ComputerActionService._read_actions) and completes directly - no
        # approval step (Batch 04 Milestone 1 dogfooding fix: the permission
        # engine's inner check was missing its ALLOW rule and silently
        # required approval for every read, unlike its sibling read
        # actions).
        completed = await self.runtime.tool_service.execute("computer.clipboard.read", {}, self.context)
        self.assertEqual(completed.status, ToolExecutionStatus.COMPLETED)
        self.assertEqual(completed.retention, ToolResultRetention.EPHEMERAL)
        self.assertEqual(completed.output["text"], CLIPBOARD_SENTINEL)
        row = self.runtime.repository.tool_call(completed.tool_call_id)
        assert row is not None
        self.assertNotIn(CLIPBOARD_SENTINEL, str(row["output_json"]))
        events = self.runtime.repository.database.connection.execute("SELECT payload_json FROM events").fetchall()
        audits = self.runtime.repository.database.connection.execute("SELECT metadata_json FROM audit_records").fetchall()
        self.assertNotIn(CLIPBOARD_SENTINEL, json.dumps([tuple(row) for row in events]))
        self.assertNotIn(CLIPBOARD_SENTINEL, json.dumps([tuple(row) for row in audits]))
        context = AgentRuntime._run_context(
            [LLMMessage(LLMRole.TOOL, json.dumps(completed.output))], None, {0: completed}
        )
        self.assertNotIn(CLIPBOARD_SENTINEL, json.dumps(context))
        self.assertEqual(len(self.fake.actions), 1)

    async def test_audio_tool_uses_bounded_change_volume_action(self) -> None:
        result = await self.runtime.tool_service.execute(
            "computer.audio.adjust", {"operation": "volume_up", "steps": 2}, self.context
        )
        self.assertEqual(result.status, ToolExecutionStatus.COMPLETED)
        self.assertEqual(self.fake.actions[0][0].action, "change_volume")
        self.assertEqual(dict(self.fake.actions[0][0].parameters), {"direction": "up", "steps": 2})
        invalid = await self.runtime.tool_service.execute(
            "computer.audio.adjust", {"operation": "volume_up", "steps": 11}, self.context
        )
        self.assertEqual(invalid.error_code, "audio_steps_invalid")

    async def test_approval_bridge_rejects_wrong_owner(self) -> None:
        pending = await self.runtime.tool_service.execute(
            "computer.keyboard.type", {"window_ref": "window-good", "text": "literal"}, self.context
        )
        other = Identity("other-identity", "Other Phase Eleven Owner", "other-owner", frozenset({"owner"}))
        with self.assertRaisesRegex(PermissionError, "approval_owner_mismatch"):
            await self.runtime.tool_service.decide_and_resume(
                str(pending.approval_id), True, other.identity_id, ToolContext(other, self.device, "other", "other")
            )
        self.assertEqual(len(self.fake.actions), 0)

    async def test_delegated_approval_replay_does_not_execute_twice(self) -> None:
        pending = await self.runtime.tool_service.execute(
            "computer.clipboard.write", {"text": "one-shot"}, self.context
        )
        completed = await self.runtime.tool_service.decide_and_resume(
            str(pending.approval_id), True, self.identity.identity_id, self.context
        )
        self.assertEqual(completed.status, ToolExecutionStatus.COMPLETED)
        replay = await self.runtime.tool_service.decide_and_resume(
            str(pending.approval_id), True, self.identity.identity_id, self.context
        )
        self.assertEqual(replay.status, ToolExecutionStatus.FAILED)
        self.assertEqual(replay.error_code, "ephemeral_arguments_unavailable")
        self.assertEqual(len(self.fake.actions), 1)
