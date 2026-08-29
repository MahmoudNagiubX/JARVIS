# Windows satellite acceptance

Enroll a real Windows satellite with an owner-bound credential, least
capabilities, and `tool.request`. Verify hello/session identity, heartbeat,
safe observation, allowlisted action, rejection of unsupported actions,
revocation, reconnect, timeout, and audit/event records. Keep transport local
or explicitly authorized; do not enable arbitrary shell execution.

Phase 06 automated tests use the typed in-process registry. No external
satellite endpoint was available during the workstation audit, so physical
acceptance is deferred.
