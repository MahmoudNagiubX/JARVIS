"""Phase 18 Workstream A Batch 06, Milestone 2 - JARVIS-owned native Win32
bounded-recovery acceptance fixture host (GAP-0104).

Evaluation-only. NEVER imported by production JARVIS startup - a standalone
process launched only by a physical acceptance runner (or a developer, by
hand), using only stdlib `ctypes` + `user32.dll`, no third-party GUI
framework, no owner data. Mirrors the exact safety discipline of the other
owned fixtures: JARVIS-owned child process only, a fresh nonce window
title, no network, no clipboard, no secrets.

Unlike the first three fixtures, this one accepts a small, explicit,
deterministic command channel over its OWN stdin - the exact pipe the
runner's own `subprocess.Popen(..., stdin=subprocess.PIPE)` created for
this exact child process, never a network socket or any channel reaching
an unrelated process. This is what lets a runner deliberately, safely, and
*deterministically* produce the pre-input environmental changes GAP-0104's
bounded recovery cycle exists to handle - moving or replacing the target
control on command - without any timing guesswork or uncontrolled process
racing: the runner always waits for `computer.semantic.read` to
independently confirm each command's effect (a fresh generation label,
new bounds) before it ever issues the actual JARVIS action under test.
Fixture-reported state (the status label) is never treated as proof of
what JARVIS itself did - only of what the fixture itself changed.

Commands (one per line on stdin):

    MOVE       - relocates the target button by a fixed offset, keeping
                 its identity (same HWND/RuntimeId) - proves "stable
                 identity with changed bounds" / "relocates before input".
    REPLACE    - destroys the current target button and creates a brand
                 new one (same visible name, genuinely different
                 HWND/RuntimeId) - proves "target replaced with a
                 different strong identity".

Layout:
    Static:  "JARVIS recovery fixture ready"
    Button:  "Recovery Target"   (BS_PUSHBUTTON -> Invoke pattern / native click)
    Static:  status=ready:gen0   (independent read-back target; becomes
             status=clicked:gen<N> when the *current* generation's button
             is actually clicked - proves exactly which incarnation of the
             control received the action)

Usage:
    python scripts/phase18/uia_recovery_fixture_host.py --nonce <uuid>
"""

from __future__ import annotations

import argparse
import ctypes
import sys
import threading
from ctypes import wintypes

user32 = ctypes.WinDLL("user32.dll", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)

WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_VISIBLE = 0x10000000
WS_CHILD = 0x40000000
WS_TABSTOP = 0x00010000

BS_PUSHBUTTON = 0x00000000
SS_LEFT = 0x00000000

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_APP = 0x8000
WM_APP_MOVE = WM_APP + 1
WM_APP_REPLACE = WM_APP + 2

SW_SHOW = 5
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004

ID_BUTTON_TARGET = 301
ID_STATIC_STATUS = 302

TARGET_LABEL = "Recovery Target"
MOVE_OFFSET_X = 220
MOVE_OFFSET_Y = 0
BUTTON_WIDTH = 160
BUTTON_HEIGHT = 40

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


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def _configure_prototypes() -> None:
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
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
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
    user32.IsDialogMessageW.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.MSG)]
    user32.IsDialogMessageW.restype = wintypes.BOOL
    user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
    user32.LoadCursorW.restype = wintypes.HANDLE
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.SetWindowPos.restype = wintypes.BOOL
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE


_hwnd_main: int | None = None
_hwnd_button: int | None = None
_hwnd_status: int | None = None
_hinstance = None
_generation = 0
_button_x = 40
_button_y = 60


def _set_status(text: str) -> None:
    if _hwnd_status is not None:
        user32.SetWindowTextW(_hwnd_status, text)


def _do_move() -> None:
    global _button_x, _button_y
    assert _hwnd_button is not None
    _button_x += MOVE_OFFSET_X
    _button_y += MOVE_OFFSET_Y
    user32.SetWindowPos(_hwnd_button, None, _button_x, _button_y, 0, 0, SWP_NOSIZE | SWP_NOZORDER)
    _set_status(f"ready:gen{_generation}")


