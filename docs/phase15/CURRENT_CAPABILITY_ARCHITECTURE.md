# Phase 15 Current Capability Architecture

Audit date: 2026-09-01
Required base: `dd52746d01aaedc1277c9d98d8aa743734e9d3ac`
Baseline: Python `342 passed, 25 subtests passed`; UI `8 files, 25 tests passed`; UI production build passed.

## Authority spine

`create_runtime()` composes one `InMemoryEventBus`, one `AgentRuntime`, one `BackgroundScheduler`, one `VoiceCore`, one `ToolRegistry`, and one `ToolExecutionService`. Identity, device, permission, approval, audit, repository, memory, world state, goals, missions, automation, browser, research, skills, workspace, engineering, and experience services are injected into that composition. No second scheduler, EventBus, VoiceCore, or agent authority is present.

## Capability flow today

1. `AgentRuntime` selects bounded schemas through `ToolSchemaSelector` using the latest user message.
2. `ToolExecutionService` resolves a registered `ToolSpec`, validates arguments, evaluates `PolicyPermissionEngine`, creates durable approvals when required, executes the handler, records bounded results, audits, and emits normalized events.
3. `SkillExecutor` evaluates `SkillPolicy`, progressively loads local Markdown instructions, executes handlers or existing tools, persists execution state, and handles approvals.
4. `BrowserActionService` applies permission/approval/audit/event behavior around `LocalBrowserController` or an injected Playwright controller.
5. `ResearchService` searches configured local documents first, optionally uses an injected browser provider, bounds sources/excerpts, records fingerprints/evidence/citations, and emits/audits state.
6. `WorkspaceIntelligenceService` operates only on an explicitly registered project root and returns bounded metadata/repo-map data.
7. `CapabilityRegistry` advertises truthful availability; `ExperienceProjection` derives read-only owner-scoped UI state from events and the existing health loader.

## Phase 15 integration rule

The new layer may discover or invoke external/local MCP servers only as clients. The required route is:

`local/external MCP stdio -> JARVIS MCP client -> normalized capability -> existing ToolRegistry/SkillRegistry -> PermissionEngine -> ApprovalEngine when needed -> ToolExecutionService -> AuditService/EventBus/ExperienceProjection`.

MCP metadata cannot grant authority. Browser, research, workspace, engineering, and skill adapters remain product-owned boundaries, with donor code used only as read-only evidence.
