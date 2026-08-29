# ADR 0006: Govern local models by identity and allowlist

- Status: accepted
- Date: 2026-08-29

## Decision

Local models are selected only through a provider-neutral gateway that records
role, model id, digest, capabilities, context limits, health, and local-only
status. Existing isolated stores are preserved. No download-on-start, public
binding, or model duplication is allowed by the foundation.

## Consequences

Model integration needs explicit inventory and license checks. Phase 01 does
not load or manipulate any model artifact.
