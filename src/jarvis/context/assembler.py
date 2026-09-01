"""Assemble relevant context without dumping the whole runtime store."""

from __future__ import annotations

import json

from ..contracts import AgentContextSnapshot, DeviceIdentity, Identity, MemoryQuery, WorldStateQuery
from ..capabilities.registry import CapabilityRegistry
from ..memory.service import DurableMemoryService
from ..offline.service import OfflineModeService
from ..personalization.service import DurablePersonalizationService
from ..proactive.service import DurableProactiveService
from ..goals.engine import DurableGoalEngine
from ..tools.registry import ToolRegistry
from ..world_state.service import DurableWorldStateService
from ..perception.desktop import ActiveDesktopContextService


class ContextAssembler:
    """Retrieves bounded, inspectable context for a single model request."""

    def __init__(
        self,
        memory: DurableMemoryService,
        world_state: DurableWorldStateService,
        goals: DurableGoalEngine,
        proactive: DurableProactiveService,
        personalization: DurablePersonalizationService,
        tools: ToolRegistry,
        offline: OfflineModeService,
        capabilities: CapabilityRegistry | None = None,
        desktop_context: ActiveDesktopContextService | None = None,
    ) -> None:
        self.memory = memory
        self.world_state = world_state
        self.goals = goals
        self.proactive = proactive
        self.personalization = personalization
        self.tools = tools
        self.offline = offline
        self.capabilities = capabilities
        self.desktop_context = desktop_context

    async def capture_input(self, identity: Identity, text: str, source_reference: str | None = None) -> None:
        await self.memory.remember_from_conversation(identity.owner_id, text, source_reference)
        await self.personalization.learn_from_text(identity.owner_id, text)

    async def assemble(
        self,
        identity: Identity,
        device: DeviceIdentity,
        query: str,
        *,
        session_id: str = "perception",
        scope: str | None = None,
        scopes: tuple[str, ...] = (),
        project_id: str | None = None,
    ) -> AgentContextSnapshot:
        effective_scopes: list[str] = list(scopes)
        if scope and scope not in effective_scopes:
            effective_scopes.append(scope)
        if project_id:
            proj_scope = f"project:{project_id}"
            if proj_scope not in effective_scopes:
                effective_scopes.append(proj_scope)
        query_scope = effective_scopes[0] if len(effective_scopes) == 1 else None
        query_scopes = tuple(effective_scopes) if len(effective_scopes) > 1 else ()

        memories = await self.memory.search(MemoryQuery(
            identity.owner_id,
            query,
            limit=6,
            scope=query_scope,
            scopes=query_scopes,
            max_item_bytes=2048,
            max_total_bytes=4096,
        ))
        facts = await self.world_state.facts(WorldStateQuery(identity.owner_id))
        goals = await self.goals.list(identity.owner_id, ("active", "waiting", "blocked", "proposed", "draft"))
        findings = await self.proactive.list(identity.owner_id, active_only=True)
        profile = await self.personalization.get(identity.owner_id)
        memory_data = tuple(self._memory(item) for item in memories)
        fact_data = tuple(self._fact(item) for item in facts[:12])
        goal_data = tuple(self._goal(item) for item in goals[:8])
        finding_data = tuple(self._finding(item) for item in findings[:6])
        evidence = tuple(
            [f"memory:{item.memory_id}:{item.source_reference}" for item in memories if item.source_reference]
            + [f"world:{item.fact_id}:{item.source_reference}" for item in facts[:12] if item.source_reference]
            + [f"proactive:{item.finding_id}" for item in findings[:6]]
        )
        capability_names = [spec.name for spec in self.tools.list()]
        if self.capabilities is not None:
            capability_names.extend(item.capability_id for item in self.capabilities.list(device_id=device.device_id))
        desktop = self.desktop_context.safe_context(identity.owner_id, device.device_id, session_id) if self.desktop_context is not None else {"available": False}
        memory_bytes = sum(len(item.content.encode("utf-8")) for item in memories)
        selection_metadata = {
            "selected_memory_ids": [item.memory_id for item in memories],
            "selected_memory_count": len(memories),
            "memory_byte_estimate": memory_bytes,
            "selected_world_facts": len(fact_data),
            "active_goal_ids": [item.goal_id for item in goals[:8]],
            "active_finding_ids": [item.finding_id for item in findings[:6]],
        }
        return AgentContextSnapshot(
            identity={"identity_id": identity.identity_id, "owner_id": identity.owner_id, "display_name": identity.display_name, "roles": sorted(identity.roles), "device_id": device.device_id},
            memories=memory_data,
            world_state=fact_data,
            goals=goal_data,
            proactive_findings=finding_data,
            personalization=dict(profile.values) | {"internet_online": self.offline.state.online},
            tool_capabilities=tuple(sorted(set(capability_names))),
            evidence=evidence,
            desktop_context=desktop,
            metadata=selection_metadata,
        )

    @staticmethod
    def prompt(snapshot: AgentContextSnapshot) -> str:
        return "JARVIS context (bounded facts; do not infer beyond evidence):\n" + json.dumps(snapshot.as_dict(), ensure_ascii=False, sort_keys=True, default=str)

    @staticmethod
    def _memory(item) -> dict[str, object]:
        return {"id": item.memory_id, "category": item.category, "content": item.content, "confidence": item.confidence, "source": item.source, "tags": list(item.tags)}

    @staticmethod
    def _fact(item) -> dict[str, object]:
        return {"id": item.fact_id, "key": item.key, "value": item.value, "source": item.source, "observed_at": item.observed_at.isoformat(), "confidence": item.confidence, "conflict_state": item.conflict_state}

    @staticmethod
    def _goal(item) -> dict[str, object]:
        return {"id": item.goal_id, "title": item.title or item.statement, "status": item.status.value, "priority": item.priority, "next_action": item.next_action, "target_date": item.target_date.isoformat() if item.target_date else None}

    @staticmethod
    def _finding(item) -> dict[str, object]:
        return {"id": item.finding_id, "type": item.finding_type, "severity": item.severity, "evidence": dict(item.evidence), "recommended_action": item.recommended_action}
