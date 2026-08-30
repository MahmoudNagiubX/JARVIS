# Windows satellite acceptance

Enroll a real Windows satellite with an owner-bound credential, least
capabilities, and `tool.request`. Verify hello/session identity, heartbeat,
safe observation, allowlisted action, rejection of unsupported actions,
revocation, reconnect, timeout, and audit/event records. Keep transport local
or explicitly authorized; do not enable arbitrary shell execution.

Automated Phase 09 tests cover the authenticated bounded HTTP transport,
typed agent, replay, limits, reconnect, revocation, and offline recovery.
No external satellite endpoint was available during the workstation audit, so
physical acceptance remains deferred; these tests do not claim a real second
machine.
