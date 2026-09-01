# Phase 15 MCP, Skills, Browser, and Research Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the Phase 15 execution file by auditing the existing Jarvis authorities, then adding a governed local MCP/capability integration layer and activating bounded workspace, browser, developer, skill, and research paths without duplicating existing runtime authority.

**Architecture:** External or local MCP servers are clients only. Their discovered capabilities are normalized into the existing ToolRegistry/SkillRegistry, then pass through PermissionEngine, ApprovalEngine where required, ToolExecutionService, and AuditService. Existing AgentRuntime, BrowserActionService, ResearchService, WorkspaceIntelligenceService, DeveloperWorkerGateway, SkillExecutor, EventBus, and ExperienceProjection remain authoritative.

**Tech Stack:** Python 3.12 project, pytest, existing FastAPI/service contracts, TypeScript/React UI, npm, stdio subprocess transport, Markdown audit records.

**Spec:** `C:\Users\mahmo\Downloads\JARVIS_MEGA_PHASE_15_MCP_SKILLS_BROWSER_RESEARCH.md`

## Global Constraints

- Preserve the required base commit `dd52746d01aaedc1277c9d98d8aa743734e9d3ac` and all Phase 14 behavior.
- Preserve `tasks/plan.md` and `tasks/todo.md` unchanged; use this plan for Phase 15 tracking.
- Donor directories are read-only evidence. Do not copy code without recording provenance and salvage rationale.
- No duplicate scheduler, EventBus, VoiceCore, identity, policy, approval, audit, browser, research, or runtime authority.
- No arbitrary internet MCP endpoints, unrestricted shell capability, raw secret persistence, broad SQL cleanup, or reopening physical voice acceptance.
- Use test-first implementation. If a test exposes a real defect, make the smallest fix required and add regression coverage.
- Keep external content separate from trusted instructions; enforce bounded payloads, schemas, timeouts, cancellation, environment allowlists, namespacing, and structured errors.

## Task 1 — Block 1 audit and baseline

- [ ] Verify branch, exact base, clean worktree, Python/package versions, and existing test baselines.
- [ ] Inspect current canonical authorities, registrations, selectors/context budgets, API/UI projections, and startup wiring in bounded batches.
- [ ] Search local candidate/donor directories read-only and record exact reuse, salvage, reject, and provenance decisions.
- [ ] Create and review:
  - `docs/phase15/CURRENT_CAPABILITY_ARCHITECTURE.md`
  - `docs/phase15/CAPABILITY_GAP_MATRIX.md`
  - `docs/phase15/DONOR_CAPABILITY_SCAN.md`
  - `docs/phase15/DONOR_SALVAGE_MAP.md`
  - `docs/THIRD_PARTY_INVENTORY.md`

## Task 2 — Governed local MCP foundation

- [ ] Add the smallest `src/jarvis/mcp/` models, stdio client, lifecycle/health handling, normalization, and policy boundary needed by the audit.
- [ ] Implement lazy start/restart, bounded discovery/results, explicit executable/argument/cwd/environment configuration, timeout/cancel handling, crash isolation, and no orphan processes.
- [ ] Namespace discovered tools and route execution into existing registry, permission, approval, execution, and audit authorities.
- [ ] Add `tests/test_phase_fifteen_mcp_foundation.py` covering discovery, health, namespace collision, read/approval policy, timeout, cancellation, crash isolation, payload bounds, environment allowlist, and secret exclusion.

## Task 3 — Bounded selection and workspace capability

- [ ] Reuse the existing tool selector/context budget and record selection reason and schema bytes; only change it when a focused test identifies a defect.
- [ ] Expose one deterministic local workspace/filesystem capability through the MCP normalization boundary and existing workspace safety checks.
- [ ] Add `tests/test_phase_fifteen_capability_selection.py` and `tests/test_phase_fifteen_workspace_mcp.py` with bilingual/mixed-language requests and path-traversal/symlink/approval cases.

## Task 4 — Skills and developer/repository capability

- [ ] Reuse SkillRegistry, SkillPolicy, SkillExecutor, DeveloperWorkerGateway, and EngineeringService contracts.
- [ ] Add one reviewed MCP-backed/enhanced skill and one safe repository/Jupyter-oriented capability; no unrestricted shell or automatic execution of untrusted skills.
- [ ] Add `tests/test_phase_fifteen_skills.py` and `tests/test_phase_fifteen_developer_capability.py` for trust, provenance, policy, approval, bounded output, and audit behavior.

## Task 5 — Deterministic browser path

- [ ] Reuse BrowserActionService and its local/injected browser controllers; do not add a second browser agent or visual default.
- [ ] Activate one local deterministic HTML fixture path for open/read/click/type as supported by existing safe contracts.
- [ ] Add `tests/test_phase_fifteen_browser.py` for local navigation, bounded DOM extraction, unsafe URL/input rejection, permission/approval, and audit behavior.

## Task 6 — Local-first research and evidence provenance

- [ ] Reuse ResearchService, LocalDocumentProvider, and BrowserResearchProvider with local/offline-first behavior.
- [ ] Add bounded evidence ledger/provenance, citation metadata, malicious-evidence isolation, and deterministic local fixture coverage.
- [ ] Add `tests/test_phase_fifteen_research.py` and focused UI research coverage where the existing frontend test structure requires it.

## Task 7 — Experience projection and operator visibility

- [ ] Extend existing read-only experience/API projection only for truthful MCP, skill, browser, research, and capability health/availability.
- [ ] Add `tests/test_phase_fifteen_experience_projection.py` and UI tests for loading, empty, offline, error, and healthy states without fake live claims.

## Task 8 — Acceptance, review, and handoff

- [ ] Run focused Phase 15 tests to zero failures, then Phase 14/13 regressions, full repository tests, frontend tests/build, compileall, diff check, and security/dependency gates supported by the repository.
- [ ] Review the complete diff for duplicate authorities, broad SQL cleanup, secret leakage, unsafe process/URL/path behavior, and ungrounded online/physical claims.
- [ ] Update Phase 15 audit/handoff docs with actual counts and known limitations.
- [ ] Make one coherent commit, push `main`, verify local HEAD equals remote `main`, verify a clean worktree, and stop before Phase 16.
