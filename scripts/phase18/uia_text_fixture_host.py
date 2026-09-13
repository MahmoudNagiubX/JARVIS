"""Phase 18 Workstream A Batch 04 - JARVIS-owned native Win32 text/drag UIA fixture host.

Evaluation-only, mirrors the exact safety discipline of
`uia_fixture_host.py` (Batch 03): NEVER imported by production JARVIS
startup - a standalone process launched only by
`scripts/phase18/computer_use_acceptance.py` (or a developer, by hand),
using only stdlib `ctypes` + `user32.dll`, no third-party GUI framework, no
owner data.

Adds coverage the first fixture does not exercise: a real EDIT control for
literal-typing/key acceptance (including non-ASCII Unicode), and a
drag-source/drop-target pair for `drag_element_to_element` acceptance.

The window title always includes a caller-supplied nonce
(`JARVIS-CUV2-TEXT-FIXTURE-<nonce>`) so a runner can find *exactly* this
instance and never accidentally match an unrelated window.

Usage:
    python scripts/phase18/uia_text_fixture_host.py --nonce <uuid>

Layout:
    Static:  "JARVIS text/drag fixture ready"
    Edit:    "JARVIS TEXT FIXTURE"    (EditControl -> Value/Text pattern, independent read-back target)
    Button:  "Drag Source"           (drag origin)
    Button:  "Drop Target"           (drag destination -> drag:accepted postcondition)
    Static:  status=idle             (independent read-back target)

Status text updates (only ever these known-safe, JARVIS-authored strings -
never owner data):
    drag:accepted / drag:rejected

Drag detection: a standard BUTTON control captures its own mouse input on
WM_LBUTTONDOWN as part of its own default click-feedback handling, so a
`WM_PARENTNOTIFY`-only approach loses the capture race (the button's own
default proc re-captures for itself immediately after). Instead, the
drag-source button's own window procedure is subclassed
(`SetWindowLongPtrW(GWLP_WNDPROC, ...)`, standard Win32 subclassing - no
custom UIA provider) so WM_LBUTTONDOWN is intercepted *before* the button's
own default handling runs at all: the subclass takes capture on the
*parent* window itself and never forwards that one message down to the
original button proc. All subsequent mouse movement/release then reaches
the parent (which holds capture) regardless of which child is visually
under the cursor, and the parent resolves the drag from its own
WM_LBUTTONUP against the drop-target's current bounds.
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

BS_PUSHBUTTON = 0x00000000

ES_AUTOHSCROLL = 0x0080

SS_LEFT = 0x00000000

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202

GWLP_WNDPROC = -4

SW_SHOW = 5

ID_EDIT_TEXT = 201
ID_BUTTON_DRAG_SOURCE = 202
ID_BUTTON_DRAG_TARGET = 203
ID_STATIC_STATUS = 204

INITIAL_EDIT_TEXT = "JARVIS TEXT FIXTURE"

# LRESULT is pointer-sized (8 bytes on x64) - see uia_fixture_host.py for the
# ctypes-marshaling rationale (the same fix applies verbatim here).
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


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


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
    user32.SetCapture.argtypes = [wintypes.HWND]
    user32.SetCapture.restype = wintypes.HWND
    user32.SetFocus.argtypes = [wintypes.HWND]
    user32.SetFocus.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.ReleaseCapture.argtypes = []
    user32.ReleaseCapture.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(POINT)]
    user32.ScreenToClient.restype = wintypes.BOOL
    user32.PtInRect.argtypes = [ctypes.POINTER(RECT), POINT]
    user32.PtInRect.restype = wintypes.BOOL
    # *Ptr variants are the pointer-sized-safe subclassing API on both 32-
    # and 64-bit Windows (plain SetWindowLongW/GetWindowLongW truncate a
    # pointer-sized WNDPROC on x64 - the exact class of bug already fixed
    # elsewhere in this fixture family for LRESULT/HWND/WPARAM/LPARAM).
    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
    user32.SetWindowLongPtrW.restype = ctypes.c_void_p
    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = ctypes.c_void_p
    user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.CallWindowProcW.restype = LRESULT
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE


_hwnd_main: int | None = None
_hwnd_status: int | None = None
_hwnd_edit: int | None = None
_hwnd_drag_source: int | None = None
_hwnd_drag_target: int | None = None
_dragging = False
_original_source_wndproc: int | None = None
# Kept alive deliberately - ctypes does not keep a reference to a callback
# once installed via SetWindowLongPtrW, and a garbage-collected callback
# object would crash the process the next time Windows invokes it.
_source_subclass_proc_ref: WNDPROC | None = None


def _set_status(text: str) -> None:
    if _hwnd_status is not None:
        user32.SetWindowTextW(_hwnd_status, text)


def _client_point_in_child_rect(hwnd_parent: int, hwnd_child: int, client_x: int, client_y: int) -> bool:
    """True if the given parent-client-coordinate point falls within
    `hwnd_child`'s current bounds - resolved fresh each time (never a
    hardcoded rect), so this stays correct even if layout ever changes."""
    rect = RECT()
    if not user32.GetWindowRect(hwnd_child, ctypes.byref(rect)):
        return False
    top_left = POINT(rect.left, rect.top)
    bottom_right = POINT(rect.right, rect.bottom)
    user32.ScreenToClient(hwnd_parent, ctypes.byref(top_left))
    user32.ScreenToClient(hwnd_parent, ctypes.byref(bottom_right))
    client_rect = RECT(top_left.x, top_left.y, bottom_right.x, bottom_right.y)
    return bool(user32.PtInRect(ctypes.byref(client_rect), POINT(client_x, client_y)))


def _source_subclass_proc(hwnd: int, message: int, wparam: int, lparam: int) -> int:
    """Subclass proc for the drag-source button. WM_LBUTTONDOWN is fully
    intercepted here - it is never forwarded to the original BUTTON window
    procedure, so the button never takes its own mouse capture and never
    races the parent for it (the root cause of an earlier version of this
    fixture, found during physical dogfooding: WM_PARENTNOTIFY correctly
    fired, but the button's own default capture silently won the race a
    moment later, so the parent's WM_LBUTTONUP handler never received the
    matching release)."""
    global _dragging
    if message == WM_LBUTTONDOWN:
        _dragging = True
        assert _hwnd_main is not None
        user32.SetCapture(_hwnd_main)
        return 0
    assert _original_source_wndproc is not None
    return user32.CallWindowProcW(_original_source_wndproc, hwnd, message, wparam, lparam)


def _handle_lbutton_up(hwnd: int, lparam: int) -> None:
    global _dragging
    if not _dragging:
        return
    _dragging = False
    user32.ReleaseCapture()
    x = ctypes.c_short(lparam & 0xFFFF).value
    y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
    assert _hwnd_drag_target is not None
    if _client_point_in_child_rect(hwnd, _hwnd_drag_target, x, y):
        _set_status("drag:accepted")
    else:
        _set_status("drag:rejected")


def _wndproc(hwnd: int, message: int, wparam: int, lparam: int) -> int:
    if message == WM_LBUTTONUP:
        _handle_lbutton_up(hwnd, lparam)
        return 0
    if message == WM_COMMAND:
        return 0
    if message == WM_CLOSE:
        user32.DestroyWindow(hwnd)
        return 0
    if message == WM_DESTROY:
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, message, wparam, lparam)


def main() -> int:
    global _hwnd_main, _hwnd_status, _hwnd_edit, _hwnd_drag_source, _hwnd_drag_target
    global _original_source_wndproc, _source_subclass_proc_ref

    _configure_prototypes()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nonce", required=True, help="Unique per-run token embedded in the window title.")
    parser.add_argument("--x", type=int, default=100, help="Evaluation-only: initial window X position (virtual desktop coordinates).")
    parser.add_argument("--y", type=int, default=100, help="Evaluation-only: initial window Y position (virtual desktop coordinates).")
    args = parser.parse_args()
    title = f"JARVIS-CUV2-TEXT-FIXTURE-{args.nonce}"

    class_name = "JarvisPhase18TextFixtureHostWindow"
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
        args.x, args.y, 340, 300, None, None, wndclass.hInstance, None,
    )
    if not hwnd:
        print("ERROR create_window_failed", file=sys.stderr)
        return 1
    _hwnd_main = hwnd

    user32.CreateWindowExW(
        0, "STATIC", "JARVIS text/drag fixture ready", WS_CHILD | WS_VISIBLE | SS_LEFT,
        10, 10, 300, 20, hwnd, None, wndclass.hInstance, None,
    )
    _hwnd_edit = user32.CreateWindowExW(
        0, "EDIT", INITIAL_EDIT_TEXT, WS_CHILD | WS_VISIBLE | WS_TABSTOP | WS_BORDER | ES_AUTOHSCROLL,
        10, 40, 300, 24, hwnd, ID_EDIT_TEXT, wndclass.hInstance, None,
    )
    _hwnd_drag_source = user32.CreateWindowExW(
        0, "BUTTON", "Drag Source", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
        10, 90, 130, 40, hwnd, ID_BUTTON_DRAG_SOURCE, wndclass.hInstance, None,
    )
    _original_source_wndproc = user32.GetWindowLongPtrW(_hwnd_drag_source, GWLP_WNDPROC)
    _source_subclass_proc_ref = WNDPROC(_source_subclass_proc)
    user32.SetWindowLongPtrW(_hwnd_drag_source, GWLP_WNDPROC, _source_subclass_proc_ref)
    _hwnd_drag_target = user32.CreateWindowExW(
        0, "BUTTON", "Drop Target", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
        180, 90, 130, 40, hwnd, ID_BUTTON_DRAG_TARGET, wndclass.hInstance, None,
    )
    _hwnd_status = user32.CreateWindowExW(
        0, "STATIC", "status=idle", WS_CHILD | WS_VISIBLE | SS_LEFT,
        10, 150, 300, 20, hwnd, ID_STATIC_STATUS, wndclass.hInstance, None,
    )

    user32.ShowWindow(hwnd, SW_SHOW)
    user32.UpdateWindow(hwnd)
    # Unlike a dialog template (which auto-focuses its first tabstop
    # control), a plain top-level window never gives keyboard focus to any
    # child automatically - without this, no WM_CHAR/keydown ever reaches
    # the Edit control and every keyboard scenario silently does nothing
    # (found during Batch 04 physical acceptance dogfooding: first-run
    # typing/Home/End/Backspace/Tab/chord scenarios all failed with the
    # Edit control's text completely unchanged). Deliberately no
    # self-SetForegroundWindow call here - matching uia_fixture_host.py
    # exactly, since an extra self-activation attempt at spawn time was
    # found (by isolating the difference between the two fixtures) to make
    # the runner's LATER, real `focus_window()` foreground activation fail
    # consistently, whereas relying solely on the runner's own activation
    # (as uia_fixture_host.py already does) works reliably.
    user32.SetFocus(_hwnd_edit)
    print(f"READY {title}", flush=True)

    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        # Same IsDialogMessageW requirement as uia_fixture_host.py - a plain
        # top-level window does not cycle Tab focus between WS_TABSTOP
        # children on its own.
        if not user32.IsDialogMessageW(hwnd, ctypes.byref(msg)):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
