"""Zero-download Windows desktop metadata and on-demand GDI capture."""

from __future__ import annotations

import ctypes
import hashlib
import platform
import time
from ctypes import wintypes
from datetime import UTC, datetime, timedelta
from pathlib import PureWindowsPath
from uuid import uuid4

from ..contracts import DesktopContextSnapshot, DesktopWindow, ScreenObservation, VisualRegion
from .frame import TransientFrame, frame_metadata
from .privacy import PerceptionPrivacyPolicy


class WindowsDesktopProvider:
    """Native user32/gdi32 provider; no shell, screenshot file, or process memory."""

    name = "windows-native"
    FRAME_MAX_PIXELS = 12_000_000
    WINDOW_REF_TTL_SECONDS = 45
    MAX_WINDOW_REFS = 256

    def __init__(self, *, window_ref_ttl_seconds: int = WINDOW_REF_TTL_SECONDS, privacy_policy: PerceptionPrivacyPolicy | None = None) -> None:
        self.available = platform.system().casefold() == "windows"
        self.reason = None if self.available else "windows_desktop_unavailable"
        self.window_ref_ttl_seconds = max(30, min(60, window_ref_ttl_seconds))
        self._window_refs: dict[str, _WindowHandle] = {}
        self.privacy_policy = privacy_policy or PerceptionPrivacyPolicy()
        self._user32 = None
        self._gdi32 = None
        self._kernel32 = None
        if self.available:
            self._load_libraries()

    def capabilities(self) -> dict[str, object]:
        return {
            "available": self.available,
            "reason": self.reason,
            "metadata": self.available,
            "screen_capture": self.available,
            "continuous_capture": False,
            "raw_frame_retention": False,
        }

    def desktop_context(self, device_id: str) -> DesktopContextSnapshot:
        if not self.available:
            return DesktopContextSnapshot(f"snapshot-{uuid4()}", device_id, datetime.now(UTC), source=self.name, confidence=0.0)
        now = datetime.now(UTC)
        active_hwnd = int(self._user32.GetForegroundWindow() or 0)
        windows: list[DesktopWindow] = []

        def callback(hwnd: int, _: int) -> bool:
            if len(windows) >= 50 or not self._user32.IsWindowVisible(hwnd):
                return True
            window = self._window_from_hwnd(int(hwnd), int(hwnd) == active_hwnd, now)
            if window is not None:
                windows.append(window)
            return True

        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(callback)
        self._user32.EnumWindows(enum_proc, 0)
        active = next((item for item in windows if item.active), None)
        width = int(self._user32.GetSystemMetrics(78))
        height = int(self._user32.GetSystemMetrics(79))
        return DesktopContextSnapshot(
            f"snapshot-{uuid4()}", device_id, now, active, tuple(windows),
            max(1, width), max(1, height), self.name, 1.0,
        )

    def capture_frame(
        self,
        *,
        mode: str = "full_virtual_desktop",
        region: VisualRegion | None = None,
        window_ref: str | None = None,
    ) -> TransientFrame:
        if not self.available:
            raise RuntimeError(self.reason or "windows_desktop_unavailable")
        left, top, width, height = self._capture_bounds(mode, region, window_ref)
        if width <= 0 or height <= 0 or width * height > self.FRAME_MAX_PIXELS:
            raise ValueError("invalid_or_oversized_capture_region")
        return self._gdi_capture(left, top, width, height)

    async def capture(self, device_id: str, window: str | None = None, region: VisualRegion | None = None) -> ScreenObservation:
        started = time.perf_counter()
        capture_mode = "explicit_region" if region else "active_window" if window else "full_virtual_desktop"
        frame = self.capture_frame(mode=capture_mode, region=region, window_ref=window)
        try:
            digest = hashlib.sha256(bytes(frame.data)).hexdigest()
            metadata = frame_metadata(frame, digest)
            width, height = frame.width, frame.height
        finally:
            frame.release()
        context = self.desktop_context(device_id)
        return ScreenObservation(
            f"observation-{uuid4()}", device_id, datetime.now(UTC), self.name,
            width=width, height=height,
            active_window=context.active_window.window_ref if context.active_window else None,
            region=region, raw_retained=False, confidence=1.0,
            metadata=metadata | {"latency_ms": round((time.perf_counter() - started) * 1000, 2)},
        )

    def focus_window(self, window_ref: str) -> bool:
        if not self.available:
            return False
        hwnd = self._resolve_window_ref(window_ref)
        if not self._user32.SetForegroundWindow(hwnd):
            return False
        return int(self._user32.GetForegroundWindow() or 0) == hwnd

    def is_foreground(self, hwnd: int) -> bool:
        return self.available and int(self._user32.GetForegroundWindow() or 0) == int(hwnd)

    def validate_input_window(self, window_ref: str) -> int:
        hwnd = self.resolve_window_ref(window_ref)
        process_id = wintypes.DWORD()
        self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        process_name = self._process_name(int(process_id.value))
        title_length = min(300, max(0, int(self._user32.GetWindowTextLengthW(hwnd))))
        title_buffer = ctypes.create_unicode_buffer(title_length + 1)
        self._user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))
        if self.privacy_policy.check_window(process_name, title_buffer.value):
            raise ValueError("sensitive_window_denied")
        return hwnd

    def window_action(self, window_ref: str, operation: str) -> bool:
        if not self.available:
            return False
        if operation not in {"minimize", "maximize", "restore"}:
            raise ValueError("window_operation_invalid")
        hwnd = self._resolve_window_ref(window_ref)
        self._user32.ShowWindow(hwnd, {"minimize": 6, "maximize": 3, "restore": 9}[operation])
        if operation == "minimize":
            return bool(self._user32.IsIconic(hwnd))
        if operation == "maximize":
            return bool(self._user32.IsZoomed(hwnd))
        return not bool(self._user32.IsIconic(hwnd)) and not bool(self._user32.IsZoomed(hwnd))

    def resolve_window_ref(self, window_ref: str) -> int:
        """Resolve only an internally issued, unexpired reference; raw HWND is rejected."""

        if not isinstance(window_ref, str) or not window_ref.startswith("window-"):
            raise ValueError("window_ref_required")
        return self._resolve_window_ref(window_ref)

    def describe_window(self, window_ref: str) -> dict[str, object]:
        """Fresh, trusted, bounded window descriptor for window-targeted
        approval preview/binding (R18B02-003) - re-reads the live title/
        process/class rather than trusting the stored fingerprint alone,
        denies privacy-sensitive windows, and detects identity drift
        (the window recycled to a different process/class since the ref was
        issued) by comparing against the stored reference. Reuses the
        existing `_window_refs` store - no second window-reference store.
        Raises `ValueError` with a typed reason on stale/sensitive/changed
        windows, matching `validate_input_window`'s convention."""
        if not self.available:
            raise ValueError("windows_desktop_unavailable")
        entry = self._window_refs.get(window_ref)
        if entry is None:
            raise ValueError("window_ref_expired")
        now = datetime.now(UTC)
        if entry.expires_at <= now:
            self._window_refs.pop(window_ref, None)
            raise ValueError("window_ref_expired")
        if not self._user32.IsWindow(entry.hwnd):
            self._window_refs.pop(window_ref, None)
            raise ValueError("window_ref_expired")
        title_length = min(300, max(0, int(self._user32.GetWindowTextLengthW(entry.hwnd))))
        title_buffer = ctypes.create_unicode_buffer(title_length + 1)
        self._user32.GetWindowTextW(entry.hwnd, title_buffer, len(title_buffer))
        title = title_buffer.value[:300] or None
        class_buffer = ctypes.create_unicode_buffer(257)
        self._user32.GetClassNameW(entry.hwnd, class_buffer, len(class_buffer))
        window_class = class_buffer.value[:200] or None
        process_id = wintypes.DWORD()
        self._user32.GetWindowThreadProcessId(entry.hwnd, ctypes.byref(process_id))
        process_name = self._process_name(int(process_id.value))
        if self.privacy_policy.check_window(process_name, title):
            raise ValueError("sensitive_window_denied")
        fresh_fingerprint = _fingerprint(title)
        if (
            fresh_fingerprint != entry.title_fingerprint
            or window_class != entry.window_class
            or int(process_id.value) != entry.process_id
        ):
            raise ValueError("window_ref_changed")
        identity_digest = hashlib.sha256(
            f"{entry.process_id}:{entry.title_fingerprint}:{entry.window_class}".encode("utf-8")
        ).hexdigest()
        return {
            "window_ref": window_ref,
            "title": title,
            "process_name": process_name,
            "expires_at": entry.expires_at,
            "identity_digest": identity_digest,
        }

    def validate_region(self, region: VisualRegion, *, width: int, height: int) -> None:
        if region.x < 0 or region.y < 0 or region.width <= 0 or region.height <= 0:
            raise ValueError("invalid_capture_region")
        if region.x + region.width > width or region.y + region.height > height:
            raise ValueError("capture_region_out_of_bounds")
        if region.width * region.height > self.FRAME_MAX_PIXELS:
            raise ValueError("capture_region_too_large")

    def _capture_bounds(self, mode: str, region: VisualRegion | None, window_ref: str | None) -> tuple[int, int, int, int]:
        if mode not in {"full_virtual_desktop", "active_window", "explicit_region", "screen", "semantic"}:
            raise ValueError("unsupported_capture_mode")
        if mode == "explicit_region" or region is not None:
            if region is None:
                raise ValueError("capture_region_required")
            width = int(self._user32.GetSystemMetrics(78))
            height = int(self._user32.GetSystemMetrics(79))
            # The public region is relative to the virtual desktop origin.
            self.validate_region(region, width=max(1, width), height=max(1, height))
            return int(self._user32.GetSystemMetrics(76)) + region.x, int(self._user32.GetSystemMetrics(77)) + region.y, region.width, region.height
        if mode == "active_window":
            hwnd = self._resolve_window_ref(window_ref) if window_ref else int(self._user32.GetForegroundWindow() or 0)
            rect = self._rect(hwnd)
            return rect
        return (
            int(self._user32.GetSystemMetrics(76)),
            int(self._user32.GetSystemMetrics(77)),
            int(self._user32.GetSystemMetrics(78)),
            int(self._user32.GetSystemMetrics(79)),
        )

    def _load_libraries(self) -> None:
        self._user32 = ctypes.WinDLL("user32.dll", use_last_error=True)
        self._gdi32 = ctypes.WinDLL("gdi32.dll", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        self._user32.GetForegroundWindow.restype = wintypes.HWND
        self._user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
        self._user32.EnumWindows.restype = wintypes.BOOL
        self._user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self._user32.IsWindowVisible.restype = wintypes.BOOL
        self._user32.IsWindow.argtypes = [wintypes.HWND]
        self._user32.IsWindow.restype = wintypes.BOOL
        self._user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        self._user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self._user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self._user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(_RECT)]
        self._user32.GetWindowRect.restype = wintypes.BOOL
        self._user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self._user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        self._user32.SetForegroundWindow.restype = wintypes.BOOL
        self._user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self._user32.ShowWindow.restype = wintypes.BOOL
        self._user32.IsIconic.argtypes = [wintypes.HWND]
        self._user32.IsIconic.restype = wintypes.BOOL
        self._user32.IsZoomed.argtypes = [wintypes.HWND]
        self._user32.IsZoomed.restype = wintypes.BOOL
        self._user32.GetDC.argtypes = [wintypes.HWND]
        self._user32.GetDC.restype = ctypes.c_void_p
        self._user32.ReleaseDC.argtypes = [wintypes.HWND, ctypes.c_void_p]
        self._user32.ReleaseDC.restype = ctypes.c_int
        self._gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
        self._gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
        self._gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        self._gdi32.CreateCompatibleBitmap.restype = ctypes.c_void_p
        self._gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self._gdi32.SelectObject.restype = ctypes.c_void_p
        self._gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
        self._gdi32.DeleteObject.restype = wintypes.BOOL
        self._gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
        self._gdi32.DeleteDC.restype = wintypes.BOOL
        self._gdi32.BitBlt.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
        self._gdi32.BitBlt.restype = wintypes.BOOL
        self._gdi32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.POINTER(_BITMAPINFO), wintypes.UINT]
        self._gdi32.GetDIBits.restype = ctypes.c_int
        self._kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self._kernel32.OpenProcess.restype = ctypes.c_void_p
        self._kernel32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self._kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        self._kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        self._kernel32.CloseHandle.restype = wintypes.BOOL

    def _window_from_hwnd(self, hwnd: int, active: bool, now: datetime) -> DesktopWindow | None:
        title_length = min(300, max(0, int(self._user32.GetWindowTextLengthW(hwnd))))
        title_buffer = ctypes.create_unicode_buffer(title_length + 1)
        self._user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))
        title = title_buffer.value[:300] or None
        class_buffer = ctypes.create_unicode_buffer(257)
        self._user32.GetClassNameW(hwnd, class_buffer, len(class_buffer))
        window_class = class_buffer.value[:200] or None
        process_id = wintypes.DWORD()
        self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        process_name = self._process_name(int(process_id.value))
        rect = self._rect(hwnd)
        if rect[2] <= 0 or rect[3] <= 0:
            return None
        window_ref = f"window-{uuid4()}"
        self._prune_window_refs(now)
        self._window_refs[window_ref] = _WindowHandle(
            hwnd, int(process_id.value), _fingerprint(title), window_class, now + timedelta(seconds=self.window_ref_ttl_seconds)
        )
        return DesktopWindow(window_ref, title, process_name, int(process_id.value) or None, window_class, VisualRegion(*rect), True, active)

    def _prune_window_refs(self, now: datetime | None = None) -> None:
        current = now or datetime.now(UTC)
        for reference, entry in tuple(self._window_refs.items()):
            if entry.expires_at <= current:
                self._window_refs.pop(reference, None)
        while len(self._window_refs) >= self.MAX_WINDOW_REFS:
            self._window_refs.pop(next(iter(self._window_refs)))

    def _process_name(self, process_id: int) -> str | None:
        if not process_id:
            return None
        handle = self._kernel32.OpenProcess(0x1000, False, process_id)
        if not handle:
            return None
        try:
            size = wintypes.DWORD(512)
            buffer = ctypes.create_unicode_buffer(size.value)
            if not self._kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return None
            return PureWindowsPath(buffer.value[:200]).name[:200] or None
        finally:
            self._kernel32.CloseHandle(handle)

    def _rect(self, hwnd: int) -> tuple[int, int, int, int]:
        rect = _RECT()
        if not hwnd or not self._user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return (0, 0, 0, 0)
        return (int(rect.left), int(rect.top), int(rect.right - rect.left), int(rect.bottom - rect.top))

    def _resolve_window_ref(self, window_ref: str) -> int:
        entry = self._window_refs.get(window_ref)
        if entry is None or entry.expires_at <= datetime.now(UTC):
            self._window_refs.pop(window_ref, None)
            raise ValueError("window_ref_expired")
        if not self._user32.IsWindow(entry.hwnd) or not self._user32.IsWindowVisible(entry.hwnd):
            self._window_refs.pop(window_ref, None)
            raise ValueError("window_ref_expired")
        process_id = wintypes.DWORD()
        self._user32.GetWindowThreadProcessId(entry.hwnd, ctypes.byref(process_id))
        if int(process_id.value) != entry.process_id:
            self._window_refs.pop(window_ref, None)
            raise ValueError("window_ref_expired")
        class_buffer = ctypes.create_unicode_buffer(257)
        self._user32.GetClassNameW(entry.hwnd, class_buffer, len(class_buffer))
        if (class_buffer.value[:200] or None) != entry.window_class:
            self._window_refs.pop(window_ref, None)
            raise ValueError("window_ref_changed")
        return entry.hwnd

    def _gdi_capture(self, left: int, top: int, width: int, height: int) -> TransientFrame:
        user32, gdi32 = self._user32, self._gdi32
        screen_dc = user32.GetDC(0)
        memory_dc = gdi32.CreateCompatibleDC(screen_dc)
        bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
        old_bitmap = gdi32.SelectObject(memory_dc, bitmap)
        try:
            if not gdi32.BitBlt(memory_dc, 0, 0, width, height, screen_dc, left, top, 0x00CC0020):
                raise OSError("bitblt_failed")
            info = _BITMAPINFO()
            info.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
            info.bmiHeader.biWidth = width
            info.bmiHeader.biHeight = -height
            info.bmiHeader.biPlanes = 1
            info.bmiHeader.biBitCount = 32
            info.bmiHeader.biCompression = 0
            row_stride = width * 4
            data = bytearray(row_stride * height)
            result = gdi32.GetDIBits(memory_dc, bitmap, 0, height, (ctypes.c_ubyte * len(data)).from_buffer(data), ctypes.byref(info), 0)
            if result != height:
                raise OSError("getdibits_failed")
            return TransientFrame(width, height, "BGRA32", datetime.now(UTC), VisualRegion(left, top, width, height), data)
        finally:
            if old_bitmap:
                gdi32.SelectObject(memory_dc, old_bitmap)
            if bitmap:
                gdi32.DeleteObject(bitmap)
            if memory_dc:
                gdi32.DeleteDC(memory_dc)
            if screen_dc:
                user32.ReleaseDC(0, screen_dc)


WindowsDesktopContextProvider = WindowsDesktopProvider


class _RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG), ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class _WindowHandle:
    __slots__ = ("hwnd", "process_id", "title_fingerprint", "window_class", "expires_at")

    def __init__(self, hwnd: int, process_id: int, title_fingerprint: str, window_class: str | None, expires_at: datetime) -> None:
        self.hwnd = hwnd
        self.process_id = process_id
        self.title_fingerprint = title_fingerprint
        self.window_class = window_class
        self.expires_at = expires_at


def _fingerprint(value: str | None) -> str:
    return hashlib.sha256((value or "").encode("utf-8", errors="ignore")).hexdigest()
