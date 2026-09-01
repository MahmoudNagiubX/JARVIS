# Phase 15 Capability Gap Matrix

Audit date: 2026-09-01. The current Phase 14 repository is green; the rows below describe Phase 15 deltas only.

| Capability | Existing authority | Current state | Phase 15 gap | Planned bounded activation | Evidence/gate |
|---|---|---|---|---|---|
| MCP client | ToolRegistry/ToolExecutionService | No `src/jarvis/mcp` package | No governed stdio lifecycle, discovery, normalization, or namespace policy | Product-owned lazy stdio client with strict config and normalized specs | Discovery, health, timeout, cancel, crash, payload, env, collision, secret tests |
| Workspace/filesystem | WorkspaceIntelligenceService and WorkspaceContextService | Explicit-root metadata is available | No MCP-facing capability | One read-only local workspace capability routed through existing path checks | Traversal/symlink/owner/bounds tests |
| Browser | BrowserActionService and LocalBrowserController | Deterministic local/read path; Playwright is injected/deferred | No MCP activation and no deterministic local integration fixture | Normalize one local browser capability; preserve existing browser authority | Local HTML, unsafe URL, approval/audit tests |
| Developer/repository | DeveloperWorkerGateway and EngineeringService | Provider seams exist; external workers deferred | No safe MCP-backed repo/Jupyter capability | Read-only repo/Jupyter adapter contract with bounded outputs | Scope, trust, approval, audit tests |
| Skills | SkillRegistry, SkillPolicy, SkillExecutor | Built-ins, versioning, progressive loading exist | No reviewed MCP-backed skill | One product-owned reviewed skill using normalized capability | Provenance/trust/policy/approval tests |
| Research | ResearchService plus local/browser providers | Local-first evidence ledger exists | No Phase 15 MCP/evidence activation and no malicious-content test matrix | Local fixture evidence path; external content remains data | Provenance, fingerprint, bounds, injection-isolation tests |
| Selection/context | ToolSchemaSelector and AgentRuntime | Max 8 schemas; English/Arabic markers exist | No MCP selection reason/byte accounting | Extend only if a failing focused test demonstrates missing accounting | Schema budget and bilingual tests |
| Experience | ExperienceProjection and API/UI health | Truthful existing projection | No MCP/skill/browser/research capability health detail | Add read-only states only after event/health contract is defined | Healthy/offline/error/empty UI tests |
| Dependencies | Empty runtime dependencies | Optional voice only | No need for MCP SDK dependency | Stdlib protocol client unless an evidence-backed dependency is unavoidable | `pyproject`, audit, compileall |

No row authorizes replacing an existing service or adding a second authority.
