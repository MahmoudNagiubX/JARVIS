# ADR 0022: Model access is an existing-runtime tunnel

- Status: accepted
- Date: 2026-08-30

## Decision

Phase 09 may inspect or call an already-running model provider through the
existing `ModelGateway` and loopback endpoint. It must not pull, download,
copy, start, or duplicate model assets.

## Consequence

The workstation can honestly report unavailable model runtime without changing
the external Ollama directory.
