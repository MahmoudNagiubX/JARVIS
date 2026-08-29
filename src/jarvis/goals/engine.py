"""Goal state machine with bounded plans and inspectable checkpoints."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from uuid import uuid4

from ..authority.audit.service import DurableAuditService
from ..bus import InMemoryEventBus
from ..contracts import AuditRecord, Goal, GoalCheckpoint, GoalStatus
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository


class DurableGoalEngine:
    """Persisted goal workflows; no recursive autonomous loop is permitted."""

    _allowed: dict[str, set[str]] = {
        "draft": {"active", "cancelled"},
        "proposed": {"active", "cancelled"},
        "active": {"waiting", "blocked", "paused", "completed", "cancelled", "failed"},
        "waiting": {"active", "blocked", "paused", "cancelled"},
        "blocked": {"active", "cancelled", "failed"},
        "paused": {"active", "cancelled"},
        "completed": set(),
        "cancelled": set(),
        "failed": set(),
    }

    def __init__(self, repository: RuntimeRepository, event_bus: InMemoryEventBus, audit: DurableAuditService | None = None) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.audit = audit

    async def create(self, goal: Goal) -> Goal:
        if self.repository.owner(goal.owner_id) is None:
            raise ValueError("goal owner is unavailable")
        title = (goal.title or goal.statement).strip()
        description = (goal.description or goal.statement).strip()
        if not title or not description:
            raise ValueError("goal title and description cannot be empty")
        if len(goal.steps) > 100 or len(goal.plan) > 100:
            raise ValueError("goal plan exceeds bounded step limit")
        budget = dict(goal.budget)
        if int(budget.get("max_steps", max(1, len(goal.steps) or 20))) > 100:
            raise ValueError("goal budget max_steps exceeds limit")
        created = goal.created_at or datetime.now(UTC)
        normalized = Goal(
            goal.goal_id or f"goal-{uuid4()}", goal.owner_id, description,
            goal.status, created, dict(goal.metadata), title, description, goal.priority,
            goal.target_date, dict(goal.constraints), budget, tuple(goal.plan), tuple(goal.steps),
            tuple(goal.dependencies), tuple(goal.checkpoints), goal.next_action,
            goal.last_reviewed_at, tuple(goal.completion_criteria),
        )
        self.repository.insert_goal(normalized)
        await self._emit("goal.created", normalized.owner_id, {"goal_id": normalized.goal_id, "title": title}, EventState.COMPLETED)
        return normalized

    async def get(self, owner_id: str, goal_id: str) -> Goal | None:
        row = self.repository.goal(owner_id, goal_id)
        return self._goal(row) if row else None

    async def list(self, owner_id: str, statuses: Sequence[GoalStatus | str] = ()) -> tuple[Goal, ...]:
        values = tuple(item.value if isinstance(item, GoalStatus) else item for item in statuses)
        return tuple(self._goal(row) for row in self.repository.goals(owner_id, values))

    async def update(
        self,
        owner_id: str,
        goal_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        priority: int | None = None,
        target_date: datetime | None = None,
        constraints: Mapping[str, object] | None = None,
        budget: Mapping[str, object] | None = None,
        next_action: str | None = None,
        completion_criteria: Sequence[str] | None = None,
    ) -> Goal:
        current = await self._required(owner_id, goal_id)
        fields: dict[str, object] = {"last_reviewed_at": datetime.now(UTC)}
        if title is not None:
            if not title.strip():
                raise ValueError("goal title cannot be empty")
            fields["title"] = title.strip()
        if description is not None:
            if not description.strip():
                raise ValueError("goal description cannot be empty")
            fields["description"] = description.strip()
        if priority is not None:
            fields["priority"] = int(priority)
        if target_date is not None:
            fields["target_date"] = target_date
        if constraints is not None:
            fields["constraints_json"] = json.dumps(dict(constraints), ensure_ascii=False)
        if budget is not None:
            normalized_budget = dict(budget)
            if int(normalized_budget.get("max_steps", current.budget.get("max_steps", 20))) > 100:
                raise ValueError("goal budget max_steps exceeds limit")
            fields["budget_json"] = json.dumps(normalized_budget, ensure_ascii=False)
        if next_action is not None:
            fields["next_action"] = next_action.strip() or None
        if completion_criteria is not None:
            fields["completion_criteria_json"] = json.dumps([item.strip() for item in completion_criteria if item.strip()], ensure_ascii=False)
        row = self.repository.update_goal(owner_id, goal_id, **fields)
        await self._emit("goal.updated", owner_id, {"goal_id": goal_id}, EventState.COMPLETED)
        return self._goal(row)

    async def transition(self, goal_id: str, status: GoalStatus, owner_id: str | None = None) -> Goal | None:
        if owner_id is None:
            raise ValueError("owner_id is required for goal transition")
        current = await self.get(owner_id, goal_id)
        if current is None:
            return None
        if status.value not in self._allowed.get(current.status.value, set()):
            raise ValueError(f"invalid goal transition {current.status.value}->{status.value}")
        row = self.repository.update_goal(owner_id, goal_id, status=status.value, last_reviewed_at=datetime.now(UTC))
        event_name = {
            GoalStatus.ACTIVE.value: "goal.activated",
            GoalStatus.BLOCKED.value: "goal.blocked",
            GoalStatus.COMPLETED.value: "goal.completed",
            GoalStatus.CANCELLED.value: "goal.cancelled",
        }.get(status.value, f"goal.{status.value}")
        await self._audit(owner_id, event_name, status.value, {"goal_id": goal_id})
        await self._emit(event_name, owner_id, {"goal_id": goal_id, "from": current.status.value, "to": status.value}, EventState.COMPLETED if status in {GoalStatus.COMPLETED, GoalStatus.CANCELLED} else EventState.ACCEPTED)
        return self._goal(row)

    async def activate(self, owner_id: str, goal_id: str) -> Goal | None:
        return await self.transition(goal_id, GoalStatus.ACTIVE, owner_id)

    async def pause(self, owner_id: str, goal_id: str) -> Goal | None:
        return await self.transition(goal_id, GoalStatus.PAUSED, owner_id)

    async def resume(self, owner_id: str, goal_id: str) -> Goal | None:
        return await self.transition(goal_id, GoalStatus.ACTIVE, owner_id)

    async def cancel(self, owner_id: str, goal_id: str) -> Goal | None:
        return await self.transition(goal_id, GoalStatus.CANCELLED, owner_id)

    async def complete(self, owner_id: str, goal_id: str) -> Goal | None:
        return await self.transition(goal_id, GoalStatus.COMPLETED, owner_id)

    async def plan(self, owner_id: str, goal_id: str, steps: Sequence[str], next_action: str | None = None) -> Goal:
        current = await self._required(owner_id, goal_id)
        if len(steps) > int(current.budget.get("max_steps", 20)) or len(steps) > 100:
            raise ValueError("goal plan exceeds budget")
        normalized_steps = tuple({"id": f"step-{index + 1}", "title": step.strip(), "status": "pending"} for index, step in enumerate(steps) if step.strip())
        row = self.repository.update_goal(owner_id, goal_id, plan_json=json.dumps(list(steps), ensure_ascii=False), steps_json=json.dumps(list(normalized_steps), ensure_ascii=False), next_action=next_action, last_reviewed_at=datetime.now(UTC))
        await self._emit("goal.step_started", owner_id, {"goal_id": goal_id, "step_count": len(normalized_steps)})
        return self._goal(row)

    async def checkpoint(self, owner_id: str, goal_id: str, title: str, *, completed: bool = False, evidence: Mapping[str, object] | None = None) -> Goal:
        current = await self._required(owner_id, goal_id)
        checkpoint = GoalCheckpoint(f"checkpoint-{uuid4()}", goal_id, title.strip(), "completed" if completed else "open", datetime.now(UTC), datetime.now(UTC) if completed else None, dict(evidence or {}))
        checkpoints = list(current.checkpoints) + [{"checkpoint_id": checkpoint.checkpoint_id, "title": checkpoint.title, "status": checkpoint.status, "created_at": checkpoint.created_at.isoformat(), "completed_at": checkpoint.completed_at.isoformat() if checkpoint.completed_at else None, "evidence": dict(checkpoint.evidence)}]
        row = self.repository.update_goal(owner_id, goal_id, checkpoints_json=json.dumps(checkpoints, ensure_ascii=False), last_reviewed_at=datetime.now(UTC))
        await self._emit("goal.step_completed" if completed else "goal.checkpoint", owner_id, {"goal_id": goal_id, "checkpoint_id": checkpoint.checkpoint_id}, EventState.COMPLETED if completed else EventState.ACCEPTED)
        return self._goal(row)

    async def bounded_replan(self, owner_id: str, goal_id: str, steps: Sequence[str], reason: str) -> Goal:
        current = await self._required(owner_id, goal_id)
        used = int(current.metadata.get("replans", 0))
        maximum = int(current.budget.get("max_replans", 3))
        if used >= maximum:
            raise ValueError("goal replan budget exhausted")
        metadata = dict(current.metadata)
        metadata["replans"] = used + 1
        metadata["last_replan_reason"] = reason
        row = self.repository.update_goal(owner_id, goal_id, metadata_json=json.dumps(metadata, ensure_ascii=False), last_reviewed_at=datetime.now(UTC))
        updated = self._goal(row)
        return await self.plan(owner_id, updated.goal_id, steps, updated.next_action)

    async def _required(self, owner_id: str, goal_id: str) -> Goal:
        goal = await self.get(owner_id, goal_id)
        if goal is None:
            raise KeyError(goal_id)
        return goal

    @staticmethod
    def _goal(row: Mapping[str, object]) -> Goal:
        return Goal(
            row["id"], row["owner_id"], row["description"], GoalStatus(row["status"]), datetime.fromisoformat(row["created_at"]), json.loads(row["metadata_json"]), row["title"], row["description"], row["priority"], datetime.fromisoformat(row["target_date"]) if row["target_date"] else None, json.loads(row["constraints_json"]), json.loads(row["budget_json"]), tuple(json.loads(row["plan_json"])), tuple(json.loads(row["steps_json"])), tuple(json.loads(row["dependencies_json"])), tuple(json.loads(row["checkpoints_json"])), row["next_action"], datetime.fromisoformat(row["last_reviewed_at"]) if row["last_reviewed_at"] else None, tuple(json.loads(row["completion_criteria_json"])),
        )

    async def _audit(self, owner_id: str, event_type: str, outcome: str, metadata: dict[str, object]) -> None:
        if self.audit:
            await self.audit.record(AuditRecord(f"audit-{uuid4()}", event_type, datetime.now(UTC), owner_id, None, f"goal-{owner_id}", outcome, None, metadata))

    async def _emit(self, event_type: str, owner_id: str, payload: dict[str, object], state: EventState = EventState.EMITTED) -> None:
        event = Event.create(event_type, EventCategory.GOAL, correlation_id=f"goal-{owner_id}", actor_id=owner_id, payload=payload, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)
