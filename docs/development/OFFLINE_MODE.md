# Offline mode

`OfflineModeService` tracks `internet.online`, `internet.last_seen`, and the
source of the last state. A probe is injectable for tests; the core has no
cloud dependency and no repeated cloud-only retry loop.

When offline, local memory, World State, goals, deterministic proactive rules,
local tools, voice/computer controller boundaries, and a configured local model
path remain available. Capabilities named `cloud.*`, `paid.*`, or `remote.*`
are reported unavailable. Local model availability is still determined by the
model gateway and is not falsely claimed by the offline service.

The default runtime is intentionally unverified until a probe or explicit state
update is supplied. No raw audio, continuous screen capture, camera stream, or
cloud memory export is introduced by this mode.

