# Phase 15 Skill Architecture

Skills remain owned by `SkillRegistry`, `SkillPolicy`, `SkillLoader`, and
`SkillExecutor`. An MCP-backed skill is only a reviewed skill step whose tool
name resolves through the existing native `ToolRegistry`.

The executor still validates the manifest, checks enablement and dependencies,
enforces the skill policy, and invokes `ToolExecutionService`. The MCP adapter
does not execute a skill directly and does not create a second approval path.

Safe local skills may read bounded MCP workspace/repository data. Consequential
steps remain approval-gated. Untrusted manifests, instructions, and tool output
are data; they cannot register arbitrary executable behavior or widen a skill's
permissions. Disabled skills and unavailable dependencies fail closed.
