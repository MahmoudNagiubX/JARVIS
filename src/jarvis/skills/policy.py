"""Skill safety checks that delegate execution authority to existing services."""

from __future__ import annotations

from ..authority.permissions.engine import PolicyPermissionEngine
from ..contracts import DeviceIdentity, Identity, PermissionEffect
from .models import Skill


class SkillPolicy:
    def __init__(self, permission: PolicyPermissionEngine) -> None:
        self.permission = permission

    async def evaluate(self, skill: Skill, identity: Identity, device: DeviceIdentity) -> tuple[bool, str]:
        if skill.manifest.status.value != "active":
            return False, "skill_disabled"
        decision = await self.permission.evaluate(identity, device, f"skill.{skill.manifest.skill_id}", {"required_scope": "tool.request", "required_capabilities": skill.manifest.required_capabilities, "risk_level": "read"})
        if decision.effect is PermissionEffect.DENY:
            return False, decision.reason_code
        return True, decision.reason_code
