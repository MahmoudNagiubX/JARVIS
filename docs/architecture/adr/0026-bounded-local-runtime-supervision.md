# ADR 0026: Bound local runtime supervision

- Status: accepted
- Date: 2026-08-30

## Decision

The local runtime is opt-in and configured with explicit executable/model
paths, loopback origin, bounded context, thread, GPU-layer, alias, and
readiness timeout values. The supervisor uses a fixed argument vector,
`shell=False`, no web UI, and a single owned process. It attaches only to a
compatible listener and reports an incompatible listener as a port conflict.
It never downloads, copies, imports, or deletes model weights.

## Consequences

Development/test bootstrap does not launch a heavy model. Shutdown terminates
only an owned process. Offline, readiness, and restart states remain visible
and deterministic to the gateway, health endpoint, HUD, and audit evidence.
