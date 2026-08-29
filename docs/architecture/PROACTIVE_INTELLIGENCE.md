# JARVIS proactive intelligence

Proactive findings are deterministic, evidence-backed records. Initial rules
cover failed builds, repeated test failures, approaching deadlines, blocked
goals, stopped development servers, disconnected devices, stalled tasks,
completed operations, aging approvals, and critical disk space.

Each finding stores type, severity, evidence, source events, detection time,
recommended action, automatic-action eligibility, cooldown, status, and
acknowledgement metadata. Fingerprints and cooldown windows prevent repeated
spam. Acknowledgement and action completion are persisted and emit normalized
events.

Safe automatic actions still pass through the common PermissionEngine,
ToolExecutionService, audit service, and EventBus. Unknown or consequential
actions do not auto-run. The API exposes `/v1/proactive/findings` and the
acknowledgement action.

