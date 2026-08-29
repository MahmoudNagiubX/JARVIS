# Experience layer

The experience layer is a read-only projection boundary under
`jarvis.experience`. `ExperienceProjection` consumes the normalized event bus
and builds owner-scoped `HudState`, system status, specialist summaries, and a
bounded event timeline. It is disposable: identity, devices, permissions,
approvals, audit, memory, world state, goals, agent runtime, model gateway,
capabilities, and tools remain authoritative in their existing services.

The gateway exposes `GET /v1/experience/state`, `/system`, `/timeline`, an
authenticated `/v1/experience/events` Server-Sent Events snapshot stream, and
a bounded `/v1/experience/events/ws` WebSocket fan-out. The
stdlib transport has no WebSocket dependency; a future WebSocket adapter must
preserve the same event envelope and authentication binding.

Events are redacted before projection. Credentials, tokens, secrets,
authorization values, raw audio, and raw frames are never presented in the
HUD timeline. UI actions must call an application use case and cannot mutate a
projection or decide an approval.

The projection maps real lifecycle events to visible states including
`STARTING`, `IDLE`, `LISTENING`, `PROCESSING`, `TOOL_EXECUTING`,
`WORKER_RUNNING`, `APPROVAL_REQUIRED`, `RESEARCHING`, `ENGINEERING_TASK`,
`SPEAKING`, `PROACTIVE_ALERT`, `DEGRADED`, and `ERROR`. No state is simulated
when the backend has not emitted evidence for it.
