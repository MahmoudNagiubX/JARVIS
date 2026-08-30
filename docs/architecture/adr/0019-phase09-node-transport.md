# ADR 0019: Use a bounded typed node transport

- Status: accepted
- Date: 2026-08-30

## Decision

Use the standard-library authenticated HTTP long-poll adapter around the
existing `WindowsSatelliteRegistry`. Keep commands typed, owner/device/session
bound, bounded by queue/TTL/payload limits, and replay-idempotent.

## Consequence

The transport can later be replaced without moving authority into a node or
adding a second EventBus, scheduler, approval path, or tool registry.
