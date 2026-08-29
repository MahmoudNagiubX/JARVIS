# ADR 0003: Use one normalized event envelope

- Status: accepted
- Date: 2026-08-29

## Decision

All cross-boundary events use `jarvis.events.Event` with event id, event type,
UTC timestamp, category, correlation id, causation id, session id, actor id,
payload, severity, and state. Phase 01 dispatches through an in-process bus.

## Consequences

Donor-specific event classes can be adapted without becoming the system-wide
schema. Durable delivery and cross-process transport remain later adapter
decisions.
