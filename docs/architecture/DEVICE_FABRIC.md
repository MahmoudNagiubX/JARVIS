# Device fabric

`DeviceFabricService` is the owner-scoped registry for primary PCs, servers,
room satellites, mobile devices, home gateways, microcontrollers, speakers,
and microphones. A record contains role, transport, room, trust, metadata,
capabilities, status, and last heartbeat. Registered devices are durable in
the product repository and are surfaced alongside identity-enrolled devices.

Registration normalizes a live device to `online`. Heartbeats refresh the
record, stale devices transition to `offline`, and revocation is terminal for
capability listing. Device registration, online/offline transitions, and
revocation emit normalized device events; registration and revocation are
audited.

The fabric is a control-plane registry, not a network scanner. Transports and
hardware discovery belong to adapters. No device is reported physically
healthy merely because a record exists.
