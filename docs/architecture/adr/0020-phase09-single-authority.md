# ADR 0020: Preserve single runtime authorities

- Status: accepted
- Date: 2026-08-30

## Decision

`WindowsSatelliteRegistry`, `DeviceFabric`, `VoiceCore`, `ModelGateway`, and
the existing authority plane remain canonical. Phase 09 adapters may report,
queue, or translate, but may not create parallel business authorities.

## Consequence

Topology and health are projections of canonical state; a node cannot approve,
authorize, invent voice identity, or bypass typed computer controls.
