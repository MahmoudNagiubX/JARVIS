"""Bounded mission lifecycle layered above the existing GoalEngine."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from ..authority.approvals.service import DurableApprovalEngine
from ..authority.audit.service import DurableAuditService
from ..authority.permissions.engine import PolicyPermissionEngine
from ..bus import InMemoryEventBus
from ..contracts import (
    ApprovalRequest, DeviceIdentity, Identity, Mission, MissionBudget,
    MissionCheckpoint, MissionDependency, MissionEvidence, MissionPlan,
    MissionResult, MissionStatus, MissionStep, PermissionEffect,
)
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository
from .planner import MissionPlanner


class MissionService:
    """One mission authority; goals, tools, workers, and approvals stay canonical."""

    def __init__(
        self,
        repository: RuntimeRepository,
        event_bus: InMemoryEventBus,
        *,
        planner: MissionPlanner | None = None,
        permission: PolicyPermissionEngine | None = None,
        approvals: DurableApprovalEngine | None = None,
        audit: DurableAuditService | None = None,
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.planner = planner or MissionPlanner()
        self.permission = permission
        self.approvals = approvals
        self.audit = audit
        self._missions: dict[str, Mission] = {}
        self.repository.reconcile_missions()

    async def create(self, mission: Mission) -> Mission:
        if self.repository.owner(mission.owner_id) is None:
            raise ValueError("mission owner is unavailable")
        title = mission.title.strip()
        request = mission.request.strip()
        if not title or not request:
            raise ValueError("mission title and request cannot be empty")
        mission.budget.validate()
        now = datetime.now(UTC)
        normalized = replace(
            mission,
            mission_id=mission.mission_id or f"mission-{uuid4()}",
            title=title, request=request, status=MissionStatus.DRAFT,
            created_at=mission.created_at or now, updated_at=now,
        )
        self._missions[normalized.mission_id] = normalized
        self.repository.insert_mission(normalized)
        await self._emit("mission.created", normalized, EventState.COMPLETED)
        return normalized

    async def get(self, owner_id: str, mission_id: str) -> Mission | None:
        current = self._missions.get(mission_id)
        if current is not None:
            return current if current.owner_id == owner_id else None
        row = self.repository.mission(owner_id, mission_id)
        return self._hydrate(row) if row else None

    async def list(self, owner_id: str) -> tuple[Mission, ...]:
        for row in self.repository.missions(owner_id):
            if str(row["id"]) not in self._missions:
                self._hydrate(row)
        return tuple(item for item in self._missions.values() if item.owner_id == owner_id)

    async def plan(self, owner_id: str, mission_id: str, *, available_capabilities: Iterable[str] = (), constraints: Mapping[str, object] | None = None) -> Mission:
        current = await self._required(owner_id, mission_id)
        if current.status not in {MissionStatus.DRAFT, MissionStatus.FAILED, MissionStatus.BLOCKED, MissionStatus.PLANNED, MissionStatus.READY}:
            raise ValueError(f"mission cannot be planned from {current.status.value}")
        plan = self.planner.plan(current, available_capabilities=available_capabilities, constraints=constraints)
        updated = replace(current, plan=plan, status=MissionStatus.READY, current_step=0, blocked_reason=None, approval_id=None, updated_at=datetime.now(UTC))
        self._save(updated)
        await self._emit("mission.planned", updated, EventState.COMPLETED)
        return updated

    async def validate(self, owner_id: str, mission_id: str, *, available_capabilities: Iterable[str] | None = None) -> dict[str, object]:
        current = await self._required(owner_id, mission_id)
        errors: list[str] = []
        if current.plan is None or not current.plan.steps:
            errors.append("mission_plan_missing")
        available = set(available_capabilities or ())
        if current.plan and available_capabilities is not None:
            for step in current.plan.steps:
                if step.required_capability and step.required_capability not in available:
                    errors.append(f"capability_unavailable:{step.required_capability}")
            for dependency in current.plan.dependencies:
                dependency_row = self.repository.mission(owner_id, dependency.mission_id)
                if dependency_row is None or str(dependency_row["status"]) != dependency.required_status:
                    errors.append(f"dependency_unmet:{dependency.mission_id}")
        if current.current_step > (len(current.plan.steps) if current.plan else 0):
            errors.append("current_step_out_of_range")
        return {"mission_id": mission_id, "valid": not errors, "errors": errors, "risk_level": current.plan.risk_level if current.plan else None}

    async def start(self, owner_id: str, mission_id: str, identity: Identity | None = None, device: DeviceIdentity | None = None) -> Mission:
        current = await self._required(owner_id, mission_id)
        validation = await self.validate(owner_id, mission_id)
        if not validation["valid"]:
            raise ValueError("mission is not ready: " + ",".join(validation["errors"]))
        if current.status not in {MissionStatus.READY, MissionStatus.PAUSED, MissionStatus.WAITING}:
            raise ValueError(f"mission cannot start from {current.status.value}")
        if identity is not None or device is not None:
            if self.permission is None:
                raise ValueError("mission authority is not configured")
            decision = await self.permission.evaluate(identity, device, "mission.start", {"required_scope": "tool.request", "risk_level": "read", "requires_approval": False})
            if decision.effect is PermissionEffect.DENY:
                raise PermissionError(decision.reason_code)
        updated = replace(current, status=MissionStatus.RUNNING, blocked_reason=None, updated_at=datetime.now(UTC))
        self._save(updated)
        await self._emit("mission.started", updated, EventState.ACCEPTED)
        return updated

    async def advance(self, owner_id: str, mission_id: str) -> Mission:
        current = await self._required(owner_id, mission_id)
        if current.status is not MissionStatus.RUNNING or current.plan is None:
            raise ValueError("mission is not running")
        if current.current_step >= len(current.plan.steps):
            return await self.complete(owner_id, mission_id, "All planned steps already have results.")
        self._check_budget(current)
        step = current.plan.steps[current.current_step]
        if step.approval_required:
            approval_id = None
            if self.approvals is not None:
                approval_id = f"approval-{uuid4()}"
                await self.approvals.request(ApprovalRequest(approval_id, f"mission.{mission_id}.{step.step_id}", owner_id, None, step.title, datetime.now(UTC), datetime.now(UTC) + timedelta(minutes=10), {"mission_id": mission_id, "step_id": step.step_id}))
            updated = replace(current, status=MissionStatus.WAITING_APPROVAL, approval_id=approval_id, blocked_reason="step_approval_required", updated_at=datetime.now(UTC))
            self._save(updated)
            await self._emit("mission.waiting_approval", updated, EventState.ACCEPTED)
            return updated
        await self._emit("mission.step_started", current, EventState.ACCEPTED, {"step_id": step.step_id, "step_index": current.current_step})
        return current

    async def complete_step(self, owner_id: str, mission_id: str, *, evidence: Mapping[str, object] | None = None, detail: str | None = None) -> Mission:
        current = await self._required(owner_id, mission_id)
        if current.status is not MissionStatus.RUNNING or current.plan is None:
            raise ValueError("mission is not running")
        if current.current_step >= len(current.plan.steps):
            return current
        step = current.plan.steps[current.current_step]
        steps = list(current.plan.steps)
        steps[current.current_step] = replace(step, status="completed", detail=detail)
        plan = replace(current.plan, steps=tuple(steps))
        updated = replace(current, plan=plan, current_step=current.current_step + 1, updated_at=datetime.now(UTC))
        if evidence:
            item = MissionEvidence(f"mission-evidence-{uuid4()}", mission_id, "step_result", step.step_id, dict(evidence), datetime.now(UTC))
            self.repository.insert_mission_evidence(item)
            updated = replace(updated, evidence=(*updated.evidence, item))
        self._save(updated)
        await self._emit("mission.step_completed", updated, EventState.COMPLETED, {"step_id": step.step_id, "step_index": current.current_step})
        if updated.current_step >= len(steps):
            return await self.complete(owner_id, mission_id, "All planned steps completed.")
        return updated

    async def pause(self, owner_id: str, mission_id: str) -> Mission:
        return await self._transition(owner_id, mission_id, MissionStatus.PAUSED, {MissionStatus.RUNNING, MissionStatus.WAITING, MissionStatus.WAITING_APPROVAL})

    async def resume(self, owner_id: str, mission_id: str, *, approval_granted: bool = False) -> Mission:
        current = await self._required(owner_id, mission_id)
        if current.status is MissionStatus.WAITING_APPROVAL:
            if not approval_granted:
                return current
            if current.approval_id and self.approvals is not None:
                decision = await self.approvals.get(current.approval_id)
                if decision is None or decision.status.value != "approved":
                    raise PermissionError("mission_approval_not_granted")
        return await self._transition(owner_id, mission_id, MissionStatus.RUNNING, {MissionStatus.PAUSED, MissionStatus.WAITING, MissionStatus.WAITING_APPROVAL})

    async def cancel(self, owner_id: str, mission_id: str) -> Mission:
        return await self._transition(owner_id, mission_id, MissionStatus.CANCELLED, {MissionStatus.DRAFT, MissionStatus.PLANNED, MissionStatus.READY, MissionStatus.RUNNING, MissionStatus.WAITING, MissionStatus.WAITING_APPROVAL, MissionStatus.BLOCKED, MissionStatus.PAUSED})

    async def checkpoint(self, owner_id: str, mission_id: str, title: str, *, completed: bool = False, evidence: Mapping[str, object] | None = None) -> Mission:
        current = await self._required(owner_id, mission_id)
        if not title.strip():
            raise ValueError("checkpoint title cannot be empty")
        item = MissionCheckpoint(f"mission-checkpoint-{uuid4()}", mission_id, title.strip(), "completed" if completed else "open", datetime.now(UTC), datetime.now(UTC) if completed else None, dict(evidence or {}))
        self.repository.insert_mission_checkpoint(item)
        updated = replace(current, checkpoints=(*current.checkpoints, item), updated_at=datetime.now(UTC))
        self._save(updated)
        await self._emit("mission.checkpoint", updated, EventState.COMPLETED if completed else EventState.ACCEPTED, {"checkpoint_id": item.checkpoint_id})
        return updated

    async def replan(self, owner_id: str, mission_id: str, *, reason: str, constraints: Mapping[str, object] | None = None) -> Mission:
        current = await self._required(owner_id, mission_id)
        if current.status not in {MissionStatus.FAILED, MissionStatus.BLOCKED, MissionStatus.WAITING, MissionStatus.PAUSED}:
            raise ValueError("replan requires a failed, blocked, waiting, or paused mission")
        if current.replan_count >= current.budget.max_replans:
            raise ValueError("mission replan budget exhausted")
        if not reason.strip():
            raise ValueError("replan reason is required")
        plan = self.planner.plan(current, constraints=constraints)
        completed = tuple(step for step in (current.plan.steps if current.plan else ()) if step.status == "completed")
        steps = completed + tuple(replace(step, step_id=f"mission-step-{len(completed) + index}") for index, step in enumerate(plan.steps[len(completed):], 1))
        updated = replace(current, plan=replace(plan, steps=steps), status=MissionStatus.READY, current_step=len(completed), replan_count=current.replan_count + 1, blocked_reason=None, updated_at=datetime.now(UTC))
        self._save(updated)
        await self._emit("mission.replanned", updated, EventState.COMPLETED, {"reason": reason, "replan_count": updated.replan_count})
        return updated

    async def complete(self, owner_id: str, mission_id: str, summary: str = "Mission completed.") -> Mission:
        current = await self._required(owner_id, mission_id)
        if current.status not in {MissionStatus.RUNNING, MissionStatus.WAITING, MissionStatus.READY}:
            raise ValueError(f"mission cannot complete from {current.status.value}")
        result = MissionResult(MissionStatus.COMPLETED.value, summary.strip() or "Mission completed.", tuple(item.evidence_id for item in current.evidence))
        updated = replace(current, status=MissionStatus.COMPLETED, result=result, updated_at=datetime.now(UTC), completed_at=datetime.now(UTC))
        self._save(updated)
        await self._emit("mission.completed", updated, EventState.COMPLETED)
        return updated

    async def fail(self, owner_id: str, mission_id: str, error_code: str) -> Mission:
        current = await self._required(owner_id, mission_id)
        result = MissionResult(MissionStatus.FAILED.value, "Mission failed.", tuple(item.evidence_id for item in current.evidence), error_code)
        updated = replace(current, status=MissionStatus.FAILED, result=result, blocked_reason=error_code, updated_at=datetime.now(UTC), completed_at=datetime.now(UTC))
        self._save(updated)
        await self._emit("mission.failed", updated, EventState.FAILED, {"error_code": error_code})
        return updated

    async def record_tool_call(self, owner_id: str, mission_id: str, count: int = 1) -> Mission:
        current = await self._required(owner_id, mission_id)
        if count < 1 or current.tool_calls + count > current.budget.max_tool_calls:
            raise ValueError("mission tool-call budget exhausted")
        updated = replace(current, tool_calls=current.tool_calls + count, updated_at=datetime.now(UTC))
        self._save(updated)
        return updated

    async def record_worker_run(self, owner_id: str, mission_id: str, count: int = 1) -> Mission:
        current = await self._required(owner_id, mission_id)
        if count < 1 or current.worker_runs + count > current.budget.max_worker_runs:
            raise ValueError("mission worker budget exhausted")
        updated = replace(current, worker_runs=current.worker_runs + count, updated_at=datetime.now(UTC))
        self._save(updated)
        return updated

    async def record_external_action(self, owner_id: str, mission_id: str, count: int = 1) -> Mission:
        current = await self._required(owner_id, mission_id)
        if count < 1 or current.external_actions + count > current.budget.max_external_actions:
            raise ValueError("mission external-action budget exhausted")
        updated = replace(current, external_actions=current.external_actions + count, updated_at=datetime.now(UTC))
        self._save(updated)
        return updated

    @staticmethod
    def _check_budget(mission: Mission) -> None:
        if mission.current_step >= mission.budget.max_steps:
            raise ValueError("mission step budget exhausted")
        if mission.created_at and (datetime.now(UTC) - mission.created_at).total_seconds() > mission.budget.max_duration:
            raise ValueError("mission duration budget exhausted")
        if mission.tool_calls > mission.budget.max_tool_calls or mission.worker_runs > mission.budget.max_worker_runs or mission.external_actions > mission.budget.max_external_actions:
            raise ValueError("mission execution budget exhausted")

    async def _transition(self, owner_id: str, mission_id: str, status: MissionStatus, allowed: set[MissionStatus]) -> Mission:
        current = await self._required(owner_id, mission_id)
        if current.status not in allowed:
            raise ValueError(f"mission cannot transition from {current.status.value}")
        updated = replace(current, status=status, updated_at=datetime.now(UTC), completed_at=datetime.now(UTC) if status is MissionStatus.CANCELLED else current.completed_at)
        self._save(updated)
        await self._emit(f"mission.{status.value}", updated, EventState.COMPLETED if status is MissionStatus.CANCELLED else EventState.ACCEPTED)
        return updated

    def _save(self, mission: Mission) -> None:
        self._missions[mission.mission_id] = mission
        self.repository.update_mission(mission)

    async def _required(self, owner_id: str, mission_id: str) -> Mission:
        mission = await self.get(owner_id, mission_id)
        if mission is None:
            raise KeyError(mission_id)
        return mission

    def _hydrate(self, row: Mapping[str, object]) -> Mission:
        plan = self._plan(row.get("plan_json"))
        budget_values = json.loads(str(row["budget_json"]))
        budget = MissionBudget(**budget_values)
        result_value = json.loads(str(row["result_json"])) if row.get("result_json") else None
        result = MissionResult(**result_value) if result_value else None
        checkpoints = tuple(MissionCheckpoint(str(item["id"]), str(item["mission_id"]), str(item["title"]), str(item["status"]), datetime.fromisoformat(str(item["created_at"])), datetime.fromisoformat(str(item["completed_at"])) if item["completed_at"] else None, json.loads(str(item["evidence_json"]))) for item in self.repository.mission_checkpoints(str(row["id"])))
        evidence = tuple(MissionEvidence(str(item["id"]), str(item["mission_id"]), str(item["kind"]), str(item["locator"]), json.loads(str(item["details_json"])), datetime.fromisoformat(str(item["created_at"]))) for item in self.repository.mission_evidence(str(row["id"])))
        mission = Mission(str(row["id"]), str(row["owner_id"]), str(row["request"]), str(row["title"]), MissionStatus(str(row["status"])), row.get("goal_id"), plan, budget, checkpoints, evidence, int(row["current_step"]), int(row["tool_calls"]), int(row["worker_runs"]), int(row["external_actions"]), int(row["replan_count"]), row.get("blocked_reason"), row.get("approval_id"), result, datetime.fromisoformat(str(row["created_at"])), datetime.fromisoformat(str(row["updated_at"])), datetime.fromisoformat(str(row["completed_at"])) if row["completed_at"] else None)
        self._missions[mission.mission_id] = mission
        return mission

    @staticmethod
    def _plan(value: object) -> MissionPlan | None:
        if not value:
            return None
        data = json.loads(str(value))
        steps = tuple(MissionStep(str(item["step_id"]), str(item["title"]), str(item.get("status", "pending")), tuple(item.get("dependencies", ())), item.get("required_capability"), str(item.get("risk_level", "read")), bool(item.get("approval_required", False)), tuple(item.get("expected_evidence", ())), item.get("detail")) for item in data.get("steps", ()))
        dependencies = tuple(MissionDependency(str(item["mission_id"]), str(item.get("required_status", "completed"))) for item in data.get("dependencies", ()))
        return MissionPlan(steps, dependencies, str(data.get("risk_level", "read")), tuple(data.get("expected_evidence", ())), tuple(data.get("completion_criteria", ())))

    async def _emit(self, event_type: str, mission: Mission, state: EventState, extra: Mapping[str, object] | None = None) -> None:
        payload = {"owner_id": mission.owner_id, "mission_id": mission.mission_id, "title": mission.title, "status": mission.status.value, **dict(extra or {})}
        event = Event.create(event_type, EventCategory.MISSION, correlation_id=mission.mission_id, actor_id=mission.owner_id, payload=payload, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)
