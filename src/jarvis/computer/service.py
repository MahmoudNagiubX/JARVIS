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
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository
from ..perception.windows import WindowsDesktopProvider


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

    def __init__(self, *, perception_provider: WindowsDesktopProvider | None = None) -> None:
        self.perception_provider = perception_provider or WindowsDesktopProvider()
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

    @staticmethod
    def _open_path(parameters: Mapping[str, Any], kind: str) -> ComputerResult:
        raw_path = parameters.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("path_required")
        path = Path(raw_path).expanduser().resolve()
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

    @staticmethod
    def _inspect_file(parameters: Mapping[str, Any]) -> ComputerResult:
        raw_path = parameters.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("path_required")
        path = Path(raw_path).expanduser().resolve()
        if not path.is_file():
            return ComputerResult("failed", error_code="file_not_found")
        if path.stat().st_size > 1_000_000:
            return ComputerResult("denied", error_code="file_too_large")
        return ComputerResult("succeeded", {"path": str(path), "content": path.read_text(encoding="utf-8", errors="replace")}, verified=True)

    @staticmethod
    def _search_files(parameters: Mapping[str, Any]) -> ComputerResult:
        raw_root = parameters.get("root") or parameters.get("path")
        pattern = parameters.get("pattern", "*")
        if not isinstance(raw_root, str) or not raw_root.strip():
            raise ValueError("root_required")
        if not isinstance(pattern, str) or len(pattern) > 200:
            raise ValueError("pattern_invalid")
        root = Path(raw_root).expanduser().resolve()
        if not root.is_dir():
            return ComputerResult("failed", error_code="root_not_found")
        matches: list[str] = []
        for path in root.rglob(pattern):
            if path.is_file():
                matches.append(str(path))
            if len(matches) >= 100:
                break
        return ComputerResult("succeeded", {"root": str(root), "matches": matches}, verified=True)

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
        self._pending: dict[str, tuple[ComputerAction, Identity, DeviceIdentity, DeviceIdentity, str, datetime]] = {}
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
                approval_id = f"approval-{uuid4()}"
                expires_at = datetime.now(UTC) + timedelta(minutes=10)
                await self.approvals.request(ApprovalRequest(approval_id, capability, identity.owner_id, device.device_id, "computer action requires approval", datetime.now(UTC), expires_at, self._approval_preview(action)))
                if len(self._pending) >= self.MAX_PENDING:
                    self._prune_pending(force_one=True)
                self._pending[approval_id] = (action, identity, device, target, adapter, expires_at)
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
            raise KeyError(approval_id)
        action, pending_identity, pending_device, target, adapter, _expires_at = pending
        if identity is not None and identity.owner_id != pending_identity.owner_id:
            raise PermissionError("approval_owner_mismatch")
        if device is not None and device.device_id != pending_device.device_id:
            raise PermissionError("approval_device_mismatch")
        decision = await self.approvals.decide(approval_id, approved, decided_by)
        self._pending.pop(approval_id, None)
        if decision.status.value != "approved":
            return ComputerResult("denied", error_code=decision.status.value, approval_id=approval_id)
        return await self._execute_controller(action, pending_identity, pending_device, target, adapter, "computer", f"computer-{approval_id}", approval_id)

    def close(self) -> None:
        self._pending.clear()

    def _prune_pending(self, *, force_one: bool = False) -> None:
        now = datetime.now(UTC)
        for approval_id, pending in tuple(self._pending.items()):
            if pending[-1] <= now:
                self._pending.pop(approval_id, None)
        if force_one and self._pending:
            self._pending.pop(next(iter(self._pending)))

    @staticmethod
    def _approval_preview(action: ComputerAction) -> dict[str, object]:
        parameters = dict(action.parameters)
        sensitive = action.action in {ComputerCapability.KEYBOARD_ACTION.value, ComputerCapability.CLIPBOARD_WRITE.value}
        if not sensitive:
            return {"action": action.action, "parameters": parameters}
        return {
            "action": action.action,
            "operation": parameters.get("operation"),
            "text_length": len(parameters.get("text", "")) if isinstance(parameters.get("text"), str) else None,
            "parameter_digest": _mapping_digest(parameters),
        }

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


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _mapping_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
