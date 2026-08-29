# JARVIS World State

World State is a current, evidence-backed projection. It is not durable
personal memory and is never silently promoted into memory.

Observations carry source, reference, timestamp, freshness, confidence,
authority, device, scope, and optional expiry. The current implementation
accepts runtime events, explicit user/runtime facts, Git workspace metadata,
build/test evidence, satellite-shaped events, and future Venom observations.

Fusion is deterministic: source authority is considered first, followed by
confidence and observation time. Competing values remain inspectable as
conflicts. Expired facts are excluded from normal snapshots and can be marked
expired by maintenance. Workspace inspection runs bounded read-only Git
commands and does not capture continuous screenshots or surveillance data.

The loopback API exposes `/v1/world-state` and
`/v1/world-state/conflicts`. Events include observation, update, conflict, and
expiration notifications.

