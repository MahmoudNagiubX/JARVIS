from __future__ import annotations

import ctypes
import unittest
from datetime import UTC, datetime, timedelta

from jarvis.computer.service import WindowsNativeComputerController
from jarvis.contracts import ComputerAction, ToolContext
from jarvis.perception.windows import WindowsDesktopProvider, _WindowHandle


class _FakeInput:
    def __init__(self, *, clipboard_text: str = "") -> None:
        self.clipboard_text = clipboard_text
        self.sent: list[int] = []
        self.clipboard_open = False
        self.clipboard_value = clipboard_text
        self.allocations: dict[int, ctypes.Array] = {}

    def SendInput(self, count, inputs, size):
        del inputs, size
        self.sent.append(int(count))
        return count

    def OpenClipboard(self, owner):
        del owner
        if self.clipboard_open:
            return 0
        self.clipboard_open = True
        return 1

    def CloseClipboard(self):
        self.clipboard_open = False
        return 1

    def GetClipboardData(self, format_id):
        del format_id
        return 1 if self.clipboard_value is not None else 0

    def EmptyClipboard(self):
        self.clipboard_value = ""
        return 1

    def SetClipboardData(self, format_id, handle):
        del format_id
        allocation = self.allocations.get(int(handle))
        if allocation is not None:
            self.clipboard_value = ctypes.wstring_at(ctypes.addressof(allocation))
        return 1


class _BusyOnceInput(_FakeInput):
    def __init__(self, *, clipboard_text: str = "") -> None:
        super().__init__(clipboard_text=clipboard_text)
        self.open_attempts = 0

    def OpenClipboard(self, owner):
        self.open_attempts += 1
        if self.open_attempts == 1:
            return 0
        return super().OpenClipboard(owner)


class _BinaryInput(_FakeInput):
    def GetClipboardData(self, format_id):
        del format_id
        return 0


class _FakeKernel:
    def __init__(self, user: _FakeInput) -> None:
        self.user = user
        self.buffer = ctypes.create_unicode_buffer(user.clipboard_value or "")
        self.next_handle = 2

    def GlobalLock(self, handle):
        if handle == 1:
            self.buffer = ctypes.create_unicode_buffer(self.user.clipboard_value or "")
            return ctypes.addressof(self.buffer)
        allocation = self.user.allocations.get(int(handle))
        return ctypes.addressof(allocation) if allocation is not None else 0

    def GlobalUnlock(self, handle):
        del handle
        return 1

    def GlobalAlloc(self, flags, size):
        del flags
        handle = self.next_handle
        self.next_handle += 1
        self.user.allocations[handle] = ctypes.create_string_buffer(size)
        return handle

    def GlobalFree(self, handle):
        self.user.allocations.pop(int(handle), None)
        return 0


class _FakeProvider:
    def __init__(self, *, foreground: list[bool] | None = None) -> None:
        self.foreground = list(foreground or [True] * 10)
        self.focused: list[str] = []
        self.windows: dict[str, str] = {}

    def window_action(self, window_ref: str, operation: str) -> bool:
        return window_ref.startswith("window-") and operation in {"minimize", "maximize", "restore"}

    def validate_input_window(self, window_ref: str) -> int:
        if window_ref == "window-sensitive":
            raise ValueError("sensitive_window_denied")
        if window_ref not in {"window-good", "window-stolen"}:
            raise ValueError("window_ref_expired")
        return 100

    def resolve_window_ref(self, window_ref: str) -> int:
        return self.validate_input_window(window_ref)

    def focus_window(self, window_ref: str) -> bool:
        self.focused.append(window_ref)
        return window_ref in {"window-good", "window-stolen"}

    def is_foreground(self, hwnd: int) -> bool:
        del hwnd
        return self.foreground.pop(0) if self.foreground else True


def _controller(provider: _FakeProvider, user: _FakeInput | None = None) -> WindowsNativeComputerController:
    controller = WindowsNativeComputerController.__new__(WindowsNativeComputerController)
    controller.perception_provider = provider
    controller._user32 = user or _FakeInput()
    controller._kernel32 = _FakeKernel(controller._user32)
    return controller


