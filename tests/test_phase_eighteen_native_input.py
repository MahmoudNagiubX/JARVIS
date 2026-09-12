"""Milestone 1 (Phase 18 Workstream A, Batch 02): grounded native input fallback.

Bounded native `SendInput` mouse (`move_to_element`/`left_click_element`) and
named-key keyboard input, strictly grounded through semantic element/window
references. No real Windows/`ctypes` SendInput dependency is exercised here -
low-level `send_input`/`get_cursor_pos`/`is_modifier_pressed`/`metrics_provider`
callables are injected so the targeting/coordinate-math/safety logic is
proven deterministically in CI.
"""

from __future__ import annotations

import unittest

from jarvis.authority.identity.service import EnrollmentGrant
from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.computer.native_input import (
    NAMED_KEY_VK,
    VK_CONTROL,
    VK_SHIFT,
    WindowsNativeInputAdapter,
    normalize_virtual_desktop_point,
)
from jarvis.contracts import ComputerAction, ToolContext
from jarvis.contracts.semantic_ui import SemanticBounds, SemanticElementSnapshot, SemanticResult


# -- coordinate math (pure function, no adapter needed) --

class CoordinateMathTests(unittest.TestCase):
    def test_primary_monitor_origin(self) -> None:
        result = normalize_virtual_desktop_point(0, 0, vleft=0, vtop=0, vwidth=1920, vheight=1080)
        self.assertEqual(result, (0, 0))

    def test_primary_monitor_far_edge(self) -> None:
        result = normalize_virtual_desktop_point(1919, 1079, vleft=0, vtop=0, vwidth=1920, vheight=1080)
        self.assertEqual(result, (65535, 65535))

    def test_negative_virtual_desktop_origin(self) -> None:
        # A monitor extends to the left of the primary monitor.
        result = normalize_virtual_desktop_point(-1920, 0, vleft=-1920, vtop=0, vwidth=3840, vheight=1080)
        self.assertEqual(result, (0, 0))

    def test_second_monitor_like_coordinate(self) -> None:
        result = normalize_virtual_desktop_point(-960, 540, vleft=-1920, vtop=0, vwidth=3840, vheight=1080)
        self.assertIsNotNone(result)
        norm_x, norm_y = result
        # -960 is the midpoint of the left [-1920, 0) monitor - roughly a
        # quarter of the way across the full 3840-wide virtual desktop.
        self.assertTrue(15000 < norm_x < 18000)
        self.assertTrue(32000 < norm_y < 33500)

    def test_exact_edges_both_axes(self) -> None:
        self.assertEqual(normalize_virtual_desktop_point(10, 20, vleft=10, vtop=20, vwidth=100, vheight=50), (0, 0))
        self.assertEqual(normalize_virtual_desktop_point(109, 69, vleft=10, vtop=20, vwidth=100, vheight=50), (65535, 65535))

    def test_one_pixel_width_and_height_defensive_math(self) -> None:
        # Never divide by zero for a degenerate 1x1 reported virtual desktop.
        result = normalize_virtual_desktop_point(5, 5, vleft=5, vtop=5, vwidth=1, vheight=1)
        self.assertEqual(result, (0, 0))

    def test_zero_area_virtual_desktop_rejected(self) -> None:
        self.assertIsNone(normalize_virtual_desktop_point(0, 0, vleft=0, vtop=0, vwidth=0, vheight=1080))
        self.assertIsNone(normalize_virtual_desktop_point(0, 0, vleft=0, vtop=0, vwidth=1920, vheight=0))

    def test_out_of_bounds_target_rejected(self) -> None:
        self.assertIsNone(normalize_virtual_desktop_point(-1, 0, vleft=0, vtop=0, vwidth=1920, vheight=1080))
        self.assertIsNone(normalize_virtual_desktop_point(1920, 0, vleft=0, vtop=0, vwidth=1920, vheight=1080))
        self.assertIsNone(normalize_virtual_desktop_point(0, -1, vleft=0, vtop=0, vwidth=1920, vheight=1080))
        self.assertIsNone(normalize_virtual_desktop_point(0, 1080, vleft=0, vtop=0, vwidth=1920, vheight=1080))


# -- adapter fakes --

