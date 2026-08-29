# ADR 0009: Specialist engineering work uses injected adapters

Status: Accepted

## Decision

Jupyter and KiCad are provider contracts, not architectural spines. Sessions
are scoped to owner, device, workspace paths, allowlisted operations, timeout,
risk, and approval policy. Engineering workers use the existing
`LocalWorkerRuntime`.

## Consequences

Offline tests can use a deterministic provider. Live notebooks, KiCad IPC, and
desktop integrations remain deployment adapters and cannot add unrestricted
shell execution or a second agent runtime.
