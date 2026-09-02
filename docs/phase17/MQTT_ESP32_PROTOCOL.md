# Restricted MQTT & ESP32 Protocol

## Topic Architecture & Prefix Gating
The `RestrictedMQTTTransport` enforces strict topic hierarchy and payload size constraints:

- **Allowed Topic Prefixes**: `jarvis/<owner_id>/` and `home/`.
- **Max Topic Length**: 250 characters.
- **Max Payload Size**: 10 KB.
- **Retain Policy**: Retained messages on command topics (`jarvis/.../command/...`) are strictly rejected to prevent stale command execution upon device reconnection.

## Message Schemas
1. **ESP32 Inbound State (`jarvis/<owner>/<device>/state/<target>`)**:
   ```json
   {
     "temperature": 24.5,
     "humidity": 55.0,
     "online": true
   }
   ```
2. **ESP32 Outbound Command (`jarvis/<owner>/<device>/command/<target>`)**:
   ```json
   {
     "command_id": "cmd-8f3a12",
     "action": "set_level",
     "parameters": {
       "level": 75
     },
     "expires_at": "2026-09-02T10:50:00Z",
     "dry_run": false
   }
   ```
3. **TTL & Expiry Validation**:
   Inbound commands parsed via `parse_esp32_command()` validate `expires_at`. If `expires_at <= datetime.now(UTC)`, the command is immediately discarded as stale.
