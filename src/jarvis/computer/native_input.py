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
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

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


def _mouse_input(dx: int, dy: int, flags: int) -> _INPUT:
    return _INPUT(0, _INPUT_UNION(mi=_MOUSEINPUT(dx, dy, 0, flags, 0, None)))


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
})


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
        target, error = await self._ground(element_ref)
        if target is None:
            return NativeInputResult(_status_for(error), {}, error)
        accepted, verified, evidence = self._move_pointer(target)
        if not accepted:
            return NativeInputResult("failed", evidence, "native_input_injection_failed", verified=False)
        return NativeInputResult("succeeded", evidence, verified=verified)

    async def left_click_element(self, element_ref: str) -> NativeInputResult:
        if not self.available:
            return NativeInputResult("failed", {}, "native_input_unavailable")
        target, error = await self._ground(element_ref)
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
        try:
            hwnd = self.window_provider.validate_input_window(window_ref)
        except ValueError as exc:
            return NativeInputResult("denied" if str(exc) == "sensitive_window_denied" else "failed", {}, str(exc) or "uia_window_stale")
        if not self.window_provider.focus_window(window_ref):
            return NativeInputResult("failed", {}, "window_focus_not_verified")
        if not self.window_provider.is_foreground(hwnd):
            return NativeInputResult("failed", {}, "window_focus_not_verified")
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
            key_inputs = (key_input(vk, 0), key_input(vk, 0x0002))
            sent = self._send_input(key_inputs)
            if sent != len(key_inputs):
                return NativeInputResult("failed", {}, "native_input_injection_failed")
        finally:
            # JARVIS-generated modifiers are always released, even on failure
            # (7.5) - guaranteed cleanup, never left physically "held".
            for modifier_vk in reversed(pressed_modifiers):
                self._send_input((key_input(modifier_vk, 0x0002),))
        target_window_foreground = self.window_provider.is_foreground(hwnd)
        return NativeInputResult(
            "succeeded",
            {"key": key, "modifiers": list(normalized_modifiers), "target_window_foreground": target_window_foreground},
            verified=False,
        )


def _status_for(error: str | None) -> str:
    if error in _DENIED_ERROR_CODES:
        return "denied"
    return "failed"
