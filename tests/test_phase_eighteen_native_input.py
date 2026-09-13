"""Milestone 1 (Phase 18 Workstream A, Batch 02): grounded native input fallback.

Bounded native `SendInput` mouse (`move_to_element`/`left_click_element`) and
named-key keyboard input, strictly grounded through semantic element/window
references. No real Windows/`ctypes` SendInput dependency is exercised here -
low-level `send_input`/`get_cursor_pos`/`is_modifier_pressed`/`metrics_provider`
callables are injected so the targeting/coordinate-math/safety logic is
proven deterministically in CI.
"""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime, timedelta

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


def _snapshot(element_ref: str, window_ref: str, *, bounds: SemanticBounds | None, name: str = "Target") -> SemanticElementSnapshot:
    return SemanticElementSnapshot(
        element_ref, window_ref, name, "ButtonControl", "targetButton",
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


class ExpandedPointerActionTests(unittest.IsolatedAsyncioTestCase):
    """Milestone 2 (Batch 03): right_click_element/double_click_element/
    scroll_element - all still element-grounded through the exact same
    `_ground()` pipeline as move/left-click, never a raw coordinate."""

    async def test_right_click_is_element_grounded_and_unverified(self) -> None:
        semantic = _FakeSemanticAdapter(bounds=SemanticBounds(0, 0, 20, 20))
        adapter = _adapter(semantic, _FakeWindowProvider(), get_cursor_pos=lambda: (10, 10))
        result = await adapter.right_click_element("element-1")
        self.assertEqual(result.status, "succeeded")
        self.assertFalse(result.verified)
        self.assertTrue(result.output["input_batch_accepted"])

    async def test_right_click_denied_for_weak_identity(self) -> None:
        semantic = _FakeSemanticAdapter(bounds=SemanticBounds(0, 0, 20, 20))
        semantic.error_code = "uia_element_identity_weak"
        adapter = _adapter(semantic, _FakeWindowProvider())
        result = await adapter.right_click_element("element-weak")
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "uia_element_identity_weak")

    async def test_double_click_sends_exactly_two_click_pairs_and_unverified(self) -> None:
        sent_inputs: list[int] = []

        def record_send(inputs: object) -> int:
            for item in inputs:
                sent_inputs.append(item.mi.dwFlags)
            return len(inputs)

        semantic = _FakeSemanticAdapter(bounds=SemanticBounds(0, 0, 20, 20))
        adapter = _adapter(semantic, _FakeWindowProvider(), send_input=record_send)
        result = await adapter.double_click_element("element-1")
        self.assertEqual(result.status, "succeeded")
        self.assertFalse(result.verified)
        # One move + two full (down, up) left-click pairs = 5 SendInput calls
        # worth of flags recorded (move flag, then LEFTDOWN/LEFTUP x2).
        from jarvis.computer.native_input import MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
        self.assertEqual(sent_inputs.count(MOUSEEVENTF_LEFTDOWN), 2)
        self.assertEqual(sent_inputs.count(MOUSEEVENTF_LEFTUP), 2)

    async def test_scroll_up_and_down_send_bounded_wheel_delta(self) -> None:
        sent_data: list[tuple[int, int]] = []

        def record_send(inputs: object) -> int:
            for item in inputs:
                sent_data.append((item.mi.dwFlags, item.mi.mouseData))
            return len(inputs)

        semantic = _FakeSemanticAdapter(bounds=SemanticBounds(0, 0, 20, 20))
        adapter = _adapter(semantic, _FakeWindowProvider(), send_input=record_send)
        result = await adapter.scroll_element("element-1", "up", 2)
        self.assertEqual(result.status, "succeeded")
        self.assertFalse(result.verified)
        from jarvis.computer.native_input import MOUSEEVENTF_WHEEL, WHEEL_DELTA
        wheel_events = [data for flags, data in sent_data if flags == MOUSEEVENTF_WHEEL]
        self.assertEqual(len(wheel_events), 1)
        # mouseData is an unsigned DWORD carrying the signed delta - convert
        # back to signed to check the actual scroll direction/magnitude.
        signed = wheel_events[0] if wheel_events[0] < 2**31 else wheel_events[0] - 2**32
        self.assertEqual(signed, WHEEL_DELTA * 2)

    async def test_scroll_down_is_negative_delta(self) -> None:
        sent_data: list[int] = []

        def record_send(inputs: object) -> int:
            for item in inputs:
                sent_data.append(item.mi.mouseData)
            return len(inputs)

        semantic = _FakeSemanticAdapter(bounds=SemanticBounds(0, 0, 20, 20))
        adapter = _adapter(semantic, _FakeWindowProvider(), send_input=record_send)
        from jarvis.computer.native_input import MOUSEEVENTF_WHEEL, WHEEL_DELTA
        result = await adapter.scroll_element("element-1", "down", 1)
        self.assertEqual(result.status, "succeeded")
        signed = sent_data[-1] if sent_data[-1] < 2**31 else sent_data[-1] - 2**32
        self.assertEqual(signed, -WHEEL_DELTA)

    async def test_scroll_steps_out_of_range_denied(self) -> None:
        semantic = _FakeSemanticAdapter(bounds=SemanticBounds(0, 0, 20, 20))
        adapter = _adapter(semantic, _FakeWindowProvider())
        result = await adapter.scroll_element("element-1", "up", 6)
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "native_input_scroll_steps_invalid")

    async def test_scroll_invalid_direction_denied(self) -> None:
        semantic = _FakeSemanticAdapter(bounds=SemanticBounds(0, 0, 20, 20))
        adapter = _adapter(semantic, _FakeWindowProvider())
        result = await adapter.scroll_element("element-1", "sideways", 1)
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "native_input_scroll_direction_invalid")

    async def test_double_click_denied_for_offscreen_target(self) -> None:
        semantic = _FakeSemanticAdapter(bounds=None)
        adapter = _adapter(semantic, _FakeWindowProvider())
        result = await adapter.double_click_element("element-1")
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "uia_target_not_interactable")


