# Phase 17 Gap Analysis Matrix

## Audit of Existing Layers & Phase 17 Resolutions

| System Area | Baseline State (Pre-Phase 17) | Phase 17 Architecture Extension | Status |
|---|---|---|---|
| **Device Contracts** | Static `DeviceRecord` with basic roles (`primary_pc`, `satellite`). | Added `DeviceStatus.ENROLLING`, `DEGRADED`. Added `DeviceEnrollmentTicket`, `DeviceEnrollmentRequest`, `DeviceEnrollmentResult`. | **RESOLVED** |
| **Device Fabric** | In-memory/basic registry without dynamic ticket redemption or degradation. | Extended `DeviceFabricService` with token generation, cryptographic ticket redemption, salted PBKDF2-HMAC-SHA256 hashing, degraded heartbeat detection, and audit logging. | **RESOLVED** |
| **Venom Node** | Simple placeholder node with boolean health. | Implemented `VenomNode` and bounded `VenomDaemon` with storage monitoring (GB/usage %), service watchdog (`mosquitto`, `jarvis-venom`), backup header validation (`SQLite format 3\000` + SHA-256), and deployment state gating. | **RESOLVED** |
| **Venom Deployment Scripts** | None. | Added idempotent Python & Bash provisioning suite under `scripts/venom/` (`preflight`, `setup`, `health_check`, `firewall_setup`, `rollback`). | **RESOLVED** |
| **Home Integration** | Simulated entity store with basic actions. | Extended `HomeActionService` with `HomeEntityMapping`, privacy-bounded `list_entities`, safe action allowlist (`turn_on`, `turn_off`, `set_brightness`, `set_color`, `trigger_scene`, `set_temperature`, `publish_mqtt`), blocked dangerous actions (`lock`, `unlock`, `alarm`, `raw_shell`), and temperature bounds (15-30°C). | **RESOLVED** |
| **MQTT & ESP32** | None. | Implemented `RestrictedMQTTTransport` with topic prefix validation (`jarvis/`, `home/`), ESP32 telemetry/state parsing, command envelope validation, and TTL expiration filtering. | **RESOLVED** |
| **Presence Hierarchy** | 4 baseline presence sources. | Canonical 7-tier `PresenceSource` fusion: `ACTIVE_DESKTOP`, `VOICE_ENDPOINT`, `EXPLICIT_ROOM`, `ORIGINATING_DEVICE`, `CLIENT_SESSION`, `DEVICE_HEARTBEAT`, `HOME_SENSOR`. Added `clear_device(owner_id, device_id)` on revocation. | **RESOLVED** |
| **Voice Routing** | Single desktop voice pipeline. | Extended `VoiceRoutingService` with multi-room endpoint registration, durable personalization persistence, state-preserving rehydration, room affinity selection, and `revoke_device_endpoints`. | **RESOLVED** |
| **Multi-Room Voice** | No multi-room coordinator. | Implemented `RoomVoiceFabric` coordinating ephemeral `RoomUtteranceEnvelope` and `RoomPlaybackEnvelope` over the single `VoiceCore` with barge-in cancellation and zero durable audio retention. | **RESOLVED** |
| **Prompt Injection Defense** | Memory and tool call isolation only. | Extended `ContextAssembler` and `DeviceFabricService` with recursive control-character sanitization, text truncation, and fact quarantine. | **RESOLVED** |
| **Command Center UI** | Simple device list. | Extended `DevicesScreen` in `Screens.tsx` with Venom Node health/storage/services card, Room fabric presence card, and verified Home controller state. | **RESOLVED** |
| **HTTP API** | Monolithic endpoints without device enrollment or Venom health. | Added `/devices/enroll/ticket`, `/devices/enroll`, `/devices/{id}/revoke`, `/nodes/venom/health`, `/nodes/venom/plan`, `/rooms`, `/rooms/{id}`, `/fabric/diagnostics`, `/voice/room/utterance`, `/voice/room/barge_in`. | **RESOLVED** |