def _do_replace() -> None:
    global _hwnd_button, _generation
    assert _hwnd_main is not None and _hwnd_button is not None
    user32.DestroyWindow(_hwnd_button)
    _generation += 1
    _hwnd_button = user32.CreateWindowExW(
        0, "BUTTON", TARGET_LABEL, WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
        _button_x, _button_y, BUTTON_WIDTH, BUTTON_HEIGHT, _hwnd_main, ID_BUTTON_TARGET, _hinstance, None,
    )
    _set_status(f"ready:gen{_generation}")


def _wndproc(hwnd: int, message: int, wparam: int, lparam: int) -> int:
    if message == WM_APP_MOVE:
        _do_move()
        return 0
    if message == WM_APP_REPLACE:
        _do_replace()
        return 0
    if message == WM_COMMAND:
        control_id = wparam & 0xFFFF
        if control_id == ID_BUTTON_TARGET:
            _set_status(f"clicked:gen{_generation}")
        return 0
    if message == WM_CLOSE:
        user32.DestroyWindow(hwnd)
        return 0
    if message == WM_DESTROY:
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, message, wparam, lparam)


def _stdin_command_loop() -> None:
    """Runs on a background thread - never touches a Win32 UI handle
    directly (all handles belong to the GUI thread); instead posts a
    message onto the main window's own queue, so every actual UI mutation
    still happens on the correct thread, same as any other Win32 app."""
    for raw_line in sys.stdin:
        command = raw_line.strip().upper()
        if not command or _hwnd_main is None:
            continue
        if command == "MOVE":
            user32.PostMessageW(_hwnd_main, WM_APP_MOVE, 0, 0)
        elif command == "REPLACE":
            user32.PostMessageW(_hwnd_main, WM_APP_REPLACE, 0, 0)


def main() -> int:
    global _hwnd_main, _hwnd_button, _hwnd_status, _hinstance

    _configure_prototypes()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nonce", required=True, help="Unique per-run token embedded in the window title.")
    args = parser.parse_args()
    title = f"JARVIS-CUV2-RECOVERY-FIXTURE-{args.nonce}"

    class_name = "JarvisPhase18RecoveryFixtureHostWindow"
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
    _hinstance = wndclass.hInstance

    hwnd = user32.CreateWindowExW(
        0, class_name, title, WS_OVERLAPPEDWINDOW | WS_VISIBLE,
        100, 100, 460, 220, None, None, wndclass.hInstance, None,
    )
    if not hwnd:
        print("ERROR create_window_failed", file=sys.stderr)
        return 1
    _hwnd_main = hwnd

    user32.CreateWindowExW(
        0, "STATIC", "JARVIS recovery fixture ready", WS_CHILD | WS_VISIBLE | SS_LEFT,
        10, 10, 400, 20, hwnd, None, wndclass.hInstance, None,
    )
    _hwnd_button = user32.CreateWindowExW(
        0, "BUTTON", TARGET_LABEL, WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
        _button_x, _button_y, BUTTON_WIDTH, BUTTON_HEIGHT, hwnd, ID_BUTTON_TARGET, wndclass.hInstance, None,
    )
    _hwnd_status = user32.CreateWindowExW(
        0, "STATIC", f"status=ready:gen{_generation}", WS_CHILD | WS_VISIBLE | SS_LEFT,
        10, 140, 400, 20, hwnd, ID_STATIC_STATUS, wndclass.hInstance, None,
    )

    user32.ShowWindow(hwnd, SW_SHOW)
    user32.UpdateWindow(hwnd)
    print(f"READY {title}", flush=True)

    reader_thread = threading.Thread(target=_stdin_command_loop, daemon=True)
    reader_thread.start()

    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        if not user32.IsDialogMessageW(hwnd, ctypes.byref(msg)):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
