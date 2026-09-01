# Phase 15 Acceptance

## Product paths

- [x] Local workspace MCP read/list and approval-gated bounded write.
- [x] Local repository inspection through registered workspace intelligence.
- [x] Existing deterministic browser navigation/read/DOM interaction path.
- [x] Shared fail-closed browser URL/redirect policy and redacted approval
  retention for browser interactions.
- [x] Browser read and interaction tools are reachable through the existing
  AgentRuntime path with exactly one delegated approval authority.
- [x] MCP-discovered input schemas are reduced to bounded structural fields
  before registration and model exposure.
- [x] MCP-backed skill step through the existing skill executor.
- [x] Local research evidence, provenance, deduplication, cancellation, and
  malicious-content isolation.
- [x] Bounded bilingual/mixed capability selection.
- [x] Truthful MCP health projection in the Command Center/API.
- [x] Existing permission, approval, audit, and EventBus authorities remain
  canonical.

## Required gates

The final review records actual output for focused Phase 15 tests, Phase 14 and
Phase 13 regression, the full Python suite, frontend tests/build/audit,
`compileall`, `git diff --check`, security review, remote equality, and clean
worktree. Final recorded counts are Phase 15 `39 passed, 11 subtests passed`,
Phase 14 `19 passed`, Phase 13 `107 passed`, full Python `383 passed, 36
subtests passed`, and frontend `13 files / 66 tests passed`. Physical voice acceptance is intentionally
not a Phase 15 gate.
