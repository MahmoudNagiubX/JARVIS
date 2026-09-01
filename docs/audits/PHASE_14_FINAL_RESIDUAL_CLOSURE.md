# JARVIS Phase 14 — Final Residual Closure

Base: `6f4b2a77e142412dccdb9f56b1c388ca8b09bbea`

## Scope

This closure addresses only the three residual UI contracts in the execution
spec. The accepted local runtime architecture remains unchanged: the existing
AgentRuntime, model gateway, NotificationService, EventBus, scheduler,
VoiceCore, loopback HTTP boundary, and embedded local asset boundary remain the
single authorities.

## Closure results

- The read-only notification projection now carries `source`, `created_at`,
  and a derived severity-based `important` flag. It does not expose canonical
  notification metadata.
- ChatScreen now keeps an explicit active run through queued, running,
  resuming, and paused states. It keeps Cancel available for long runs, shows
  paused approval state, and clears only on succeeded, failed, or cancelled.
  Watcher/reconciliation failures are retried and are never shown as a false
  backend terminal failure.
- ApprovalCard now awaits the existing decision callback and always releases
  its in-flight lock, including after a rejected POST, while retaining
  duplicate-submit protection.

## Verification

All results below are fresh local results for this residual closure:

| Gate | Result |
| --- | --- |
| Focused residual frontend | 4 passed, 0 failed |
| Focused residual Python | 1 passed, 0 failed |
| Full frontend suite | 25 passed, 0 failed |
| Phase 14 Python regression | 17 passed, 0 failed |
| Phase 13 regression | 107 passed, 0 failed |
| Full Python repository suite | 342 passed, 25 subtests passed, 0 failed |
| Frontend production build | PASS |
| Deterministic embedded asset build | PASS |
| `npm audit --json` | PASS — 0 vulnerabilities |
| `python -m compileall src tests` | PASS |
| `git diff --check` | PASS |
| Remote-asset scan | PASS — no `http://` or `https://` references |

## Review constraints

- No duplicate EventBus, scheduler, VoiceCore, AgentRuntime, model gateway, or
  notification authority was introduced.
- No broad SQL cleanup, retention expansion, local-model change, cloud/MCP
  integration, Phase 15 work, or physical voice work was introduced.
- `PHYSICAL_TEXT_UI` remains `NOT_RUN`; physical voice remains `DEFERRED`.
- GitHub CI status is not claimed; verification is local.

## Handoff

Commit message: `fix: close phase 14 residual ui contracts`

The final commit SHA, remote equality, and clean-worktree state are recorded in
the execution handoff after the single commit and push.
