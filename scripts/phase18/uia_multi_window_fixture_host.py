"""Phase 18 Workstream A Batch 07 - JARVIS-owned multi-window UIA fixture.

Evaluation-only. This standalone native Win32 process is launched only by the
bounded Phase 18 acceptance runner. It has no production import, network,
clipboard, filesystem dialog, shell, or owner-application dependency.

The process owns a primary window and a separately enumerated owned dialog.
The dialog title carries the same fresh nonce as the primary title and a
generation suffix. Recreate destroys the old dialog and creates a new title,
which gives stale-reference and approval-binding scenarios an independent
identity transition without touching another process or an owner's desktop
data.

Usage:
    python scripts/phase18/uia_multi_window_fixture_host.py --nonce <uuid>

Primary controls:
    Open Owned Dialog     -> creates the owned dialog
    Main Focus Target     -> focus transition target
    main:ready/open/...   -> known-safe status read-back

Dialog controls:
    Dialog Action         -> dialog:acted
    Consequential Target  -> dialog:clicked
    Recreate Dialog       -> destroys generation N and creates generation N+1
    Close Dialog          -> destroys the dialog and returns to the primary
    Dialog Focus Target   -> focus transition target
"""

from __future__ import annotations

import argparse
import ctypes
import sys
import uuid
from ctypes import wintypes

user32 = ctypes.WinDLL("user32.dll", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)

WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_VISIBLE = 0x10000000
WS_CHILD = 0x40000000
WS_TABSTOP = 0x00010000

WS_EX_DLGMODALFRAME = 0x00000001
BS_PUSHBUTTON = 0x00000000
SS_LEFT = 0x00000000

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
BN_CLICKED = 0
SW_SHOW = 5

ID_MAIN_OPEN = 501
ID_MAIN_FOCUS = 502
ID_MAIN_STATUS = 503
ID_DIALOG_ACTION = 601
ID_DIALOG_CONSEQUENTIAL = 602
ID_DIALOG_RECREATE = 603
ID_DIALOG_CLOSE = 604
ID_DIALOG_FOCUS = 605
ID_DIALOG_STATUS = 606

MAIN_CLASS = "JarvisPhase18MultiWindowMain"
DIALOG_CLASS = "JarvisPhase18MultiWindowDialog"
MAIN_TITLE_PREFIX = "JARVIS-CUV2-MULTI-FIXTURE-"
DIALOG_TITLE_PREFIX = "JARVIS-CUV2-MULTI-DIALOG-"

# LRESULT is pointer-sized on 64-bit Windows. Keeping the callback and all
# pointer-sized Win32 prototypes explicit prevents ctypes truncation.
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
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE


_hwnd_main: int | None = None
_hwnd_main_status: int | None = None
_hwnd_dialog: int | None = None
_hwnd_dialog_status: int | None = None
_instance: int | None = None
_nonce = ""
_x = 100
_y = 100
_dialog_generation = 0
_main_wndproc_ref: WNDPROC | None = None
_dialog_wndproc_ref: WNDPROC | None = None


def _set_text(hwnd: int | None, text: str) -> None:
    if hwnd is not None:
        user32.SetWindowTextW(hwnd, text)


def _set_main_status(text: str) -> None:
    _set_text(_hwnd_main_status, text)


def _set_dialog_status(text: str) -> None:
    _set_text(_hwnd_dialog_status, text)


def _dialog_title(generation: int) -> str:
    return f"{DIALOG_TITLE_PREFIX}{_nonce}-GEN-{generation}"


def _destroy_dialog() -> None:
    if _hwnd_dialog is not None:
        user32.DestroyWindow(_hwnd_dialog)


def _dialog_command(control_id: int, notification: int) -> None:
    if notification != BN_CLICKED:
        return
    if control_id == ID_DIALOG_ACTION:
        _set_dialog_status("dialog:acted")
    elif control_id == ID_DIALOG_CONSEQUENTIAL:
        _set_dialog_status("dialog:clicked")
    elif control_id == ID_DIALOG_RECREATE:
        _recreate_dialog()
    elif control_id == ID_DIALOG_CLOSE:
        _set_main_status("dialog:closed")
        _destroy_dialog()


def _main_command(control_id: int, notification: int) -> None:
    if control_id == ID_MAIN_OPEN and notification == BN_CLICKED:
        if _hwnd_dialog is None and _create_dialog():
            _set_main_status("dialog:open")


def _main_wndproc(hwnd: int, message: int, wparam: int, lparam: int) -> int:
    if message == WM_COMMAND:
        _main_command(wparam & 0xFFFF, (wparam >> 16) & 0xFFFF)
        return 0
    if message == WM_CLOSE:
        _destroy_dialog()
        user32.DestroyWindow(hwnd)
        return 0
    if message == WM_DESTROY:
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, message, wparam, lparam)


def _dialog_wndproc(hwnd: int, message: int, wparam: int, lparam: int) -> int:
    global _hwnd_dialog, _hwnd_dialog_status
    if message == WM_COMMAND:
        _dialog_command(wparam & 0xFFFF, (wparam >> 16) & 0xFFFF)
        return 0
    if message == WM_CLOSE:
        _set_main_status("dialog:closed")
        _destroy_dialog()
        return 0
    if message == WM_DESTROY:
        if _hwnd_dialog == hwnd:
            _hwnd_dialog = None
            _hwnd_dialog_status = None
        return 0
    return user32.DefWindowProcW(hwnd, message, wparam, lparam)


def _create_control(class_name: str, text: str | None, style: int, x: int, y: int, width: int, height: int, parent: int, control_id: int) -> int:
    assert _instance is not None
    return int(user32.CreateWindowExW(0, class_name, text, style, x, y, width, height, parent, control_id, _instance, None) or 0)


