# Device Fabric — Multi-Device Architecture

## Canonical Device Fabric Design
`DeviceFabricService` provides the authoritative registry, capability gating, and lifecycle management for all connected nodes, satellites, and peripherals on the core authority (NIGHTFURY).

```
+-------------------------------------------------------------------------------+
| DeviceFabricService (NIGHTFURY)                                               |
| - Registers verified devices: DeviceRecord(device_id, owner_id, capabilities)  |
| - Manages status: REGISTERED, ENROLLING, ONLINE, DEGRADED, OFFLINE, REVOKED   |
| - Heartbeat monitor: tracks last_seen_at and transitions stale devices        |
| - Capability matcher: filters devices supporting requested actions            |
| - Diagnostics provider: returns live counts (online, degraded, offline, revoked|
+---------------------------------------+---------------------------------------+
                                        |
       +--------------------------------+-------------------------------+
       |                                |                               |
       v                                v                               v
+--------------+                +---------------+               +---------------+
| Primary PC   |                | Satellite Mic |                | ESP32 Sensor  |
| (NIGHTFURY)  |                | (Living Room) |                | (DHT22 / MQTT)|
+--------------+                +---------------+               +---------------+
```

## Device Status Lifecycle & Semantics
- `REGISTERED`: Initial static record in repository prior to live authentication.
- `ENROLLING`: Ephemeral state while a one-time enrollment ticket is outstanding.
- `ONLINE`: Device is active, authenticated via cryptographic credential, and heartbeating within `heartbeat_interval_seconds * 3`.
- `DEGRADED`: Explicitly marked degraded by health monitors or experiencing partial transport degradation.
- `OFFLINE`: Heartbeat timed out beyond the stale threshold (`mark_stale_offline`). Kept in durable registry but excluded from active capability routing.
- `REVOKED`: Permanently disabled (`revoke`). Credentials invalidated in database, presence purged from `PresenceService`, voice endpoints unregistered, and future requests rejected fail-closed.
