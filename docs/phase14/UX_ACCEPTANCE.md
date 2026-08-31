# Phase 14 UX acceptance

## Automated acceptance

The focused product test covers:

- local static shell and asset delivery;
- strict static security headers and no remote/localStorage surfaces;
- one-use desktop bootstrap and credential redaction;
- HttpOnly session establishment and owner-scoped state;
- CSRF and Origin protection for cookie mutations;
- same-runtime text conversation and canonical history;
- wrong-owner and wrong-conversation rejection;
- normal-launch targeting of `/app`;
- deterministic frontend build.

The final exact counts are recorded in `docs/audits/MEGA_PHASE_14_REVIEW.md`
after the repository-wide verification pass.

Current focused evidence before the final repository gate is 11 frontend tests
and 8 Phase 14 Python regression tests, all passing. The Phase 13 regression is
107 passed; final full-suite counts are recorded after the last clean run.

## Human review checklist

1. Start JARVIS from the existing Start Menu/desktop lifecycle.
2. Confirm the Command Center opens directly, without npm, a terminal, or a
   development server.
3. Send a text question and verify the answer comes from the local runtime.
4. Inspect Home, Chat, Memory, Missions, Devices, and Settings.
5. Verify pending approvals remain explicit and owner-controlled.
6. Verify offline/degraded panels identify what remains usable.
7. Close/reopen the browser surface and confirm state rebuilds from the API.

Physical voice acceptance is intentionally not a Phase 14 gate. The Phase 13
backlog remains deferred for Phase 19.