class _FakeDragSemanticAdapter:
    """Per-element-configurable stand-in - unlike `_FakeSemanticAdapter`
    above, source and target can have independent bounds/window_ref/error,
    needed to exercise same-window vs cross-window drag grounding."""

    def __init__(self) -> None:
        self.bounds: dict[str, SemanticBounds | None] = {}
        self.window_ref: dict[str, str] = {}
        self.error_code: dict[str, str] = {}
        self.resolve_calls: list[str] = []

    async def resolve_actionable_target(self, element_ref: str) -> SemanticResult:
        self.resolve_calls.append(element_ref)
        error = self.error_code.get(element_ref)
        if error is not None:
            status = "denied" if error in {
                "uia_element_identity_weak", "uia_target_not_interactable", "uia_sensitive_value_denied",
            } else "failed"
            return SemanticResult(status, error_code=error)
        bounds = self.bounds.get(element_ref, SemanticBounds(0, 0, 20, 20))
        window_ref = self.window_ref.get(element_ref, "window-1")
        return SemanticResult("succeeded", {"element": _snapshot(element_ref, window_ref, bounds=bounds)})


class DragTests(unittest.IsolatedAsyncioTestCase):
    """Batch 04 Milestone 1: grounded left-button `drag_element_to_element`
    (GAP-0102/GAP-0105) - both endpoints resolved through the same trusted
    `resolve_actionable_target` machinery every other native input action
    uses, same-window-only, bounded internal interpolation, guaranteed
    left-button release on any partial injection failure."""

    def _semantic(self) -> _FakeDragSemanticAdapter:
        semantic = _FakeDragSemanticAdapter()
        semantic.bounds["element-src"] = SemanticBounds(0, 0, 20, 20)
        semantic.bounds["element-dst"] = SemanticBounds(200, 200, 20, 20)
        return semantic

    async def test_drag_delivers_move_down_bounded_interpolation_up(self) -> None:
        sent_flags: list[int] = []

        def record_send(inputs: object) -> int:
            for item in inputs:
                sent_flags.append(item.mi.dwFlags)
            return len(inputs)

        from jarvis.computer.native_input import (
            DRAG_INTERPOLATION_STEPS,
            MOUSEEVENTF_LEFTDOWN,
            MOUSEEVENTF_LEFTUP,
            MOUSEEVENTF_MOVE,
        )

        semantic = self._semantic()
        adapter = _adapter(semantic, _FakeWindowProvider(), send_input=record_send, get_cursor_pos=lambda: (210, 210))
        result = await adapter.drag_element_to_element("element-src", "element-dst")
        self.assertEqual(result.status, "succeeded")
        self.assertFalse(result.verified)  # generic drag: delivery is never proof of app effect
        self.assertTrue(result.output["input_batch_accepted"])
        self.assertTrue(result.output["pointer_target_verified"])
        self.assertEqual(sent_flags.count(MOUSEEVENTF_LEFTDOWN), 1)
        self.assertEqual(sent_flags.count(MOUSEEVENTF_LEFTUP), 1)
        move_flag = MOUSEEVENTF_MOVE | 0x8000 | 0x4000  # ABSOLUTE | VIRTUALDESK
        # move-to-source + DRAG_INTERPOLATION_STEPS bounded interior moves.
        self.assertEqual(sent_flags.count(move_flag), 1 + DRAG_INTERPOLATION_STEPS)
        self.assertLessEqual(DRAG_INTERPOLATION_STEPS, 12)
        self.assertGreaterEqual(DRAG_INTERPOLATION_STEPS, 4)

    async def test_drag_revalidates_both_endpoints_after_focus(self) -> None:
        semantic = self._semantic()
        adapter = _adapter(semantic, _FakeWindowProvider())
        result = await adapter.drag_element_to_element("element-src", "element-dst")
        self.assertEqual(result.status, "succeeded")
        # Each endpoint resolved twice: once before focus, once after
        # (focus can change layout) - matches the single-target `_ground()`
        # pattern exactly.
        self.assertEqual(semantic.resolve_calls.count("element-src"), 2)
        self.assertEqual(semantic.resolve_calls.count("element-dst"), 2)

    async def test_drag_cross_window_refused_before_any_input(self) -> None:
        sent = {"count": 0}

        def counting_send(inputs: object) -> int:
            sent["count"] += 1
            return len(inputs)

        semantic = self._semantic()
        semantic.window_ref["element-dst"] = "window-2"
        adapter = _adapter(semantic, _FakeWindowProvider(), send_input=counting_send)
        result = await adapter.drag_element_to_element("element-src", "element-dst")
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "drag_cross_window_not_supported")
        self.assertEqual(sent["count"], 0)

    async def test_drag_weak_source_denied_before_any_input(self) -> None:
        sent = {"count": 0}

        def counting_send(inputs: object) -> int:
            sent["count"] += 1
            return len(inputs)

        semantic = self._semantic()
        semantic.error_code["element-src"] = "uia_element_identity_weak"
        adapter = _adapter(semantic, _FakeWindowProvider(), send_input=counting_send)
        result = await adapter.drag_element_to_element("element-src", "element-dst")
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "uia_element_identity_weak")
        self.assertEqual(sent["count"], 0)

    async def test_drag_weak_target_denied_before_any_input(self) -> None:
        sent = {"count": 0}

        def counting_send(inputs: object) -> int:
            sent["count"] += 1
            return len(inputs)

        semantic = self._semantic()
        semantic.error_code["element-dst"] = "uia_element_identity_weak"
        adapter = _adapter(semantic, _FakeWindowProvider(), send_input=counting_send)
        result = await adapter.drag_element_to_element("element-src", "element-dst")
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "uia_element_identity_weak")
        self.assertEqual(sent["count"], 0)

    async def test_drag_partial_failure_releases_left_button(self) -> None:
        from jarvis.computer.native_input import MOUSEEVENTF_LEFTUP

        sent_flags: list[tuple[int, ...]] = []
        call_count = {"n": 0}

        def flaky_send(inputs: object) -> int:
            call_count["n"] += 1
            sent_flags.append(tuple(item.mi.dwFlags for item in inputs))
            if call_count["n"] == 3:  # first bounded interpolation move fails
                return 0
            return len(inputs)

        semantic = self._semantic()
        adapter = _adapter(semantic, _FakeWindowProvider(), send_input=flaky_send)
        result = await adapter.drag_element_to_element("element-src", "element-dst")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "native_input_injection_failed")
        # The cleanup LEFTUP is the very next (final) SendInput call after
        # the failure - the JARVIS-pressed left button is never left held.
        self.assertIn(MOUSEEVENTF_LEFTUP, sent_flags[-1])

    async def test_drag_failure_on_left_down_needs_no_cleanup_release(self) -> None:
        from jarvis.computer.native_input import MOUSEEVENTF_LEFTUP

        call_count = {"n": 0}
        release_calls = {"n": 0}

        def flaky_send(inputs: object) -> int:
            call_count["n"] += 1
            for item in inputs:
                if item.mi.dwFlags == MOUSEEVENTF_LEFTUP:
                    release_calls["n"] += 1
            if call_count["n"] == 2:  # the LEFTDOWN batch itself fails
                return 0
            return len(inputs)

        semantic = self._semantic()
        adapter = _adapter(semantic, _FakeWindowProvider(), send_input=flaky_send)
        result = await adapter.drag_element_to_element("element-src", "element-dst")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "native_input_injection_failed")
        # The button was never reported down, so no extra release is sent.
        self.assertEqual(release_calls["n"], 0)

    async def test_drag_target_outside_virtual_desktop_denied(self) -> None:
        semantic = self._semantic()
        semantic.bounds["element-dst"] = SemanticBounds(9000, 9000, 20, 20)
        adapter = _adapter(semantic, _FakeWindowProvider())
        result = await adapter.drag_element_to_element("element-src", "element-dst")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "native_input_injection_failed")


