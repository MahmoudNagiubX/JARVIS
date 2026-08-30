"""The single policy-controlled tool execution pipeline."""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import uuid4

from ..authority.audit.service import DurableAuditService
from ..authority.approvals.service import DurableApprovalEngine
from ..authority.permissions.engine import PolicyPermissionEngine
from ..bus import InMemoryEventBus
from ..contracts import (
    ApprovalRequest,
    AuditRecord,
    PermissionEffect,
    ToolContext,
    ToolResult,
    ToolResultRetention,
    ToolResultStatus,
)
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository
from .registry import ToolRegistry, ToolSpec


class ToolExecutionStatus(StrEnum):
    COMPLETED = "completed"
    APPROVAL_REQUIRED = "approval_required"
    DENIED = "denied"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ToolCallResult:
    tool_call_id: str
    name: str
    status: ToolExecutionStatus
    output: object = None
    error_code: str | None = None
    approval_id: str | None = None
    argument_digest: str | None = None
    retention: ToolResultRetention = ToolResultRetention.DURABLE


@dataclass(slots=True)
class _PendingArguments:
    tool_call_id: str
    arguments: dict[str, object]
    owner_id: str
    device_id: str | None
    digest: str
    expires_at: datetime


@dataclass(slots=True)
class _DelegatedApproval:
    tool_call_id: str
    name: str
    run_id: str | None
    digest: str
    retention: ToolResultRetention


