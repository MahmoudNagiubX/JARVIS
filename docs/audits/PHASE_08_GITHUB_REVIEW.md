# Phase 08 GitHub Review Remediation

This remediation preserves the Phase 08 authority boundaries. It repairs the
owner-bound auto-send PATCH path, verifies scoped auto-send through the
existing communications authority, makes home context and routines explicitly
configured, coalesces passive presence, and adds bounded briefing selection.

The implementation remains local-first and does not simulate unavailable
physical voice, Home Assistant, or external communication adapters. Notification
records remain in-process; restart durability for queued delivery is documented
as follow-up technical debt.
