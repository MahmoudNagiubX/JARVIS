# ADR 0008: Experience is an event-derived read model

Status: Accepted

## Decision

HUD and client state are projections of normalized events plus authenticated
queries to existing authorities. They are disposable, owner-scoped, redacted,
and cannot mutate business state or approve actions.

## Consequences

The stdlib edge can serve a useful local HUD without a frontend dependency.
Rebuilds and future WebSocket transports preserve authority ownership. The
current event stream is an SSE snapshot adapter; durable distributed delivery
is later work.