class _FakeWindowProvider:
    def __init__(self, *, hwnd: int = 111, foreground_sequence: list[bool] | None = None) -> None:
        self.hwnd = hwnd
        self._foreground_sequence = list(foreground_sequence) if foreground_sequence is not None else None
        self.focus_calls: list[str] = []
        self.focus_result = True
        self.deny_window = False
        self.validate_calls = 0

    def validate_input_window(self, window_ref: str) -> int:
        self.validate_calls += 1
        if self.deny_window:
            raise ValueError("sensitive_window_denied")
        return self.hwnd

    def focus_window(self, window_ref: str) -> bool:
        self.focus_calls.append(window_ref)
        return self.focus_result

    def is_foreground(self, hwnd: int) -> bool:
        if self._foreground_sequence is not None and self._foreground_sequence:
            return self._foreground_sequence.pop(0)
        return True


def _snapshot(element_ref: str, window_ref: str, *, bounds: SemanticBounds | None) -> SemanticElementSnapshot:
    return SemanticElementSnapshot(
        element_ref, window_ref, "Target", "ButtonControl", "targetButton",
        True, False, False, True, bounds, ("Invoke",), None, None, actionable=True,
    )


class _FakeSemanticAdapter:
    def __init__(self, *, bounds: SemanticBounds | None, window_ref: str = "window-1") -> None:
        self.bounds = bounds
        self.window_ref = window_ref
        self.error_code: str | None = None
        self.resolve_calls = 0

    async def resolve_actionable_target(self, element_ref: str) -> SemanticResult:
        self.resolve_calls += 1
        if self.error_code is not None:
            status = "denied" if self.error_code in {
                "uia_element_identity_weak", "uia_target_not_interactable", "uia_sensitive_value_denied",
            } else "failed"
            return SemanticResult(status, error_code=self.error_code)
        return SemanticResult("succeeded", {"element": _snapshot(element_ref, self.window_ref, bounds=self.bounds)})


def _adapter(
    semantic: _FakeSemanticAdapter, provider: _FakeWindowProvider, **overrides: object
) -> WindowsNativeInputAdapter:
    defaults: dict[str, object] = {
        "metrics_provider": lambda: (0, 0, 1920, 1080),
        "send_input": lambda inputs: len(inputs),
        "get_cursor_pos": lambda: (100, 100),
        "is_modifier_pressed": lambda vk: False,
    }
    defaults.update(overrides)
    return WindowsNativeInputAdapter(provider, semantic, **defaults)  # type: ignore[arg-type]


