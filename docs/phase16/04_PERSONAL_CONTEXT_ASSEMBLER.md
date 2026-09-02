# Phase 16: Personal Context Assembler

## 1. Assembly Architecture & Priority Order
`ContextAssembler` builds an inspectable, bounded snapshot for every model request. Context is assembled following a strict priority hierarchy:

1. **Authority & Policy Boundaries**: Root system instructions, tool capability constraints, offline mode state.
2. **Current Request / User Turn**: The explicit prompt or request provided by the owner.
3. **Fresh Authoritative World State**: Up to 12 active unexpired facts from `DurableWorldStateService`.
4. **Active Goals & Missions**: Up to 8 active or blocked goals from `DurableGoalEngine`.
5. **Accepted Relevant Memories**: Up to 6 high-confidence records ranked by `KeywordMemoryRetriever`.
6. **Desktop & Peripheral Perception**: Bounded active window and device telemetry from `ActiveDesktopContextService`.
7. **Personalization & Preferences**: Profile settings, verbosity preferences, and online connectivity state.

## 2. Strict Budget Caps & Selection Metadata

```python
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
    desktop_context: Mapping[str, object] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)
```

### Selection Metadata Trace
Every snapshot includes transparent selection telemetry:
- `selected_memory_ids`: Exact UUIDs of memories chosen for the turn.
- `selected_memory_count`: Total memory count (capped <= 6).
- `memory_byte_estimate`: Byte volume of memory payload.
- `selected_world_facts`: Fact count (capped <= 12).
- `active_goal_ids`: Goal IDs provided in context (capped <= 8).
- `active_finding_ids`: Proactive finding IDs (capped <= 6).

## 3. Symmetric Project Context Scoping
When assembling context for a specific `project_id` (e.g. `"alpha"`):
- `effective_scopes` is expanded to include `"owner"` (global) and `"project:alpha"`.
- Both `MemoryQuery` and `WorldStateQuery` are scoped symmetrically with `scopes=("owner", "project:alpha")`.
- Global owner preferences and facts, alongside project-specific memories and facts, are included in the turn context.
- Unrelated project memories and world facts (e.g. `project:beta`) are strictly excluded.
