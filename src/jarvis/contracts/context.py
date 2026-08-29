"""Inspectable, budgeted agent-context contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AgentContextSnapshot:
    identity: Mapping[str, object]
    memories: tuple[Mapping[str, object], ...] = ()
    world_state: tuple[Mapping[str, object], ...] = ()
    goals: tuple[Mapping[str, object], ...] = ()
    proactive_findings: tuple[Mapping[str, object], ...] = ()
    personalization: Mapping[str, object] = field(default_factory=dict)
    tool_capabilities: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "identity": dict(self.identity),
            "memories": [dict(item) for item in self.memories],
            "world_state": [dict(item) for item in self.world_state],
            "goals": [dict(item) for item in self.goals],
            "proactive_findings": [dict(item) for item in self.proactive_findings],
            "personalization": dict(self.personalization),
            "tool_capabilities": list(self.tool_capabilities),
            "evidence": list(self.evidence),
        }
