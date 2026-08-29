"""Skill policy that preserves the risk and authority of every source step."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ..authority.permissions.engine import PolicyPermissionEngine
from ..contracts import DeviceIdentity, Identity, PermissionEffect
from ..tools.registry import ToolRegistry
from .models import Skill, SkillStep


RISK_ORDER = {
    "read": 0,
    "safe": 1,
    "reversible": 2,
    "consequential": 3,
    "critical": 4,
    "forbidden_autonomous": 5,
}


@dataclass(frozen=True, slots=True)
class SkillPolicyDecision:
    allowed: bool
    reason: str
    effect: PermissionEffect = PermissionEffect.DENY
    effective_risk: str = "read"
    approval_required: bool = False


class SkillPolicy:
    def __init__(self, permission: PolicyPermissionEngine, registry: ToolRegistry | None = None) -> None:
        self.permission = permission
        self.registry = registry

    async def evaluate(self, skill: Skill, identity: Identity, device: DeviceIdentity) -> tuple[bool, str]:
        decision = await self.evaluate_detail(skill, identity, device)
        return decision.allowed, decision.reason

    async def evaluate_detail(self, skill: Skill, identity: Identity, device: DeviceIdentity) -> SkillPolicyDecision:
        if skill.manifest.status.value != "active":
            return SkillPolicyDecision(False, "skill_disabled")
        risks: list[str] = [skill.manifest.risk_level]
        for step in skill.steps:
            risks.append(step.risk_level)
            if step.requires_approval and RISK_ORDER.get(step.risk_level, -1) < RISK_ORDER["consequential"]:
                risks.append("consequential")
            if step.action.startswith("tool:"):
                if self.registry is None:
                    return SkillPolicyDecision(False, "tool_registry_unavailable")
                spec = self.registry.get(step.action.removeprefix("tool:"))
                if spec is None or not spec.enabled:
                    return SkillPolicyDecision(False, "unknown_or_disabled_tool")
                risks.append(spec.risk_level)
                if spec.requires_approval:
                    risks.append("consequential")
        risk = self._most_restrictive(risks)
        if risk is None:
            return SkillPolicyDecision(False, "unknown_risk_level")
        required = set(skill.manifest.required_capabilities)
        required.update(cap for step in skill.steps for cap in step.required_capabilities)
        effect = PermissionEffect.ALLOW
        reason = "registered_skill_execution"
        steps = skill.steps or (SkillStep("skill", skill.manifest.name, f"skill.{skill.manifest.skill_id}", risk_level=risk),)
        for step in steps:
            step_risk = self._most_restrictive((skill.manifest.risk_level, step.risk_level))
            if step_risk is None:
                return SkillPolicyDecision(False, "unknown_risk_level", effective_risk=risk)
            step_required = tuple(required | set(step.required_capabilities))
            action = step.action.removeprefix("tool:") if step.action.startswith("tool:") else step.action
            resource = {
                "required_scope": "tool.request",
                "required_capabilities": step_required,
                "risk_level": step_risk,
                "requires_approval": step.requires_approval,
            }
            decision = await self.permission.evaluate(identity, device, f"tool.{action}" if step.action.startswith("tool:") else action, resource)
            if decision.effect is PermissionEffect.DENY:
                return SkillPolicyDecision(False, decision.reason_code, decision.effect, risk)
            if decision.effect is PermissionEffect.REQUIRE_APPROVAL:
                effect = decision.effect
                reason = "approval_required"
        return SkillPolicyDecision(True, reason, effect, risk, effect is PermissionEffect.REQUIRE_APPROVAL)

    @staticmethod
    def _most_restrictive(risks: Iterable[str]) -> str | None:
        values = tuple(risks)
        if any(risk not in RISK_ORDER for risk in values):
            return None
        return max(values, key=lambda risk: RISK_ORDER[risk], default="read")
