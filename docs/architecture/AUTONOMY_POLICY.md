# JARVIS autonomy policy

JARVIS uses explicit levels:

- L0 `OBSERVE`: read or report only.
- L1 `SAFE_AUTO`: bounded local reversible work may run automatically.
- L2 `AUTO_NOTIFY`: safe work may run with notification evidence.
- L3 `APPROVAL_REQUIRED`: execution pauses for an owner decision.
- L4 `BLOCKED`: destructive, security-sensitive, or otherwise forbidden.

The current default policy allows bounded local test execution and read-only
workspace inspection, observes computer state, requires approval for computer
input and external messages, and blocks deletion/account operations. Unknown
actions fail closed. Automatic proactive execution is permitted only when the
finding and policy both allow it.

All executed actions use the existing permission, tool, audit, and event
boundaries. The policy does not grant shell access, remote deployment, public
network binding, or permission to bypass approval.

Phase 07 missions, skills, and automations inherit these levels. Mission
budgets are hard limits; consequential mission and skill steps pause for
approval. Automation can invoke only registered skills and existing services.
Learned skills start as drafts, and self-evaluation can report regressions but
cannot apply source changes or alter policy.