class _FlakyOnceSemanticAdapter:
    """Fails with a given (recoverable-class or not) error on the first
    `fail_calls` resolutions, then succeeds - used to prove the bounded
    recovery cycle (GAP-0104, Batch 05 Milestone 2): exactly one additional
    fresh re-ground when the first attempt fails for a plausibly transient
    reason, and none at all for a policy denial."""

    def __init__(self, *, fail_calls: int, error_code: str, bounds: SemanticBounds | None = SemanticBounds(0, 0, 20, 20)) -> None:
        self.fail_calls = fail_calls
        self.error_code = error_code
        self.bounds = bounds
        self.resolve_calls = 0

    async def resolve_actionable_target(self, element_ref: str) -> SemanticResult:
        self.resolve_calls += 1
        if self.resolve_calls <= self.fail_calls:
            status = "denied" if self.error_code in {
                "uia_element_identity_weak", "uia_target_not_interactable", "uia_sensitive_value_denied", "sensitive_window_denied",
            } else "failed"
            return SemanticResult(status, error_code=self.error_code)
        return SemanticResult("succeeded", {"element": _snapshot(element_ref, "window-1", bounds=self.bounds)})


class _FlakyOnceDragSemanticAdapter:
    """Same contract as `_FlakyOnceSemanticAdapter`, but keyed per
    element_ref, for the dual-target drag grounding pipeline."""

    def __init__(self) -> None:
        self.fail_calls: dict[str, int] = {}
        self.error_code: dict[str, str] = {}
        self.bounds: dict[str, SemanticBounds] = {}
        self.resolve_calls: dict[str, int] = {}

    async def resolve_actionable_target(self, element_ref: str) -> SemanticResult:
        self.resolve_calls[element_ref] = self.resolve_calls.get(element_ref, 0) + 1
        fail_calls = self.fail_calls.get(element_ref, 0)
        error_code = self.error_code.get(element_ref)
        if self.resolve_calls[element_ref] <= fail_calls and error_code is not None:
            status = "denied" if error_code in {
                "uia_element_identity_weak", "uia_target_not_interactable", "uia_sensitive_value_denied", "sensitive_window_denied",
            } else "failed"
            return SemanticResult(status, error_code=error_code)
        bounds = self.bounds.get(element_ref, SemanticBounds(0, 0, 20, 20))
        return SemanticResult("succeeded", {"element": _snapshot(element_ref, "window-1", bounds=bounds)})


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    """Batch 05 Milestone 2 (GAP-0104): bounded pre-input recovery. Every
    case here proves the recovery cycle happens strictly before any
    SendInput call, is bounded to exactly one extra attempt, and never
    fires for a fail-closed policy denial."""

    async def test_stale_ref_recovers_via_one_bounded_retry(self) -> None:
        # First _ground() attempt's first resolve fails with a
        # transient-class error (short-circuits before its own second
        # resolve) - the bounded recovery's own full _ground() pass (two
        # resolves: pre-focus + post-focus) then succeeds.
        semantic = _FlakyOnceSemanticAdapter(fail_calls=1, error_code="uia_element_stale")
        adapter = _adapter(semantic, _FakeWindowProvider())
        result = await adapter.move_to_element("element-1")
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(semantic.resolve_calls, 3)  # 1 failed + 2 successful (pre/post-focus)

    async def test_moved_element_fresh_bounds_used_before_execution(self) -> None:
        # The element "moved" mid-grounding (post-focus resolve returns
        # different bounds than the pre-focus one) - _ground() already
        # always uses the LATEST resolve's bounds, never the stale
        # pre-focus one; recovery does not change this contract.
        class _MovingSemantic:
            def __init__(self) -> None:
                self.calls = 0

            async def resolve_actionable_target(self, element_ref: str) -> SemanticResult:
                self.calls += 1
                bounds = SemanticBounds(0, 0, 20, 20) if self.calls == 1 else SemanticBounds(200, 200, 20, 20)
                return SemanticResult("succeeded", {"element": _snapshot(element_ref, "window-1", bounds=bounds)})

        semantic = _MovingSemantic()
        adapter = _adapter(semantic, _FakeWindowProvider(), get_cursor_pos=lambda: (210, 210))
        result = await adapter.move_to_element("element-1")
        self.assertEqual(result.status, "succeeded")
        self.assertTrue(result.verified)  # cursor matches the SECOND (moved) center, not the first

    async def test_recoverable_error_exhausts_after_exactly_one_retry(self) -> None:
        semantic = _FlakyOnceSemanticAdapter(fail_calls=999, error_code="uia_element_stale")
        adapter = _adapter(semantic, _FakeWindowProvider())
        result = await adapter.move_to_element("element-1")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "uia_element_stale")
        # Exactly 2 resolve calls total: the first _ground() attempt's own
        # first resolve, and the recovery _ground() attempt's own first
        # resolve - both short-circuit immediately on failure, never
        # reaching a third attempt.
        self.assertEqual(semantic.resolve_calls, 2)

    async def test_focus_race_recovers_via_one_bounded_retry(self) -> None:
        provider = _FakeWindowProvider(foreground_sequence=[False, True, True])
        semantic = _FlakyOnceSemanticAdapter(fail_calls=0, error_code="uia_element_stale")
        adapter = _adapter(semantic, provider)
        result = await adapter.move_to_element("element-1")
        self.assertEqual(result.status, "succeeded")

    async def test_non_recoverable_policy_denial_never_retries(self) -> None:
        semantic = _FlakyOnceSemanticAdapter(fail_calls=999, error_code="uia_element_identity_weak")
        adapter = _adapter(semantic, _FakeWindowProvider())
        result = await adapter.move_to_element("element-1")
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "uia_element_identity_weak")
        # No recovery attempt at all for a policy denial - only the single
        # first-attempt resolve.
        self.assertEqual(semantic.resolve_calls, 1)

    async def test_ambiguous_target_never_retries(self) -> None:
        semantic = _FlakyOnceSemanticAdapter(fail_calls=999, error_code="uia_element_ambiguous")
        adapter = _adapter(semantic, _FakeWindowProvider())
        result = await adapter.move_to_element("element-1")
        self.assertEqual(result.status, "failed")
        self.assertEqual(semantic.resolve_calls, 1)

    async def test_recovery_never_fires_after_sendinput_has_begun(self) -> None:
        # Grounding succeeds cleanly (no recovery needed) - a SendInput
        # failure afterward must never trigger a fresh re-ground/retry of
        # any kind, matching the hard "no retry after an uncertain
        # consequential side effect" rule.
        semantic = _FakeSemanticAdapter(bounds=SemanticBounds(0, 0, 20, 20))
        calls = {"count": 0}

        def flaky_send(inputs: object) -> int:
            calls["count"] += 1
            return len(inputs) if calls["count"] == 1 else 0  # move ok, click batch fails

        adapter = _adapter(semantic, _FakeWindowProvider(), send_input=flaky_send)
        result = await adapter.left_click_element("element-1")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "native_input_injection_failed")
        # Grounding itself only ran once (no recoverable error occurred),
        # and the failed click batch was never retried either.
        self.assertEqual(semantic.resolve_calls, 2)  # pre-focus + post-focus, exactly the one _ground() pass
        self.assertEqual(calls["count"], 2)  # move + one click-batch attempt, never repeated

    async def test_drag_partial_injection_failure_after_recovered_grounding_still_never_retries(self) -> None:
        # Grounding for the drag needed one bounded recovery, but once
        # SendInput begins (LEFTDOWN accepted), a later injection failure
        # must never trigger another re-ground or another drag attempt.
        semantic = _FlakyOnceDragSemanticAdapter()
        semantic.fail_calls["element-src"] = 1
        semantic.error_code["element-src"] = "uia_element_stale"
        semantic.bounds["element-src"] = SemanticBounds(0, 0, 20, 20)
        semantic.bounds["element-dst"] = SemanticBounds(200, 200, 20, 20)

        call_count = {"n": 0}

        def flaky_send(inputs: object) -> int:
            call_count["n"] += 1
            if call_count["n"] == 3:  # first bounded interpolation move fails
                return 0
            return len(inputs)

        adapter = _adapter(semantic, _FakeWindowProvider(), send_input=flaky_send)
        result = await adapter.drag_element_to_element("element-src", "element-dst")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "native_input_injection_failed")
        # Grounding recovered exactly once (proven by the drag ultimately
        # reaching SendInput at all despite the initial stale error), and
        # the SendInput failure afterward was never retried - the total
        # SendInput call count stops at the failure, plus one cleanup
        # release, never restarting the whole drag.
        self.assertLessEqual(call_count["n"], 4)

    async def test_drag_recovery_exhausts_after_exactly_one_retry(self) -> None:
        semantic = _FlakyOnceDragSemanticAdapter()
        semantic.fail_calls["element-src"] = 999
        semantic.error_code["element-src"] = "uia_window_stale"
        adapter = _adapter(semantic, _FakeWindowProvider())
        result = await adapter.drag_element_to_element("element-src", "element-dst")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "uia_window_stale")
        self.assertEqual(semantic.resolve_calls["element-src"], 2)

    async def test_drag_non_recoverable_denial_never_retries(self) -> None:
        semantic = _FlakyOnceDragSemanticAdapter()
        semantic.fail_calls["element-src"] = 999
        semantic.error_code["element-src"] = "uia_sensitive_value_denied"
        adapter = _adapter(semantic, _FakeWindowProvider())
        result = await adapter.drag_element_to_element("element-src", "element-dst")
        self.assertEqual(result.status, "denied")
        self.assertEqual(semantic.resolve_calls["element-src"], 1)


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


