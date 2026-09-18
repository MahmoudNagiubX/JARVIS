"""Policy-controlled engineering sessions over injected specialist adapters."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from ..agents.workers.runtime import LocalWorkerRuntime, WorkerCategory, WorkerRequest, WorkerResult, WorkerStatus
from ..authority.approvals.service import DurableApprovalEngine
from ..authority.audit.service import DurableAuditService
from ..authority.permissions.engine import PolicyPermissionEngine
from ..bus import InMemoryEventBus
from ..contracts import (
    ApprovalRequest,
    AuditRecord,
    DeviceIdentity,
    EngineeringAction,
    EngineeringProvider,
    EngineeringResult,
    EngineeringSession,
    EngineeringWorkspace,
    Identity,
    PermissionEffect,
)
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository


class EngineeringService:
    """One gateway for engineering actions, never a shell or second agent."""

    READ_ACTIONS = frozenset({"list", "inspect", "read", "output", "plot", "error", "inspect_board", "read_schematic"})
    WRITE_ACTIONS = frozenset({"insert", "edit", "execute", "restart", "erc"})

    def __init__(
        self,
        repository: RuntimeRepository,
        event_bus: InMemoryEventBus,
        permission: PolicyPermissionEngine,
        approvals: DurableApprovalEngine,
        audit: DurableAuditService,
        providers: tuple[EngineeringProvider, ...] = (),
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.permission = permission
        self.approvals = approvals
        self.audit = audit
        self.providers: dict[str, EngineeringProvider] = {provider.name: provider for provider in providers}
        self._sessions: dict[str, EngineeringSession] = {}
        self._pending: dict[str, tuple[EngineeringAction, Identity, DeviceIdentity]] = {}

    def list_providers(self) -> tuple[dict[str, object], ...]:
        return tuple({"name": provider.name, "available": provider.available, "capabilities": provider.capabilities()} for provider in self.providers.values())

    async def create_session(
        self,
        identity: Identity,
        device: DeviceIdentity,
        provider: str,
        workspace: EngineeringWorkspace,
    ) -> EngineeringSession:
        selected = self.providers.get(provider)
        if selected is None:
            raise ValueError("engineering provider is not registered")
        if identity.owner_id != device.owner_id:
            raise PermissionError("owner_binding_mismatch")
        root = self._resolved(workspace.root)
        if workspace.read_scope and not self._in_scope(root, workspace.read_scope):
            raise PermissionError("workspace_outside_read_scope")
        normalized = EngineeringWorkspace(
            workspace.workspace_id or f"workspace-{uuid4()}", str(root),
            tuple(str(self._resolved(item)) for item in workspace.read_scope) or (str(root),),
            tuple(str(self._resolved(item)) for item in workspace.write_scope),
            workspace.allowed_tools, min(max(workspace.timeout_seconds, 1.0), 300.0), workspace.risk, workspace.approval_required,
        )
        session = EngineeringSession(f"engineering-{uuid4()}", identity.owner_id, device.device_id, provider, normalized, created_at=datetime.now(UTC))
        self._sessions[session.session_id] = session
        await self._emit("engineering.session.started", identity, device, {"owner_id": identity.owner_id, "session_id": session.session_id, "provider": provider}, EventState.COMPLETED)
        return session

    def get_session(self, session_id: str, owner_id: str) -> EngineeringSession | None:
        session = self._sessions.get(session_id)
        return session if session and session.owner_id == owner_id else None

    async def execute(self, action: EngineeringAction, identity: Identity, device: DeviceIdentity) -> EngineeringResult:
        session = self._sessions.get(action.session_id)
        if session is None or session.owner_id != identity.owner_id or session.device_id != device.device_id:
            return EngineeringResult(action.action_id or f"engineering-action-{uuid4()}", "failed", error_code="session_binding_mismatch")
        provider = self.providers.get(session.provider)
        if provider is None:
            return EngineeringResult(action.action_id or f"engineering-action-{uuid4()}", "failed", error_code="provider_not_registered")
        if action.action not in set(provider.capabilities()) or action.action not in self.READ_ACTIONS | self.WRITE_ACTIONS:
            return EngineeringResult(action.action_id or f"engineering-action-{uuid4()}", "failed", error_code="engineering_action_not_allowlisted")
        if session.workspace.allowed_tools and action.action not in session.workspace.allowed_tools:
            return EngineeringResult(action.action_id or f"engineering-action-{uuid4()}", "denied", error_code="engineering_tool_not_scoped")
        if action.target and not self._target_allowed(action.target, session.workspace, write=action.action in self.WRITE_ACTIONS):
            return EngineeringResult(action.action_id or f"engineering-action-{uuid4()}", "denied", error_code="engineering_target_out_of_scope")
        action_id = action.action_id or f"engineering-action-{uuid4()}"
        normalized = EngineeringAction(action.session_id, action.action, action.target, dict(action.parameters), action.dry_run, action_id)
        decision = await self.permission.evaluate(
            identity, device, f"engineering.{session.provider}.{action.action}",
            {"required_scope": "tool.request", "required_capabilities": (f"engineering.{session.provider}",),
             "risk_level": "consequential" if action.action in self.WRITE_ACTIONS and not action.dry_run else "read",
             "requires_approval": session.workspace.approval_required and action.action in self.WRITE_ACTIONS and not action.dry_run},
        )
        await self._emit("engineering.action.requested", identity, device, {"owner_id": identity.owner_id, "session_id": session.session_id, "action": action.action, "action_id": action_id})
        if decision.effect is PermissionEffect.DENY:
            return EngineeringResult(action_id, "denied", error_code=decision.reason_code)
        if decision.effect is PermissionEffect.REQUIRE_APPROVAL:
            approval_id = f"approval-{uuid4()}"
            await self.approvals.request(ApprovalRequest(
                approval_id, f"engineering.{session.provider}.{action.action}", identity.owner_id, device.device_id,
                "engineering write or execution", datetime.now(UTC), datetime.now(UTC) + timedelta(minutes=10),
                {"session_id": session.session_id, "action": action.action, "target": action.target, "action_id": action_id},
            ))
            self._pending[approval_id] = (normalized, identity, device)
            await self._emit("engineering.action.approval_required", identity, device, {"owner_id": identity.owner_id, "session_id": session.session_id, "action": action.action, "action_id": action_id, "approval_id": approval_id})
            return EngineeringResult(action_id, "approval_required", approval_id=approval_id)
        return await self._run(normalized, session, provider, identity, device)

    async def decide(self, approval_id: str, approved: bool, decided_by: str) -> EngineeringResult:
        pending = self._pending.get(approval_id)
        if pending is None:
            raise KeyError(approval_id)
        decision = await self.approvals.decide(approval_id, approved, decided_by)
        action, identity, device = pending
        if decision.status.value != "approved":
            self._pending.pop(approval_id, None)
            await self._emit("engineering.action.failed", identity, device, {"owner_id": identity.owner_id, "session_id": action.session_id, "action": action.action, "approval_id": approval_id, "error_code": "approval_not_approved"}, EventState.FAILED)
            return EngineeringResult(action.action_id or f"engineering-action-{uuid4()}", "denied", error_code="approval_not_approved", approval_id=approval_id)
        session = self._sessions[action.session_id]
        provider = self.providers[session.provider]
        self._pending.pop(approval_id, None)
        return await self._run(action, session, provider, identity, device)

    async def _run(self, action: EngineeringAction, session: EngineeringSession, provider: EngineeringProvider, identity: Identity, device: DeviceIdentity) -> EngineeringResult:
        await self._emit("engineering.action.started", identity, device, {"owner_id": identity.owner_id, "session_id": session.session_id, "action": action.action, "action_id": action.action_id})
        try:
            result = await asyncio.wait_for(provider.execute(action, session.workspace), session.workspace.timeout_seconds)
        except asyncio.TimeoutError:
            result = EngineeringResult(action.action_id or "unknown", "failed", error_code="engineering_timeout")
        except Exception as exc:
            result = EngineeringResult(action.action_id or "unknown", "failed", error_code=exc.__class__.__name__)
        event_name = "engineering.action.completed" if result.status == "completed" else "engineering.action.failed"
        if result.artifacts:
            await self._emit("engineering.artifact.changed", identity, device, {"owner_id": identity.owner_id, "session_id": session.session_id, "action": action.action, "artifact_count": len(result.artifacts)})
        await self._emit(event_name, identity, device, {"owner_id": identity.owner_id, "session_id": session.session_id, "action": action.action, "action_id": action.action_id, "artifact_count": len(result.artifacts), "error_code": result.error_code}, EventState.COMPLETED if result.status == "completed" else EventState.FAILED)
        await self.audit.record(AuditRecord(f"audit-{uuid4()}", event_name, datetime.now(UTC), identity.identity_id, device.device_id, action.action_id or "engineering", result.status, result.error_code, {"provider": provider.name, "action": action.action, "target": action.target}))
        return result

    def _target_allowed(self, target: str, workspace: EngineeringWorkspace, *, write: bool) -> bool:
        path = self._resolved(target)
        scopes = workspace.write_scope if write else workspace.read_scope
        return bool(scopes) and self._in_scope(path, scopes)

    @staticmethod
    def _resolved(value: str) -> Path:
        return Path(value).expanduser().resolve(strict=False)

    @staticmethod
    def _in_scope(path: Path, scopes: tuple[str, ...] | list[str]) -> bool:
        return any(
            path == Path(scope).expanduser().resolve(strict=False)
            or Path(scope).expanduser().resolve(strict=False) in path.parents
            for scope in scopes
        )

    async def _emit(self, event_type: str, identity: Identity, device: DeviceIdentity, payload: Mapping[str, object], state: EventState = EventState.EMITTED) -> None:
        event = Event.create(event_type, EventCategory.ENGINEERING, correlation_id=str(payload.get("action_id", payload.get("session_id", uuid4()))), actor_id=identity.identity_id, payload=dict(payload), state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)


class EngineeringWorker:
    """Use the existing bounded worker runtime for engineering tasks."""

    def __init__(self, service: EngineeringService, event_bus: InMemoryEventBus, repository: RuntimeRepository) -> None:
        self.service = service
        self.event_bus = event_bus
        self.repository = repository
        self.runtime = LocalWorkerRuntime({WorkerCategory.ENGINEERING: self._handle})

    async def run(self, task: str, session_id: str, identity: Identity, device: DeviceIdentity, *, timeout_seconds: float = 60.0) -> WorkerResult:
        request = WorkerRequest(task, WorkerCategory.ENGINEERING, self.service._sessions[session_id].workspace.root, True, timeout_seconds, 1, {"session_id": session_id, "identity": identity, "device": device})
        await self._emit("developer.worker.started", identity, device, {"owner_id": identity.owner_id, "session_id": session_id, "category": "engineering"})
        result = await self.runtime.run(request)
        await self._emit("developer.worker.completed" if result.status is WorkerStatus.SUCCEEDED else "developer.worker.failed", identity, device, {"owner_id": identity.owner_id, "session_id": session_id, "worker_id": result.worker_id, "status": result.status.value}, EventState.COMPLETED if result.status is WorkerStatus.SUCCEEDED else EventState.FAILED)
        return result

    async def _handle(self, request: WorkerRequest) -> WorkerResult:
        identity = request.context["identity"]
        device = request.context["device"]
        session_id = str(request.context["session_id"])
        result = await self.service.execute(EngineeringAction(session_id, "execute", parameters={"task": request.task}, dry_run=True), identity, device)
        status = WorkerStatus.SUCCEEDED if result.status == "completed" else WorkerStatus.FAILED
        return WorkerResult(f"worker-{uuid4()}", status, result.status, error_code=result.error_code, completed_at=datetime.now(UTC))

    async def _emit(self, event_type: str, identity: Identity, device: DeviceIdentity, payload: Mapping[str, object], state: EventState = EventState.EMITTED) -> None:
        event = Event.create(event_type, EventCategory.DEVELOPER_WORKER, actor_id=identity.identity_id, payload=dict(payload), state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)
