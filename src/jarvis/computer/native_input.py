"""Product-owned grounded native Windows input adapter (Computer Use V2, Layer 2).

Adds a small, deliberately bounded native `SendInput` execution surface -
`move_to_element`/`left_click_element` (mouse) and `press_key` (a fixed
named-key allowlist) - as a fallback for when semantic UIA patterns are
unavailable (GAP-0102). This is an execution provider, not an authority: it
sits behind `ComputerActionService`/`WindowsNativeComputerController` exactly
like `WindowsUIAutomationAdapter`, and every action is grounded through an
existing opaque `element_ref`/`window_ref` - the model never supplies x, y,
an HWND, a raw virtual-key code, or raw Win32 flags.

Targeting pipeline (mouse):

    element_ref -> semantic re-validation (strong/actionable, fresh bounds)
    -> containing window privacy/focus/foreground checks
    -> re-validation AGAIN after focus (focus can change layout)
    -> center of the fresh bounds, normalized to the Windows *virtual*
       desktop (SM_XVIRTUALSCREEN/SM_YVIRTUALSCREEN/SM_CXVIRTUALSCREEN/
       SM_CYVIRTUALSCREEN), never the primary monitor alone
    -> SendInput (MOUSEEVENTF_MOVE|ABSOLUTE|VIRTUALDESK[, LEFTDOWN, LEFTUP])
    -> bounded, honest evidence - a generic click is `verified=False` unless
       a separate evaluator independently observes the intended effect.

The re-validation step reuses `SemanticDesktopAdapter.resolve_actionable_target`
(the same fail-closed strong/enabled/onscreen/non-sensitive checks
invoke/toggle/select already perform - R18B01-005) rather than re-deriving
those checks independently, so there is exactly one place that decides
whether a target may be actuated.

Windows `SendInput` is subject to UIPI: JARVIS never elevates, never
requests UIAccess, and never claims "UIPI blocked" unless independently
provable - a partial/zero SendInput count is reported as the generic
`native_input_injection_failed`.
"""

from __future__ import annotations

import ctypes
import platform
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass
from typing import Any

from ..contracts.semantic_ui import SemanticDesktopAdapter
from ..perception.windows import WindowsDesktopProvider

# -- Win32 constants (never exposed to the model) --

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000
WHEEL_DELTA = 120
MAX_SCROLL_STEPS = 5
# Bounded internal pointer-move interpolation for a grounded drag (Batch 04
# Milestone 1) - fixed count within the recommended 4-12 range, no random
# jitter, no "human simulation" timing; the goal is robust input delivery,
# not behavioral imitation. Intermediate points are never exposed to the
# model.
DRAG_INTERPOLATION_STEPS = 8

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LWIN = 0x5B
VK_RWIN = 0x5C

# Bounded, reviewed named-key allowlist. No raw VK integer, no scan code, no
# Windows key, no Ctrl+Alt+Delete, no arbitrary hotkey string (7.6).
NAMED_KEY_VK: dict[str, int] = {
    "tab": 0x09,
    "enter": 0x0D,
    "escape": 0x1B,
    "space": 0x20,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "home": 0x24,
    "end": 0x23,
    "page_up": 0x21,
    "page_down": 0x22,
    "backspace": 0x08,
    "delete": 0x2E,
}

MODIFIER_VK: dict[str, int] = {"shift": VK_SHIFT}

# The only modifier+key combinations this milestone allows - a small,
# explicit, reviewed set, never a general hotkey string (7.6).
_ALLOWED_MODIFIER_COMBOS: frozenset[tuple[tuple[str, ...], str]] = frozenset({
    ((), key) for key in NAMED_KEY_VK
} | {(("shift",), "tab")})

# A very small explicit chord allowlist (9.5) - never an arbitrary
# modifier+key parser. Deliberately excludes paste (Ctrl+V), save (Ctrl+S),
# Alt+F4, any Windows-key combination, and Ctrl+Alt+Delete.
NAMED_CHORDS: dict[str, tuple[int, int]] = {
    "ctrl+a": (VK_CONTROL, ord("A")),
    "ctrl+c": (VK_CONTROL, ord("C")),
    "ctrl+f": (VK_CONTROL, ord("F")),
    "ctrl+z": (VK_CONTROL, ord("Z")),
    "ctrl+y": (VK_CONTROL, ord("Y")),
}