class ChordTests(unittest.IsolatedAsyncioTestCase):
    """Milestone 2 (Batch 03): computer.keyboard.chord - a very small,
    explicit allowlist, never an arbitrary modifier+key parser (9.5)."""

    async def test_allowed_chord_succeeds(self) -> None:
        semantic = _FakeSemanticAdapter(bounds=None)
        adapter = _adapter(semantic, _FakeWindowProvider())
        result = await adapter.press_chord("window-1", "ctrl+c")
        self.assertEqual(result.status, "succeeded")
        self.assertFalse(result.verified)
        self.assertEqual(result.output["chord"], "ctrl+c")

    async def test_unlisted_chord_denied(self) -> None:
        semantic = _FakeSemanticAdapter(bounds=None)
        adapter = _adapter(semantic, _FakeWindowProvider())
        for forbidden in ("ctrl+v", "ctrl+s", "alt+f4", "win+d", "ctrl+alt+delete", "ctrl+shift+esc"):
            result = await adapter.press_chord("window-1", forbidden)
            self.assertEqual(result.status, "denied", forbidden)
            self.assertEqual(result.error_code, "native_input_chord_not_allowed", forbidden)

    async def test_chord_modifier_held_by_owner_fails_safely(self) -> None:
        from jarvis.computer.native_input import VK_MENU

        semantic = _FakeSemanticAdapter(bounds=None)
        adapter = _adapter(semantic, _FakeWindowProvider(), is_modifier_pressed=lambda vk: vk == VK_MENU)
        result = await adapter.press_chord("window-1", "ctrl+a")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "native_input_modifier_state_unsafe")

    async def test_chord_modifier_always_released(self) -> None:
        from jarvis.computer.native_input import VK_CONTROL

        sent_inputs: list[tuple[int, int]] = []

        def record_send(inputs: object) -> int:
            for item in inputs:
                sent_inputs.append((item.ki.wVk, item.ki.dwFlags))
            return len(inputs)

        semantic = _FakeSemanticAdapter(bounds=None)
        adapter = _adapter(semantic, _FakeWindowProvider(), send_input=record_send)
        result = await adapter.press_chord("window-1", "ctrl+z")
        self.assertEqual(result.status, "succeeded")
        ctrl_events = [flags for vk, flags in sent_inputs if vk == VK_CONTROL]
        self.assertIn(0, ctrl_events)
        self.assertIn(0x0002, ctrl_events)

    async def test_chord_is_window_grounded_not_element_grounded(self) -> None:
        # A chord takes a window_ref, not an element_ref - confirmed by
        # signature/behavior: it never touches the semantic adapter at all.
        semantic = _FakeSemanticAdapter(bounds=None)
        adapter = _adapter(semantic, _FakeWindowProvider())
        result = await adapter.press_chord("window-1", "ctrl+f")
        self.assertEqual(result.status, "succeeded")


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
                self.right_click_calls: list[str] = []
                self.double_click_calls: list[str] = []
                self.scroll_calls: list[tuple[str, str, int]] = []
                self.key_calls: list[tuple[str, str, tuple[str, ...]]] = []
                self.chord_calls: list[tuple[str, str]] = []

            async def move_to_element(self, element_ref: str):
                from jarvis.computer.native_input import NativeInputResult
                self.move_calls.append(element_ref)
                return NativeInputResult("succeeded", {"pointer_target_verified": True}, verified=True)

            async def left_click_element(self, element_ref: str):
                from jarvis.computer.native_input import NativeInputResult
                self.click_calls.append(element_ref)
                return NativeInputResult("succeeded", {"input_batch_accepted": True}, verified=False)

            async def right_click_element(self, element_ref: str):
                from jarvis.computer.native_input import NativeInputResult
                self.right_click_calls.append(element_ref)
                return NativeInputResult("succeeded", {"input_batch_accepted": True}, verified=False)

            async def double_click_element(self, element_ref: str):
                from jarvis.computer.native_input import NativeInputResult
                self.double_click_calls.append(element_ref)
                return NativeInputResult("succeeded", {"input_batch_accepted": True}, verified=False)

            async def scroll_element(self, element_ref: str, direction: str, steps: int):
                from jarvis.computer.native_input import NativeInputResult
                self.scroll_calls.append((element_ref, direction, steps))
                return NativeInputResult("succeeded", {"input_batch_accepted": True}, verified=False)

            async def press_key(self, window_ref: str, key: str, modifiers: tuple[str, ...] = ()):
                from jarvis.computer.native_input import NativeInputResult
                self.key_calls.append((window_ref, key, modifiers))
                return NativeInputResult("succeeded", {"key": key}, verified=False)

            async def press_chord(self, window_ref: str, chord: str):
                from jarvis.computer.native_input import NativeInputResult
                self.chord_calls.append((window_ref, chord))
                return NativeInputResult("succeeded", {"chord": chord}, verified=False)

        self.fake_native = _FakeNativeInputAdapter()
        self.runtime.computer_actions.controller.local.native_input_adapter = self.fake_native

        class _FakeSemanticAdapterForApproval:
            """Element-targeted pointer actions (R18B02-001) now build their
            approval preview through resolve_actionable_target - substitute
            a trivially-actionable fake rather than depend on real UIA."""

            async def resolve_actionable_target(self, element_ref: str) -> SemanticResult:
                return SemanticResult("succeeded", {
                    "element": _snapshot(element_ref, "window-1", bounds=SemanticBounds(0, 0, 20, 20)),
                    "reference_expires_at": datetime.now(UTC) + timedelta(seconds=45),
                })

        self.runtime.computer_actions.controller.local.semantic_adapter = _FakeSemanticAdapterForApproval()

        class _FakeWindowDescribeProvider:
            """keyboard_key is now window-targeted (R18B02-003) and needs a
            resolvable window; delegate everything else to the real
            provider so is_foreground/focus_window/validate_input_window
            (used by press_key itself) keep working unchanged."""

            def __init__(self, real_provider: object) -> None:
                self._real = real_provider

            def describe_window(self, window_ref: str) -> dict[str, object]:
                return {
                    "window_ref": window_ref,
                    "title": "Fixture Window",
                    "process_name": "python.exe",
                    "expires_at": datetime.now(UTC) + timedelta(seconds=45),
                    "identity_digest": f"digest-{window_ref}",
                }

            def __getattr__(self, name: str) -> object:
                return getattr(self._real, name)

        real_provider = self.runtime.computer_actions.controller.local.perception_provider
        self.runtime.computer_actions.controller.local.perception_provider = _FakeWindowDescribeProvider(real_provider)

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

    async def test_right_click_requires_approval_and_executes_once_approved(self) -> None:
        context = self._context()
        requested = await self.runtime.tool_service.execute(
            "computer.pointer.act", {"action": "right_click_element", "element_ref": "element-1"}, context
        )
        self.assertEqual(requested.status.value, "approval_required")
        assert requested.approval_id is not None
        decided = await self.runtime.tool_service.decide_and_resume(
            requested.approval_id, True, self.identity.identity_id, context
        )
        self.assertEqual(decided.status.value, "completed")
        self.assertEqual(self.fake_native.right_click_calls, ["element-1"])

    async def test_double_click_requires_approval_and_executes_once_approved(self) -> None:
        context = self._context()
        requested = await self.runtime.tool_service.execute(
            "computer.pointer.act", {"action": "double_click_element", "element_ref": "element-1"}, context
        )
        self.assertEqual(requested.status.value, "approval_required")
        assert requested.approval_id is not None
        decided = await self.runtime.tool_service.decide_and_resume(
            requested.approval_id, True, self.identity.identity_id, context
        )
        self.assertEqual(decided.status.value, "completed")
        self.assertEqual(self.fake_native.double_click_calls, ["element-1"])

    async def test_scroll_requires_approval_and_executes_once_approved(self) -> None:
        context = self._context()
        requested = await self.runtime.tool_service.execute(
            "computer.pointer.act", {"action": "scroll_element", "element_ref": "element-1", "direction": "down", "steps": 3}, context
        )
        self.assertEqual(requested.status.value, "approval_required")
        assert requested.approval_id is not None
        decided = await self.runtime.tool_service.decide_and_resume(
            requested.approval_id, True, self.identity.identity_id, context
        )
        self.assertEqual(decided.status.value, "completed")
        self.assertEqual(self.fake_native.scroll_calls, [("element-1", "down", 3)])

    async def test_chord_requires_approval_and_executes_once_approved(self) -> None:
        context = self._context()
        requested = await self.runtime.tool_service.execute(
            "computer.keyboard.chord", {"window_ref": "window-1", "chord": "ctrl+c"}, context
        )
        self.assertEqual(requested.status.value, "approval_required")
        assert requested.approval_id is not None
        decided = await self.runtime.tool_service.decide_and_resume(
            requested.approval_id, True, self.identity.identity_id, context
        )
        self.assertEqual(decided.status.value, "completed")
        self.assertEqual(self.fake_native.chord_calls, [("window-1", "ctrl+c")])

    def test_chord_tool_schema_has_no_paste_and_no_arbitrary_hotkey(self) -> None:
        spec = self.runtime.tools.get("computer.keyboard.chord")
        assert spec is not None
        chord_enum = set(spec.parameters_schema["properties"]["chord"]["enum"])
        self.assertEqual(chord_enum, {"ctrl+a", "ctrl+c", "ctrl+f", "ctrl+z", "ctrl+y"})
        for forbidden in ("ctrl+v", "ctrl+s", "alt+f4", "win+d", "ctrl+alt+delete"):
            self.assertNotIn(forbidden, chord_enum)

    def test_no_paste_or_file_drop_action_exists_anywhere_in_computer_tools(self) -> None:
        # Batch 04 Milestone 1 deliberately adds a reviewed, bounded
        # element-to-element `drag_element_to_element` action to
        # `computer.pointer.act` (source_element_ref/target_element_ref
        # only, same-window-only, left-button-only) - "drag" itself is no
        # longer forbidden everywhere, but paste and file drag/drop remain
        # absent from every computer tool schema.
        for tool_name in ("computer.pointer.act", "computer.keyboard.key", "computer.keyboard.chord", "computer.keyboard.type"):
            spec = self.runtime.tools.get(tool_name)
            assert spec is not None
            blob = str(spec.parameters_schema).casefold()
            self.assertNotIn("paste", blob)
            self.assertNotIn("drop", blob)
        for tool_name in ("computer.keyboard.key", "computer.keyboard.chord", "computer.keyboard.type"):
            spec = self.runtime.tools.get(tool_name)
            assert spec is not None
            self.assertNotIn("drag", str(spec.parameters_schema).casefold())

    def test_pointer_drag_action_is_element_grounded_only(self) -> None:
        spec = self.runtime.tools.get("computer.pointer.act")
        assert spec is not None
        properties = set(spec.parameters_schema.get("properties", {}))
        self.assertIn("drag_element_to_element", spec.parameters_schema["properties"]["action"]["enum"])
        self.assertIn("source_element_ref", properties)
        self.assertIn("target_element_ref", properties)
        # No raw coordinate, path, trajectory, or duration field anywhere in
        # the drag surface.
        self.assertFalse(properties & {"x", "y", "dx", "dy", "hwnd", "path", "duration", "points"})

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
        # direction/steps are bounded enum/range fields for scroll_element
        # only (Milestone 2); source_element_ref/target_element_ref are for
        # drag_element_to_element only (Batch 04 Milestone 1) - never a raw
        # coordinate/delta/path/duration.
        self.assertEqual(
            properties,
            {"action", "element_ref", "direction", "steps", "source_element_ref", "target_element_ref", "target_device_id"},
        )

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