class MouseTests(unittest.IsolatedAsyncioTestCase):
    async def test_weak_ref_denied(self) -> None:
        semantic = _FakeSemanticAdapter(bounds=SemanticBounds(0, 0, 20, 20))
        semantic.error_code = "uia_element_identity_weak"
        adapter = _adapter(semantic, _FakeWindowProvider())
        result = await adapter.move_to_element("element-weak")
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "uia_element_identity_weak")

    async def test_disabled_denied(self) -> None:
        semantic = _FakeSemanticAdapter(bounds=SemanticBounds(0, 0, 20, 20))
        semantic.error_code = "uia_target_not_interactable"
        adapter = _adapter(semantic, _FakeWindowProvider())
        result = await adapter.move_to_element("element-disabled")
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "uia_target_not_interactable")

    async def test_offscreen_denied(self) -> None:
        semantic = _FakeSemanticAdapter(bounds=None)  # no bounds => offscreen/not-interactable
        adapter = _adapter(semantic, _FakeWindowProvider())
        result = await adapter.move_to_element("element-offscreen")
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "uia_target_not_interactable")

    async def test_stale_denied(self) -> None:
        semantic = _FakeSemanticAdapter(bounds=SemanticBounds(0, 0, 20, 20))
        semantic.error_code = "uia_element_stale"
        adapter = _adapter(semantic, _FakeWindowProvider())
        result = await adapter.move_to_element("element-stale")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "uia_element_stale")

    async def test_containing_window_foreground_verified(self) -> None:
        provider = _FakeWindowProvider()
        provider.focus_result = False
        semantic = _FakeSemanticAdapter(bounds=SemanticBounds(0, 0, 20, 20))
        adapter = _adapter(semantic, provider)
        result = await adapter.move_to_element("element-1")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "window_focus_not_verified")

    async def test_target_revalidated_after_focus(self) -> None:
        semantic = _FakeSemanticAdapter(bounds=SemanticBounds(0, 0, 20, 20))
        adapter = _adapter(semantic, _FakeWindowProvider())
        result = await adapter.move_to_element("element-1")
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(semantic.resolve_calls, 2)  # pre-focus AND post-focus

    async def test_send_input_partial_count_is_failure(self) -> None:
        semantic = _FakeSemanticAdapter(bounds=SemanticBounds(0, 0, 20, 20))
        adapter = _adapter(semantic, _FakeWindowProvider(), send_input=lambda inputs: 0)
        result = await adapter.move_to_element("element-1")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "native_input_injection_failed")

    async def test_pointer_position_mismatch_not_verified(self) -> None:
        semantic = _FakeSemanticAdapter(bounds=SemanticBounds(0, 0, 20, 20))
        adapter = _adapter(semantic, _FakeWindowProvider(), get_cursor_pos=lambda: (9999, 9999))
        result = await adapter.move_to_element("element-1")
        self.assertEqual(result.status, "succeeded")
        self.assertFalse(result.verified)

    async def test_pointer_position_match_is_verified(self) -> None:
        # Element center for bounds(0,0,20,20) is (10, 10).
        semantic = _FakeSemanticAdapter(bounds=SemanticBounds(0, 0, 20, 20))
        adapter = _adapter(semantic, _FakeWindowProvider(), get_cursor_pos=lambda: (10, 10))
        result = await adapter.move_to_element("element-1")
        self.assertEqual(result.status, "succeeded")
        self.assertTrue(result.verified)

    async def test_left_click_never_generically_verified_true(self) -> None:
        semantic = _FakeSemanticAdapter(bounds=SemanticBounds(0, 0, 20, 20))
        adapter = _adapter(semantic, _FakeWindowProvider(), get_cursor_pos=lambda: (10, 10))
        result = await adapter.left_click_element("element-1")
        self.assertEqual(result.status, "succeeded")
        self.assertFalse(result.verified)
        self.assertTrue(result.output["input_batch_accepted"])

    async def test_left_click_input_delivery_failure(self) -> None:
        semantic = _FakeSemanticAdapter(bounds=SemanticBounds(0, 0, 20, 20))
        calls = {"count": 0}

        def flaky_send(inputs: object) -> int:
            calls["count"] += 1
            return len(inputs) if calls["count"] == 1 else 0  # move ok, click batch fails

        adapter = _adapter(semantic, _FakeWindowProvider(), send_input=flaky_send)
        result = await adapter.left_click_element("element-1")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "native_input_injection_failed")

    async def test_target_outside_virtual_desktop_denied(self) -> None:
        # Bounds center lands outside the injected 1920x1080 virtual desktop.
        semantic = _FakeSemanticAdapter(bounds=SemanticBounds(5000, 5000, 20, 20))
        adapter = _adapter(semantic, _FakeWindowProvider())
        result = await adapter.move_to_element("element-1")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "native_input_injection_failed")


