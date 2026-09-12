"""Phase 18 Workstream A Batch 03 - JARVIS-owned native Win32 UIA fixture host.

Evaluation-only. NEVER imported by production JARVIS startup - it is a
standalone process launched only by `scripts/phase18/computer_use_acceptance.py`
(or a developer, by hand) for physical acceptance testing.

Standard Win32 controls (`BUTTON` with `BS_PUSHBUTTON`/`BS_AUTOCHECKBOX`,
`LISTBOX`) are UIA-accessible out of the box through the OS's built-in
default UIA provider - no custom UIA provider implementation is needed here,
and no third-party GUI framework dependency was added solely for this
fixture (stdlib `ctypes` + `user32.dll` only).

The window title always includes a caller-supplied nonce
(`JARVIS-CUV2-FIXTURE-<nonce>`) so a runner can find *exactly* this
instance and never accidentally match an unrelated window.

Usage:
    python scripts/phase18/uia_fixture_host.py --nonce <uuid>

Layout:
    Static:    "JARVIS fixture ready"
    Button:    "Invoke Target"      (BS_PUSHBUTTON  -> Invoke pattern)
    CheckBox:  "Toggle Target"      (BS_AUTOCHECKBOX -> Toggle pattern)
    ListBox:   Alpha / Beta / Gamma (-> SelectionItem pattern on each item)
    Button:    "Second Focusable"   (plain second control for Tab/focus tests)
    Static:    status=idle          (independent read-back target)

Status text updates (and only ever contains these known-safe, JARVIS-authored
strings - never owner data):
    invoked
    toggle:on / toggle:off
    selected:<Alpha|Beta|Gamma>
"""

from __future__ import annotations

import argparse
import ctypes
import sys
from ctypes import wintypes

user32 = ctypes.WinDLL("user32.dll", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)

WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_VISIBLE = 0x10000000
WS_CHILD = 0x40000000
WS_TABSTOP = 0x00010000
WS_BORDER = 0x00800000
WS_VSCROLL = 0x00200000

BS_PUSHBUTTON = 0x00000000
BS_AUTOCHECKBOX = 0x00000003

LBS_NOTIFY = 0x0001
LBS_STANDARD = 0x00A00003

SS_LEFT = 0x00000000

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_SETTEXT = 0x000C

BN_CLICKED = 0
LBN_SELCHANGE = 1

BM_GETCHECK = 0x00F0
BM_SETCHECK = 0x00F1
BST_CHECKED = 0x0001
BST_UNCHECKED = 0x0000

LB_ADDSTRING = 0x0180
LB_GETCURSEL = 0x0188
LB_GETTEXT = 0x0189

SW_SHOW = 5

ID_BUTTON_INVOKE = 101
ID_CHECKBOX_TOGGLE = 102
ID_LISTBOX_SELECT = 103
ID_STATIC_STATUS = 104
ID_BUTTON_SECOND = 105

# LRESULT is pointer-sized (8 bytes on x64) - a plain c_long (4 bytes) return
# type on the WNDPROC callback truncates/overflows real window-procedure
# results and made DefWindowProcW's own lparam pass-through fail.
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


def _configure_prototypes() -> None:
    """Explicit argtypes/restype for every WinAPI call this fixture makes -
    without them, ctypes' default (32-bit int) marshaling truncates/overflows
    pointer-sized values (HWND, LRESULT, WPARAM/LPARAM) on 64-bit Windows."""
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.RegisterClassW.restype = wintypes.ATOM
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
    ]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = LRESULT
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.PostQuitMessage.argtypes = [ctypes.c_int]
    user32.PostQuitMessage.restype = None
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = LRESULT
    user32.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
    user32.SetWindowTextW.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.UpdateWindow.argtypes = [wintypes.HWND]
    user32.UpdateWindow.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = ctypes.c_int
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.TranslateMessage.restype = wintypes.BOOL
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.restype = LRESULT
    # The 2nd param is a resource ordinal (IDC_ARROW=32512) cast as a pointer
    # (MAKEINTRESOURCEW), never a real string - c_void_p accepts that integer
    # directly, LPCWSTR would not.
    user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
    user32.LoadCursorW.restype = wintypes.HANDLE
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE


# SendMessageW's 4th parameter (lParam) means different things for different
# messages - a plain integer for BM_GETCHECK/BM_SETCHECK/LB_GETCURSEL, but a
# string pointer for LB_ADDSTRING and an output buffer pointer for
# LB_GETTEXT. ctypes needs a distinctly-typed callable per shape (the shared
# `user32.SendMessageW` symbol keeps the plain-integer prototype).
_send_message_str = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPCWSTR)(("SendMessageW", user32))
_send_message_buf = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPWSTR)(("SendMessageW", user32))

_hwnd_status: int | None = None
_hwnd_checkbox: int | None = None
_hwnd_listbox: int | None = None


def _set_status(text: str) -> None:
    if _hwnd_status is not None:
        user32.SetWindowTextW(_hwnd_status, text)


