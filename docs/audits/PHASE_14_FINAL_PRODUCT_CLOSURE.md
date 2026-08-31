# JARVIS Phase 14 final product closure

## Scope

This closure keeps the accepted React + TypeScript + Vite Command Center over the
existing local runtime. It does not add a second AgentRuntime, model authority,
tool registry, scheduler, event bus, memory/mission authority, or VoiceCore.
The loopback-only HTTP boundary, one-use desktop bootstrap, HttpOnly session
cookie, CSRF protection, and owner/device binding remain in force.

## Closure changes

- Added safe desktop-session renewal with cookie/CSRF rotation, old-session
  revocation, principal revalidation, bounded TTL, and frontend renewal before
  expiry. Failed renewal presents `Session expired. Reopen JARVIS.`.
- Added the thin asynchronous `/v1/messages/start` transport over the existing
  `AgentRuntime`, with durable run status, cancellation, and client-message
  idempotency preserved.
- Added backend-truth `run_id` to pending approval projection/detail and made
  approval actions single-submit with same-run resume protection.
- Added run-scoped, redacted `/v1/runs/{run_id}/activity` for chat activity.
- Fixed research evidence envelope parsing, notification filters, and settings
  dead/self-link controls.

## Verification

All results below are from fresh local commands for this closure:

| Gate | Result |
| --- | --- |
| Focused closure frontend | 10 passed, 0 failed |
| Focused closure Python | 8 passed, 0 failed |
| Full frontend suite | 21 passed, 0 failed |
| Phase 14 Python regression | 16 passed, 0 failed |
| Phase 13 regression | 107 passed, 0 failed |
| Full Python repository suite | 340 passed, 1 expected platform skip, 25 subtests passed, 0 failed |
| Frontend production build | PASS |
| Deterministic embedded asset build | PASS |
| `npm audit --json` | 0 vulnerabilities |
| `python -m compileall src tests` | PASS |
| `git diff --check` | PASS |
| Remote-asset scan | PASS |

The Phase 13 skip is the existing Windows active-window test skip when no
active Windows window is available. No physical Qwen browser smoke was run;
`PHYSICAL_TEXT_UI` is therefore `NOT_RUN`. Physical voice remains deferred.

## Review constraints

- No duplicate scheduler, EventBus, VoiceCore, AgentRuntime, or model gateway
  was introduced.
- No broad SQL cleanup or retention expansion was introduced in this closure.
- UI assets contain no remote `http://` or `https://` dependencies.
- GitHub CI status is not claimed; these are local verification results.

## Handoff

Base: `ffc59669520b2a207eea2986f10ee1e0dd47d2f9`

Expected closure commit: `fix: close phase 14 command center product gaps`