# Physically-held modifiers JARVIS must never try to "correct" (7.5).
_INTERFERING_MODIFIER_VKS: tuple[int, ...] = (VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN)

MOVE_TOLERANCE_PIXELS = 2


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", wintypes.DWORD), ("data", _INPUT_UNION)]


class _POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


def key_input(virtual_key: int, flags: int) -> _INPUT:
    """Shared low-level SendInput primitive - the same structure literal
    keyboard typing (`computer/service.py`) already uses, so native input
    never grows a second, independently-maintained SendInput stack."""
    return _INPUT(1, _INPUT_UNION(ki=_KEYBDINPUT(virtual_key, 0, flags, 0, None)))


def unicode_input(unit: int, flags: int) -> _INPUT:
    return _INPUT(1, _INPUT_UNION(ki=_KEYBDINPUT(0, unit, flags, 0, None)))


def _mouse_input(dx: int, dy: int, flags: int, *, mouse_data: int = 0) -> _INPUT:
    return _INPUT(0, _INPUT_UNION(mi=_MOUSEINPUT(dx, dy, mouse_data & 0xFFFFFFFF, flags, 0, None)))


def normalize_virtual_desktop_point(
    x: int, y: int, *, vleft: int, vtop: int, vwidth: int, vheight: int,
) -> tuple[int, int] | None:
    """Pure coordinate math: map a virtual-desktop pixel to SendInput's
    `0..65535` absolute space (MOUSEEVENTF_ABSOLUTE|VIRTUALDESK), mapping the
    virtual desktop's own top-left/bottom-right corners to 0/65535 exactly.
    Returns None when the point is outside the virtual desktop or the
    reported virtual desktop has no area (defensive - never divide by zero).
    """
    if vwidth <= 0 or vheight <= 0:
        return None
    if x < vleft or x >= vleft + vwidth or y < vtop or y >= vtop + vheight:
        return None
    norm_x = round((x - vleft) * 65535 / max(1, vwidth - 1))
    norm_y = round((y - vtop) * 65535 / max(1, vheight - 1))
    return max(0, min(65535, norm_x)), max(0, min(65535, norm_y))


@dataclass(slots=True)
class NativeInputResult:
    status: str
    output: dict[str, object]
    error_code: str | None = None
    verified: bool = False


@dataclass(slots=True)
class _GroundedTarget:
    hwnd: int
    window_ref: str
    center_x: int
    center_y: int


_DENIED_ERROR_CODES = frozenset({
    "sensitive_window_denied",
    "uia_sensitive_value_denied",
    "uia_element_identity_weak",
    "uia_target_not_interactable",
    "drag_cross_window_not_supported",
})

# Batch 05 Milestone 2 (GAP-0104): errors that plausibly reflect a
# transient, pre-input condition - a stale ref because the target moved/
# re-laid-out, a window ref racing a rebuild, or a momentary focus race -
# rather than a deliberate fail-closed policy denial. Only these are
# eligible for the single bounded recovery cycle below. Deliberately
# EXCLUDES every code in `_DENIED_ERROR_CODES` (weak identity/sensitive/
# not-interactable are policy refusals, not transient failures - retrying
# them cannot change the outcome and would blur "policy remains
# authoritative" into "policy gets bypassed by looping"), and excludes
# `uia_element_ambiguous` (a structural problem a re-observe cannot fix).
_RECOVERABLE_GROUND_ERRORS = frozenset({
    "uia_element_stale",
    "uia_element_not_found",
    "uia_window_stale",
    "window_focus_not_verified",
})


@dataclass(slots=True)
class _RecoveryBudget:
    """Batch 06 (R18B05-003): one bounded recovery attempt per *action*, not
    per grounding call. `drag_element_to_element` grounds the dual-target
    pair twice - once before focus, once again after focus can change
    layout - and each of those two calls used to own its own independent
    one-retry allowance, so a single drag request could consume up to two
    separate recovery cycles. A single `_RecoveryBudget` instance, created
    once per action and threaded through both grounding calls, closes that
    gap: whichever of the two grounding calls hits a recoverable error
    first spends the one allowed retry, and the other call sees `used=True`
    and returns its raw error immediately, no bounded second chance."""

    used: bool = False


