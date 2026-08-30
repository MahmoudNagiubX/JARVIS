# Mega Phase 11 review

Phase 11 adds bounded, grounded Windows desktop interaction on top of the
existing Phase 10 perception and Phase 09 typed-device topology. The existing
`ComputerActionService`, `ToolExecutionService`, permission engine, approval
engine, audit service, EventBus, and satellite registry remain the authorities.

Implemented:

- minimize, maximize, and restore over short-lived, PID/class-revalidated
  `window_ref` values with a 256-reference in-memory cap;
- bounded media-key volume adjustment; mute/unmute remain truthful
  `audio_state_unavailable` where state cannot be queried;
- native Unicode clipboard read/write with 16,000-code-point limits, bounded
  retries, readback verification, and digest/length metadata;
- literal Unicode keyboard typing with a 2,000-code-point limit, UTF-16
  chunks of at most 64 code units, exact foreground checks, and sensitive-window
  protection;
- narrow computer tools in the existing ToolRegistry and typed satellite
  allowlist extensions without a protocol-version bump;
- ephemeral clipboard output and sensitive keyboard/clipboard-write argument
  retention, with bounded in-memory approval arguments and no restart fallback;
- sanitized same-host physical acceptance evidence.

Focused and regression evidence from the final validation run:

- Phase 11 focused matrix: 17 passed, 0 failed;
- Final remediation focused tests: 9 passed, 0 failed;
- Phase 11 final total: 26 passed, 0 failed;
- Phase 10 regression: 31 passed, 0 failed;
- Phase 09 regression: 39 passed, 0 failed;
- Phase 08 regression: 13 passed, 0 failed;
- full repository suite: 173 passed, 0 failed, 0 errors;
- `python -m compileall src tests`: PASS;
- `git diff --check`: PASS.

Physical acceptance on 2026-08-30 passed window minimize/restore verification,
clipboard marker write/read digest comparison with original clipboard restore,
and literal keyboard execution. Keyboard verification is intentionally
`false` because this boundary has no readback. Audio was not exercised so the
user volume was unchanged. A separate same-host satellite process also
completed a clipboard marker write and restoration through loopback HTTP
long-poll; this does not claim a second physical host.

## Independent GitHub Review Remediation

The final review remediation preserved all accepted Phase 11 desktop features
and closed the approval lifecycle gaps with bounded changes:

- delegated approvals now retain the canonical approval expiry, prune against
  `DurableApprovalEngine.get()`, release expired capacity, and reconcile bound
  tool calls and paused runs to `approval_expired`;
- `ComputerActionService` checks its live pending capacity before creating a
  durable approval, so overflow cannot evict a live payload or create an
  orphan approval;
- Agent-bound computer approvals are rejected by the standalone computer
  approval endpoint and must use the Agent resume path, while standalone
  direct computer approvals remain supported;
- Phase 11 HTTP approval decisions attribute `decided_by` to the authenticated
  principal, ignoring client-supplied attribution;
- a deterministic model-to-Agent-to-domain-approval-to-resume test proves one
  controller execution, two model responses, durable sentinel absence before
  and after execution, and replay safety;
- a real process-separated same-host satellite run completed the new clipboard
  action over `http-long-poll`, with sanitized evidence and no second-host
  claim.

Remediation evidence: 9 focused tests, 26 Phase 11 tests, 31 Phase 10 tests,
39 Phase 09 tests, 13 Phase 08 tests, and 173 full-suite tests, all with zero
failures. The final review confirmed one implementation each for the
ComputerActionService, ToolExecutionService, ApprovalEngine, PermissionEngine,
EventBus, scheduler, and VoiceCore path; no SQL/migration, shell, mouse, or
protected BMO evidence changes were made.

Explicitly deferred: coordinate mouse input, arbitrary virtual keys,
clipboard paste as an input mechanism, accessibility/UI automation, OCR,
local vision models, continuous capture, and reliable mute-state querying.
The final diff review confirmed one ComputerActionService, one
ToolExecutionService, one EventBus, one scheduler, one VoiceCore path, no
SQL/migration changes, and no shell or mouse-input implementation.
