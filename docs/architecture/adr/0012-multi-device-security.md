# ADR 0012: Multi-device clients remain authenticated projections

Status: Accepted

## Decision

Each logical client session carries an owner, identity, optional enrolled
device, capability snapshot, allowlisted topics, UI profile, and last-seen
state. Every requested owner is checked against the existing principal.

## Consequences

Reconnection and multiple clients do not create another authority. Revocation,
permissions, approvals, audit, and event redaction remain core concerns. No
secrets are placed in client state or event payloads.
