# ADR 0005: Keep providers and transports out of the foundation core

- Status: accepted
- Date: 2026-08-29

## Decision

Phase 01 uses stdlib-only contracts and no-op/in-memory implementations. Model
SDKs, network transports, audio drivers, databases, browser automation, and
OS clients are optional adapters outside the core package.

## Consequences

The bootstrap is deterministic and offline. Real integrations must be added
with explicit dependency, security, licensing, and acceptance evidence in
later phases.
