# Room Presence & Spatial Boundaries

## Room Hierarchy & Entity Binding
`RoomService` organizes devices, voice endpoints, and home entities into logical spatial boundaries:
- **Default Rooms**: `office`, `living_room`, `bedroom`, `kitchen`, `lab`.
- **Bindings**:
  - `bind_device(owner_id, room_id, device_id)`
  - `bind_voice_endpoint(owner_id, room_id, endpoint_id)`
  - `bind_home_entity(owner_id, room_id, entity_id)`

## Presence Priority Fusion
`PresenceService` fuses observations across the canonical `PresenceSource` tiers defined in `src/jarvis/contracts/presence.py`:

| Source | Description |
|---|---|
| `ACTIVE_DESKTOP` | Active focused interaction or input on primary desktop PC. |
| `VOICE_ENDPOINT` | Direct microphone input or active turn on a bound room voice endpoint. |
| `EXPLICIT_ROOM` | Explicit user-selected room context. |
| `ORIGINATING_DEVICE` | Interaction originating directly from a bound room device. |
| `CLIENT_SESSION` | Active client session mapped to room location. |
| `DEVICE_HEARTBEAT` | Live heartbeat telemetry from room-located devices. |
| `HOME_SENSOR` | PIR motion sensor or environmental state update. |

When a device is revoked, `clear_device(owner_id, device_id)` immediately removes all associated presence observations from the fusion table.
