# Phase 08 GitHub Review Remediation

This remediation preserves the Phase 08 authority boundaries. It repairs the
owner-bound auto-send PATCH path, verifies scoped auto-send through the
existing communications authority, makes home context and routines explicitly
configured, coalesces passive presence, and adds bounded briefing selection.

The implementation remains local-first and does not simulate unavailable
physical voice, Home Assistant, or external communication adapters. Notification
records remain in-process; restart durability for queued delivery is documented
as follow-up technical debt.

## Final Closure (2026-08-30)

The remaining Phase 08 closure work was validated before Phase 09 work began:

- Focused closure matrix: 4 passed, 0 failed.
- Phase 08 regression: 9/9 passed, 0 failed.
- Full repository suite: 77 passed, 0 failed.
- `python -m compileall src tests`: PASS.
- `git diff --check`: PASS.
- Notification queue delivery is idempotent and reevaluates after attention-mode changes.
- Follow-ups remain owner- and thread-scoped; VoiceCore remains a single runtime authority with device/owner context checks.
- Retention removes only aged operational attempts/runs/history and preserves active focus, current mode, open follow-ups, audit records, and device credentials.
- Owner timezone is applied to both Attention quiet-hours and scoped auto-send windows through the shared `in_time_window()` implementation. Windows validation uses the free `tzdata` development extra; invalid timezone identifiers fail closed.
- The proactive test runner now passes the repository `src` path to its bounded subprocess, preserving the existing no-runtime-dependency contract.
