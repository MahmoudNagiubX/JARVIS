"""Explicit, fail-closed permission evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ...contracts import DeviceIdentity, Identity, PermissionDecision, PermissionEffect


@dataclass(frozen=True, slots=True)
class PermissionRule:
    action_prefix: str
    effect: PermissionEffect
    reason_code: str


class PolicyPermissionEngine:
    """Evaluate actor, device, capability, scope, risk, and policy together."""

    def __init__(self, rules: tuple[PermissionRule, ...] = ()) -> None:
        self.rules = rules or (
            PermissionRule("tool.status.read", PermissionEffect.ALLOW, "safe_read_tool"),
            PermissionRule("tool.echo.reversible", PermissionEffect.ALLOW, "reversible_tool"),
            PermissionRule("tool.", PermissionEffect.REQUIRE_APPROVAL, "tool_policy_requires_approval"),
            PermissionRule("computer.", PermissionEffect.REQUIRE_APPROVAL, "computer_action_requires_approval"),
        )

    async def evaluate(
        self,
        identity: Identity | None,
        device: DeviceIdentity | None,
        action: str,
        resource: Mapping[str, object] | None = None,
    ) -> PermissionDecision:
        resource = resource or {}
        if identity is None or device is None:
            return PermissionDecision(PermissionEffect.DENY, "identity_or_device_missing")
        if identity.owner_id != device.owner_id:
            return PermissionDecision(PermissionEffect.DENY, "owner_binding_mismatch")
        required_scope = resource.get("required_scope")
        if isinstance(required_scope, str) and required_scope not in device.scopes:
            return PermissionDecision(PermissionEffect.DENY, "scope_missing")
        required_capabilities = resource.get("required_capabilities", ())
        if any(capability not in device.capabilities for capability in required_capabilities):
            return PermissionDecision(PermissionEffect.DENY, "device_capability_missing")
        risk = str(resource.get("risk_level", "read"))
        if risk in {"critical", "forbidden_autonomous"}:
            return PermissionDecision(PermissionEffect.DENY, "risk_forbidden_by_default")
        if bool(resource.get("requires_approval", False)) or risk == "consequential":
            return PermissionDecision(PermissionEffect.REQUIRE_APPROVAL, "risk_requires_approval")
        for rule in self.rules:
            if action.startswith(rule.action_prefix):
                return PermissionDecision(rule.effect, rule.reason_code)
        return PermissionDecision(PermissionEffect.DENY, "no_allow_rule")
