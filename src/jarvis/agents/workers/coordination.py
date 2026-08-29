"""Bounded specialist worker selection and delegation records."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from ...authority.permissions.engine import PolicyPermissionEngine
from ...bus import InMemoryEventBus
from ...contracts import DeviceIdentity, Identity, PermissionEffect
from ...events import Event, EventCategory, EventState
from ...persistence.repositories import RuntimeRepository
from .runtime import LocalWorkerRuntime, WorkerCategory, WorkerRequest, WorkerResult


@dataclass(frozen=True, slots=True)
class WorkerSelection:
    worker: str
    reason: str
    available: bool
    scope: str | None = None


@dataclass(frozen=True, slots=True)
class WorkerDelegation:
    delegation_id: str
    owner_id: str
    worker: str
    reason: str
    scope: str | None
    task: str
    result: Mapping[str, object]
    started_at: datetime
    completed_at: datetime | None = None


class WorkerCoordinator:
    """Local handlers first; optional developer adapters remain explicit."""

    def __init__(self, repository: RuntimeRepository, event_bus: InMemoryEventBus, *, local: LocalWorkerRuntime | None = None, developer_gateway: Any = None, permission: PolicyPermissionEngine | None = None) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.local = local or LocalWorkerRuntime()
        self.developer_gateway = developer_gateway
        self.permission = permission

    def select(self, task: str, *, required_capability: str | None = None, workspace_scope: str | None = None, read_only: bool = True, internet_available: bool = False) -> WorkerSelection:
        text = task.casefold()
        if any(word in text for word in ("research", "citation", "source")):
            category = "research"
        elif any(word in text for word in ("browser", "web page", "website")):
            category = "browser"
        elif any(word in text for word in ("build", "code", "test", "debug", "implement")):
            category = "coding"
        elif any(word in text for word in ("circuit", "cad", "notebook")):
            category = "engineering"
        else:
            category = "general_background"
        if required_capability and required_capability.startswith("browser") and not internet_available:
            return WorkerSelection(category, "internet-required capability unavailable", False, workspace_scope)
        available = WorkerCategory(category) in self.local.handlers or bool(self.developer_gateway and category == "coding" and any(item.available for item in self.developer_gateway.providers()))
        return WorkerSelection(category, f"task classified as {category}; local/free preference", available, workspace_scope)

    async def run(self, owner_id: str, task: str, *, workspace_scope: str | None = None, read_only: bool = True, timeout_seconds: float = 60.0, required_capability: str | None = None, identity: Identity | None = None, device: DeviceIdentity | None = None) -> WorkerDelegation:
        if workspace_scope is not None:
            scope = Path(workspace_scope).expanduser().resolve()
            if not scope.exists() or not scope.is_dir():
                raise ValueError("worker workspace scope must be an existing directory")
            workspace_scope = str(scope)
        selected = self.select(task, required_capability=required_capability, workspace_scope=workspace_scope, read_only=read_only, internet_available=False)
        started = datetime.now(UTC)
        if not read_only:
            if self.permission is None or identity is None or device is None:
                result: Mapping[str, object] = {"status": "approval_required", "error_code": "developer_change_requires_identity_and_approval"}
            else:
                decision = await self.permission.evaluate(identity, device, "developer.worker", {"required_scope": "tool.request", "risk_level": "consequential", "requires_approval": True})
                result = {"status": "approval_required" if decision.effect is PermissionEffect.REQUIRE_APPROVAL else "denied", "reason": decision.reason_code}
        elif not selected.available:
            result = {"status": "unavailable", "error_code": "worker_unavailable", "worker": selected.worker}
        elif selected.worker == "coding" and self.developer_gateway is not None and not self.local.handlers.get(WorkerCategory.CODING):
            provider = next((item.name for item in self.developer_gateway.providers() if item.available), "")
            result = await self.developer_gateway.run(provider, task, workspace_scope, timeout_seconds=timeout_seconds)
        else:
            category = WorkerCategory(selected.worker)
            worker_result: WorkerResult = await self.local.run(WorkerRequest(task, category, workspace_scope, True, min(max(timeout_seconds, 1.0), 300.0), 1))
            result = asdict(worker_result)
        completed = datetime.now(UTC)
        delegation = WorkerDelegation(f"delegation-{uuid4()}", owner_id, selected.worker, selected.reason, workspace_scope, task[:1_000], result, started, completed)
        self.repository.insert_worker_delegation(delegation)
        await self._emit("worker.delegated", delegation, EventState.ACCEPTED)
        await self._emit("worker.completed" if result.get("status") in {"succeeded", "completed", "deferred"} else "worker.failed", delegation, EventState.COMPLETED if result.get("status") in {"succeeded", "completed", "deferred"} else EventState.FAILED)
        return delegation

    async def list(self, owner_id: str) -> tuple[WorkerDelegation, ...]:
        return tuple(self._from_row(row) for row in self.repository.worker_delegations(owner_id))

    async def _emit(self, name: str, delegation: WorkerDelegation, state: EventState) -> None:
        event = Event.create(name, EventCategory.WORKER, correlation_id=delegation.delegation_id, actor_id=delegation.owner_id, payload={"owner_id": delegation.owner_id, "delegation_id": delegation.delegation_id, "worker": delegation.worker, "scope": delegation.scope, "status": delegation.result.get("status")}, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)

    @staticmethod
    def _from_row(row: Mapping[str, object]) -> WorkerDelegation:
        import json
        return WorkerDelegation(str(row["id"]), str(row["owner_id"]), str(row["worker"]), str(row["reason"]), row.get("scope") if isinstance(row.get("scope"), str) else None, str(row["task"]), json.loads(str(row["result_json"])), datetime.fromisoformat(str(row["started_at"])), datetime.fromisoformat(str(row["completed_at"])) if row.get("completed_at") else None)