def _create_dialog() -> bool:
    global _hwnd_dialog, _hwnd_dialog_status
    if _hwnd_dialog is not None or _hwnd_main is None or _instance is None:
        return False
    hwnd = user32.CreateWindowExW(
        WS_EX_DLGMODALFRAME, DIALOG_CLASS, _dialog_title(_dialog_generation),
        WS_OVERLAPPEDWINDOW | WS_VISIBLE,
        _x + 35, _y + 35, 470, 300, _hwnd_main, None, _instance, None,
    )
    if not hwnd:
        return False
    _hwnd_dialog = int(hwnd)
    base_style = WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON
    _create_control("STATIC", "JARVIS owned dialog ready", WS_CHILD | WS_VISIBLE | SS_LEFT, 14, 14, 410, 22, _hwnd_dialog, 0)
    _create_control("BUTTON", "Dialog Action", base_style, 14, 52, 180, 32, _hwnd_dialog, ID_DIALOG_ACTION)
    _create_control("BUTTON", "Consequential Target", base_style, 210, 52, 190, 32, _hwnd_dialog, ID_DIALOG_CONSEQUENTIAL)
    _create_control("BUTTON", "Recreate Dialog", base_style, 14, 98, 180, 32, _hwnd_dialog, ID_DIALOG_RECREATE)
    _create_control("BUTTON", "Close Dialog", base_style, 210, 98, 190, 32, _hwnd_dialog, ID_DIALOG_CLOSE)
    _create_control("BUTTON", "Dialog Focus Target", base_style, 14, 144, 180, 32, _hwnd_dialog, ID_DIALOG_FOCUS)
    _hwnd_dialog_status = _create_control(
        "STATIC", "dialog:ready", WS_CHILD | WS_VISIBLE | SS_LEFT,
        14, 204, 410, 24, _hwnd_dialog, ID_DIALOG_STATUS,
    )
    user32.ShowWindow(_hwnd_dialog, SW_SHOW)
    user32.UpdateWindow(_hwnd_dialog)
    return True


def _recreate_dialog() -> None:
    global _dialog_generation
    _destroy_dialog()
    _dialog_generation += 1
    _create_dialog()
    _set_main_status("dialog:recreated")


def _register_class(class_name: str, callback: WNDPROC) -> bool:
    assert _instance is not None
    wndclass = WNDCLASSW()
    wndclass.style = 0
    wndclass.lpfnWndProc = callback
    wndclass.hInstance = _instance
    wndclass.hCursor = user32.LoadCursorW(None, 32512)  # IDC_ARROW
    wndclass.hbrBackground = 6  # COLOR_WINDOW + 1
    wndclass.lpszClassName = class_name
    return bool(user32.RegisterClassW(ctypes.byref(wndclass)))


def main() -> int:
    global _hwnd_main, _hwnd_main_status, _instance, _nonce, _x, _y
    global _main_wndproc_ref, _dialog_wndproc_ref

    _configure_prototypes()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nonce", required=True, help="Unique per-run UUID embedded in every top-level title.")
    parser.add_argument("--x", type=int, default=100, help="Evaluation-only primary window X position.")
    parser.add_argument("--y", type=int, default=100, help="Evaluation-only primary window Y position.")
    args = parser.parse_args()
    try:
        _nonce = str(uuid.UUID(args.nonce))
    except (AttributeError, TypeError, ValueError):
        print("ERROR nonce_must_be_uuid", file=sys.stderr)
        return 2
    _x, _y = args.x, args.y
    _instance = int(kernel32.GetModuleHandleW(None) or 0)
    _main_wndproc_ref = WNDPROC(_main_wndproc)
    _dialog_wndproc_ref = WNDPROC(_dialog_wndproc)
    if not _register_class(MAIN_CLASS, _main_wndproc_ref) or not _register_class(DIALOG_CLASS, _dialog_wndproc_ref):
        print("ERROR register_class_failed", file=sys.stderr)
        return 1

    _hwnd_main = int(user32.CreateWindowExW(
        0, MAIN_CLASS, f"{MAIN_TITLE_PREFIX}{_nonce}", WS_OVERLAPPEDWINDOW | WS_VISIBLE,
        _x, _y, 430, 260, None, None, _instance, None,
    ) or 0)
    if not _hwnd_main:
        print("ERROR create_primary_window_failed", file=sys.stderr)
        return 1
    _create_control("STATIC", "JARVIS multi-window fixture ready", WS_CHILD | WS_VISIBLE | SS_LEFT, 14, 14, 370, 22, _hwnd_main, 0)
    base_style = WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON
    _create_control("BUTTON", "Open Owned Dialog", base_style, 14, 54, 180, 32, _hwnd_main, ID_MAIN_OPEN)
    _create_control("BUTTON", "Main Focus Target", base_style, 210, 54, 180, 32, _hwnd_main, ID_MAIN_FOCUS)
    _hwnd_main_status = _create_control(
        "STATIC", "main:ready", WS_CHILD | WS_VISIBLE | SS_LEFT,
        14, 116, 370, 24, _hwnd_main, ID_MAIN_STATUS,
    )
    user32.ShowWindow(_hwnd_main, SW_SHOW)
    user32.UpdateWindow(_hwnd_main)
    print(f"READY {MAIN_TITLE_PREFIX}{_nonce}", flush=True)

    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        handled = False
        if _hwnd_dialog is not None:
            handled = bool(user32.IsDialogMessageW(_hwnd_dialog, ctypes.byref(msg)))
        if not handled and _hwnd_main is not None:
            handled = bool(user32.IsDialogMessageW(_hwnd_main, ctypes.byref(msg)))
        if not handled:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
