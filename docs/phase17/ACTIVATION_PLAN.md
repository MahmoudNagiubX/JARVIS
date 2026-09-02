# Activation & Rollback Plan — Phase 17

## Safe Activation Sequence
1. **Host Verification (Authoritative Core)**:
   - Verify NIGHTFURY core health via `GET /health`.
   - Verify SQLite database integrity (`PRAGMA integrity_check`).
   - Confirm local GPU model availability (`Qwen-2.5-Coder-7B-Instruct`).
2. **Device Fabric & Room Initialization**:
   - `RoomService.initialize_defaults()` bootstraps standard home rooms (`office`, `living_room`, `bedroom`, `kitchen`, `lab`).
   - Device Fabric registers local primary desktop and prepares enrollment endpoint.
3. **Venom Node Inspection (Physical Gate)**:
   - Inspect environment variable `JARVIS_VENOM_HOST`.
   - If not set, Venom status is `NOT_CONFIGURED` and physical deployment status is `BLOCKED_WAITING_FOR_CONNECTION_DETAILS`.
   - When configured, run `scripts/venom/preflight.py` and `scripts/venom/health_check.py`.
4. **MQTT & Home Transport Connection**:
   - `RestrictedMQTTTransport` connects to configured broker with strict topic prefixes.
   - Initial ESP32 device manifests and state observations are registered.
5. **Multi-Room Voice Fabric Arming**:
   - `RoomVoiceFabric` verifies connectivity to `VoiceCore` and registers active room endpoints.

## Automated Rollback Procedure
If any critical subsystem fails during deployment or activation:
1. **Service Rollback on Venom**:
   - Run `bash scripts/venom/rollback.sh`.
   - Stops and disables `jarvis-venom.service`.
   - Restores the previous configuration template from `/opt/jarvis-venom/backups/`.
   - Preserves all verified SQLite database backups in `/opt/jarvis-venom/backups/sqlite/`.
2. **Device Fabric Revocation**:
   - Call `POST /devices/{device_id}/revoke` on NIGHTFURY.
   - Immediately revokes all active bearer tokens, closes long-poll sessions, and removes the device from the presence fusion table.
3. **Voice Core Fail-Safe**:
   - In case of multi-room voice transport failure, `RoomVoiceFabric` falls back directly to the local primary desktop microphone/speaker on NIGHTFURY.
