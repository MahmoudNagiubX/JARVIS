"""Phase 18 Workstream A Batch 06 - JARVIS-owned native Win32 OCR/visual
acceptance fixture host.

Evaluation-only. NEVER imported by production JARVIS startup - a standalone
process launched only by a physical acceptance runner (or a developer, by
hand), using only stdlib `ctypes` + `user32.dll`, no third-party GUI
framework, no owner data. Mirrors the exact safety discipline of
`uia_fixture_host.py`/`uia_text_fixture_host.py`: JARVIS-owned child process
only, a fresh nonce window title so a runner can find *exactly* this
instance, no network, no clipboard, no secrets.

Dedicated to the physical Arabic/mixed OCR acceptance (GAP-0103) and the
bounded visual-actuation acceptance. The OCR labels remain plain
STATIC/TextControl observations. The visual-actuation target is one real
Win32 BUTTON with a fixture-owned status STATIC that changes only when the
button receives a real user click. The optional duplicate-target variant is
used only to prove ambiguity refusal in the physical evaluator.

The Arabic/mixed labels below are plain Python `str` literals containing
real Arabic Unicode codepoints in ordinary logical reading order - passed
straight through `SetWindowTextW`'s `LPCWSTR` marshaling with no
reshaping/bidi library involved on the JARVIS side. This is deliberate: a
real, live Win32 STATIC control's own text rendering already goes through
Windows' own Uniscribe/DirectWrite shaping engine, which correctly joins
Arabic glyphs and applies the Unicode Bidi Algorithm - the exact rendering
path an *offline* PIL-rendered PNG (Batch 04/05's benchmark fixture) did
not have without an explicit shaping library. Never substitute a Latin
transliteration for these strings.

Usage:
    python scripts/phase18/uia_ocr_fixture_host.py --nonce <uuid>

Layout (OCR labels are STATIC/TextControl; the final rows are the visual
actuation target and its independent status read-back):
    "JARVIS OCR fixture ready"    (English, fixture status line)
    "مرحبا يا جارفيس"              (Arabic-only, "Hello JARVIS")
    "الإعدادات"                    (Arabic-only, "Settings")
    "JARVIS الإعدادات"             (mixed Latin+Arabic)
    "JARVIS OCR FIXTURE"          (English-only, cross-check control)
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

SS_LEFT = 0x00000000
BS_PUSHBUTTON = 0x00000000

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
BN_CLICKED = 0

SW_SHOW = 5
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010

# LRESULT is pointer-sized (8 bytes on x64) - matching the fix already
# applied across this fixture family.
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

# The exact strings this fixture exists to prove OCR against - never
# transliterated, never generated, always these literal characters.
LABEL_READY = "JARVIS OCR fixture ready"
LABEL_ARABIC_GREETING = "مرحبا يا جارفيس"
LABEL_ARABIC_SETTINGS = "الإعدادات"
LABEL_MIXED_SETTINGS = "JARVIS الإعدادات"
LABEL_ENGLISH_ONLY = "JARVIS OCR FIXTURE"
VISUAL_ACTION_LABEL = "GO"
VISUAL_STATUS_READY = "VISUAL STATUS READY"
VISUAL_STATUS_APPLIED = "VISUAL STATUS APPLIED"
VISUAL_ACTION_CONTROL_ID = 501
VISUAL_DUPLICATE_CONTROL_ID = 502

_visual_status_hwnd: int | None = None


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
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.UpdateWindow.argtypes = [wintypes.HWND]
    user32.UpdateWindow.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = ctypes.c_int
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.TranslateMessage.restype = wintypes.BOOL
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.restype = LRESULT
    user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
    user32.LoadCursorW.restype = wintypes.HANDLE
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE


def _wndproc(hwnd: int, message: int, wparam: int, lparam: int) -> int:
    if message == WM_COMMAND:
        command_id = int(wparam) & 0xFFFF
        notification_code = (int(wparam) >> 16) & 0xFFFF
        if (
            notification_code == BN_CLICKED
            and command_id in {VISUAL_ACTION_CONTROL_ID, VISUAL_DUPLICATE_CONTROL_ID}
        ):
            if _visual_status_hwnd:
                user32.SetWindowTextW(_visual_status_hwnd, VISUAL_STATUS_APPLIED)
            return 0
        return 0
    if message == WM_CLOSE:
        user32.DestroyWindow(hwnd)
        return 0
    if message == WM_DESTROY:
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, message, wparam, lparam)


def main() -> int:
    global _visual_status_hwnd

    _configure_prototypes()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nonce", required=True, help="Unique per-run token embedded in the window title.")
    parser.add_argument("--x", type=int, default=100, help="Evaluation-only: initial window X position (virtual desktop coordinates).")
    parser.add_argument("--y", type=int, default=100, help="Evaluation-only: initial window Y position (virtual desktop coordinates).")
    parser.add_argument(
        "--duplicate-visual-target",
        action="store_true",
        help="Evaluation-only variant with a second overlapping GO label.",
    )
    args = parser.parse_args()
    title = f"JARVIS-CUV2-OCR-FIXTURE-{args.nonce}"

    class_name = "JarvisPhase18OcrFixtureHostWindow"
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
        args.x, args.y, 480, 330, None, None, wndclass.hInstance, None,
    )
    if not hwnd:
        print("ERROR create_window_failed", file=sys.stderr)
        return 1

    labels = (
        (LABEL_READY, 10, 10),
        (LABEL_ARABIC_GREETING, 10, 50),
        (LABEL_ARABIC_SETTINGS, 10, 90),
        (LABEL_MIXED_SETTINGS, 10, 130),
        (LABEL_ENGLISH_ONLY, 10, 170),
    )
    for text, x, y in labels:
        user32.CreateWindowExW(
            0, "STATIC", text, WS_CHILD | WS_VISIBLE | SS_LEFT,
            x, y, 440, 30, hwnd, None, wndclass.hInstance, None,
        )

    user32.CreateWindowExW(
        0,
        "BUTTON",
        VISUAL_ACTION_LABEL,
        WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
        10,
        215,
        180,
        34,
        hwnd,
        VISUAL_ACTION_CONTROL_ID,
        wndclass.hInstance,
        None,
    )
    if args.duplicate_visual_target:
        user32.CreateWindowExW(
            0,
            "BUTTON",
            VISUAL_ACTION_LABEL,
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
            150,
            215,
            180,
            34,
            hwnd,
            VISUAL_DUPLICATE_CONTROL_ID,
            wndclass.hInstance,
            None,
        )
    _visual_status_hwnd = user32.CreateWindowExW(
        0,
        "STATIC",
        VISUAL_STATUS_READY,
        WS_CHILD | WS_VISIBLE | SS_LEFT,
        10,
        270,
        440,
        25,
        hwnd,
        None,
        wndclass.hInstance,
        None,
    )

    user32.ShowWindow(hwnd, SW_SHOW)
    user32.UpdateWindow(hwnd)
    # The physical OCR acceptance captures the live visible window rather
    # than a hidden/off-screen fixture. This is fixture setup only; the
    # visual action still has to ground and focus the window again through
    # JARVIS's canonical computer service.
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
    user32.SetForegroundWindow(hwnd)
    print(f"READY {title}", flush=True)

    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
