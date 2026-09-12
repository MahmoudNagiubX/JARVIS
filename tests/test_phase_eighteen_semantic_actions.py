"""Milestone 3 (Phase 18 Workstream A, Batch 01): bounded semantic UI actions
(invoke/toggle/select) through the canonical approval path.

No real `uiautomation`/Windows dependency is used - a fake
SemanticDesktopAdapter is injected at the WindowsNativeComputerController
boundary. These tests prove the approval/architecture contract; pattern-level
verification correctness (toggle/select state checks, stale/ambiguous
re-resolution) is already covered in test_phase_eighteen_semantic_uia.py.
"""

from __future__ import annotations

import unittest

from jarvis.authority.identity.service import EnrollmentGrant
from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.contracts import ComputerAction, ToolContext
from jarvis.contracts.semantic_ui import SemanticResult


class _FakeActingAdapter:
    """Deterministic stand-in for WindowsUIAutomationAdapter's actuation methods."""

    def __init__(self) -> None:
        self.available = True
        self.invoke_calls: list[str] = []
        self.toggle_calls: list[str] = []
        self.select_calls: list[str] = []

    async def list_windows(self, device_id: str) -> SemanticResult:
        return SemanticResult("succeeded", {"windows": ()})

    async def inspect_window(self, window_ref: str, *, depth: int) -> SemanticResult:
        return SemanticResult("failed", error_code="uia_element_not_found")

    async def find_elements(self, window_ref: str, **_kwargs: object) -> SemanticResult:
        return SemanticResult("succeeded", {"matches": (), "ambiguous": False})

    async def get_element(self, element_ref: str) -> SemanticResult:
        return SemanticResult("failed", error_code="uia_element_not_found")

    async def get_text_or_value(self, element_ref: str) -> SemanticResult:
        return SemanticResult("failed", error_code="uia_element_not_found")

    async def revalidate_reference(self, element_ref: str) -> SemanticResult:
        return SemanticResult("failed", {"state": "not_found"}, "uia_element_not_found")

    async def invoke(self, element_ref: str) -> SemanticResult:
        self.invoke_calls.append(element_ref)
        if element_ref == "element-unsupported":
            return SemanticResult("failed", error_code="uia_pattern_unsupported")
        if element_ref == "element-password":
            return SemanticResult("denied", error_code="uia_sensitive_value_denied")
        return SemanticResult("succeeded", {"element": _fake_snapshot(element_ref), "verified": False})

    async def toggle(self, element_ref: str) -> SemanticResult:
        self.toggle_calls.append(element_ref)
        changed = element_ref != "element-stuck-toggle"
        return SemanticResult(
            "succeeded",
            {
                "element": _fake_snapshot(element_ref),
                "verified": changed,
                "toggle_state_before": 0,
                "toggle_state_after": 1 if changed else 0,
            },
        )

    async def select(self, element_ref: str) -> SemanticResult:
        self.select_calls.append(element_ref)
        return SemanticResult("succeeded", {"element": _fake_snapshot(element_ref), "verified": True})


def _fake_snapshot(element_ref: str):
    from jarvis.contracts.semantic_ui import SemanticElementSnapshot

    return SemanticElementSnapshot(
        element_ref, "window-1", "Target", "ButtonControl", "targetButton",
        True, False, False, True, None, ("Invoke", "Toggle", "SelectionItem"), None, None,
    )


class SemanticActionsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        self.identity = await self.runtime.identity.bootstrap_owner("Phase Eighteen Actions Owner")
        enrollment = await self.runtime.identity.create_enrollment(
            EnrollmentGrant(
                self.identity.owner_id, "Phase Eighteen Actions Device", "desktop", "windows",
                ("tool.request",), ("computer.observe", "computer.input"),
            )
        )
        issued = await self.runtime.identity.redeem_enrollment(enrollment.code)
        self.device = await self.runtime.identity.authenticate(issued.raw, issued.device_id)
        assert self.device is not None
        self.fake_adapter = _FakeActingAdapter()
        self.runtime.computer_actions.controller.local.semantic_adapter = self.fake_adapter

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    def _context(self) -> ToolContext:
        session = self.runtime.repository.create_session(self.identity.owner_id, self.device.device_id)
        return ToolContext(self.identity, self.device, session.id, "correlation-semantic-act")

    # -- permission / approval --

    async def test_invoke_requires_canonical_approval(self) -> None:
        result = await self.runtime.tool_service.execute(
            "computer.semantic.act", {"action": "invoke", "element_ref": "element-1"}, self._context()
        )
        self.assertEqual(result.status.value, "approval_required")
        self.assertEqual(self.fake_adapter.invoke_calls, [])  # no actuation before approval

    async def test_toggle_and_select_also_require_approval(self) -> None:
        for action in ("toggle", "select"):
            result = await self.runtime.tool_service.execute(
                "computer.semantic.act", {"action": action, "element_ref": "element-1"}, self._context()
            )
            self.assertEqual(result.status.value, "approval_required")
        self.assertEqual(self.fake_adapter.toggle_calls, [])
        self.assertEqual(self.fake_adapter.select_calls, [])

    async def test_approved_invoke_executes_exactly_once_on_repeated_decide(self) -> None:
        context = self._context()
        requested = await self.runtime.tool_service.execute(
            "computer.semantic.act", {"action": "invoke", "element_ref": "element-1"}, context
        )
        self.assertEqual(requested.status.value, "approval_required")
        assert requested.approval_id is not None

        first = await self.runtime.tool_service.decide_and_resume(requested.approval_id, True, self.identity.identity_id, context)
        self.assertEqual(first.status.value, "completed")
        self.assertEqual(self.fake_adapter.invoke_calls, ["element-1"])

        # A second decide on the same (already-consumed) approval must not act again -
        # ephemeral argument retention (matching keyboard.type/window.control) means
        # the pending arguments were already consumed, so this hits the existing
        # typed ephemeral_arguments_unavailable failure rather than re-executing.
        second = await self.runtime.tool_service.decide_and_resume(requested.approval_id, True, self.identity.identity_id, context)
        self.assertEqual(second.status.value, "failed")
        self.assertEqual(second.error_code, "ephemeral_arguments_unavailable")
        self.assertEqual(self.fake_adapter.invoke_calls, ["element-1"])  # still exactly one call

    async def test_denied_approval_never_acts(self) -> None:
        context = self._context()
        requested = await self.runtime.tool_service.execute(
            "computer.semantic.act", {"action": "invoke", "element_ref": "element-1"}, context
        )
        assert requested.approval_id is not None
        result = await self.runtime.tool_service.decide_and_resume(requested.approval_id, False, self.identity.identity_id, context)
        self.assertEqual(result.status.value, "denied")
        self.assertEqual(self.fake_adapter.invoke_calls, [])

    async def test_stale_pending_action_cannot_execute(self) -> None:
        # Direct ComputerActionService.decide on an approval_id that was never
        # requested (simulating a restart-lost / stale pending entry) must fail
        # typed, not act - mirrors the Phase 18A.2 F18A1-007 fix, exercised here
        # for the new semantic actuation actions specifically.
        result = await self.runtime.computer_actions.decide("approval-never-existed", True, self.identity.identity_id)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "pending_action_unavailable_after_restart")
        self.assertEqual(self.fake_adapter.invoke_calls, [])

    # -- pattern safety / verification, exercised end-to-end through the approval path --

    async def test_invoke_unsupported_pattern_typed_failure_after_approval(self) -> None:
        context = self._context()
        raw = await self.runtime.computer_actions.execute(
            ComputerAction("semantic_invoke", {"element_ref": "element-unsupported"}, False), self.identity, self.device,
        )
        self.assertEqual(raw.status, "approval_required")
        assert raw.approval_id is not None
        decided = await self.runtime.computer_actions.decide(raw.approval_id, True, self.identity.identity_id)
        self.assertEqual(decided.status, "failed")
        self.assertEqual(decided.error_code, "uia_pattern_unsupported")

    async def test_invoke_on_password_control_denied_after_approval(self) -> None:
        raw = await self.runtime.computer_actions.execute(
            ComputerAction("semantic_invoke", {"element_ref": "element-password"}, False), self.identity, self.device,
        )
        self.assertEqual(raw.status, "approval_required")
        assert raw.approval_id is not None
        decided = await self.runtime.computer_actions.decide(raw.approval_id, True, self.identity.identity_id)
        self.assertEqual(decided.status, "denied")
        self.assertEqual(decided.error_code, "uia_sensitive_value_denied")

    async def test_toggle_verified_true_end_to_end(self) -> None:
        raw = await self.runtime.computer_actions.execute(
            ComputerAction("semantic_toggle", {"element_ref": "element-toggle-ok"}, False), self.identity, self.device,
        )
        assert raw.approval_id is not None
        decided = await self.runtime.computer_actions.decide(raw.approval_id, True, self.identity.identity_id)
        self.assertEqual(decided.status, "succeeded")
        self.assertTrue(decided.verified)

    async def test_toggle_verified_false_end_to_end(self) -> None:
        raw = await self.runtime.computer_actions.execute(
            ComputerAction("semantic_toggle", {"element_ref": "element-stuck-toggle"}, False), self.identity, self.device,
        )
        assert raw.approval_id is not None
        decided = await self.runtime.computer_actions.decide(raw.approval_id, True, self.identity.identity_id)
        self.assertEqual(decided.status, "succeeded")
        self.assertFalse(decided.verified)

    async def test_select_verified_end_to_end(self) -> None:
        raw = await self.runtime.computer_actions.execute(
            ComputerAction("semantic_select", {"element_ref": "element-item"}, False), self.identity, self.device,
        )
        assert raw.approval_id is not None
        decided = await self.runtime.computer_actions.decide(raw.approval_id, True, self.identity.identity_id)
        self.assertEqual(decided.status, "succeeded")
        self.assertTrue(decided.verified)

    async def test_invoke_generic_action_never_verified_true(self) -> None:
        raw = await self.runtime.computer_actions.execute(
            ComputerAction("semantic_invoke", {"element_ref": "element-plain"}, False), self.identity, self.device,
        )
        assert raw.approval_id is not None
        decided = await self.runtime.computer_actions.decide(raw.approval_id, True, self.identity.identity_id)
        self.assertEqual(decided.status, "succeeded")
        self.assertFalse(decided.verified)

    # -- architecture --

    async def test_action_travels_through_computer_action_service_with_audit(self) -> None:
        context = self._context()
        requested = await self.runtime.tool_service.execute(
            "computer.semantic.act", {"action": "invoke", "element_ref": "element-1"}, context
        )
        assert requested.approval_id is not None
        await self.runtime.tool_service.decide_and_resume(requested.approval_id, True, self.identity.identity_id, context)
        event_types = {row["event_type"] for row in self.runtime.repository.audit(context.correlation_id)}
        self.assertIn("computer.permission_checked", event_types)

        approval_events = [row for row in self.runtime.repository.events() if row["event_type"] == "computer.action_completed"]
        self.assertTrue(approval_events)

    async def test_no_filesystem_action_introduced(self) -> None:
        spec = self.runtime.tools.get("computer.semantic.act")
        assert spec is not None
        properties = set(spec.parameters_schema.get("properties", {}))
        self.assertFalse(properties & {"path", "root", "pattern", "file", "folder", "value", "text"})


if __name__ == "__main__":
    unittest.main()
