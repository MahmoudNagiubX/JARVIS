"""Product-owned, typed computer control with a bounded Windows backend."""

from __future__ import annotations

import asyncio
import ctypes
import csv
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import time
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4
from ctypes import wintypes

from ..authority.audit.service import DurableAuditService
from ..authority.approvals.service import DurableApprovalEngine
from ..authority.permissions.engine import PolicyPermissionEngine
from ..bus import InMemoryEventBus
from ..contracts import ApprovalRequest, AuditRecord, ComputerAction, ComputerCapability, ComputerController, ComputerResult, DeviceIdentity, Identity, ToolContext
from ..contracts.semantic_ui import SemanticDesktopAdapter, SemanticElementSnapshot, SemanticTreeNode
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository
from ..perception.windows import WindowsDesktopProvider
from .file_access import FileAccessPolicy
from .native_input import NativeInputResult, WindowsNativeInputAdapter
from .semantic_uia import WindowsUIAutomationAdapter
from .visual_ocr import EasyOcrVisualAdapter, VisualResult


class WindowsNativeComputerController:
    """Execute a small allowlisted set of local actions without a shell API."""

    SAFE_APPLICATIONS = {
        "code": "code.exe",
        "vscode": "code.exe",
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "explorer": "explorer.exe",
    }
    SAFE_STOP_PROCESSES = frozenset({"notepad.exe", "calc.exe", "calculator.exe", "code.exe"})
    MAX_CLIPBOARD_TEXT = 16_000
    MAX_KEYBOARD_TEXT = 2_000
    MAX_KEYBOARD_CHUNK_UNITS = 64
    MEDIA_KEYS = {"up": 0xAF, "down": 0xAE}

    MAX_SEMANTIC_DEPTH = 5
    DEFAULT_SEMANTIC_DEPTH = 3

    def __init__(
        self,
        *,
        perception_provider: WindowsDesktopProvider | None = None,
        semantic_adapter: SemanticDesktopAdapter | None = None,
        native_input_adapter: WindowsNativeInputAdapter | None = None,
        file_access_policy: FileAccessPolicy | None = None,
        visual_ocr_adapter: EasyOcrVisualAdapter | None = None,
    ) -> None:
        self.perception_provider = perception_provider or WindowsDesktopProvider()
        self.semantic_adapter = semantic_adapter or WindowsUIAutomationAdapter(self.perception_provider)
        self.native_input_adapter = native_input_adapter or WindowsNativeInputAdapter(self.perception_provider, self.semantic_adapter)
        # Fail-closed by default (GAP-0503): no configured roots means every
        # path-requiring file action is denied, never silently unrestricted.
        self.file_access_policy = file_access_policy or FileAccessPolicy()
        # Optional (`computer-ocr` extra) - `EasyOcrVisualAdapter.available`
        # is False when the dependency is absent; every visual_ocr_* action
        # returns a typed `visual_ocr_not_available` result rather than an
        # import-time crash (Batch 05 Milestone 1, GAP-0103).
        self.visual_ocr_adapter = visual_ocr_adapter or EasyOcrVisualAdapter(self.perception_provider, self.semantic_adapter)
        self._user32 = None
        self._kernel32 = None
        if platform.system().casefold() == "windows":
            self._load_input_libraries()

    async def execute(self, action: ComputerAction, context: ToolContext) -> ComputerResult:
        try:
            capability = ComputerCapability(action.action)
        except ValueError:
            return ComputerResult("denied", error_code="unsupported_computer_action")
        if context.device is None:
            return ComputerResult("denied", error_code="device_missing")
        if action.dry_run:
            return ComputerResult("succeeded", {"dry_run": True, "action": capability.value}, verified=True)
        if platform.system().casefold() != "windows":
            return ComputerResult("failed", error_code="windows_backend_unavailable")
        try:
            if capability is ComputerCapability.OPEN_APPLICATION:
                return await asyncio.to_thread(self._open_application, action.parameters)
            if capability is ComputerCapability.OPEN_FILE:
                return await asyncio.to_thread(self._open_path, action.parameters, "file")
            if capability is ComputerCapability.OPEN_FOLDER:
                return await asyncio.to_thread(self._open_path, action.parameters, "folder")
            if capability is ComputerCapability.LIST_PROCESSES:
                return await asyncio.to_thread(self._list_processes)
            if capability is ComputerCapability.INSPECT_FILE:
                return await asyncio.to_thread(self._inspect_file, action.parameters)
            if capability is ComputerCapability.SEARCH_FILES:
                return await asyncio.to_thread(self._search_files, action.parameters)
            if capability is ComputerCapability.STOP_SAFE_PROCESS:
                return await asyncio.to_thread(self._stop_safe_process, action.parameters)
            if capability is ComputerCapability.FOCUS_WINDOW:
                return await asyncio.to_thread(self._focus_window, action.parameters)
            if capability is ComputerCapability.WINDOW_ACTION:
                return await asyncio.to_thread(self._window_action, action.parameters)
            if capability is ComputerCapability.CHANGE_VOLUME:
                return await asyncio.to_thread(self._change_volume, action.parameters)
            if capability is ComputerCapability.MUTE:
                return await asyncio.to_thread(self._mute)
            if capability is ComputerCapability.UNMUTE:
                return await asyncio.to_thread(self._unmute)
            if capability is ComputerCapability.CLIPBOARD_READ:
                return await asyncio.to_thread(self._clipboard_read)
            if capability is ComputerCapability.CLIPBOARD_WRITE:
                return await asyncio.to_thread(self._clipboard_write, action.parameters)
            if capability is ComputerCapability.KEYBOARD_ACTION:
                return await asyncio.to_thread(self._keyboard_action, action.parameters)
            if capability is ComputerCapability.SEMANTIC_LIST_WINDOWS:
                return await self._semantic_list_windows(context)
            if capability is ComputerCapability.SEMANTIC_INSPECT_WINDOW:
                return await self._semantic_inspect_window(action.parameters)
            if capability is ComputerCapability.SEMANTIC_FIND_ELEMENTS:
                return await self._semantic_find_elements(action.parameters)
            if capability is ComputerCapability.SEMANTIC_GET_ELEMENT:
                return await self._semantic_get_element(action.parameters)
            if capability is ComputerCapability.SEMANTIC_GET_TEXT:
                return await self._semantic_get_text(action.parameters)
            if capability is ComputerCapability.SEMANTIC_REVALIDATE:
                return await self._semantic_revalidate(action.parameters)
            if capability is ComputerCapability.SEMANTIC_INVOKE:
                return await self._semantic_act("invoke", action.parameters)
            if capability is ComputerCapability.SEMANTIC_TOGGLE:
                return await self._semantic_act("toggle", action.parameters)
            if capability is ComputerCapability.SEMANTIC_SELECT:
                return await self._semantic_act("select", action.parameters)
            if capability is ComputerCapability.POINTER_MOVE_TO_ELEMENT:
                return await self._pointer_act("move_to_element", action.parameters)
            if capability is ComputerCapability.POINTER_LEFT_CLICK_ELEMENT:
                return await self._pointer_act("left_click_element", action.parameters)
            if capability is ComputerCapability.POINTER_RIGHT_CLICK_ELEMENT:
                return await self._pointer_act("right_click_element", action.parameters)
            if capability is ComputerCapability.POINTER_DOUBLE_CLICK_ELEMENT:
                return await self._pointer_act("double_click_element", action.parameters)
            if capability is ComputerCapability.POINTER_SCROLL_ELEMENT:
                return await self._pointer_scroll(action.parameters)
            if capability is ComputerCapability.POINTER_DRAG_ELEMENT_TO_ELEMENT:
                return await self._pointer_drag(action.parameters)
            if capability is ComputerCapability.KEYBOARD_KEY:
                return await self._keyboard_key(action.parameters)
            if capability is ComputerCapability.KEYBOARD_CHORD:
                return await self._keyboard_chord(action.parameters)
            if capability is ComputerCapability.VISUAL_OCR_WINDOW:
                return await self._visual_ocr_window(action.parameters)
            if capability is ComputerCapability.VISUAL_OCR_ELEMENT:
                return await self._visual_ocr_element(action.parameters)
            if capability is ComputerCapability.RESOLVE_ELEMENT_TARGET:
                return await self._resolve_element_target(action.parameters)
            if capability is ComputerCapability.RESOLVE_WINDOW_TARGET:
                return await asyncio.to_thread(self._resolve_window_target, action.parameters)
            return ComputerResult("failed", error_code="native_action_not_configured")
        except (OSError, ValueError) as exc:
            return ComputerResult("failed", error_code=str(exc) or exc.__class__.__name__)

    def _open_application(self, parameters: Mapping[str, Any]) -> ComputerResult:
        name = str(parameters.get("application", parameters.get("name", ""))).casefold().strip()
        executable = self.SAFE_APPLICATIONS.get(name)
        if executable is None:
            return ComputerResult("denied", error_code="application_not_allowlisted")
        resolved = shutil.which(executable)
        if resolved is None:
            return ComputerResult("failed", {"application": name}, "application_not_installed")
        subprocess.Popen([resolved], shell=False, close_fds=True)
        return ComputerResult("succeeded", {"application": name, "executable": resolved}, verified=True)

    def _open_path(self, parameters: Mapping[str, Any], kind: str) -> ComputerResult:
        raw_path = parameters.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("path_required")
        decision = self.file_access_policy.evaluate(raw_path)
        if not decision.allowed:
            return ComputerResult("denied", error_code=decision.reason_code)
        path = decision.resolved_path
        assert path is not None
        if not path.exists() or (kind == "file" and not path.is_file()) or (kind == "folder" and not path.is_dir()):
            return ComputerResult("failed", {"path": str(path)}, "path_not_found")
        os.startfile(str(path))
        return ComputerResult("succeeded", {"path": str(path), "kind": kind}, verified=True)

    @staticmethod
    def _list_processes() -> ComputerResult:
        result = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True,
            timeout=5, check=False, shell=False,
        )
        if result.returncode != 0:
            return ComputerResult("failed", error_code="process_list_failed")
        rows = []
        for row in csv.reader(io.StringIO(result.stdout)):
            if len(row) >= 2:
                rows.append({"image": row[0], "pid": row[1]})
            if len(rows) >= 200:
                break
        return ComputerResult("succeeded", {"processes": rows}, verified=True)

    def _inspect_file(self, parameters: Mapping[str, Any]) -> ComputerResult:
        raw_path = parameters.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("path_required")
        decision = self.file_access_policy.evaluate(raw_path)
        if not decision.allowed:
            return ComputerResult("denied", error_code=decision.reason_code)
        path = decision.resolved_path
        assert path is not None
        if not path.is_file():
            return ComputerResult("failed", error_code="file_not_found")
        if path.stat().st_size > 1_000_000:
            return ComputerResult("denied", error_code="file_too_large")
        return ComputerResult("succeeded", {"path": str(path), "content": path.read_text(encoding="utf-8", errors="replace")}, verified=True)

    def _search_files(self, parameters: Mapping[str, Any]) -> ComputerResult:
        raw_root = parameters.get("root") or parameters.get("path")
        pattern = parameters.get("pattern", "*")
        if not isinstance(raw_root, str) or not raw_root.strip():
            raise ValueError("root_required")
        if not isinstance(pattern, str) or len(pattern) > 200:
            raise ValueError("pattern_invalid")
        decision = self.file_access_policy.evaluate_search_root(raw_root)
        if not decision.allowed:
            return ComputerResult("denied", error_code=decision.reason_code)
        root = decision.resolved_path
        assert root is not None
        matches, filtered_count = self.file_access_policy.iter_search_candidates(root, pattern)
        return ComputerResult("succeeded", {"root": str(root), "matches": matches, "filtered_count": filtered_count}, verified=True)

    def _stop_safe_process(self, parameters: Mapping[str, Any]) -> ComputerResult:
        name = str(parameters.get("name", "")).casefold().strip()
        if name not in self.SAFE_STOP_PROCESSES:
            return ComputerResult("denied", error_code="process_not_allowlisted")
        result = subprocess.run(["taskkill", "/IM", name, "/T"], capture_output=True, text=True, timeout=5, check=False, shell=False)
        return ComputerResult("succeeded" if result.returncode == 0 else "failed", {"name": name, "output": result.stdout[-1000:]}, None if result.returncode == 0 else "process_stop_failed", result.returncode == 0)

    def _focus_window(self, parameters: Mapping[str, Any]) -> ComputerResult:
        if set(parameters) - {"window_ref"} or not isinstance(parameters.get("window_ref"), str):
            return ComputerResult("denied", error_code="window_ref_required")
        try:
            verified = self.perception_provider.focus_window(str(parameters["window_ref"]))
        except ValueError as exc:
            return ComputerResult("failed", error_code=str(exc))
        return ComputerResult("succeeded", {"window_ref": parameters["window_ref"]}, verified=True) if verified else ComputerResult("failed", error_code="window_focus_not_verified")

    def _window_action(self, parameters: Mapping[str, Any]) -> ComputerResult:
        if set(parameters) != {"operation", "window_ref"}:
            return ComputerResult("denied", error_code="window_action_parameters_invalid")
        operation = parameters.get("operation")
        window_ref = parameters.get("window_ref")
        if operation not in {"minimize", "maximize", "restore"} or not isinstance(window_ref, str) or not window_ref.startswith("window-"):
            return ComputerResult("denied", error_code="window_action_parameters_invalid")
        try:
            verified = self.perception_provider.window_action(window_ref, str(operation))
        except ValueError as exc:
            return ComputerResult("failed", error_code=str(exc))
        if not verified:
            return ComputerResult("failed", error_code="window_state_not_verified")
        return ComputerResult("succeeded", {"operation": operation, "window_ref": window_ref}, verified=True)

    def _change_volume(self, parameters: Mapping[str, Any]) -> ComputerResult:
        if set(parameters) != {"direction", "steps"}:
            return ComputerResult("denied", error_code="audio_parameters_invalid")
        direction = parameters.get("direction")
        steps = parameters.get("steps")
        if direction not in self.MEDIA_KEYS or not isinstance(steps, int) or isinstance(steps, bool) or not 1 <= steps <= 10:
            return ComputerResult("denied", error_code="audio_parameters_invalid")
        if self._user32 is None:
            return ComputerResult("failed", error_code="windows_audio_unavailable")
        for _ in range(steps):
            if self._send_key(self.MEDIA_KEYS[str(direction)]) != 2:
                return ComputerResult("failed", error_code="audio_input_failed")
        return ComputerResult("succeeded", {"direction": direction, "steps": steps, "verified": False}, verified=False)

    @staticmethod
    def _mute() -> ComputerResult:
        return ComputerResult("failed", error_code="audio_state_unavailable")

    @staticmethod
    def _unmute() -> ComputerResult:
        return ComputerResult("failed", error_code="audio_state_unavailable")

    def _clipboard_read(self) -> ComputerResult:
        if self._user32 is None or self._kernel32 is None:
            return ComputerResult("failed", error_code="windows_clipboard_unavailable")
        last_error = "clipboard_unavailable"
        for attempt in range(3):
            if self._user32.OpenClipboard(None):
                try:
                    handle = self._user32.GetClipboardData(13)
                    if not handle:
                        return ComputerResult("failed", error_code="clipboard_format_unavailable")
                    pointer = self._kernel32.GlobalLock(handle)
                    if not pointer:
                        last_error = "clipboard_read_failed"
                        continue
                    try:
                        text = ctypes.wstring_at(pointer)
                    finally:
                        self._kernel32.GlobalUnlock(handle)
                    if len(text) > self.MAX_CLIPBOARD_TEXT:
                        return ComputerResult("denied", error_code="clipboard_text_too_large")
                    digest = _text_digest(text)
                    return ComputerResult("succeeded", {"text": text, "length": len(text), "digest": digest, "format": "CF_UNICODETEXT"}, verified=True)
                finally:
                    self._user32.CloseClipboard()
            else:
                last_error = "clipboard_busy"
            if attempt < 2:
                time.sleep(0.01 * (attempt + 1))
        return ComputerResult("failed", error_code=last_error)

    def _clipboard_write(self, parameters: Mapping[str, Any]) -> ComputerResult:
        if set(parameters) != {"text"} or not isinstance(parameters.get("text"), str):
            return ComputerResult("denied", error_code="clipboard_text_invalid")
        text = str(parameters["text"])
        if not text or len(text) > self.MAX_CLIPBOARD_TEXT or "\x00" in text:
            return ComputerResult("denied", error_code="clipboard_text_invalid")
        if self._user32 is None or self._kernel32 is None:
            return ComputerResult("failed", error_code="windows_clipboard_unavailable")
        encoded = (text + "\x00").encode("utf-16-le")
        last_error = "clipboard_unavailable"
        for attempt in range(3):
            if self._user32.OpenClipboard(None):
                handle = self._kernel32.GlobalAlloc(0x0002, len(encoded))
                pointer = self._kernel32.GlobalLock(handle) if handle else None
                try:
                    if not handle or not pointer:
                        last_error = "clipboard_write_failed"
                        continue
                    ctypes.memmove(pointer, encoded, len(encoded))
                    self._kernel32.GlobalUnlock(handle)
                    if not self._user32.EmptyClipboard() or not self._user32.SetClipboardData(13, handle):
                        last_error = "clipboard_write_failed"
                        continue
                    verify_handle = self._user32.GetClipboardData(13)
                    verify_pointer = self._kernel32.GlobalLock(verify_handle) if verify_handle else None
                    try:
                        verified_text = ctypes.wstring_at(verify_pointer) if verify_pointer else None
                    finally:
                        if verify_pointer:
                            self._kernel32.GlobalUnlock(verify_handle)
                    if verified_text != text:
                        last_error = "clipboard_write_verification_failed"
                        handle = None
                        continue
                    handle = None
                    return ComputerResult("succeeded", {"length": len(text), "digest": _text_digest(text), "format": "CF_UNICODETEXT"}, verified=True)
                finally:
                    if pointer:
                        self._kernel32.GlobalUnlock(handle) if handle else None
                    if handle:
                        self._kernel32.GlobalFree(handle)
                    self._user32.CloseClipboard()
            else:
                last_error = "clipboard_busy"
            if attempt < 2:
                time.sleep(0.01 * (attempt + 1))
        return ComputerResult("failed", error_code=last_error)

    def _keyboard_action(self, parameters: Mapping[str, Any]) -> ComputerResult:
        if set(parameters) != {"operation", "window_ref", "text"} or parameters.get("operation") != "type_text":
            return ComputerResult("denied", error_code="keyboard_action_parameters_invalid")
        window_ref = parameters.get("window_ref")
        text = parameters.get("text")
        if not isinstance(window_ref, str) or not window_ref.startswith("window-"):
            return ComputerResult("denied", error_code="window_ref_required")
        if not isinstance(text, str) or not text or len(text) > self.MAX_KEYBOARD_TEXT or "\x00" in text:
            return ComputerResult("denied", error_code="keyboard_text_invalid")
        if self._user32 is None:
            return ComputerResult("failed", error_code="windows_keyboard_unavailable")
        try:
            hwnd = self.perception_provider.validate_input_window(window_ref)
            if not self.perception_provider.focus_window(window_ref):
                return ComputerResult("failed", error_code="window_focus_not_verified")
            hwnd = self.perception_provider.resolve_window_ref(window_ref)
            if not self.perception_provider.is_foreground(hwnd):
                return ComputerResult("failed", error_code="window_focus_not_verified")
            sent_units = 0
            units = _utf16_units(text)
            for chunk in _chunks(units, self.MAX_KEYBOARD_CHUNK_UNITS):
                if not self.perception_provider.is_foreground(hwnd):
                    return ComputerResult("failed", {"chars_sent": _chars_from_units(units[:sent_units]), "window_ref": window_ref}, "keyboard_target_changed", verified=False)
                inputs = (_unicode_inputs(chunk))
                sent = self._user32.SendInput(len(inputs), inputs, ctypes.sizeof(_INPUT))
                if int(sent) != len(inputs):
                    return ComputerResult("failed", {"chars_sent": _chars_from_units(units[:sent_units]), "window_ref": window_ref}, "keyboard_input_incomplete", verified=False)
                sent_units += len(chunk)
            return ComputerResult("succeeded", {"chars_sent": len(text), "window_ref": window_ref}, verified=False)
        except ValueError as exc:
            return ComputerResult("failed", error_code=str(exc))

    async def _semantic_list_windows(self, context: ToolContext) -> ComputerResult:
        device_id = context.device.device_id if context.device else ""
        result = await self.semantic_adapter.list_windows(device_id)
        if result.status != "succeeded":
            return ComputerResult(result.status, {}, result.error_code, False)
        windows = result.output.get("windows", ())
        payload = [
            {"window_ref": w.window_ref, "title": w.title, "process_name": w.process_name, "active": w.active}
            for w in windows
        ]
        return ComputerResult(
            "succeeded",
            {"windows": payload, "filtered_count": result.output.get("filtered_count", 0)},
            verified=True,
        )

    async def _semantic_inspect_window(self, parameters: Mapping[str, Any]) -> ComputerResult:
        if set(parameters) - {"window_ref", "depth"} or not isinstance(parameters.get("window_ref"), str):
            return ComputerResult("denied", error_code="window_ref_required")
        window_ref = str(parameters["window_ref"])
        if not window_ref.startswith("window-"):
            return ComputerResult("denied", error_code="window_ref_required")
        depth = parameters.get("depth", self.DEFAULT_SEMANTIC_DEPTH)
        if not isinstance(depth, int) or isinstance(depth, bool) or not 1 <= depth <= self.MAX_SEMANTIC_DEPTH:
            return ComputerResult("denied", error_code="semantic_depth_invalid")
        result = await self.semantic_adapter.inspect_window(window_ref, depth=depth)
        if result.status != "succeeded":
            return ComputerResult(result.status, {}, result.error_code, False)
        tree = result.output.get("tree")
        payload = {
            "tree": _semantic_tree_dict(tree) if tree is not None else None,
            "element_count": result.output.get("element_count", 0),
            "truncated": bool(result.output.get("truncated", False)),
        }
        return ComputerResult("succeeded", payload, verified=True)

    async def _semantic_find_elements(self, parameters: Mapping[str, Any]) -> ComputerResult:
        allowed_keys = {"window_ref", "control_type", "name", "automation_id"}
        if set(parameters) - allowed_keys or not isinstance(parameters.get("window_ref"), str):
            return ComputerResult("denied", error_code="window_ref_required")
        window_ref = str(parameters["window_ref"])
        if not window_ref.startswith("window-"):
            return ComputerResult("denied", error_code="window_ref_required")
        control_type = parameters.get("control_type")
        name = parameters.get("name")
        automation_id = parameters.get("automation_id")
        if control_type is None and name is None and automation_id is None:
            return ComputerResult("denied", error_code="semantic_find_filter_required")
        result = await self.semantic_adapter.find_elements(
            window_ref,
            control_type=control_type if isinstance(control_type, str) else None,
            name=name if isinstance(name, str) else None,
            automation_id=automation_id if isinstance(automation_id, str) else None,
        )
        if result.status != "succeeded":
            return ComputerResult(result.status, {}, result.error_code, False)
        matches = result.output.get("matches", ())
        payload = {
            "matches": [_semantic_snapshot_dict(item) for item in matches],
            "ambiguous": bool(result.output.get("ambiguous", False)),
        }
        return ComputerResult("succeeded", payload, verified=True)

    async def _semantic_get_element(self, parameters: Mapping[str, Any]) -> ComputerResult:
        element_ref = self._require_element_ref(parameters)
        if element_ref is None:
            return ComputerResult("denied", error_code="element_ref_required")
        result = await self.semantic_adapter.get_element(element_ref)
        if result.status != "succeeded":
            return ComputerResult(result.status, {}, result.error_code, False)
        return ComputerResult("succeeded", {"element": _semantic_snapshot_dict(result.output["element"])}, verified=True)

    async def _semantic_get_text(self, parameters: Mapping[str, Any]) -> ComputerResult:
        element_ref = self._require_element_ref(parameters)
        if element_ref is None:
            return ComputerResult("denied", error_code="element_ref_required")
        result = await self.semantic_adapter.get_text_or_value(element_ref)
        if result.status != "succeeded":
            return ComputerResult(result.status, {}, result.error_code, False)
        return ComputerResult(
            "succeeded",
            {"text": result.output.get("text"), "truncated": bool(result.output.get("truncated", False))},
            verified=True,
        )

    async def _semantic_revalidate(self, parameters: Mapping[str, Any]) -> ComputerResult:
        element_ref = self._require_element_ref(parameters)
        if element_ref is None:
            return ComputerResult("denied", error_code="element_ref_required")
        result = await self.semantic_adapter.revalidate_reference(element_ref)
        payload: dict[str, Any] = {"state": result.output.get("state") if isinstance(result.output, Mapping) else None}
        element = result.output.get("element") if isinstance(result.output, Mapping) else None
        if element is not None:
            payload["element"] = _semantic_snapshot_dict(element)
        return ComputerResult(result.status, payload, result.error_code, verified=result.status == "succeeded")

    async def _semantic_act(self, pattern: str, parameters: Mapping[str, Any]) -> ComputerResult:
        element_ref = self._require_element_ref(parameters)
        if element_ref is None:
            return ComputerResult("denied", error_code="element_ref_required")
        method = getattr(self.semantic_adapter, pattern)
        result = await method(element_ref)
        if result.status != "succeeded":
            return ComputerResult(result.status, {}, result.error_code, False)
        output = dict(result.output)
        verified = bool(output.pop("verified", False))
        element = output.pop("element", None)
        payload: dict[str, Any] = dict(output)
        if element is not None:
            payload["element"] = _semantic_snapshot_dict(element)
        return ComputerResult("succeeded", payload, verified=verified)

    async def _pointer_act(self, action: str, parameters: Mapping[str, Any]) -> ComputerResult:
        element_ref = self._require_element_ref(parameters)
        if element_ref is None:
            return ComputerResult("denied", error_code="element_ref_required")
        method = getattr(self.native_input_adapter, action)
        result: NativeInputResult = await method(element_ref)
        return ComputerResult(result.status, dict(result.output), result.error_code, result.verified)

    async def _pointer_scroll(self, parameters: Mapping[str, Any]) -> ComputerResult:
        allowed_keys = {"element_ref", "direction", "steps"}
        if set(parameters) != allowed_keys:
            return ComputerResult("denied", error_code="scroll_parameters_invalid")
        element_ref = parameters.get("element_ref")
        direction = parameters.get("direction")
        steps = parameters.get("steps")
        if not isinstance(element_ref, str) or not element_ref.startswith("element-"):
            return ComputerResult("denied", error_code="element_ref_required")
        if direction not in ("up", "down"):
            return ComputerResult("denied", error_code="native_input_scroll_direction_invalid")
        if not isinstance(steps, int) or isinstance(steps, bool) or not 1 <= steps <= 5:
            return ComputerResult("denied", error_code="native_input_scroll_steps_invalid")
        result: NativeInputResult = await self.native_input_adapter.scroll_element(element_ref, direction, steps)
        return ComputerResult(result.status, dict(result.output), result.error_code, result.verified)

    async def _pointer_drag(self, parameters: Mapping[str, Any]) -> ComputerResult:
        if set(parameters) != {"source_element_ref", "target_element_ref"}:
            return ComputerResult("denied", error_code="drag_parameters_invalid")
        source_ref = parameters.get("source_element_ref")
        target_ref = parameters.get("target_element_ref")
        if not isinstance(source_ref, str) or not source_ref.startswith("element-"):
            return ComputerResult("denied", error_code="element_ref_required")
        if not isinstance(target_ref, str) or not target_ref.startswith("element-"):
            return ComputerResult("denied", error_code="element_ref_required")
        result: NativeInputResult = await self.native_input_adapter.drag_element_to_element(source_ref, target_ref)
        return ComputerResult(result.status, dict(result.output), result.error_code, result.verified)

    async def _keyboard_chord(self, parameters: Mapping[str, Any]) -> ComputerResult:
        if set(parameters) != {"window_ref", "chord"}:
            return ComputerResult("denied", error_code="keyboard_chord_parameters_invalid")
        window_ref = parameters.get("window_ref")
        chord = parameters.get("chord")
        if not isinstance(window_ref, str) or not window_ref.startswith("window-"):
            return ComputerResult("denied", error_code="window_ref_required")
        if not isinstance(chord, str):
            return ComputerResult("denied", error_code="native_input_chord_not_allowed")
        result: NativeInputResult = await self.native_input_adapter.press_chord(window_ref, chord)
        return ComputerResult(result.status, dict(result.output), result.error_code, result.verified)

    async def _keyboard_key(self, parameters: Mapping[str, Any]) -> ComputerResult:
        allowed_keys = {"window_ref", "key", "modifiers"}
        if set(parameters) - allowed_keys or "window_ref" not in parameters or "key" not in parameters:
            return ComputerResult("denied", error_code="keyboard_key_parameters_invalid")
        window_ref = parameters.get("window_ref")
        key = parameters.get("key")
        modifiers = parameters.get("modifiers", [])
        if not isinstance(window_ref, str) or not window_ref.startswith("window-"):
            return ComputerResult("denied", error_code="window_ref_required")
        if not isinstance(key, str):
            return ComputerResult("denied", error_code="native_input_key_not_allowed")
        if not isinstance(modifiers, list) or not all(isinstance(item, str) for item in modifiers):
            return ComputerResult("denied", error_code="native_input_key_not_allowed")
        result: NativeInputResult = await self.native_input_adapter.press_key(window_ref, key, tuple(modifiers))
        return ComputerResult(result.status, dict(result.output), result.error_code, result.verified)

    async def _visual_ocr_window(self, parameters: Mapping[str, Any]) -> ComputerResult:
        if set(parameters) != {"window_ref"} or not isinstance(parameters.get("window_ref"), str):
            return ComputerResult("denied", error_code="window_ref_required")
        window_ref = parameters["window_ref"]
        if not window_ref.startswith("window-"):
            return ComputerResult("denied", error_code="window_ref_required")
        result: VisualResult = await self.visual_ocr_adapter.ocr_window(window_ref)
        return ComputerResult(result.status, result.output, result.error_code, result.verified)

    async def _visual_ocr_element(self, parameters: Mapping[str, Any]) -> ComputerResult:
        element_ref = self._require_element_ref(parameters)
        if element_ref is None:
            return ComputerResult("denied", error_code="element_ref_required")
        result: VisualResult = await self.visual_ocr_adapter.ocr_element(element_ref)
        return ComputerResult(result.status, result.output, result.error_code, result.verified)

    async def _resolve_element_target(self, parameters: Mapping[str, Any]) -> ComputerResult:
        """Internal-only: fresh, trusted, actuation-grade element target
        descriptor (R18B02-001/002). Never reachable through any tool
        schema - only `ComputerActionService` calls this, to build an
        element-targeted approval preview/binding."""
        element_ref = self._require_element_ref(parameters)
        if element_ref is None:
            return ComputerResult("denied", error_code="element_ref_required")
        result = await self.semantic_adapter.resolve_actionable_target(element_ref)
        if result.status != "succeeded":
            return ComputerResult(result.status, {}, result.error_code, False)
        element = result.output["element"]
        payload = {
            "element": _semantic_snapshot_dict(element),
            "reference_expires_at": result.output.get("reference_expires_at"),
        }
        return ComputerResult("succeeded", payload, verified=True)

    def _resolve_window_target(self, parameters: Mapping[str, Any]) -> ComputerResult:
        """Internal-only: fresh, trusted window target descriptor
        (R18B02-003), built from the existing `WindowsDesktopProvider`
        window-reference store - no second reference store. Never reachable
        through any tool schema."""
        if set(parameters) != {"window_ref"} or not isinstance(parameters.get("window_ref"), str):
            return ComputerResult("denied", error_code="window_ref_required")
        try:
            descriptor = self.perception_provider.describe_window(str(parameters["window_ref"]))
        except ValueError as exc:
            reason = str(exc) or "window_ref_expired"
            status = "denied" if reason in {"sensitive_window_denied"} else "failed"
            return ComputerResult(status, {}, reason, False)
        return ComputerResult("succeeded", dict(descriptor), verified=True)

    @staticmethod
    def _require_element_ref(parameters: Mapping[str, Any]) -> str | None:
        if set(parameters) != {"element_ref"}:
            return None
        element_ref = parameters.get("element_ref")
        if not isinstance(element_ref, str) or not element_ref.startswith("element-"):
            return None
        return element_ref

    def _load_input_libraries(self) -> None:
        self._user32 = ctypes.WinDLL("user32.dll", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        self._user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
        self._user32.SendInput.restype = wintypes.UINT
        self._user32.OpenClipboard.argtypes = [wintypes.HWND]
        self._user32.OpenClipboard.restype = wintypes.BOOL
        self._user32.CloseClipboard.restype = wintypes.BOOL
        self._user32.GetClipboardData.argtypes = [wintypes.UINT]
        self._user32.GetClipboardData.restype = wintypes.HANDLE
        self._user32.EmptyClipboard.restype = wintypes.BOOL
        self._user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        self._user32.SetClipboardData.restype = wintypes.HANDLE
        self._kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        self._kernel32.GlobalLock.restype = ctypes.c_void_p
        self._kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        self._kernel32.GlobalUnlock.restype = wintypes.BOOL
        self._kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        self._kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        self._kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
        self._kernel32.GlobalFree.restype = wintypes.HGLOBAL

    def _send_key(self, virtual_key: int) -> int:
        inputs = (_INPUT * 2)(
            _key_input(virtual_key, 0),
            _key_input(virtual_key, 0x0002),
        )
        return int(self._user32.SendInput(2, inputs, ctypes.sizeof(_INPUT)))


class ComputerActionService:
    """Common permission, audit, event, and controller boundary."""

    _read_actions = frozenset({
        ComputerCapability.LIST_PROCESSES.value,
        ComputerCapability.INSPECT_FILE.value,
        ComputerCapability.SEARCH_FILES.value,
        ComputerCapability.SCREEN_SNAPSHOT_ON_DEMAND.value,
        ComputerCapability.CLIPBOARD_READ.value,
        ComputerCapability.SEMANTIC_LIST_WINDOWS.value,
        ComputerCapability.SEMANTIC_INSPECT_WINDOW.value,
        ComputerCapability.SEMANTIC_FIND_ELEMENTS.value,
        ComputerCapability.SEMANTIC_GET_ELEMENT.value,
        ComputerCapability.SEMANTIC_GET_TEXT.value,
        ComputerCapability.SEMANTIC_REVALIDATE.value,
        ComputerCapability.VISUAL_OCR_WINDOW.value,
        ComputerCapability.VISUAL_OCR_ELEMENT.value,
    })
    _safe_actions = frozenset({
        ComputerCapability.OPEN_APPLICATION.value,
        ComputerCapability.CHANGE_VOLUME.value,
        ComputerCapability.MUTE.value,
        ComputerCapability.UNMUTE.value,
        ComputerCapability.OPEN_FILE.value,
        ComputerCapability.OPEN_FOLDER.value,
        ComputerCapability.STOP_SAFE_PROCESS.value,
        ComputerCapability.SEARCH_FILES.value,
        ComputerCapability.FOCUS_WINDOW.value,
    })
    # Every action grounded by an element_ref requires a target-aware,
    # time-bounded approval (R18B01-004, generalized by R18B02-001): the
    # preview shown to the approver, and the deadline the approval can live
    # under, must both be derived from a fresh trusted observation of the
    # target rather than model-supplied text. Any new element-targeted
    # pointer action must be added here too.
    _element_targeted_actions = frozenset({
        ComputerCapability.SEMANTIC_INVOKE.value,
        ComputerCapability.SEMANTIC_TOGGLE.value,
        ComputerCapability.SEMANTIC_SELECT.value,
        ComputerCapability.POINTER_MOVE_TO_ELEMENT.value,
        ComputerCapability.POINTER_LEFT_CLICK_ELEMENT.value,
        ComputerCapability.POINTER_RIGHT_CLICK_ELEMENT.value,
        ComputerCapability.POINTER_DOUBLE_CLICK_ELEMENT.value,
        ComputerCapability.POINTER_SCROLL_ELEMENT.value,
    })
    # Every action grounded by a window_ref (not an element_ref) instead
    # gets a trusted WINDOW-target preview/binding (R18B02-003): a bounded
    # window title/process name, never an opaque window_ref alone.
    _window_targeted_actions = frozenset({
        ComputerCapability.KEYBOARD_ACTION.value,
        ComputerCapability.KEYBOARD_KEY.value,
        ComputerCapability.KEYBOARD_CHORD.value,
    })
    # Two-target action (Batch 04 Milestone 1): a drag has a source AND a
    # target element, so it cannot be forced into the single-target element
    # digest above - it gets its own dual-target preview/binding
    # (`_drag_target_preview`) that describes and binds BOTH endpoints.
    _dual_target_actions = frozenset({
        ComputerCapability.POINTER_DRAG_ELEMENT_TO_ELEMENT.value,
    })

    def __init__(
        self,
        controller: ComputerController,
        repository: RuntimeRepository,
        event_bus: InMemoryEventBus,
        permission: PolicyPermissionEngine,
        audit: DurableAuditService,
        approvals: DurableApprovalEngine | None = None,
    ) -> None:
        self.controller = controller
        self.repository = repository
        self.event_bus = event_bus
        self.permission = permission
        self.audit = audit
        self.approvals = approvals
        # Trailing elements carry the trusted target-identity digest (None
        # for a plain generic-preview approval) and which kind of target it
        # binds to ("element" | "window" | None) so `decide()` can detect a
        # target swapped out from under a pending approval and re-validate
        # it the right way (R18B01-004, generalized by R18B02-001/003).
        self._pending: dict[str, tuple[ComputerAction, Identity, DeviceIdentity, DeviceIdentity, str, datetime, str | None, str | None]] = {}
        self.MAX_PENDING = 32

    async def execute(
        self,
        action: ComputerAction,
        identity: Identity,
        device: DeviceIdentity,
        *,
        target_device: DeviceIdentity | None = None,
        execution_adapter: str | None = None,
        session_id: str = "computer",
        correlation_id: str | None = None,
    ) -> ComputerResult:
        correlation = correlation_id or f"computer-{uuid4()}"
        target = target_device or device
        adapter = execution_adapter or "local"
        self._prune_pending()
        if target.owner_id != identity.owner_id:
            await self._audit(
                identity,
                device,
                correlation,
                "computer.target_rejected",
                "denied",
                {
                    "action": action.action,
                    "request_device_id": device.device_id,
                    "target_device_id": target.device_id,
                    "execution_adapter": adapter,
                    "reason": "target_owner_mismatch",
                },
            )
            return ComputerResult("denied", error_code="target_owner_mismatch")
        capability = f"computer.{action.action}"
        required = "computer.observe" if action.action in self._read_actions else "computer.input"
        decision = await self.permission.evaluate(identity, device, capability, {
            "required_scope": "tool.request",
            "required_capabilities": frozenset({required}),
            "risk_level": "read" if action.action in self._read_actions or action.action in self._safe_actions else "consequential",
        })
        await self._audit(
            identity,
            device,
            correlation,
            "computer.permission_checked",
            decision.effect.value,
            {
                "action": action.action,
                "request_device_id": device.device_id,
                "target_device_id": target.device_id,
                "execution_adapter": adapter,
                "reason": decision.reason_code,
            },
        )
        if decision.effect.value != "allow":
            if decision.effect.value == "require_approval" and self.approvals is not None:
                if len(self._pending) >= self.MAX_PENDING:
                    await self._emit(
                        "computer.action_failed",
                        identity.owner_id,
                        correlation,
                        {"action": action.action, "reason": "computer_pending_store_full"},
                        EventState.FAILED,
                    )
                    return ComputerResult("failed", error_code="computer_pending_store_full")
                identity_digest: str | None = None
                target_kind: str | None = None
                preview: dict[str, object]
                now = datetime.now(UTC)
                expires_at = now + timedelta(minutes=10)
                if (
                    action.action in self._element_targeted_actions
                    or action.action in self._window_targeted_actions
                    or action.action in self._dual_target_actions
                ):
                    if action.action in self._element_targeted_actions:
                        target_kind = "element"
                        target_preview, identity_digest, preview_error, reference_expires_at = await self._element_target_preview(
                            action, identity, target, adapter, session_id, correlation,
                        )
                    elif action.action in self._dual_target_actions:
                        target_kind = "drag"
                        target_preview, identity_digest, preview_error, reference_expires_at = await self._drag_target_preview(
                            action, identity, target, adapter, session_id, correlation,
                        )
                    else:
                        target_kind = "window"
                        target_preview, identity_digest, preview_error, reference_expires_at = await self._window_target_preview(
                            action, identity, target, adapter, session_id, correlation,
                        )
                    if target_preview is None:
                        await self._audit(
                            identity,
                            device,
                            correlation,
                            "computer.approval_refused",
                            "denied",
                            {"action": action.action, "reason": preview_error},
                        )
                        await self._emit(
                            "computer.action_failed",
                            identity.owner_id,
                            correlation,
                            {"action": action.action, "reason": preview_error},
                            EventState.FAILED,
                        )
                        return ComputerResult("denied", error_code=preview_error)
                    preview = target_preview
                    # The approval can never legitimately outlive the actual
                    # target reference it binds to - computed once here from
                    # a fresh trusted read, never re-derived from a global
                    # constant (R18B02-002). Nothing later recomputes this:
                    # any subsequent unrelated re-read of the same reference
                    # (e.g. a UI "polling" the preview again) cannot extend
                    # an already-created approval's stored deadline.
                    if reference_expires_at is not None:
                        expires_at = min(expires_at, reference_expires_at)
                else:
                    preview = self._approval_preview(action)
                approval_id = f"approval-{uuid4()}"
                await self.approvals.request(ApprovalRequest(approval_id, capability, identity.owner_id, device.device_id, "computer action requires approval", now, expires_at, preview))
                self._pending[approval_id] = (action, identity, device, target, adapter, expires_at, identity_digest, target_kind)
                await self._emit(
                    "computer.action_requested",
                    identity.owner_id,
                    correlation,
                    {
                        "action": action.action,
                        "approval_id": approval_id,
                        "request_device_id": device.device_id,
                        "target_device_id": target.device_id,
                        "execution_adapter": adapter,
                    },
                    EventState.ACCEPTED,
                )
                return ComputerResult("approval_required", error_code=decision.reason_code, approval_id=approval_id)
            await self._emit("computer.action_failed", identity.owner_id, correlation, {"action": action.action, "reason": decision.reason_code}, EventState.FAILED)
            return ComputerResult("approval_required" if decision.effect.value == "require_approval" else "denied", error_code=decision.reason_code)
        return await self._execute_controller(action, identity, device, target, adapter, session_id, correlation)

    async def decide(
        self,
        approval_id: str,
        approved: bool,
        decided_by: str,
        *,
        identity: Identity | None = None,
        device: DeviceIdentity | None = None,
    ) -> ComputerResult:
        pending = self._pending.get(approval_id)
        if pending is None or self.approvals is None:
            # Missing/stale in-memory pending approval (restart, or already
            # consumed by a prior decide) must degrade truthfully, matching the
            # Browser/Home approval-path convention, not raise a raw KeyError.
            return ComputerResult("failed", error_code="pending_action_unavailable_after_restart", verified=False, approval_id=approval_id)
        action, pending_identity, pending_device, target, adapter, _expires_at, identity_digest, target_kind = pending
        if identity is not None and identity.owner_id != pending_identity.owner_id:
            raise PermissionError("approval_owner_mismatch")
        if device is not None and device.device_id != pending_device.device_id:
            raise PermissionError("approval_device_mismatch")
        decision = await self.approvals.decide(approval_id, approved, decided_by)
        self._pending.pop(approval_id, None)
        if decision.status.value == "expired":
            return ComputerResult("denied", error_code="approval_expired", approval_id=approval_id)
        if decision.status.value != "approved":
            return ComputerResult("denied", error_code=decision.status.value, approval_id=approval_id)
        correlation = f"computer-{approval_id}"
        if identity_digest is not None:
            if target_kind == "window":
                _preview, fresh_digest, preview_error, _exp = await self._window_target_preview(
                    action, pending_identity, target, adapter, "computer", correlation,
                )
            elif target_kind == "drag":
                _preview, fresh_digest, preview_error, _exp = await self._drag_target_preview(
                    action, pending_identity, target, adapter, "computer", correlation,
                )
            else:
                _preview, fresh_digest, preview_error, _exp = await self._element_target_preview(
                    action, pending_identity, target, adapter, "computer", correlation,
                )
            if fresh_digest is None:
                await self._audit(
                    pending_identity,
                    pending_device,
                    correlation,
                    "computer.approval_refused",
                    "denied",
                    {"action": action.action, "reason": preview_error},
                )
                return ComputerResult("denied", error_code=preview_error, approval_id=approval_id)
            if fresh_digest != identity_digest:
                reason = "approval_target_changed"
                if target_kind == "drag":
                    # Distinguish which endpoint specifically changed, per
                    # the dual-target composite digest ("source|target").
                    old_parts = identity_digest.split("|", 1)
                    new_parts = fresh_digest.split("|", 1)
                    if len(old_parts) == 2 and len(new_parts) == 2 and old_parts[0] != new_parts[0]:
                        reason = "drag_source_changed"
                    else:
                        reason = "drag_target_changed"
                await self._audit(
                    pending_identity,
                    pending_device,
                    correlation,
                    "computer.approval_refused",
                    "denied",
                    {"action": action.action, "reason": reason},
                )
                return ComputerResult("denied", error_code=reason, approval_id=approval_id)
        return await self._execute_controller(action, pending_identity, pending_device, target, adapter, "computer", correlation, approval_id)

    def close(self) -> None:
        self._pending.clear()

    def _prune_pending(self) -> None:
        now = datetime.now(UTC)
        for approval_id, pending in tuple(self._pending.items()):
            if pending[5] <= now:
                self._pending.pop(approval_id, None)

    @staticmethod
    def _approval_preview(action: ComputerAction) -> dict[str, object]:
        parameters = dict(action.parameters)
        sensitive = action.action == ComputerCapability.CLIPBOARD_WRITE.value
        if not sensitive:
            return {"action": action.action, "parameters": parameters}
        return {
            "action": action.action,
            "text_length": len(parameters.get("text", "")) if isinstance(parameters.get("text"), str) else None,
            "parameter_digest": _mapping_digest(parameters),
        }

    async def _element_target_preview(
        self,
        action: ComputerAction,
        identity: Identity,
        target_device: DeviceIdentity,
        adapter: str,
        session_id: str,
        correlation: str,
    ) -> tuple[dict[str, object] | None, str | None, str | None, datetime | None]:
        """Fetch a fresh, trusted preview of an element-targeted action via
        the internal-only `resolve_element_target` capability (never a
        second adapter access point) and derive a bounded identity digest
        from it. Returns (preview, identity_digest, error_code,
        reference_expires_at) - preview/digest/expiry are None and
        error_code is set whenever the target must not be approved
        (R18B01-004, generalized by R18B02-001/002)."""
        element_ref = action.parameters.get("element_ref") if isinstance(action.parameters, Mapping) else None
        if not isinstance(element_ref, str) or not element_ref.startswith("element-"):
            return None, None, "element_ref_required", None
        metadata = {
            "request_device_id": target_device.device_id,
            "target_device_id": target_device.device_id,
            "execution_adapter": adapter,
        }
        resolve_action = ComputerAction(ComputerCapability.RESOLVE_ELEMENT_TARGET.value, {"element_ref": element_ref}, dry_run=False)
        result = await self.controller.execute(resolve_action, ToolContext(identity, target_device, session_id, correlation, metadata=metadata))
        if result.status != "succeeded":
            return None, None, result.error_code or "uia_target_unavailable", None
        element = result.output.get("element") if isinstance(result.output, Mapping) else None
        if not isinstance(element, Mapping) or not element.get("actionable", False):
            return None, None, "uia_target_not_actionable", None
        name = element.get("name")
        bounded_name = name[:80] if isinstance(name, str) else None
        preview = {
            "action": action.action,
            "control_type": element.get("control_type"),
            "automation_id": element.get("automation_id"),
            "name": bounded_name,
            "window_ref": element.get("window_ref"),
            "element_ref": element_ref,
        }
        identity_digest = _mapping_digest({
            "element_ref": element_ref,
            "window_ref": element.get("window_ref"),
            "control_type": element.get("control_type"),
            "automation_id": element.get("automation_id"),
            "name": element.get("name"),
        })
        reference_expires_at = result.output.get("reference_expires_at") if isinstance(result.output, Mapping) else None
        return preview, identity_digest, None, reference_expires_at

    async def _resolve_drag_endpoint(
        self,
        element_ref: str,
        identity: Identity,
        target_device: DeviceIdentity,
        adapter: str,
        session_id: str,
        correlation: str,
    ) -> tuple[tuple[Mapping[str, Any], str, datetime | None] | None, str | None]:
        """One drag endpoint's fresh trusted descriptor + identity digest,
        via the same internal-only `resolve_element_target` capability
        `_element_target_preview` uses - no second resolution path."""
        metadata = {
            "request_device_id": target_device.device_id,
            "target_device_id": target_device.device_id,
            "execution_adapter": adapter,
        }
        resolve_action = ComputerAction(ComputerCapability.RESOLVE_ELEMENT_TARGET.value, {"element_ref": element_ref}, dry_run=False)
        result = await self.controller.execute(resolve_action, ToolContext(identity, target_device, session_id, correlation, metadata=metadata))
        if result.status != "succeeded":
            return None, result.error_code or "uia_target_unavailable"
        element = result.output.get("element") if isinstance(result.output, Mapping) else None
        if not isinstance(element, Mapping) or not element.get("actionable", False):
            return None, "uia_target_not_actionable"
        digest = _mapping_digest({
            "element_ref": element_ref,
            "window_ref": element.get("window_ref"),
            "control_type": element.get("control_type"),
            "automation_id": element.get("automation_id"),
            "name": element.get("name"),
        })
        reference_expires_at = result.output.get("reference_expires_at") if isinstance(result.output, Mapping) else None
        return (dict(element), digest, reference_expires_at), None

    async def _drag_target_preview(
        self,
        action: ComputerAction,
        identity: Identity,
        target_device: DeviceIdentity,
        adapter: str,
        session_id: str,
        correlation: str,
    ) -> tuple[dict[str, object] | None, str | None, str | None, datetime | None]:
        """Fetch fresh, trusted previews of BOTH the drag source and drag
        target elements (Batch 04 Milestone 1) - a two-target action must
        never be forced into a single-target digest. Returns (preview,
        identity_digest, error_code, reference_expires_at); identity_digest
        is a composite ``"source_digest|target_digest"`` string so `decide()`
        can tell which endpoint specifically changed on resume. Both
        endpoints must belong to the same trusted window - cross-window drag
        is refused with `drag_cross_window_not_supported` rather than
        silently resolved."""
        parameters = action.parameters if isinstance(action.parameters, Mapping) else {}
        source_ref = parameters.get("source_element_ref")
        target_ref = parameters.get("target_element_ref")
        if not isinstance(source_ref, str) or not source_ref.startswith("element-"):
            return None, None, "element_ref_required", None
        if not isinstance(target_ref, str) or not target_ref.startswith("element-"):
            return None, None, "element_ref_required", None
        source_info, source_error = await self._resolve_drag_endpoint(source_ref, identity, target_device, adapter, session_id, correlation)
        if source_info is None:
            return None, None, source_error or "drag_source_stale", None
        target_info, target_error = await self._resolve_drag_endpoint(target_ref, identity, target_device, adapter, session_id, correlation)
        if target_info is None:
            return None, None, target_error or "drag_target_stale", None
        source_element, source_digest, source_expiry = source_info
        target_element, target_digest, target_expiry = target_info
        if source_element.get("window_ref") != target_element.get("window_ref"):
            return None, None, "drag_cross_window_not_supported", None

        def _bounded(descriptor: Mapping[str, Any]) -> dict[str, object]:
            name = descriptor.get("name")
            return {
                "name": name[:80] if isinstance(name, str) else None,
                "control_type": descriptor.get("control_type"),
                "automation_id": descriptor.get("automation_id"),
                "window_ref": descriptor.get("window_ref"),
            }

        preview: dict[str, object] = {
            "action": action.action,
            "source": _bounded(source_element),
            "target": _bounded(target_element),
        }
        identity_digest = f"{source_digest}|{target_digest}"
        expiries = [value for value in (source_expiry, target_expiry) if value is not None]
        reference_expires_at = min(expiries) if expiries else None
        return preview, identity_digest, None, reference_expires_at

    async def _window_target_preview(
        self,
        action: ComputerAction,
        identity: Identity,
        target_device: DeviceIdentity,
        adapter: str,
        session_id: str,
        correlation: str,
    ) -> tuple[dict[str, object] | None, str | None, str | None, datetime | None]:
        """Fetch a fresh, trusted preview of a window-targeted native-input
        action via the internal-only `resolve_window_target` capability,
        built from the existing `WindowsDesktopProvider` window-reference
        store (R18B02-003) - never a raw PID/HWND, never model-supplied
        title/process text, never raw typed text for literal keyboard
        input."""
        window_ref = action.parameters.get("window_ref") if isinstance(action.parameters, Mapping) else None
        if not isinstance(window_ref, str) or not window_ref.startswith("window-"):
            return None, None, "window_ref_required", None
        metadata = {
            "request_device_id": target_device.device_id,
            "target_device_id": target_device.device_id,
            "execution_adapter": adapter,
        }
        describe_action = ComputerAction(ComputerCapability.RESOLVE_WINDOW_TARGET.value, {"window_ref": window_ref}, dry_run=False)
        result = await self.controller.execute(describe_action, ToolContext(identity, target_device, session_id, correlation, metadata=metadata))
        if result.status != "succeeded":
            return None, None, result.error_code or "window_target_unavailable", None
        descriptor = result.output if isinstance(result.output, Mapping) else {}
        title = descriptor.get("title")
        bounded_title = title[:80] if isinstance(title, str) else None
        parameters = dict(action.parameters)
        preview: dict[str, object] = {
            "action": action.action,
            "window_title": bounded_title,
            "process_name": descriptor.get("process_name"),
            "window_ref": window_ref,
        }
        if action.action == ComputerCapability.KEYBOARD_ACTION.value:
            preview["operation"] = parameters.get("operation")
            text = parameters.get("text")
            # Never the raw typed text in durable approval data - only its
            # bounded length and a digest (existing ephemeral-argument
            # behavior is unchanged; this only adds the trusted window
            # identity alongside it).
            preview["text_length"] = len(text) if isinstance(text, str) else None
            preview["text_digest"] = _text_digest(text) if isinstance(text, str) else None
        elif action.action == ComputerCapability.KEYBOARD_CHORD.value:
            preview["chord"] = parameters.get("chord")
        else:
            preview["key"] = parameters.get("key")
            modifiers = parameters.get("modifiers")
            if modifiers:
                preview["modifiers"] = list(modifiers)
        identity_digest = descriptor.get("identity_digest")
        reference_expires_at = descriptor.get("expires_at")
        return preview, identity_digest, None, reference_expires_at

    async def _execute_controller(
        self,
        action: ComputerAction,
        identity: Identity,
        request_device: DeviceIdentity,
        target_device: DeviceIdentity,
        adapter: str,
        session_id: str,
        correlation: str,
        approval_id: str | None = None,
    ) -> ComputerResult:
        metadata = {
            "request_device_id": request_device.device_id,
            "target_device_id": target_device.device_id,
            "execution_adapter": adapter,
        }
        await self._emit("computer.action_requested", identity.owner_id, correlation, {"action": action.action, **metadata})
        await self._emit("computer.action_started", identity.owner_id, correlation, {"action": action.action, **metadata}, EventState.ACCEPTED)
        result = await self.controller.execute(action, ToolContext(identity, target_device, session_id, correlation, metadata=metadata))
        event = "computer.action_completed" if result.status == "succeeded" else "computer.action_failed"
        await self._emit(event, identity.owner_id, correlation, {"action": action.action, "error_code": result.error_code, **metadata}, EventState.COMPLETED if result.status == "succeeded" else EventState.FAILED)
        await self._audit(identity, request_device, correlation, event, result.status, {"action": action.action, "error_code": result.error_code, **metadata})
        return ComputerResult(result.status, result.output, result.error_code, result.verified, approval_id)

    async def _audit(self, identity: Identity, device: DeviceIdentity, correlation: str, event_type: str, outcome: str, metadata: dict[str, object]) -> None:
        await self.audit.record(AuditRecord(f"audit-{uuid4()}", event_type, datetime.now(UTC), identity.identity_id, device.device_id, correlation, outcome, None, metadata))

    async def _emit(self, event_type: str, owner_id: str, correlation: str, payload: dict[str, object], state: EventState = EventState.EMITTED) -> None:
        event = Event.create(event_type, EventCategory.COMPUTER, correlation_id=correlation, actor_id=owner_id, payload=payload, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _INPUT_UNION(ctypes.Union):
    # The native INPUT union is 32 bytes on 64-bit Windows. Keep the unused
    # portion padded without defining or exposing a mouse input path.
    _fields_ = [("ki", _KEYBDINPUT), ("_padding", ctypes.c_byte * 32)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", wintypes.DWORD), ("data", _INPUT_UNION)]


def _key_input(virtual_key: int, flags: int) -> _INPUT:
    return _INPUT(1, _INPUT_UNION(_KEYBDINPUT(virtual_key, 0, flags, 0, None)))


def _unicode_inputs(units: list[int]) -> Any:
    values: list[_INPUT] = []
    for unit in units:
        values.append(_INPUT(1, _INPUT_UNION(_KEYBDINPUT(0, unit, 0x0004, 0, None))))
        values.append(_INPUT(1, _INPUT_UNION(_KEYBDINPUT(0, unit, 0x0006, 0, None))))
    return (_INPUT * len(values))(*values)


def _utf16_units(value: str) -> list[int]:
    encoded = value.encode("utf-16-le", errors="surrogatepass")
    return [encoded[index] | (encoded[index + 1] << 8) for index in range(0, len(encoded), 2)]


def _chunks(values: list[int], size: int):
    for index in range(0, len(values), size):
        chunk = values[index:index + size]
        if chunk and 0xD800 <= chunk[-1] <= 0xDBFF and index + len(chunk) < len(values):
            chunk = values[index:index + size - 1]
        yield chunk


def _chars_from_units(units: list[int]) -> int:
    encoded = bytearray()
    for unit in units:
        encoded.extend((unit & 0xFF, unit >> 8))
    return len(bytes(encoded).decode("utf-16-le", errors="surrogatepass"))


def _semantic_snapshot_dict(snapshot: SemanticElementSnapshot) -> dict[str, object]:
    bounds = snapshot.bounds
    return {
        "element_ref": snapshot.element_ref,
        "window_ref": snapshot.window_ref,
        "name": snapshot.name,
        "control_type": snapshot.control_type,
        "automation_id": snapshot.automation_id,
        "enabled": snapshot.enabled,
        "offscreen": snapshot.offscreen,
        "focused": snapshot.focused,
        "focusable": snapshot.focusable,
        "bounds": {"x": bounds.x, "y": bounds.y, "width": bounds.width, "height": bounds.height} if bounds else None,
        "supported_patterns": list(snapshot.supported_patterns),
        "actionable": snapshot.actionable,
    }


def _semantic_tree_dict(node: SemanticTreeNode) -> dict[str, object]:
    payload = _semantic_snapshot_dict(node.snapshot)
    payload["children"] = [_semantic_tree_dict(child) for child in node.children]
    return payload


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _mapping_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