class ToolExecutionService:
    """Registry -> permission -> approval -> executor -> audit -> events."""

    def __init__(
        self,
        repository: RuntimeRepository,
        event_bus: InMemoryEventBus,
        registry: ToolRegistry,
        permission: PolicyPermissionEngine,
        approvals: DurableApprovalEngine,
        audit: DurableAuditService,
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.registry = registry
        self.permission = permission
        self.approvals = approvals
        self.audit = audit
        self.MAX_EPHEMERAL_ARGUMENTS = 32
        self._pending_arguments: dict[str, _PendingArguments] = {}
        self._delegated_approvals: dict[str, _DelegatedApproval] = {}
        self._delegated_resumer: Callable[[str, bool, str], Awaitable[object]] | None = None

    def set_delegated_approval_resumer(self, resumer: Callable[[str, bool, str], Awaitable[object]]) -> None:
        self._delegated_resumer = resumer

    def close(self) -> None:
        self._pending_arguments.clear()
        self._delegated_approvals.clear()

    async def execute(
        self,
        name: str,
        arguments: dict[str, object],
        context: ToolContext,
        *,
        run_id: str | None = None,
    ) -> ToolCallResult:
        spec = self.registry.get(name)
        tool_call_id = f"tool-call-{uuid4()}"
        if spec is None or not spec.enabled:
            return await self._denied(tool_call_id, name, context, "unknown_or_disabled_tool", run_id=run_id)
        try:
            normalized = spec.validate_arguments(arguments)
        except ValueError as exc:
            return await self._denied(tool_call_id, name, context, str(exc), run_id=run_id, retention=spec.retention)
        digest = hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.repository.insert_tool_call(tool_call_id, run_id, name, _retained_arguments(spec, normalized, digest), digest, "requested")
        await self._emit("tool.requested", EventCategory.TOOL, context, {"tool_call_id": tool_call_id, "name": name})
        decision = await self.permission.evaluate(
            context.identity,
            context.device,
            f"tool.{name}",
            {
                "required_scope": spec.required_scope,
                "required_capabilities": spec.required_capabilities,
                "risk_level": spec.risk_level,
                "requires_approval": spec.requires_approval,
            },
        )
        await self._emit(
            "tool.permission_checked",
            EventCategory.TOOL,
            context,
            {"tool_call_id": tool_call_id, "effect": decision.effect.value, "reason": decision.reason_code},
        )
        await self.audit.record(
            AuditRecord(
                f"audit-{uuid4()}", "permission.checked", datetime.now(UTC),
                context.identity.identity_id if context.identity else None,
                context.device.device_id if context.device else None,
                context.correlation_id, decision.effect.value, decision.reason_code,
                {"tool_call_id": tool_call_id, "tool": name},
            )
        )
        if decision.effect is PermissionEffect.DENY:
            self.repository.update_tool_call(tool_call_id, "denied", {"reason": decision.reason_code})
            return ToolCallResult(tool_call_id, name, ToolExecutionStatus.DENIED, error_code=decision.reason_code, argument_digest=digest, retention=spec.retention)
        if decision.effect is PermissionEffect.REQUIRE_APPROVAL:
            approval_id = f"approval-{uuid4()}"
            expires_at = datetime.now(UTC) + timedelta(minutes=10)
            if spec.argument_retention is ToolResultRetention.EPHEMERAL:
                self._prune_ephemeral_arguments()
                if len(self._pending_arguments) >= self.MAX_EPHEMERAL_ARGUMENTS:
                    self.repository.update_tool_call(tool_call_id, "failed", {"retained": False, "error_code": "ephemeral_argument_store_full"})
                    return ToolCallResult(tool_call_id, name, ToolExecutionStatus.FAILED, error_code="ephemeral_argument_store_full", argument_digest=digest, retention=spec.retention)
                self._pending_arguments[approval_id] = _PendingArguments(
                    tool_call_id,
                    normalized,
                    context.identity.owner_id if context.identity else "unknown",
                    context.device.device_id if context.device else None,
                    digest,
                    expires_at,
                )
            request = ApprovalRequest(
                approval_id, f"tool.{name}", context.identity.owner_id if context.identity else "unknown",
                context.device.device_id if context.device else None,
                "consequential tool execution", datetime.now(UTC), expires_at,
                {"tool_call_id": tool_call_id, "tool": name, "arguments": _retained_arguments(spec, normalized, digest), "argument_digest": digest},
            )
            await self.approvals.request(request)
            self.repository.update_tool_call(tool_call_id, "awaiting_approval")
            self.repository.set_tool_call_approval(tool_call_id, approval_id)
            self.repository.update_run(run_id, pending_approval_id=approval_id) if run_id else None
            await self._emit("tool.approval_required", EventCategory.APPROVAL, context, {"approval_id": approval_id, "tool_call_id": tool_call_id})
            return ToolCallResult(tool_call_id, name, ToolExecutionStatus.APPROVAL_REQUIRED, approval_id=approval_id, argument_digest=digest, retention=spec.retention)
        return await self._run_handler(spec, tool_call_id, normalized, context, run_id, digest)

    async def decide_and_resume(
        self, approval_id: str, approved: bool, decided_by: str, context: ToolContext
    ) -> ToolCallResult:
        approval_row = self.repository.approval(approval_id)
        if approval_row is None or (context.identity is not None and approval_row.get("requester_id") != context.identity.owner_id):
            raise PermissionError("approval_owner_mismatch")
        if context.device is not None and approval_row.get("device_id") not in {None, context.device.device_id}:
            raise PermissionError("approval_device_mismatch")
        delegated = self._delegated_approvals.get(approval_id)
        if delegated is not None:
            try:
                if self._delegated_resumer is None:
                    return self._delegated_failure(delegated, "delegated_approval_unavailable")
                result = await self._delegated_resumer(approval_id, approved, decided_by)
                return await self._finish_delegated(delegated, approval_id, result, context)
            except KeyError:
                return self._delegated_failure(delegated, "ephemeral_arguments_unavailable")
            finally:
                self._delegated_approvals.pop(approval_id, None)
        decision = await self.approvals.decide(approval_id, approved, decided_by)
        row = self.repository.tool_call_by_approval(approval_id)
        if row is None:
            raise KeyError(approval_id)
        name = str(row["name"])
        tool_call_id = str(row["id"])
        if decision.status.value != "approved":
            self.repository.update_tool_call(tool_call_id, "denied", {"reason": decision.status.value})
            await self.audit.record(
                AuditRecord(f"audit-{uuid4()}", "approval.decided", datetime.now(UTC), decided_by,
                            context.device.device_id if context.device else None, context.correlation_id,
                            decision.status.value, "approval_not_approved", {"approval_id": approval_id}),
            )
            await self._emit("approval.denied", EventCategory.APPROVAL, context, {"approval_id": approval_id})
            self._pending_arguments.pop(approval_id, None)
            return ToolCallResult(tool_call_id, name, ToolExecutionStatus.DENIED, error_code=decision.status.value)
        spec = self.registry.get(name)
        if spec is None:
            raise KeyError(name)
        pending_arguments = self._pending_arguments.pop(approval_id, None)
        if spec.argument_retention is ToolResultRetention.EPHEMERAL:
            if (
                pending_arguments is None
                or pending_arguments.expires_at <= datetime.now(UTC)
                or pending_arguments.tool_call_id != tool_call_id
                or pending_arguments.digest != str(row["argument_digest"])
            ):
                self.repository.update_tool_call(tool_call_id, "failed", {"retained": False, "error_code": "ephemeral_arguments_unavailable"})
                return ToolCallResult(tool_call_id, name, ToolExecutionStatus.FAILED, error_code="ephemeral_arguments_unavailable", retention=spec.retention)
            arguments = pending_arguments.arguments
        else:
            arguments = json.loads(str(row["arguments_json"]))
        digest = str(row["argument_digest"])
        await self._emit("approval.approved", EventCategory.APPROVAL, context, {"approval_id": approval_id})
        return await self._run_handler(spec, tool_call_id, arguments, context, row["run_id"], digest)

    async def _run_handler(self, spec: ToolSpec, tool_call_id: str, arguments: dict[str, object], context: ToolContext, run_id: str | None, digest: str) -> ToolCallResult:
        self.repository.update_tool_call(tool_call_id, "started")
        await self._emit("tool.started", EventCategory.TOOL, context, {"tool_call_id": tool_call_id, "name": spec.name})
        try:
            result = spec.handler(arguments, context)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            self.repository.update_tool_call(tool_call_id, "failed", {"error": exc.__class__.__name__})
            await self.audit.record(AuditRecord(f"audit-{uuid4()}", "tool.failed", datetime.now(UTC),
                                                context.identity.identity_id if context.identity else None,
                                                context.device.device_id if context.device else None,
                                                context.correlation_id, "failed", "executor_error",
                                                {"tool_call_id": tool_call_id, "tool": spec.name}))
            await self._emit("tool.failed", EventCategory.TOOL, context, {"tool_call_id": tool_call_id})
            return ToolCallResult(tool_call_id, spec.name, ToolExecutionStatus.FAILED, error_code="executor_error", argument_digest=digest, retention=spec.retention)
        if result.status is ToolResultStatus.APPROVAL_REQUIRED:
            if not result.approval_id:
                self.repository.update_tool_call(tool_call_id, "failed", {"retained": False, "error_code": "approval_id_missing"})
                return ToolCallResult(tool_call_id, spec.name, ToolExecutionStatus.FAILED, error_code="approval_id_missing", argument_digest=digest, retention=spec.retention)
            if len(self._delegated_approvals) >= self.MAX_EPHEMERAL_ARGUMENTS:
                self.repository.update_tool_call(tool_call_id, "failed", {"retained": False, "error_code": "delegated_approval_store_full"})
                return ToolCallResult(tool_call_id, spec.name, ToolExecutionStatus.FAILED, error_code="delegated_approval_store_full", argument_digest=digest, retention=spec.retention)
            self._delegated_approvals[result.approval_id] = _DelegatedApproval(tool_call_id, spec.name, run_id, digest, spec.retention)
            self.repository.update_tool_call(tool_call_id, "awaiting_approval")
            self.repository.set_tool_call_approval(tool_call_id, result.approval_id)
            if run_id:
                self.repository.update_run(run_id, pending_approval_id=result.approval_id)
            await self._emit("tool.approval_required", EventCategory.APPROVAL, context, {"approval_id": result.approval_id, "tool_call_id": tool_call_id})
            return ToolCallResult(tool_call_id, spec.name, ToolExecutionStatus.APPROVAL_REQUIRED, approval_id=result.approval_id, argument_digest=digest, retention=spec.retention)
        if result.status is not ToolResultStatus.SUCCEEDED:
            status = ToolExecutionStatus.DENIED if result.status is ToolResultStatus.DENIED else ToolExecutionStatus.FAILED
            self.repository.update_tool_call(tool_call_id, status.value, _retained_output(spec, result.output))
            return ToolCallResult(tool_call_id, spec.name, status, result.output, result.error_code, argument_digest=digest, retention=spec.retention)
        self.repository.update_tool_call(tool_call_id, "completed", _retained_output(spec, result.output))
        await self.audit.record(AuditRecord(f"audit-{uuid4()}", "tool.completed", datetime.now(UTC),
                                            context.identity.identity_id if context.identity else None,
                                            context.device.device_id if context.device else None,
                                            context.correlation_id, "succeeded", None,
                                            {"tool_call_id": tool_call_id, "tool": spec.name, "verified": result.verified}))
        await self._emit("tool.completed", EventCategory.TOOL, context, {"tool_call_id": tool_call_id, "verified": result.verified}, state=EventState.COMPLETED)
        return ToolCallResult(tool_call_id, spec.name, ToolExecutionStatus.COMPLETED, result.output, argument_digest=digest, retention=spec.retention)

    async def _finish_delegated(self, pending: _DelegatedApproval, approval_id: str, result: object, context: ToolContext) -> ToolCallResult:
        raw_status = str(getattr(result, "status", "failed"))
        output = getattr(result, "output", None)
        error_code = getattr(result, "error_code", None)
        verified = bool(getattr(result, "verified", False))
        if raw_status == "succeeded":
            status = ToolExecutionStatus.COMPLETED
            self.repository.update_tool_call(pending.tool_call_id, "completed", _retained_output_by_retention(pending.retention, output))
            await self.audit.record(AuditRecord(
                f"audit-{uuid4()}", "tool.completed", datetime.now(UTC),
                context.identity.identity_id if context.identity else None,
                context.device.device_id if context.device else None,
                context.correlation_id, "succeeded", None,
                {"tool_call_id": pending.tool_call_id, "tool": pending.name, "verified": verified},
            ))
            await self._emit("tool.completed", EventCategory.TOOL, context, {"tool_call_id": pending.tool_call_id, "verified": verified}, state=EventState.COMPLETED)
        elif raw_status == "denied":
            status = ToolExecutionStatus.DENIED
            self.repository.update_tool_call(pending.tool_call_id, "denied", _retained_output_by_retention(pending.retention, output))
        else:
            status = ToolExecutionStatus.FAILED
            self.repository.update_tool_call(pending.tool_call_id, "failed", {"retained": False, "error_code": error_code or "delegated_action_failed"})
        return ToolCallResult(pending.tool_call_id, pending.name, status, output, error_code, approval_id, pending.digest, pending.retention)

    def _delegated_failure(self, pending: _DelegatedApproval, error_code: str) -> ToolCallResult:
        self.repository.update_tool_call(pending.tool_call_id, "failed", {"retained": False, "error_code": error_code})
        return ToolCallResult(pending.tool_call_id, pending.name, ToolExecutionStatus.FAILED, error_code=error_code, argument_digest=pending.digest, retention=pending.retention)

    def _prune_ephemeral_arguments(self) -> None:
        now = datetime.now(UTC)
        for approval_id, pending in tuple(self._pending_arguments.items()):
            if pending.expires_at <= now:
                self._pending_arguments.pop(approval_id, None)

    async def _denied(
        self,
        tool_call_id: str,
        name: str,
        context: ToolContext,
        reason: str,
        *,
        run_id: str | None,
        retention: ToolResultRetention = ToolResultRetention.DURABLE,
    ) -> ToolCallResult:
        self.repository.insert_tool_call(tool_call_id, run_id, name, {}, "", "denied")
        await self.audit.record(AuditRecord(f"audit-{uuid4()}", "tool.denied", datetime.now(UTC),
                                            context.identity.identity_id if context.identity else None,
                                            context.device.device_id if context.device else None,
                                            context.correlation_id, "denied", reason, {"tool": name}))
        await self._emit("tool.failed", EventCategory.TOOL, context, {"tool_call_id": tool_call_id, "reason": reason}, state=EventState.FAILED)
        return ToolCallResult(tool_call_id, name, ToolExecutionStatus.DENIED, error_code=reason, retention=retention)

    async def _emit(self, event_type: str, category: EventCategory, context: ToolContext, payload: dict[str, object], *, state: EventState = EventState.EMITTED) -> None:
        event = Event.create(
            event_type, category, correlation_id=context.correlation_id, session_id=context.session_id,
            actor_id=context.identity.identity_id if context.identity else None, payload=payload, state=state,
        )
        self.repository.append_event(event)
        await self.event_bus.publish(event)


def _retained_output(spec: ToolSpec, output: object) -> object:
    return _retained_output_by_retention(spec.retention, output)


def _retained_output_by_retention(retention: ToolResultRetention, output: object) -> object:
    if retention is ToolResultRetention.DURABLE:
        return output
    return {"retained": False, "content_digest": hashlib.sha256(json.dumps(output, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest(), "source": "ephemeral-tool"}


def _retained_arguments(spec: ToolSpec, arguments: dict[str, object], digest: str) -> object:
    if spec.argument_retention is ToolResultRetention.DURABLE:
        return arguments
    return {"retained": False, "argument_digest": digest, "keys": sorted(arguments)}
