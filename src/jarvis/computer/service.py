"""Product-owned, typed computer control with a bounded Windows backend."""

from __future__ import annotations

import asyncio
import csv
import io
import os
import platform
import shutil
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

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

    def __init__(self, *, perception_provider: WindowsDesktopProvider | None = None) -> None:
        self.perception_provider = perception_provider or WindowsDesktopProvider()

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
        self._pending: dict[str, tuple[ComputerAction, Identity, DeviceIdentity, DeviceIdentity, str]] = {}

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
                await self.approvals.request(ApprovalRequest(approval_id, capability, identity.owner_id, device.device_id, "computer action requires approval", datetime.now(UTC), datetime.now(UTC) + timedelta(minutes=10), {"action": action.action, "parameters": dict(action.parameters)}))
                self._pending[approval_id] = (action, identity, device, target, adapter)
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

    async def decide(self, approval_id: str, approved: bool, decided_by: str) -> ComputerResult:
        pending = self._pending.get(approval_id)
        if pending is None or self.approvals is None:
            raise KeyError(approval_id)
        action, identity, device, target, adapter = pending
        decision = await self.approvals.decide(approval_id, approved, decided_by)
        self._pending.pop(approval_id, None)
        if decision.status.value != "approved":
            return ComputerResult("denied", error_code=decision.status.value, approval_id=approval_id)
        return await self._execute_controller(action, identity, device, target, adapter, "computer", f"computer-{approval_id}", approval_id)

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
