# Distributed runtime

Phase 09 adds a bounded distributed shape around the existing JARVIS
authorities. The core remains the owner of identity, permission, approval,
audit, model routing, VoiceCore, DeviceFabric, and world-state freshness.
Windows satellites are capability-limited execution nodes; they do not become
independent JARVIS authorities.

```text
owner-bound credential
        |
core HTTP long-poll transport
        |
typed SatelliteCommand / CommandObservation
        |
existing WindowsSatelliteRegistry + DeviceFabric
        |
bounded Windows native controller
```

The transport is an adapter around the existing registry. It owns only
session, queue, TTL, payload, replay, and heartbeat mechanics. It does not
create a second scheduler, EventBus, approval engine, VoiceCore, or tool
registry. Product computer actions use this single authority flow:

```text
authenticated actor + request device
        |
ComputerActionService: permission -> approval -> audit
        |
owner-scoped target resolution
        |
ComputerExecutionRouter
        +--> local WindowsNativeComputerController
        +--> remote WindowsComputerController -> typed satellite transport
```

The requesting device and execution target are separate fields. An explicit
remote target must belong to the same owner, remain non-revoked, declare the
required capability, and have a fresh reachable session. It never silently
falls back to the local controller.

Runtime profiles are `test`, `development`, `live-workstation`, and
`live-distributed`. `runtime_role` is `core` or `satellite`; node identity and
core URL are explicit configuration. The default endpoints are HTTP loopback
and the default voice adapters are NoOp. A profile reports topology in health
and the experience projection without exposing credentials.

The core marks a satellite online only after an accepted hello and refreshes
its DeviceFabric and World State on a real transition. Identical heartbeat
refreshes advance `last_seen` without emitting duplicate lifecycle events or
World-State observations. The existing scheduler expires sessions after the
bounded stale threshold and projects transport, registry, DeviceFabric, and
World State offline together. Canonical identity revocation propagates through
the existing EventBus and fails pending work. Disconnect, revocation,
reconnect, queue overflow, expired commands, and rejected results are
observable failures; inactive reconnect history is bounded.

Phase 10 extends the same typed transport with protocol v2 and the separate
`perception.screen` capability. Perception routes by topology, including when
request and target device IDs are equal, and an unavailable explicit target
returns `perception_target_offline` without falling back to another screen.
The result channel permits bounded structured metadata, dimensions, digests,
and locally derived semantic data only; raw bitmaps and base64 image payloads
are rejected.
