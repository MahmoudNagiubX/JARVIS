"""Durable, approval-aware execution of declarative skills."""

from __future__ import annotations

import inspect
import json
import hashlib
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from ..authority.approvals.service import DurableApprovalEngine
from ..authority.audit.service import DurableAuditService
from ..bus import InMemoryEventBus
from ..contracts import ApprovalRequest, AuditRecord, DeviceIdentity, Identity, ToolContext
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository
from ..tools.service import ToolExecutionService, ToolExecutionStatus
from .loader import SkillLoader
from .models import Skill, SkillExecution, SkillExecutionStatus, SkillInput, SkillOutput
from .policy import SkillPolicy
from .registry import SkillRegistry


SkillHandler = Callable[[Skill, Mapping[str, object], Identity, DeviceIdentity], object | Awaitable[object]]


class SkillExecutor:
    def __init__(
        self,
        registry: SkillRegistry,
        policy: SkillPolicy,
        event_bus: InMemoryEventBus,
        repository: RuntimeRepository,
        *,
        tools: ToolExecutionService | None = None,
        handlers: Mapping[str, SkillHandler] | None = None,
        loader: SkillLoader | None = None,
        approvals: DurableApprovalEngine | None = None,
        audit: DurableAuditService | None = None,
    ) -> None:
        self.registry = registry
        self.policy = policy
        self.event_bus = event_bus
        self.repository = repository
        self.tools = tools
        self.handlers = dict(handlers or {})
        self.loader = loader or SkillLoader()
        self.approvals = approvals
        self.audit = audit

    async def execute(self, skill_id: str, values: Mapping[str, object], identity: Identity, device: DeviceIdentity) -> SkillOutput:
        skill = self.registry.get(skill_id)
        if skill is None:
            return SkillOutput(skill_id, "unavailable", error_code="skill_not_found")
        now = datetime.now(UTC)
        execution = SkillExecution(
            execution_id=f"skill-execution-{uuid4()}", skill_id=skill_id, owner_id=identity.owner_id,
            identity_id=identity.identity_id, device_id=device.device_id, current_step=0,
            status=SkillExecutionStatus.QUEUED, correlation_id=f"skill-execution-{uuid4()}",
            values=dict(values), created_at=now, updated_at=now,
        )
        self.repository.insert_skill_execution(execution)
        return await self._start(execution, skill, identity, device)

    async def resume(self, execution_id: str, identity: Identity, device: DeviceIdentity) -> SkillOutput:
        execution = self._load_execution(execution_id)
        if execution is None:
            return SkillOutput("", "unavailable", error_code="skill_execution_not_found", execution_id=execution_id)
        if execution.owner_id != identity.owner_id or execution.identity_id != identity.identity_id or execution.device_id != device.device_id:
            raise PermissionError("skill_execution_owner_device_mismatch")
        if execution.status in {SkillExecutionStatus.COMPLETED, SkillExecutionStatus.FAILED, SkillExecutionStatus.DENIED}:
            return self._output(execution)
        skill = self.registry.get(execution.skill_id)
        if skill is None:
            return await self._finish(execution, SkillExecutionStatus.FAILED, "skill_not_found")
        if execution.status is not SkillExecutionStatus.WAITING_APPROVAL or not execution.approval_id:
            return await self._start(execution, skill, identity, device)
        if self.approvals is None:
            return await self._finish(execution, SkillExecutionStatus.FAILED, "approval_engine_unavailable")
        row = self.repository.approval(execution.approval_id)
        decision = await self.approvals.get(execution.approval_id)
        if row is None or decision is None:
            return await self._finish(execution, SkillExecutionStatus.FAILED, "approval_not_found")
        if row.get("requester_id") != identity.owner_id:
            raise PermissionError("approval_owner_mismatch")
        preview = self._json(row.get("preview_json"))
        if preview.get("skill_id") != execution.skill_id or preview.get("step_index") != execution.current_step:
            if not preview.get("tool_call_id"):
                raise PermissionError("approval_skill_step_mismatch")
        if decision.status.value == "pending":
            return self._output(execution)
        if decision.status.value != "approved":
            return await self._finish(execution, SkillExecutionStatus.DENIED, "approval_not_approved")
        if preview.get("tool_call_id"):
            if self.tools is None:
                return await self._finish(execution, SkillExecutionStatus.FAILED, "tool_executor_unavailable")
            context = ToolContext(identity, device, execution.correlation_id, f"skill-{execution.skill_id}")
            result = await self.tools.decide_and_resume(execution.approval_id, True, identity.identity_id, context)
            results = (*execution.results, {"step_id": preview.get("step_id", ""), "status": result.status.value, "output": result.output, "error_code": result.error_code})
            if result.status is not ToolExecutionStatus.COMPLETED:
                return await self._finish(execution, SkillExecutionStatus.DENIED if result.status is ToolExecutionStatus.DENIED else SkillExecutionStatus.FAILED, result.error_code)
            execution = self._save_execution(execution, current_step=execution.current_step + 1, status=SkillExecutionStatus.RUNNING, results=results, approval_id=None)
            return await self._run(execution, skill, identity, device)
        execution = self._save_execution(execution, status=SkillExecutionStatus.RUNNING, approval_id=None)
        return await self._run(execution, skill, identity, device, approved_step=execution.current_step)

    async def _start(self, execution: SkillExecution, skill: Skill, identity: Identity, device: DeviceIdentity) -> SkillOutput:
        detail = await self.policy.evaluate_detail(skill, identity, device)
        if not detail.allowed:
            return await self._finish(execution, SkillExecutionStatus.DENIED, detail.reason)
        try:
            loaded = self.loader.load(skill)
        except Exception as exc:
            return await self._finish(execution, SkillExecutionStatus.FAILED, f"instructions:{exc.__class__.__name__}")
        await self._emit("skill.loaded", loaded, identity.owner_id, {"progressive": True})
        return await self._run(self._save_execution(execution, status=SkillExecutionStatus.RUNNING), loaded, identity, device)

    async def _run(self, execution: SkillExecution, skill: Skill, identity: Identity, device: DeviceIdentity, *, approved_step: int | None = None) -> SkillOutput:
        await self._emit("skill.started", skill, identity.owner_id, {"execution_id": execution.execution_id})
        results = list(execution.results)
        for index in range(execution.current_step, len(skill.steps)):
            step = skill.steps[index]
            detail = await self.policy.evaluate_detail(Skill(skill.manifest, (step,), skill.instructions_path, skill.instructions), identity, device)
            if not detail.allowed:
                return await self._finish(execution, SkillExecutionStatus.DENIED, detail.reason, results=results)
            if detail.approval_required and index != approved_step:
                if self.approvals is None:
                    return await self._finish(execution, SkillExecutionStatus.FAILED, "approval_engine_unavailable", results=results)
                approval_id = f"approval-{uuid4()}"
                await self.approvals.request(ApprovalRequest(
                    approval_id, f"skill.{skill.manifest.skill_id}.{step.step_id}", identity.owner_id, device.device_id,
                    "skill step requires approval", datetime.now(UTC), datetime.now(UTC) + timedelta(minutes=10),
                    {"skill_id": skill.manifest.skill_id, "step_id": step.step_id, "step_index": index, "action": step.action, "risk_level": detail.effective_risk},
                ))
                waiting = self._save_execution(execution, current_step=index, status=SkillExecutionStatus.WAITING_APPROVAL, results=results, approval_id=approval_id)
                await self._emit("skill.waiting_approval", skill, identity.owner_id, {"execution_id": execution.execution_id, "approval_id": approval_id, "step_id": step.step_id}, EventState.ACCEPTED)
                return self._output(waiting)
            arguments = dict(step.arguments)
            arguments.update(execution.values)
            if step.action.startswith("tool:"):
                if self.tools is None:
                    return await self._finish(execution, SkillExecutionStatus.FAILED, "tool_executor_unavailable", results=results)
                context = ToolContext(identity, device, execution.correlation_id, f"skill-{skill.manifest.skill_id}")
                result = await self.tools.execute(step.action.removeprefix("tool:"), arguments, context)
                results.append({"step_id": step.step_id, "status": result.status.value, "output": result.output, "error_code": result.error_code})
                if result.status is ToolExecutionStatus.APPROVAL_REQUIRED:
                    if not result.approval_id:
                        return await self._finish(execution, SkillExecutionStatus.FAILED, "approval_id_missing", results=results)
                    waiting = self._save_execution(execution, current_step=index, status=SkillExecutionStatus.WAITING_APPROVAL, results=results, approval_id=result.approval_id)
                    return self._output(waiting)
                if result.status is not ToolExecutionStatus.COMPLETED:
                    return await self._finish(execution, SkillExecutionStatus.DENIED if result.status is ToolExecutionStatus.DENIED else SkillExecutionStatus.FAILED, result.error_code or result.status.value, results=results)
            else:
                handler = self.handlers.get(step.action)
                if handler is None:
                    return await self._finish(execution, SkillExecutionStatus.FAILED, f"handler_not_configured:{step.action}", results=results)
                try:
                    value = handler(skill, arguments, identity, device)
                    value = await value if inspect.isawaitable(value) else value
                    result = value if isinstance(value, Mapping) else {"value": value}
                    results.append(result)
                    await self._audit(identity, device, execution.correlation_id, step.action, "completed")
                except Exception as exc:
                    await self._audit(identity, device, execution.correlation_id, step.action, "failed", exc.__class__.__name__)
                    return await self._finish(execution, SkillExecutionStatus.FAILED, exc.__class__.__name__, results=results)
            execution = self._save_execution(execution, current_step=index + 1, status=SkillExecutionStatus.RUNNING, results=results, approval_id=None)
        completed = self._save_execution(execution, status=SkillExecutionStatus.COMPLETED, evidence=(f"skill:{skill.manifest.skill_id}",), completed_at=datetime.now(UTC))
        await self._emit("skill.completed", skill, identity.owner_id, {"execution_id": completed.execution_id, "step_count": len(skill.steps)}, EventState.COMPLETED)
        return self._output(completed)

    async def _finish(self, execution: SkillExecution, status: SkillExecutionStatus, error_code: str | None, *, results: list[Mapping[str, object]] | None = None) -> SkillOutput:
        updated = self._save_execution(execution, status=status, error_code=error_code, results=tuple(results if results is not None else execution.results), completed_at=datetime.now(UTC))
        skill = self.registry.get(execution.skill_id)
        if skill is not None:
            await self._emit("skill.failed" if status is not SkillExecutionStatus.DENIED else "skill.denied", skill, execution.owner_id, {"execution_id": execution.execution_id, "error_code": error_code}, EventState.FAILED)
        return self._output(updated)

    def _load_execution(self, execution_id: str) -> SkillExecution | None:
        row = self.repository.skill_execution(execution_id)
        if row is None:
            return None
        return SkillExecution(
            str(row["id"]), str(row["skill_id"]), str(row["owner_id"]), str(row["identity_id"]), str(row["device_id"]),
            int(row["current_step"]), SkillExecutionStatus(str(row["status"])), row.get("approval_id"), str(row["correlation_id"]),
            self._json(row.get("values_json")), tuple(self._json(row.get("results_json")) or ()), tuple(self._json(row.get("evidence_json")) or ()),
            row.get("error_code"), datetime.fromisoformat(str(row["created_at"])), datetime.fromisoformat(str(row["updated_at"])),
            datetime.fromisoformat(str(row["completed_at"])) if row.get("completed_at") else None,
        )

    def _save_execution(self, execution: SkillExecution, **changes: object) -> SkillExecution:
        if "results" in changes:
            changes["results"] = tuple(self._bound_result(item) for item in changes["results"])[-32:]
        if "evidence" in changes:
            changes["evidence"] = tuple(changes["evidence"])
        updated = replace(execution, updated_at=datetime.now(UTC), **changes)
        fields = {"current_step": updated.current_step, "status": updated.status.value, "approval_id": updated.approval_id, "values_json": dict(updated.values), "results_json": list(updated.results), "evidence_json": list(updated.evidence), "error_code": updated.error_code, "updated_at": updated.updated_at, "completed_at": updated.completed_at}
        self.repository.update_skill_execution(updated.execution_id, **fields)
        return updated

    @staticmethod
    def _bound_result(value: object) -> Mapping[str, object]:
        if not isinstance(value, Mapping):
            value = {"value": value}
        try:
            encoded = json.dumps(dict(value), ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            encoded = str(value)
        if len(encoded) <= 8000:
            return dict(value)
        return {"truncated": True, "digest": hashlib.sha256(encoded.encode()).hexdigest(), "preview": encoded[:4000]}

    @staticmethod
    def _json(value: object) -> object:
        if not value:
            return {}
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return {}
        return value

    @staticmethod
    def _output(execution: SkillExecution) -> SkillOutput:
        return SkillOutput(execution.skill_id, execution.status.value, execution.results, execution.error_code, execution.evidence, execution.execution_id, execution.approval_id, execution.current_step, execution.correlation_id)

    async def _audit(self, identity: Identity, device: DeviceIdentity, correlation_id: str, action: str, outcome: str, reason: str | None = None) -> None:
        if self.audit is not None:
            await self.audit.record(AuditRecord(f"audit-{uuid4()}", "skill.handler", datetime.now(UTC), identity.identity_id, device.device_id, correlation_id, outcome, reason, {"action": action}))

    async def _emit(self, event_type: str, skill: Skill, owner_id: str, extra: Mapping[str, object] | None = None, state: EventState = EventState.EMITTED) -> None:
        event = Event.create(event_type, EventCategory.SKILL, correlation_id=f"skill-{skill.manifest.skill_id}", actor_id=owner_id, payload={"owner_id": owner_id, "skill_id": skill.manifest.skill_id, "version": skill.manifest.version, **dict(extra or {})}, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)