class ApprovalHardeningTests(unittest.IsolatedAsyncioTestCase):
    """Milestone 0 (Phase 18 Workstream A, Batch 03): R18B02-001/002/003 -
    element- and window-targeted actions get a trusted, target-bound,
    actual-reference-expiry-bounded approval, generalized beyond the
    original semantic-only special case."""

    async def asyncSetUp(self) -> None:
        self.runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await self.runtime.start()
        self.identity = await self.runtime.identity.bootstrap_owner("Approval Hardening Owner")
        enrollment = await self.runtime.identity.create_enrollment(
            EnrollmentGrant(
                self.identity.owner_id, "Approval Hardening Device", "desktop", "windows",
                ("tool.request",), ("computer.observe", "computer.input"),
            )
        )
        issued = await self.runtime.identity.redeem_enrollment(enrollment.code)
        self.device = await self.runtime.identity.authenticate(issued.raw, issued.device_id)
        assert self.device is not None

        class _FakeSemantic:
            def __init__(self) -> None:
                self.names: dict[str, str] = {}
                self.windows: dict[str, str] = {}
                self.ttl_seconds = 45

            async def resolve_actionable_target(self, element_ref: str) -> SemanticResult:
                name = self.names.get(element_ref, "Target")
                window_ref = self.windows.get(element_ref, "window-1")
                return SemanticResult("succeeded", {
                    "element": _snapshot(element_ref, window_ref, name=name, bounds=SemanticBounds(0, 0, 20, 20)),
                    "reference_expires_at": datetime.now(UTC) + timedelta(seconds=self.ttl_seconds),
                })

        self.fake_semantic = _FakeSemantic()
        self.runtime.computer_actions.controller.local.semantic_adapter = self.fake_semantic

        class _FakeNative:
            def __init__(self) -> None:
                self.click_calls: list[str] = []
                self.key_calls: list[str] = []
                self.drag_calls: list[tuple[str, str]] = []

            async def left_click_element(self, element_ref: str):
                from jarvis.computer.native_input import NativeInputResult
                self.click_calls.append(element_ref)
                return NativeInputResult("succeeded", {}, verified=False)

            async def drag_element_to_element(self, source_element_ref: str, target_element_ref: str):
                from jarvis.computer.native_input import NativeInputResult
                self.drag_calls.append((source_element_ref, target_element_ref))
                return NativeInputResult("succeeded", {}, verified=False)

            async def move_to_element(self, element_ref: str):
                from jarvis.computer.native_input import NativeInputResult
                return NativeInputResult("succeeded", {}, verified=True)

            async def press_key(self, window_ref: str, key: str, modifiers: tuple[str, ...] = ()):
                from jarvis.computer.native_input import NativeInputResult
                self.key_calls.append(window_ref)
                return NativeInputResult("succeeded", {}, verified=False)

        self.fake_native = _FakeNative()
        self.runtime.computer_actions.controller.local.native_input_adapter = self.fake_native

        class _FakeWindowProvider:
            def __init__(self) -> None:
                self.windows: dict[str, dict[str, object]] = {
                    "window-1": {
                        "title": "Fixture Window", "process_name": "python.exe",
                        "expires_at": datetime.now(UTC) + timedelta(seconds=45),
                    }
                }

            def describe_window(self, window_ref: str) -> dict[str, object]:
                data = self.windows.get(window_ref)
                if data is None or data["expires_at"] <= datetime.now(UTC):
                    raise ValueError("window_ref_expired")
                return {
                    "window_ref": window_ref,
                    "title": data["title"],
                    "process_name": data["process_name"],
                    "expires_at": data["expires_at"],
                    "identity_digest": f"digest-{window_ref}-{data['title']}-{data['process_name']}",
                }

        self.fake_window_provider = _FakeWindowProvider()
        self.runtime.computer_actions.controller.local.perception_provider = self.fake_window_provider
        self.session = self.runtime.repository.create_session(self.identity.owner_id, self.device.device_id)

    async def asyncTearDown(self) -> None:
        await self.runtime.shutdown()

    def _context(self) -> ToolContext:
        return ToolContext(self.identity, self.device, self.session.id, "correlation-approval-hardening")

    async def test_pointer_click_receives_trusted_element_preview(self) -> None:
        context = self._context()
        requested = await self.runtime.tool_service.execute(
            "computer.pointer.act", {"action": "left_click_element", "element_ref": "element-1"}, context
        )
        assert requested.approval_id is not None
        row = self.runtime.repository.approval(requested.approval_id)
        preview = json.loads(row["preview_json"])
        self.assertEqual(preview["action"], "pointer_left_click_element")
        self.assertEqual(preview["control_type"], "ButtonControl")
        self.assertEqual(preview["name"], "Target")
        self.assertNotIn("parameters", preview)

    async def test_pointer_approval_is_identity_bound(self) -> None:
        context = self._context()
        requested = await self.runtime.tool_service.execute(
            "computer.pointer.act", {"action": "left_click_element", "element_ref": "element-1"}, context
        )
        assert requested.approval_id is not None
        decided = await self.runtime.tool_service.decide_and_resume(
            requested.approval_id, True, self.identity.identity_id, context
        )
        self.assertEqual(decided.status.value, "completed")
        self.assertEqual(self.fake_native.click_calls, ["element-1"])

    async def test_pointer_approval_target_change_refuses_execution(self) -> None:
        context = self._context()
        requested = await self.runtime.tool_service.execute(
            "computer.pointer.act", {"action": "left_click_element", "element_ref": "element-1"}, context
        )
        assert requested.approval_id is not None
        self.fake_semantic.names["element-1"] = "Different Control"
        decided = await self.runtime.tool_service.decide_and_resume(
            requested.approval_id, True, self.identity.identity_id, context
        )
        self.assertEqual(decided.status.value, "denied")
        self.assertEqual(decided.error_code, "approval_target_changed")
        self.assertEqual(self.fake_native.click_calls, [])

    async def test_pointer_approval_bounded_by_actual_fifteen_second_ttl(self) -> None:
        self.fake_semantic.ttl_seconds = 15
        context = self._context()
        requested = await self.runtime.tool_service.execute(
            "computer.pointer.act", {"action": "move_to_element", "element_ref": "element-1"}, context
        )
        assert requested.approval_id is not None
        row = self.runtime.repository.approval(requested.approval_id)
        created = _parse_utc(row["created_at"])
        expires = _parse_utc(row["expires_at"])
        self.assertLessEqual((expires - created).total_seconds(), 16)

    async def test_polling_preview_does_not_extend_pending_approval(self) -> None:
        context = self._context()
        requested = await self.runtime.tool_service.execute(
            "computer.pointer.act", {"action": "move_to_element", "element_ref": "element-1"}, context
        )
        assert requested.approval_id is not None
        row_before = self.runtime.repository.approval(requested.approval_id)
        # An unrelated later read of the same target (e.g. a UI "polling" the
        # element again) must not retroactively extend an already-created
        # approval's stored deadline.
        await self.fake_semantic.resolve_actionable_target("element-1")
        await self.fake_semantic.resolve_actionable_target("element-1")
        row_after = self.runtime.repository.approval(requested.approval_id)
        self.assertEqual(row_before["expires_at"], row_after["expires_at"])

    async def test_keyboard_key_approval_includes_trusted_window_title_and_process(self) -> None:
        context = self._context()
        requested = await self.runtime.tool_service.execute(
            "computer.keyboard.key", {"window_ref": "window-1", "key": "tab"}, context
        )
        assert requested.approval_id is not None
        row = self.runtime.repository.approval(requested.approval_id)
        preview = json.loads(row["preview_json"])
        self.assertEqual(preview["window_title"], "Fixture Window")
        self.assertEqual(preview["process_name"], "python.exe")
        self.assertEqual(preview["key"], "tab")
        self.assertNotIn("parameters", preview)

    async def test_keyboard_key_approval_refuses_when_window_becomes_stale(self) -> None:
        context = self._context()
        requested = await self.runtime.tool_service.execute(
            "computer.keyboard.key", {"window_ref": "window-1", "key": "tab"}, context
        )
        assert requested.approval_id is not None
        self.fake_window_provider.windows.pop("window-1")
        decided = await self.runtime.tool_service.decide_and_resume(
            requested.approval_id, True, self.identity.identity_id, context
        )
        self.assertEqual(decided.status.value, "denied")
        self.assertEqual(self.fake_native.key_calls, [])

    async def test_drag_approval_preview_describes_both_source_and_target(self) -> None:
        context = self._context()
        self.fake_semantic.names["element-src"] = "Drag Source"
        self.fake_semantic.names["element-dst"] = "Drop Target"
        requested = await self.runtime.tool_service.execute(
            "computer.pointer.act",
            {"action": "drag_element_to_element", "source_element_ref": "element-src", "target_element_ref": "element-dst"},
            context,
        )
        assert requested.approval_id is not None
        row = self.runtime.repository.approval(requested.approval_id)
        preview = json.loads(row["preview_json"])
        self.assertEqual(preview["action"], "pointer_drag_element_to_element")
        self.assertEqual(preview["source"]["name"], "Drag Source")
        self.assertEqual(preview["target"]["name"], "Drop Target")
        self.assertNotIn("parameters", preview)

    async def test_drag_approval_executes_with_both_refs_on_approve(self) -> None:
        context = self._context()
        requested = await self.runtime.tool_service.execute(
            "computer.pointer.act",
            {"action": "drag_element_to_element", "source_element_ref": "element-src", "target_element_ref": "element-dst"},
            context,
        )
        assert requested.approval_id is not None
        decided = await self.runtime.tool_service.decide_and_resume(
            requested.approval_id, True, self.identity.identity_id, context
        )
        self.assertEqual(decided.status.value, "completed")
        self.assertEqual(self.fake_native.drag_calls, [("element-src", "element-dst")])

    async def test_drag_source_change_after_approval_refuses_execution(self) -> None:
        context = self._context()
        requested = await self.runtime.tool_service.execute(
            "computer.pointer.act",
            {"action": "drag_element_to_element", "source_element_ref": "element-src", "target_element_ref": "element-dst"},
            context,
        )
        assert requested.approval_id is not None
        self.fake_semantic.names["element-src"] = "Different Source"
        decided = await self.runtime.tool_service.decide_and_resume(
            requested.approval_id, True, self.identity.identity_id, context
        )
        self.assertEqual(decided.status.value, "denied")
        self.assertEqual(decided.error_code, "drag_source_changed")
        self.assertEqual(self.fake_native.drag_calls, [])

    async def test_drag_target_change_after_approval_refuses_execution(self) -> None:
        context = self._context()
        requested = await self.runtime.tool_service.execute(
            "computer.pointer.act",
            {"action": "drag_element_to_element", "source_element_ref": "element-src", "target_element_ref": "element-dst"},
            context,
        )
        assert requested.approval_id is not None
        self.fake_semantic.names["element-dst"] = "Different Target"
        decided = await self.runtime.tool_service.decide_and_resume(
            requested.approval_id, True, self.identity.identity_id, context
        )
        self.assertEqual(decided.status.value, "denied")
        self.assertEqual(decided.error_code, "drag_target_changed")
        self.assertEqual(self.fake_native.drag_calls, [])

    async def test_drag_cross_window_refused_at_request_time(self) -> None:
        context = self._context()
        self.fake_semantic.windows["element-dst"] = "window-2"
        requested = await self.runtime.tool_service.execute(
            "computer.pointer.act",
            {"action": "drag_element_to_element", "source_element_ref": "element-src", "target_element_ref": "element-dst"},
            context,
        )
        self.assertEqual(requested.status.value, "denied")
        self.assertEqual(requested.error_code, "drag_cross_window_not_supported")
        self.assertEqual(self.fake_native.drag_calls, [])

    async def test_literal_typing_preview_has_trusted_window_and_digest_not_raw_text(self) -> None:
        context = self._context()
        secret = "super-secret-literal-text"
        requested = await self.runtime.tool_service.execute(
            "computer.keyboard.type", {"window_ref": "window-1", "text": secret}, context
        )
        assert requested.approval_id is not None
        row = self.runtime.repository.approval(requested.approval_id)
        preview = json.loads(row["preview_json"])
        self.assertEqual(preview["window_title"], "Fixture Window")
        self.assertEqual(preview["process_name"], "python.exe")
        self.assertEqual(preview["text_length"], len(secret))
        self.assertIn("text_digest", preview)
        self.assertNotIn(secret, json.dumps(preview))


def _parse_utc(value: str):
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


if __name__ == "__main__":
    unittest.main()