class PhaseElevenWindowsInteractionTests(unittest.TestCase):
    def test_window_reference_store_prunes_expired_and_caps_oldest(self) -> None:
        provider = WindowsDesktopProvider.__new__(WindowsDesktopProvider)
        provider._window_refs = {}
        now = datetime.now(UTC)
        for index in range(1_100):
            provider._window_refs[f"window-{index}"] = _WindowHandle(
                index, index, "fingerprint", "Notepad", now + timedelta(minutes=1)
            )
        provider._window_refs["window-expired"] = _WindowHandle(
            9_999, 9_999, "fingerprint", "Notepad", now - timedelta(seconds=1)
        )
        provider._prune_window_refs(now)
        self.assertLessEqual(len(provider._window_refs), provider.MAX_WINDOW_REFS)
        self.assertNotIn("window-expired", provider._window_refs)
        self.assertNotIn("window-1", provider._window_refs)
        self.assertIn("window-1099", provider._window_refs)

    def test_window_actions_are_allowlisted_and_verified_by_provider(self) -> None:
        controller = _controller(_FakeProvider())
        for operation in ("minimize", "maximize", "restore"):
            result = controller._window_action({"operation": operation, "window_ref": "window-good"})
            self.assertEqual(result.status, "succeeded")
            self.assertTrue(result.verified)
        rejected = controller._window_action({"operation": "close", "window_ref": "window-good"})
        self.assertEqual(rejected.error_code, "window_action_parameters_invalid")
        raw_hwnd = controller._window_action({"operation": "restore", "window_ref": "100"})
        self.assertEqual(raw_hwnd.error_code, "window_action_parameters_invalid")

    def test_clipboard_is_unicode_bounded_and_returns_digest_only_for_writes(self) -> None:
        user = _FakeInput(clipboard_text="JARVIS_PHASE_11_CLIPBOARD_ACCEPTANCE")
        controller = _controller(_FakeProvider(), user)
        read = controller._clipboard_read()
        self.assertEqual(read.status, "succeeded")
        self.assertEqual(read.output["text"], "JARVIS_PHASE_11_CLIPBOARD_ACCEPTANCE")
        self.assertEqual(read.output["format"], "CF_UNICODETEXT")
        write = controller._clipboard_write({"text": "transient"})
        self.assertEqual(write.status, "succeeded")
        self.assertNotIn("text", write.output)
        self.assertEqual(write.output["length"], 9)
        too_large = controller._clipboard_write({"text": "x" * 16_001})
        self.assertEqual(too_large.error_code, "clipboard_text_invalid")
        null = controller._clipboard_write({"text": "bad\x00text"})
        self.assertEqual(null.error_code, "clipboard_text_invalid")

        busy = _BusyOnceInput(clipboard_text="retry")
        retried = _controller(_FakeProvider(), busy)._clipboard_read()
        self.assertEqual(retried.status, "succeeded")
        self.assertEqual(busy.open_attempts, 2)
        unavailable = _controller(_FakeProvider(), _BinaryInput())._clipboard_read()
        self.assertEqual(unavailable.error_code, "clipboard_format_unavailable")

    def test_audio_is_bounded_and_never_fakes_mute_state(self) -> None:
        controller = _controller(_FakeProvider(), _FakeInput())
        up = controller._change_volume({"direction": "up", "steps": 3})
        self.assertEqual(up.status, "succeeded")
        self.assertFalse(up.verified)
        self.assertEqual(controller._user32.sent, [2, 2, 2])
        self.assertEqual(controller._change_volume({"direction": "sideways", "steps": 1}).error_code, "audio_parameters_invalid")
        self.assertEqual(controller._change_volume({"direction": "up", "steps": 11}).error_code, "audio_parameters_invalid")
        self.assertEqual(controller._mute().error_code, "audio_state_unavailable")
        self.assertEqual(controller._unmute().error_code, "audio_state_unavailable")

    def test_keyboard_types_literal_utf16_chunks_and_rechecks_foreground(self) -> None:
        provider = _FakeProvider()
        user = _FakeInput()
        controller = _controller(provider, user)
        text = "A" * 64 + "✓"
        result = controller._keyboard_action({"operation": "type_text", "window_ref": "window-good", "text": text})
        self.assertEqual(result.status, "succeeded")
        self.assertFalse(result.verified)
        self.assertEqual(result.output, {"chars_sent": 65, "window_ref": "window-good"})
        self.assertEqual(user.sent, [128, 2])
        self.assertEqual(provider.focused, ["window-good"])

        stolen = _controller(_FakeProvider(foreground=[True, False]), _FakeInput())
        changed = stolen._keyboard_action({"operation": "type_text", "window_ref": "window-stolen", "text": "no leak"})
        self.assertEqual(changed.error_code, "keyboard_target_changed")
        self.assertEqual(stolen._user32.sent, [])

        unfocused = _controller(_FakeProvider(foreground=[False]), _FakeInput())
        not_verified = unfocused._keyboard_action({"operation": "type_text", "window_ref": "window-good", "text": "no input"})
        self.assertEqual(not_verified.error_code, "window_focus_not_verified")
        self.assertEqual(unfocused._user32.sent, [])

    def test_safe_paste_uses_unicode_typing_without_touching_clipboard(self) -> None:
        provider = _FakeProvider()
        user = _BusyOnceInput(clipboard_text="owner-clipboard-must-not-be-read")
        controller = _controller(provider, user)
        result = controller._paste_text({"window_ref": "window-good", "text": "bounded insertion ✓"})
        self.assertEqual(result.status, "succeeded")
        self.assertFalse(result.verified)
        self.assertEqual(result.output["strategy"], "unicode_typing")
        self.assertEqual(result.output["text_length"], len("bounded insertion ✓"))
        self.assertNotIn("text", result.output)
        self.assertEqual(user.open_attempts, 0)

        invalid = controller._paste_text({"window_ref": "window-good", "text": "bad\x00text"})
        self.assertEqual(invalid.error_code, "paste_text_invalid")

    def test_keyboard_rejects_sensitive_windows_and_invalid_shapes(self) -> None:
        controller = _controller(_FakeProvider())
        sensitive = controller._keyboard_action({"operation": "type_text", "window_ref": "window-sensitive", "text": "literal"})
        self.assertEqual(sensitive.error_code, "sensitive_window_denied")
        invalid = controller._keyboard_action({"operation": "type_text", "window_ref": "window-good", "text": "bad\x00text"})
        self.assertEqual(invalid.error_code, "keyboard_text_invalid")
        extra = controller._keyboard_action({"operation": "type_text", "window_ref": "window-good", "text": "x", "vk": 13})
        self.assertEqual(extra.error_code, "keyboard_action_parameters_invalid")
        self.assertEqual(
            controller._keyboard_action({"operation": "type_text", "window_ref": "window-good", "text": "x" * 2_001}).error_code,
            "keyboard_text_invalid",
        )