class KeyboardTests(unittest.IsolatedAsyncioTestCase):
    async def test_key_allowlist_enforced_unsupported_key_denied(self) -> None:
        semantic = _FakeSemanticAdapter(bounds=None)
        adapter = _adapter(semantic, _FakeWindowProvider())
        result = await adapter.press_key("window-1", "F1")
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "native_input_key_not_allowed")

    async def test_raw_vk_like_string_denied(self) -> None:
        semantic = _FakeSemanticAdapter(bounds=None)
        adapter = _adapter(semantic, _FakeWindowProvider())
        result = await adapter.press_key("window-1", "0x09")
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "native_input_key_not_allowed")

    async def test_unreviewed_modifier_combo_denied(self) -> None:
        semantic = _FakeSemanticAdapter(bounds=None)
        adapter = _adapter(semantic, _FakeWindowProvider())
        # shift+enter is not in the reviewed allowlist (only shift+tab is).
        result = await adapter.press_key("window-1", "enter", ("shift",))
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "native_input_key_not_allowed")

    async def test_plain_named_key_succeeds(self) -> None:
        semantic = _FakeSemanticAdapter(bounds=None)
        adapter = _adapter(semantic, _FakeWindowProvider())
        result = await adapter.press_key("window-1", "tab")
        self.assertEqual(result.status, "succeeded")
        self.assertFalse(result.verified)

    async def test_modifier_currently_held_fails_safely(self) -> None:
        semantic = _FakeSemanticAdapter(bounds=None)
        adapter = _adapter(semantic, _FakeWindowProvider(), is_modifier_pressed=lambda vk: vk == VK_CONTROL)
        result = await adapter.press_key("window-1", "tab")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "native_input_modifier_state_unsafe")

    async def test_jarvis_own_modifier_does_not_trigger_interference_check(self) -> None:
        # Shift is JARVIS's OWN intended modifier for shift+tab - it must not
        # be treated as owner interference.
        semantic = _FakeSemanticAdapter(bounds=None)
        adapter = _adapter(semantic, _FakeWindowProvider(), is_modifier_pressed=lambda vk: vk == VK_SHIFT)
        result = await adapter.press_key("window-1", "tab", ("shift",))
        self.assertEqual(result.status, "succeeded")

    async def test_jarvis_generated_modifier_always_released(self) -> None:
        sent_inputs: list[tuple[int, int]] = []  # (wVk, dwFlags)

        def record_send(inputs: object) -> int:
            for item in inputs:
                sent_inputs.append((item.ki.wVk, item.ki.dwFlags))
            return len(inputs)

        semantic = _FakeSemanticAdapter(bounds=None)
        adapter = _adapter(semantic, _FakeWindowProvider(), send_input=record_send)
        result = await adapter.press_key("window-1", "tab", ("shift",))
        self.assertEqual(result.status, "succeeded")
        # shift down (flags=0) ... shift up (flags=0x0002) must both be present.
        shift_events = [flags for vk, flags in sent_inputs if vk == VK_SHIFT]
        self.assertIn(0, shift_events)
        self.assertIn(0x0002, shift_events)

    async def test_jarvis_generated_modifier_released_even_on_key_injection_failure(self) -> None:
        sent_inputs: list[tuple[int, int]] = []
        calls = {"count": 0}

        def flaky_send(inputs: object) -> int:
            calls["count"] += 1
            for item in inputs:
                sent_inputs.append((item.ki.wVk, item.ki.dwFlags))
            if calls["count"] == 1:
                return len(inputs)  # modifier press succeeds
            if calls["count"] == 2:
                return 0  # key press batch fails
            return len(inputs)  # cleanup release

        semantic = _FakeSemanticAdapter(bounds=None)
        adapter = _adapter(semantic, _FakeWindowProvider(), send_input=flaky_send)
        result = await adapter.press_key("window-1", "tab", ("shift",))
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "native_input_injection_failed")
        shift_events = [flags for vk, flags in sent_inputs if vk == VK_SHIFT]
        self.assertIn(0x0002, shift_events)  # release still happened

    async def test_foreground_change_before_key_press_blocks_injection(self) -> None:
        provider = _FakeWindowProvider(foreground_sequence=[True, False])
        semantic = _FakeSemanticAdapter(bounds=None)
        adapter = _adapter(semantic, provider)
        result = await adapter.press_key("window-1", "tab")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "window_focus_not_verified")

    async def test_send_input_partial_is_failure(self) -> None:
        semantic = _FakeSemanticAdapter(bounds=None)
        adapter = _adapter(semantic, _FakeWindowProvider(), send_input=lambda inputs: 0)
        result = await adapter.press_key("window-1", "tab")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "native_input_injection_failed")


class ArchitectureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        self.identity = await self.runtime.identity.bootstrap_owner("Phase 18 Batch 02 Native Input Owner")
        enrollment = await self.runtime.identity.create_enrollment(
            EnrollmentGrant(
                self.identity.owner_id, "Phase 18 Batch 02 Native Input Device", "desktop", "windows",
                ("tool.request",), ("computer.observe", "computer.input"),
            )
        )
        issued = await self.runtime.identity.redeem_enrollment(enrollment.code)
        self.device = await self.runtime.identity.authenticate(issued.raw, issued.device_id)
        assert self.device is not None

        class _FakeNativeInputAdapter:
            def __init__(self) -> None:
                self.move_calls: list[str] = []
                self.click_calls: list[str] = []
                self.key_calls: list[tuple[str, str, tuple[str, ...]]] = []

            async def move_to_element(self, element_ref: str):
                from jarvis.computer.native_input import NativeInputResult
                self.move_calls.append(element_ref)
                return NativeInputResult("succeeded", {"pointer_target_verified": True}, verified=True)

            async def left_click_element(self, element_ref: str):
                from jarvis.computer.native_input import NativeInputResult
                self.click_calls.append(element_ref)
                return NativeInputResult("succeeded", {"input_batch_accepted": True}, verified=False)

            async def press_key(self, window_ref: str, key: str, modifiers: tuple[str, ...] = ()):
                from jarvis.computer.native_input import NativeInputResult
                self.key_calls.append((window_ref, key, modifiers))
                return NativeInputResult("succeeded", {"key": key}, verified=False)

        self.fake_native = _FakeNativeInputAdapter()
        self.runtime.computer_actions.controller.local.native_input_adapter = self.fake_native

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    def _context(self) -> ToolContext:
        session = self.runtime.repository.create_session(self.identity.owner_id, self.device.device_id)
        return ToolContext(self.identity, self.device, session.id, "correlation-native-input")

    async def test_pointer_move_requires_approval_through_computer_action_service(self) -> None:
        result = await self.runtime.tool_service.execute(
            "computer.pointer.act", {"action": "move_to_element", "element_ref": "element-1"}, self._context()
        )
        self.assertEqual(result.status.value, "approval_required")
        self.assertEqual(self.fake_native.move_calls, [])

    async def test_pointer_click_requires_approval_and_executes_once_approved(self) -> None:
        context = self._context()
        requested = await self.runtime.tool_service.execute(
            "computer.pointer.act", {"action": "left_click_element", "element_ref": "element-1"}, context
        )
        self.assertEqual(requested.status.value, "approval_required")
        assert requested.approval_id is not None
        decided = await self.runtime.tool_service.decide_and_resume(
            requested.approval_id, True, self.identity.identity_id, context
        )
        self.assertEqual(decided.status.value, "completed")
        self.assertFalse(decided.verified)
        self.assertEqual(self.fake_native.click_calls, ["element-1"])

    async def test_keyboard_key_requires_approval_and_executes_once_approved(self) -> None:
        context = self._context()
        requested = await self.runtime.tool_service.execute(
            "computer.keyboard.key", {"window_ref": "window-1", "key": "tab"}, context
        )
        self.assertEqual(requested.status.value, "approval_required")
        assert requested.approval_id is not None
        decided = await self.runtime.tool_service.decide_and_resume(
            requested.approval_id, True, self.identity.identity_id, context
        )
        self.assertEqual(decided.status.value, "completed")
        self.assertEqual(self.fake_native.key_calls, [("window-1", "tab", ())])

    async def test_audit_and_permission_events_recorded(self) -> None:
        context = self._context()
        requested = await self.runtime.tool_service.execute(
            "computer.pointer.act", {"action": "move_to_element", "element_ref": "element-1"}, context
        )
        assert requested.approval_id is not None
        await self.runtime.tool_service.decide_and_resume(requested.approval_id, True, self.identity.identity_id, context)
        event_types = {row["event_type"] for row in self.runtime.repository.audit(context.correlation_id)}
        self.assertIn("computer.permission_checked", event_types)
        completed = [row for row in self.runtime.repository.events() if row["event_type"] == "computer.action_completed"]
        self.assertTrue(completed)

    def test_pointer_tool_schema_has_no_raw_coordinates_or_filesystem_fields(self) -> None:
        spec = self.runtime.tools.get("computer.pointer.act")
        assert spec is not None
        properties = set(spec.parameters_schema.get("properties", {}))
        self.assertFalse(properties & {"x", "y", "hwnd", "path", "root", "pattern", "file", "folder", "vk", "flags"})
        self.assertEqual(properties, {"action", "element_ref", "target_device_id"})

    def test_keyboard_key_tool_schema_has_no_raw_vk_or_filesystem_fields(self) -> None:
        spec = self.runtime.tools.get("computer.keyboard.key")
        assert spec is not None
        properties = set(spec.parameters_schema.get("properties", {}))
        self.assertFalse(properties & {"x", "y", "hwnd", "path", "root", "pattern", "file", "folder", "vk", "code", "flags"})
        key_schema = spec.parameters_schema["properties"]["key"]
        self.assertEqual(key_schema["type"], "string")
        self.assertIn("enum", key_schema)
        self.assertEqual(set(key_schema["enum"]), set(NAMED_KEY_VK))

    def test_no_filesystem_action_introduced(self) -> None:
        for tool_name in ("computer.pointer.act", "computer.keyboard.key"):
            spec = self.runtime.tools.get(tool_name)
            assert spec is not None
            properties = set(spec.parameters_schema.get("properties", {}))
            self.assertFalse(properties & {"path", "root", "pattern", "file", "folder", "value", "text"})


if __name__ == "__main__":
    unittest.main()
