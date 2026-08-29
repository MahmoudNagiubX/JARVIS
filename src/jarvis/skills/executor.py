"""Declarative skill executor; no skill can invoke a shell or bypass tools."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from uuid import uuid4

from ..bus import InMemoryEventBus
from ..contracts import DeviceIdentity, Identity, ToolContext
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository
from ..tools.service import ToolExecutionService, ToolExecutionStatus
from .loader import SkillLoader
from .models import Skill, SkillInput, SkillOutput
from .policy import SkillPolicy
from .registry import SkillRegistry


SkillHandler = Callable[[Skill, Mapping[str, object], Identity, DeviceIdentity], object | Awaitable[object]]


class SkillExecutor:
    def __init__(self, registry: SkillRegistry, policy: SkillPolicy, event_bus: InMemoryEventBus, repository: RuntimeRepository, *, tools: ToolExecutionService | None = None, handlers: Mapping[str, SkillHandler] | None = None, loader: SkillLoader | None = None) -> None:
        self.registry = registry
        self.policy = policy
        self.event_bus = event_bus
        self.repository = repository
        self.tools = tools
        self.handlers = dict(handlers or {})
        self.loader = loader or SkillLoader()

    async def execute(self, skill_id: str, values: Mapping[str, object], identity: Identity, device: DeviceIdentity) -> SkillOutput:
        skill = self.registry.get(skill_id)
        if skill is None:
            return SkillOutput(skill_id, "unavailable", error_code="skill_not_found")
        allowed, reason = await self.policy.evaluate(skill, identity, device)
        if not allowed:
            return SkillOutput(skill_id, "denied", error_code=reason)
        try:
            skill = self.loader.load(skill)
        except Exception as exc:
            return SkillOutput(skill_id, "failed", error_code=f"instructions:{exc.__class__.__name__}")
        await self._emit("skill.loaded", skill, identity.owner_id, {"progressive": True})
        await self._emit("skill.started", skill, identity.owner_id)
        results: list[Mapping[str, object]] = []
        for step in skill.steps:
            if step.requires_approval:
                await self._emit("skill.failed", skill, identity.owner_id, {"error_code": "approval_required"}, EventState.FAILED)
                return SkillOutput(skill_id, "approval_required", tuple(results), "approval_required")
            arguments = dict(step.arguments)
            arguments.update(values)
            if step.action.startswith("tool:"):
                if self.tools is None:
                    return SkillOutput(skill_id, "unavailable", tuple(results), "tool_executor_unavailable")
                context = ToolContext(identity, device, f"skill-{uuid4()}", f"skill-{skill_id}")
                result = await self.tools.execute(step.action.removeprefix("tool:"), arguments, context)
                results.append({"step_id": step.step_id, "status": result.status.value, "output": result.output, "error_code": result.error_code})
                if result.status is not ToolExecutionStatus.COMPLETED:
                    await self._emit("skill.failed", skill, identity.owner_id, {"error_code": result.error_code or result.status.value}, EventState.FAILED)
                    return SkillOutput(skill_id, result.status.value, tuple(results), result.error_code)
                continue
            handler = self.handlers.get(step.action)
            if handler is None:
                return SkillOutput(skill_id, "unavailable", tuple(results), f"handler_not_configured:{step.action}")
            try:
                value = handler(skill, arguments, identity, device)
                value = await value if inspect.isawaitable(value) else value
                results.append(value if isinstance(value, Mapping) else {"value": value})
            except Exception as exc:
                await self._emit("skill.failed", skill, identity.owner_id, {"error_code": exc.__class__.__name__}, EventState.FAILED)
                return SkillOutput(skill_id, "failed", tuple(results), exc.__class__.__name__)
        await self._emit("skill.completed", skill, identity.owner_id, {"step_count": len(skill.steps)}, EventState.COMPLETED)
        return SkillOutput(skill_id, "completed", tuple(results), evidence=(f"skill:{skill_id}",))

    async def _emit(self, event_type: str, skill: Skill, owner_id: str, extra: Mapping[str, object] | None = None, state: EventState = EventState.EMITTED) -> None:
        event = Event.create(event_type, EventCategory.SKILL, correlation_id=f"skill-{skill.manifest.skill_id}", actor_id=owner_id, payload={"owner_id": owner_id, "skill_id": skill.manifest.skill_id, "version": skill.manifest.version, **dict(extra or {})}, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)
