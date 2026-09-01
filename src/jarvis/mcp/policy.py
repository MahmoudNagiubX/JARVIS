"""Explicit, host-owned MCP risk classification."""

from __future__ import annotations

from collections.abc import Mapping

from .models import MCPDiscoveredTool, MCPPolicyDecision, MCPRisk


class MCPPolicy:
    """Classify tools from host policy, never from server metadata alone."""

    def __init__(self, risk_overrides: Mapping[str, MCPRisk] | None = None) -> None:
        self._risk_overrides = dict(risk_overrides or {})

    def classify(self, tool: MCPDiscoveredTool) -> MCPPolicyDecision:
        key = f"{tool.server_id}.{tool.name}"
        namespaced = f"mcp.{key}"
        risk = self._risk_overrides.get(key, self._risk_overrides.get(namespaced, MCPRisk.DANGEROUS))
        if not isinstance(risk, MCPRisk):
            risk = MCPRisk(str(risk))
        # The existing JARVIS permission engine has an explicit consequential
        # approval path and fail-closed critical-risk behavior. Dangerous MCP
        # actions therefore retain dangerous metadata/autonomy while entering
        # that existing approval path instead of bypassing it.
        mapping = {
            MCPRisk.READ_ONLY: ("read", False, 0),
            MCPRisk.REVERSIBLE: ("reversible", False, 2),
            MCPRisk.CONSEQUENTIAL: ("consequential", True, 3),
            MCPRisk.DANGEROUS: ("consequential", True, 4),
        }
        tool_risk, approval, autonomy = mapping[risk]
        return MCPPolicyDecision(risk, tool_risk, approval, autonomy)
