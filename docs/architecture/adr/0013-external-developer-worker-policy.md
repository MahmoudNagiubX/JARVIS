# ADR 0013: External developer workers are optional bounded adapters

Status: Accepted

## Decision

Detect installed Codex, Gemini, and Antigravity CLIs without installing or
launching them. Any future executor must be explicitly injected, scoped to a
workspace, time-bounded, and routed through existing worker/audit/event policy.
OpenClaw remains an optional adapter seam.

## Consequences

The runtime can report unavailable capabilities honestly and remains offline
first. External CLI behavior, credentials, model selection, and network access
cannot silently become JARVIS authority.