def _handle_command(wparam: int) -> None:
    control_id = wparam & 0xFFFF
    notification = (wparam >> 16) & 0xFFFF
    if control_id == ID_BUTTON_INVOKE and notification == BN_CLICKED:
        _set_status("invoked")
    elif control_id == ID_CHECKBOX_TOGGLE and notification == BN_CLICKED:
        # BS_AUTOCHECKBOX already flips its own check state before BN_CLICKED
        # is delivered (true for a real mouse click and for UIA's
        # TogglePattern.Toggle(), which drives this the same way) - just
        # reflect the already-current state. Manually calling BM_SETCHECK
        # here as well double-toggles it right back (a real bug caught
        # during Batch 03 physical acceptance: every toggle reported
        # "toggle:off" instead of alternating).
        assert _hwnd_checkbox is not None
        checked = user32.SendMessageW(_hwnd_checkbox, BM_GETCHECK, 0, 0) == BST_CHECKED
        _set_status("toggle:on" if checked else "toggle:off")
    elif control_id == ID_LISTBOX_SELECT and notification == LBN_SELCHANGE:
        assert _hwnd_listbox is not None
        index = user32.SendMessageW(_hwnd_listbox, LB_GETCURSEL, 0, 0)
        if index >= 0:
            buffer = ctypes.create_unicode_buffer(64)
            _send_message_buf(_hwnd_listbox, LB_GETTEXT, index, buffer)
            _set_status(f"selected:{buffer.value}")


def _wndproc(hwnd: int, message: int, wparam: int, lparam: int) -> int:
    if message == WM_COMMAND:
        _handle_command(wparam)
        return 0
    if message == WM_CLOSE:
        user32.DestroyWindow(hwnd)
        return 0
    if message == WM_DESTROY:
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, message, wparam, lparam)


def main() -> int:
    global _hwnd_status, _hwnd_checkbox, _hwnd_listbox

    _configure_prototypes()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nonce", required=True, help="Unique per-run token embedded in the window title.")
    args = parser.parse_args()
    title = f"JARVIS-CUV2-FIXTURE-{args.nonce}"

    class_name = "JarvisPhase18FixtureHostWindow"
    wndproc_cb = WNDPROC(_wndproc)
    wndclass = WNDCLASSW()
    wndclass.style = 0
    wndclass.lpfnWndProc = wndproc_cb
    wndclass.hInstance = kernel32.GetModuleHandleW(None)
    wndclass.hCursor = user32.LoadCursorW(None, 32512)  # IDC_ARROW
    wndclass.hbrBackground = 6  # COLOR_WINDOW + 1
    wndclass.lpszClassName = class_name
    if not user32.RegisterClassW(ctypes.byref(wndclass)):
        print("ERROR register_class_failed", file=sys.stderr)
        return 1

    hwnd = user32.CreateWindowExW(
        0, class_name, title, WS_OVERLAPPEDWINDOW | WS_VISIBLE,
        100, 100, 340, 360, None, None, wndclass.hInstance, None,
    )
    if not hwnd:
        print("ERROR create_window_failed", file=sys.stderr)
        return 1

    user32.CreateWindowExW(
        0, "STATIC", "JARVIS fixture ready", WS_CHILD | WS_VISIBLE | SS_LEFT,
        10, 10, 300, 20, hwnd, None, wndclass.hInstance, None,
    )
    user32.CreateWindowExW(
        0, "BUTTON", "Invoke Target", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
        10, 40, 150, 30, hwnd, ID_BUTTON_INVOKE, wndclass.hInstance, None,
    )
    _hwnd_checkbox = user32.CreateWindowExW(
        0, "BUTTON", "Toggle Target", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_AUTOCHECKBOX,
        10, 80, 150, 30, hwnd, ID_CHECKBOX_TOGGLE, wndclass.hInstance, None,
    )
    _hwnd_listbox = user32.CreateWindowExW(
        0, "LISTBOX", None, WS_CHILD | WS_VISIBLE | WS_TABSTOP | WS_BORDER | LBS_NOTIFY | LBS_STANDARD,
        10, 120, 150, 90, hwnd, ID_LISTBOX_SELECT, wndclass.hInstance, None,
    )
    for item in ("Alpha", "Beta", "Gamma"):
        _send_message_str(_hwnd_listbox, LB_ADDSTRING, 0, item)
    user32.CreateWindowExW(
        0, "BUTTON", "Second Focusable", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
        10, 220, 150, 30, hwnd, ID_BUTTON_SECOND, wndclass.hInstance, None,
    )
    _hwnd_status = user32.CreateWindowExW(
        0, "STATIC", "status=idle", WS_CHILD | WS_VISIBLE | SS_LEFT,
        10, 260, 300, 20, hwnd, ID_STATIC_STATUS, wndclass.hInstance, None,
    )

    user32.ShowWindow(hwnd, SW_SHOW)
    user32.UpdateWindow(hwnd)
    print(f"READY {title}", flush=True)

    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
