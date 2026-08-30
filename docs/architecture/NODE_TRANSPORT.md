# Node transport

The Phase 09 transport is a standard-library authenticated HTTP long-poll
adapter. The core binds to loopback by default; a public bind is rejected by
the server constructor. Credentials are carried in an `Authorization: Bearer`
header and node/identity identifiers are header-bound for GET requests.

| Method | Route | Purpose |
|---|---|---|
| POST | `/v1/satellites/connect` | owner/device-bound hello and session creation |
| POST | `/v1/satellites/heartbeat` | freshness update |
| GET | `/v1/satellites/commands` | bounded long-poll for a typed command |
| POST | `/v1/satellites/results` | typed command observation |
| POST | `/v1/satellites/disconnect` | session closure |

Every command has an id, typed action/capability, parameters, and dry-run
flag. The current bounds are 64 queued commands per device, 64 KiB command
parameters, 256 KiB result output, a 30 second command TTL, and a bounded
completed-command replay cache. Replaying the same command id and fingerprint
is idempotent; reusing an id with different content is denied.

The registry validates protocol version, Windows platform, owner/device
identity, and declared capabilities. The transport additionally binds every
poll, heartbeat, result, and disconnect to the authenticated owner, device,
and session. Query-string credentials are rejected. No route accepts shell,
PowerShell, Python evaluation, or arbitrary executable text.

The health scheduler calls the transport's bounded stale-session expiration.
Expired sessions are disconnected from the registry, pending commands fail as
`satellite_stale`, and the same transition is projected to DeviceFabric and
World State. Heartbeats update freshness but lifecycle events are coalesced;
reconnect keeps only a bounded inactive history. Canonical
`device.revoked` events invalidate the transport and deny future connects.

Public `/health` returns only aggregate transport fields (`transport`,
`available`, `online_sessions`, and `degraded`). Authenticated experience
topology may use the detailed view with device/session state.

Long-poll is an adapter choice, not a new authority. A future authorized
transport may replace it while preserving the same typed contracts and
security ordering.
