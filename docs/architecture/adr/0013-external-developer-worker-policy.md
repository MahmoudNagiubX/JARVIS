# ADR 0013: External developer workers are optional bounded adapters

Status: Accepted

## Decision

Report only the safe local Codex candidate without installing or launching it.
Google-account-backed CLI candidates are excluded from discovery. Any future
executor must be explicitly injected, scoped to a workspace, time-bounded, and
routed through existing worker/audit/event policy. OpenClaw remains an optional
adapter seam.

## Consequences

The runtime can report unavailable capabilities honestly and remains offline
first. External CLI behavior, credentials, model selection, and network access
cannot silently become JARVIS authority.