def _drag_interpolation_steps(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
    """Fixed, deterministic linear interpolation from `start` to `end` in
    `DRAG_INTERPOLATION_STEPS` bounded points (last point lands exactly on
    `end`). No randomness, no timing exposed - callers only see the final
    delivery evidence, never the intermediate points."""
    steps: list[tuple[int, int]] = []
    for index in range(1, DRAG_INTERPOLATION_STEPS + 1):
        fraction = index / DRAG_INTERPOLATION_STEPS
        x = round(start[0] + (end[0] - start[0]) * fraction)
        y = round(start[1] + (end[1] - start[1]) * fraction)
        steps.append((x, y))
    return steps


class WindowsNativeInputAdapter:
    """Bounded, grounded native mouse/keyboard execution provider.

    Never an authority: it holds no permission/approval logic of its own and
    is only ever reached through `ComputerActionService` ->
    `WindowsNativeComputerController`, exactly like the semantic UIA adapter.
    """

    name = "windows-native-input"

    def __init__(
        self,
        window_provider: WindowsDesktopProvider,
        semantic_adapter: SemanticDesktopAdapter,
        *,
        metrics_provider: Callable[[], tuple[int, int, int, int]] | None = None,
        send_input: Callable[[Any], int] | None = None,
        get_cursor_pos: Callable[[], tuple[int, int]] | None = None,
        is_modifier_pressed: Callable[[int], bool] | None = None,
    ) -> None:
        self.window_provider = window_provider
        self.semantic_adapter = semantic_adapter
        injected = send_input is not None or get_cursor_pos is not None or metrics_provider is not None
        if injected:
            self._metrics_provider = metrics_provider or (lambda: (0, 0, 1920, 1080))
            self._send_input = send_input or (lambda inputs: len(inputs))
            self._get_cursor_pos = get_cursor_pos or (lambda: (0, 0))
            self._is_modifier_pressed = is_modifier_pressed or (lambda vk: False)
            self.available = True
        elif platform.system().casefold() == "windows":
            self._user32 = ctypes.WinDLL("user32.dll", use_last_error=True)
            self._user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
            self._user32.SendInput.restype = wintypes.UINT
            self._user32.GetCursorPos.argtypes = [ctypes.POINTER(_POINT)]
            self._user32.GetCursorPos.restype = wintypes.BOOL
            self._user32.GetSystemMetrics.argtypes = [ctypes.c_int]
            self._user32.GetSystemMetrics.restype = ctypes.c_int
            self._user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
            self._user32.GetAsyncKeyState.restype = wintypes.SHORT
            self._metrics_provider = self._real_metrics
            self._send_input = self._real_send_input
            self._get_cursor_pos = self._real_cursor_pos
            self._is_modifier_pressed = lambda vk: bool(self._user32.GetAsyncKeyState(vk) & 0x8000)
            self.available = True
        else:
            self._metrics_provider = lambda: (0, 0, 0, 0)
            self._send_input = lambda inputs: 0
            self._get_cursor_pos = lambda: (0, 0)
            self._is_modifier_pressed = lambda vk: False
            self.available = False

    def _real_metrics(self) -> tuple[int, int, int, int]:
        return (
            int(self._user32.GetSystemMetrics(SM_XVIRTUALSCREEN)),
            int(self._user32.GetSystemMetrics(SM_YVIRTUALSCREEN)),
            int(self._user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)),
            int(self._user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)),
        )

    def _real_send_input(self, inputs: tuple[_INPUT, ...]) -> int:
        array = (_INPUT * len(inputs))(*inputs)
        return int(self._user32.SendInput(len(array), array, ctypes.sizeof(_INPUT)))

    def _real_cursor_pos(self) -> tuple[int, int]:
        point = _POINT()
        if not self._user32.GetCursorPos(ctypes.byref(point)):
            return (0, 0)
        return (int(point.x), int(point.y))

    # -- mouse --

    async def move_to_element(self, element_ref: str) -> NativeInputResult:
        if not self.available:
            return NativeInputResult("failed", {}, "native_input_unavailable")
        target, error = await self._ground_with_recovery(element_ref)
        if target is None:
            return NativeInputResult(_status_for(error), {}, error)
        accepted, verified, evidence = self._move_pointer(target)
        if not accepted:
            return NativeInputResult("failed", evidence, "native_input_injection_failed", verified=False)
        return NativeInputResult("succeeded", evidence, verified=verified)

    async def left_click_element(self, element_ref: str) -> NativeInputResult:
        if not self.available:
            return NativeInputResult("failed", {}, "native_input_unavailable")
        target, error = await self._ground_with_recovery(element_ref)
        if target is None:
            return NativeInputResult(_status_for(error), {}, error)
        accepted, pointer_verified, evidence = self._move_pointer(target)
        if not accepted:
            return NativeInputResult("failed", evidence, "native_input_injection_failed", verified=False)
        click_inputs = (
            _mouse_input(0, 0, MOUSEEVENTF_LEFTDOWN),
            _mouse_input(0, 0, MOUSEEVENTF_LEFTUP),
        )
        sent = self._send_input(click_inputs)
        input_batch_accepted = sent == len(click_inputs)
        target_window_foreground = self.window_provider.is_foreground(target.hwnd)
        evidence = {
            **evidence,
            "input_batch_accepted": input_batch_accepted,
            "target_window_foreground": target_window_foreground,
        }
        if not input_batch_accepted:
            return NativeInputResult("failed", evidence, "native_input_injection_failed", verified=False)
        # Generic click: SendInput delivery alone never proves the application
        # performed the intended semantic action (7.3.3) - always unverified
        # here; a separate evaluator may independently prove a scenario.
        return NativeInputResult("succeeded", evidence, verified=False)

    async def right_click_element(self, element_ref: str) -> NativeInputResult:
        if not self.available:
            return NativeInputResult("failed", {}, "native_input_unavailable")
        target, error = await self._ground_with_recovery(element_ref)
        if target is None:
            return NativeInputResult(_status_for(error), {}, error)
        accepted, _pointer_verified, evidence = self._move_pointer(target)
        if not accepted:
            return NativeInputResult("failed", evidence, "native_input_injection_failed", verified=False)
        click_inputs = (
            _mouse_input(0, 0, MOUSEEVENTF_RIGHTDOWN),
            _mouse_input(0, 0, MOUSEEVENTF_RIGHTUP),
        )
        sent = self._send_input(click_inputs)
        input_batch_accepted = sent == len(click_inputs)
        evidence = {
            **evidence,
            "input_batch_accepted": input_batch_accepted,
            "target_window_foreground": self.window_provider.is_foreground(target.hwnd),
        }
        if not input_batch_accepted:
            return NativeInputResult("failed", evidence, "native_input_injection_failed", verified=False)
        # Never assumed a context menu opened merely because input was
        # delivered (9.2) - generic right click stays unverified, same
        # honesty rule as left click.
        return NativeInputResult("succeeded", evidence, verified=False)

    async def double_click_element(self, element_ref: str) -> NativeInputResult:
        if not self.available:
            return NativeInputResult("failed", {}, "native_input_unavailable")
        target, error = await self._ground_with_recovery(element_ref)
        if target is None:
            return NativeInputResult(_status_for(error), {}, error)
        accepted, _pointer_verified, evidence = self._move_pointer(target)
        if not accepted:
            return NativeInputResult("failed", evidence, "native_input_injection_failed", verified=False)
        # Exactly one bounded double-click sequence - never an arbitrary
        # click count, and no timing is ever exposed to the model (9.3).
        # System double-click timing (GetDoubleClickTime) governs whether
        # Windows itself recognizes this as a double click; the two clicks
        # are still delivered as a single bounded SendInput batch.
        click_inputs = (
            _mouse_input(0, 0, MOUSEEVENTF_LEFTDOWN),
            _mouse_input(0, 0, MOUSEEVENTF_LEFTUP),
            _mouse_input(0, 0, MOUSEEVENTF_LEFTDOWN),
            _mouse_input(0, 0, MOUSEEVENTF_LEFTUP),
        )
        sent = self._send_input(click_inputs)
        input_batch_accepted = sent == len(click_inputs)
        evidence = {
            **evidence,
            "input_batch_accepted": input_batch_accepted,
            "target_window_foreground": self.window_provider.is_foreground(target.hwnd),
        }
        if not input_batch_accepted:
            return NativeInputResult("failed", evidence, "native_input_injection_failed", verified=False)
        return NativeInputResult("succeeded", evidence, verified=False)

    async def scroll_element(self, element_ref: str, direction: str, steps: int) -> NativeInputResult:
        if not self.available:
            return NativeInputResult("failed", {}, "native_input_unavailable")
        if direction not in ("up", "down"):
            return NativeInputResult("denied", {}, "native_input_scroll_direction_invalid")
        if not isinstance(steps, int) or isinstance(steps, bool) or not 1 <= steps <= MAX_SCROLL_STEPS:
            return NativeInputResult("denied", {}, "native_input_scroll_steps_invalid")
        target, error = await self._ground_with_recovery(element_ref)
        if target is None:
            return NativeInputResult(_status_for(error), {}, error)
        accepted, _pointer_verified, evidence = self._move_pointer(target)
        if not accepted:
            return NativeInputResult("failed", evidence, "native_input_injection_failed", verified=False)
        # Bounded signed multiple of WHEEL_DELTA only - never a raw wheel
        # delta from the model (9.4).
        signed_delta = WHEEL_DELTA * steps * (1 if direction == "up" else -1)
        scroll_inputs = (_mouse_input(0, 0, MOUSEEVENTF_WHEEL, mouse_data=signed_delta),)
        sent = self._send_input(scroll_inputs)
        input_batch_accepted = sent == len(scroll_inputs)
        evidence = {
            **evidence,
            "input_batch_accepted": input_batch_accepted,
            "target_window_foreground": self.window_provider.is_foreground(target.hwnd),
        }
        if not input_batch_accepted:
            return NativeInputResult("failed", evidence, "native_input_injection_failed", verified=False)
        # Delivery evidence only - never a generic "content changed" claim
        # (9.4).
        return NativeInputResult("succeeded", evidence, verified=False)

    async def drag_element_to_element(self, source_element_ref: str, target_element_ref: str) -> NativeInputResult:
        """Grounded left-button drag from one previously observed element to
        another (Batch 04 Milestone 1, GAP-0102/GAP-0105). Both endpoints are
        resolved through the same trusted `resolve_actionable_target`
        machinery `_ground()` uses; the two elements must belong to the same
        trusted window - cross-window drag is deliberately deferred
        (`drag_cross_window_not_supported`) as a more consequential,
        harder-to-verify, file-transfer-adjacent scenario reserved for a
        later, separately reviewed batch."""
        if not self.available:
            return NativeInputResult("failed", {}, "native_input_unavailable")
        # Batch 06 (R18B05-003): one shared budget for the whole action -
        # both the pre-focus and post-focus grounding calls below draw from
        # it, so this drag can consume at most one bounded recovery cycle
        # in total, never one per call.
        recovery_budget = _RecoveryBudget()
        source, target, error = await self._ground_drag_pair_with_recovery(
            source_element_ref, target_element_ref, recovery_budget,
        )
        if error is not None:
            return NativeInputResult(_status_for(error), {}, error)
        assert source is not None and target is not None
        if not self.window_provider.focus_window(source.window_ref):
            return NativeInputResult("failed", {}, "window_focus_not_verified")
        if not self.window_provider.is_foreground(source.hwnd):
            return NativeInputResult("failed", {}, "window_focus_not_verified")
        # Focus can change layout - re-resolve BOTH endpoints again after
        # focus, never reuse the pre-focus observation (matches the single-
        # target `_ground()` pattern above). Same shared budget - if the
        # pre-focus call above already consumed it, this call gets no
        # second recovery attempt.
        source, target, error = await self._ground_drag_pair_with_recovery(
            source_element_ref, target_element_ref, recovery_budget,
        )
        if error is not None:
            return NativeInputResult(_status_for(error), {}, error)
        assert source is not None and target is not None
        if not self.window_provider.is_foreground(source.hwnd):
            return NativeInputResult("failed", {}, "window_focus_not_verified")
        return self._execute_drag(source, target)

    async def _ground_drag_pair_with_recovery(
        self, source_element_ref: str, target_element_ref: str, budget: _RecoveryBudget,
    ) -> tuple[_GroundedTarget | None, _GroundedTarget | None, str | None]:
        """Bounded recovery (GAP-0104, Batch 05 Milestone 2; action-scoped
        per R18B05-003, Batch 06): exactly one additional fresh OBSERVE/
        re-ground attempt of the whole dual-target pipeline, across BOTH
        calls this method may receive for a single `drag_element_to_element`
        action - and only when the first attempt failed for a plausibly
        transient, pre-input reason (`_RECOVERABLE_GROUND_ERRORS`) - never
        for a policy denial (weak identity/sensitive/cross-window), never
        more than once per action (`budget.used`), and always entirely
        before any SendInput call. No LLM-managed counter, no second
        authority - `_ground_drag_pair` itself is simply given one more try,
        at most once total, not once per call site."""
        source, target, error = await self._ground_drag_pair(source_element_ref, target_element_ref)
        if source is not None or error not in _RECOVERABLE_GROUND_ERRORS or budget.used:
            return source, target, error
        budget.used = True
        return await self._ground_drag_pair(source_element_ref, target_element_ref)

    async def _ground_drag_pair(
        self, source_element_ref: str, target_element_ref: str,
    ) -> tuple[_GroundedTarget | None, _GroundedTarget | None, str | None]:
        source_raw, source_error = await self._resolve_grounded(source_element_ref)
        if source_raw is None:
            return None, None, source_error
        target_raw, target_error = await self._resolve_grounded(target_element_ref)
        if target_raw is None:
            return None, None, target_error
        if source_raw.window_ref != target_raw.window_ref:
            return None, None, "drag_cross_window_not_supported"
        try:
            hwnd = self.window_provider.validate_input_window(source_raw.window_ref)
        except ValueError as exc:
            return None, None, str(exc) or "uia_window_stale"
        source = _GroundedTarget(hwnd, source_raw.window_ref, source_raw.center_x, source_raw.center_y)
        target = _GroundedTarget(hwnd, target_raw.window_ref, target_raw.center_x, target_raw.center_y)
        return source, target, None

    def _execute_drag(self, source: _GroundedTarget, target: _GroundedTarget) -> NativeInputResult:
        vleft, vtop, vwidth, vheight = self._metrics_provider()
        source_norm = normalize_virtual_desktop_point(source.center_x, source.center_y, vleft=vleft, vtop=vtop, vwidth=vwidth, vheight=vheight)
        target_norm = normalize_virtual_desktop_point(target.center_x, target.center_y, vleft=vleft, vtop=vtop, vwidth=vwidth, vheight=vheight)
        if source_norm is None or target_norm is None:
            return NativeInputResult("failed", {"reason": "target_outside_virtual_desktop"}, "native_input_injection_failed", verified=False)
        left_button_down = False
        try:
            move_to_source = (_mouse_input(source_norm[0], source_norm[1], MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK),)
            if self._send_input(move_to_source) != len(move_to_source):
                return NativeInputResult("failed", {"stage": "move_to_source"}, "native_input_injection_failed", verified=False)
            down_inputs = (_mouse_input(0, 0, MOUSEEVENTF_LEFTDOWN),)
            if self._send_input(down_inputs) != len(down_inputs):
                return NativeInputResult("failed", {"stage": "left_down"}, "native_input_injection_failed", verified=False)
            left_button_down = True
            for step_x, step_y in _drag_interpolation_steps(source_norm, target_norm):
                step_inputs = (_mouse_input(step_x, step_y, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK),)
                if self._send_input(step_inputs) != len(step_inputs):
                    return NativeInputResult("failed", {"stage": "drag_move"}, "native_input_injection_failed", verified=False)
            up_inputs = (_mouse_input(0, 0, MOUSEEVENTF_LEFTUP),)
            if self._send_input(up_inputs) != len(up_inputs):
                return NativeInputResult("failed", {"stage": "left_up"}, "native_input_injection_failed", verified=False)
            left_button_down = False
            cursor_x, cursor_y = self._get_cursor_pos()
            pointer_target_verified = (
                abs(cursor_x - target.center_x) <= MOVE_TOLERANCE_PIXELS
                and abs(cursor_y - target.center_y) <= MOVE_TOLERANCE_PIXELS
            )
            evidence = {
                "input_batch_accepted": True,
                "pointer_target_verified": pointer_target_verified,
                "target_window_foreground": self.window_provider.is_foreground(source.hwnd),
            }
            # Generic drag: SendInput delivery alone never proves the target
            # application performed the intended drag-drop (same honesty
            # rule as the existing generic click/scroll) - always unverified
            # here; only a separate owned-fixture evaluator observing a real
            # postcondition may independently prove a scenario.
            return NativeInputResult("succeeded", evidence, verified=False)
        finally:
            if left_button_down:
                # Guaranteed cleanup on any partial injection failure - never
                # leave the JARVIS-pressed left button physically held.
                self._send_input((_mouse_input(0, 0, MOUSEEVENTF_LEFTUP),))

    def _move_pointer(self, target: _GroundedTarget) -> tuple[bool, bool, dict[str, object]]:
        vleft, vtop, vwidth, vheight = self._metrics_provider()
        normalized = normalize_virtual_desktop_point(
            target.center_x, target.center_y, vleft=vleft, vtop=vtop, vwidth=vwidth, vheight=vheight,
        )
        if normalized is None:
            return False, False, {"reason": "target_outside_virtual_desktop"}
        norm_x, norm_y = normalized
        move_inputs = (_mouse_input(norm_x, norm_y, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK),)
        sent = self._send_input(move_inputs)
        if sent != len(move_inputs):
            return False, False, {"input_batch_accepted": False}
        cursor_x, cursor_y = self._get_cursor_pos()
        pointer_target_verified = (
            abs(cursor_x - target.center_x) <= MOVE_TOLERANCE_PIXELS
            and abs(cursor_y - target.center_y) <= MOVE_TOLERANCE_PIXELS
        )
        return True, pointer_target_verified, {
            "input_batch_accepted": True,
            "pointer_target_verified": pointer_target_verified,
            "target_window_foreground": self.window_provider.is_foreground(target.hwnd),
        }

    async def _ground_with_recovery(self, element_ref: str) -> tuple[_GroundedTarget | None, str | None]:
        """Bounded recovery (GAP-0104, Batch 05 Milestone 2): exactly one
        additional fresh OBSERVE/re-ground attempt, and only when the first
        attempt failed for a plausibly transient, pre-input reason
        (`_RECOVERABLE_GROUND_ERRORS`) - never for a policy denial, never
        more than once, and always entirely before any SendInput call (this
        method only ever returns a target to ground on; the caller sends
        input only after it succeeds - the OBSERVE/GROUND/pre-action-
        failure/re-OBSERVE/re-GROUND cycle happens strictly before ACT).
        No LLM-managed retry counter, no second authority - `_ground()`
        itself is simply given one more try."""
        target, error = await self._ground(element_ref)
        if target is not None or error not in _RECOVERABLE_GROUND_ERRORS:
            return target, error
        return await self._ground(element_ref)

    async def _ground(self, element_ref: str) -> tuple[_GroundedTarget | None, str | None]:
        first, error = await self._resolve_grounded(element_ref)
        if first is None:
            return None, error
        try:
            hwnd = self.window_provider.validate_input_window(first.window_ref)
        except ValueError as exc:
            return None, str(exc) or "uia_window_stale"
        if not self.window_provider.focus_window(first.window_ref):
            return None, "window_focus_not_verified"
        if not self.window_provider.is_foreground(hwnd):
            return None, "window_focus_not_verified"
        # Focus can change layout - revalidate + re-fetch fresh bounds again,
        # never reuse the pre-focus observation (7.3.1).
        second, error = await self._resolve_grounded(element_ref)
        if second is None:
            return None, error
        if not self.window_provider.is_foreground(hwnd):
            return None, "window_focus_not_verified"
        return _GroundedTarget(hwnd, second.window_ref, second.center_x, second.center_y), None

    async def _resolve_grounded(self, element_ref: str) -> tuple[_GroundedTarget | None, str | None]:
        result = await self.semantic_adapter.resolve_actionable_target(element_ref)
        if result.status != "succeeded":
            return None, result.error_code or "uia_element_not_found"
        element = result.output.get("element") if isinstance(result.output, dict) else None
        bounds = getattr(element, "bounds", None) if element is not None else None
        if bounds is None:
            return None, "uia_target_not_interactable"
        center_x = bounds.x + bounds.width // 2
        center_y = bounds.y + bounds.height // 2
        return _GroundedTarget(0, element.window_ref, center_x, center_y), None

    # -- keyboard: bounded named-key input only --

    async def press_key(self, window_ref: str, key: str, modifiers: tuple[str, ...] = ()) -> NativeInputResult:
        if not self.available:
            return NativeInputResult("failed", {}, "native_input_unavailable")
        normalized_modifiers = tuple(sorted(modifiers))
        if (normalized_modifiers, key) not in _ALLOWED_MODIFIER_COMBOS:
            return NativeInputResult("denied", {}, "native_input_key_not_allowed")
        vk = NAMED_KEY_VK.get(key)
        if vk is None:
            return NativeInputResult("denied", {}, "native_input_key_not_allowed")
        modifier_vks = [MODIFIER_VK[name] for name in normalized_modifiers]
        hwnd, ground_failure = self._ground_window(window_ref)
        if hwnd is None:
            return ground_failure
        failure = await self._press_key_sequence(hwnd, vk, modifier_vks)
        if failure is not None:
            return failure
        target_window_foreground = self.window_provider.is_foreground(hwnd)
        return NativeInputResult(
            "succeeded",
            {"key": key, "modifiers": list(normalized_modifiers), "target_window_foreground": target_window_foreground},
            verified=False,
        )

    async def press_chord(self, window_ref: str, chord: str) -> NativeInputResult:
        if not self.available:
            return NativeInputResult("failed", {}, "native_input_unavailable")
        mapping = NAMED_CHORDS.get(chord)
        if mapping is None:
            return NativeInputResult("denied", {}, "native_input_chord_not_allowed")
        modifier_vk, key_vk = mapping
        hwnd, ground_failure = self._ground_window(window_ref)
        if hwnd is None:
            return ground_failure
        failure = await self._press_key_sequence(hwnd, key_vk, [modifier_vk])
        if failure is not None:
            return failure
        target_window_foreground = self.window_provider.is_foreground(hwnd)
        return NativeInputResult("succeeded", {"chord": chord, "target_window_foreground": target_window_foreground}, verified=False)

    def _ground_window(self, window_ref: str) -> tuple[int | None, NativeInputResult | None]:
        try:
            hwnd = self.window_provider.validate_input_window(window_ref)
        except ValueError as exc:
            reason = str(exc) or "uia_window_stale"
            return None, NativeInputResult("denied" if reason == "sensitive_window_denied" else "failed", {}, reason)
        if not self.window_provider.focus_window(window_ref):
            return None, NativeInputResult("failed", {}, "window_focus_not_verified")
        if not self.window_provider.is_foreground(hwnd):
            return None, NativeInputResult("failed", {}, "window_focus_not_verified")
        return hwnd, None

    async def _press_key_sequence(self, hwnd: int, key_vk: int, modifier_vks: list[int]) -> NativeInputResult | None:
        """Shared modifier-press/key-press/guaranteed-release sequence used
        by both `press_key` and `press_chord` - one input-sequencing
        implementation, not two. Returns None on success, or the failure
        `NativeInputResult` to propagate."""
        # Never try to "correct" modifiers the real user is physically
        # holding - fail safely instead (7.5). JARVIS's own intended
        # modifiers (if any) are not owner interference.
        own_modifier_set = set(modifier_vks)
        for candidate_vk in _INTERFERING_MODIFIER_VKS:
            if candidate_vk in own_modifier_set:
                continue
            if self._is_modifier_pressed(candidate_vk):
                return NativeInputResult("failed", {}, "native_input_modifier_state_unsafe")
        pressed_modifiers: list[int] = []
        try:
            for modifier_vk in modifier_vks:
                sent = self._send_input((key_input(modifier_vk, 0),))
                if sent != 1:
                    return NativeInputResult("failed", {"modifiers_pressed": len(pressed_modifiers)}, "native_input_injection_failed")
                pressed_modifiers.append(modifier_vk)
            if not self.window_provider.is_foreground(hwnd):
                return NativeInputResult("failed", {}, "window_focus_not_verified")
            key_inputs = (key_input(key_vk, 0), key_input(key_vk, 0x0002))
            sent = self._send_input(key_inputs)
            if sent != len(key_inputs):
                return NativeInputResult("failed", {}, "native_input_injection_failed")
        finally:
            # JARVIS-generated modifiers are always released, even on failure
            # (7.5) - guaranteed cleanup, never left physically "held".
            for modifier_vk in reversed(pressed_modifiers):
                self._send_input((key_input(modifier_vk, 0x0002),))
        return None


def _status_for(error: str | None) -> str:
    if error in _DENIED_ERROR_CODES:
        return "denied"
    return "failed"
