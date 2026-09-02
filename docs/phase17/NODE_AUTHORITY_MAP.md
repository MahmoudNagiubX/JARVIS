# Node Authority Map — Single Authority Boundaries

## Foundational Principle
JARVIS enforces **one logical authority** across all devices, rooms, and satellite nodes. No duplicate, conflicting, or split-brain runtimes are permitted.

```
+-----------------------------------------------------------------------------------+
|                           NIGHTFURY (Authoritative Core)                          |
|                                                                                   |
|  +-------------------+  +--------------------+  +-------------------------------+ |
|  | Single SQLite DB  |  | Single VoiceCore   |  | Single AgentRuntime & LLM     | |
|  | (Single Writer)   |  | (Arbitration & TTS)|  | (RTX 4080 Inference)          | |
|  +---------+---------+  +---------+----------+  +---------------+---------------+ |
|            |                      |                             |                 |
|  +---------v----------------------v-----------------------------v---------------+ |
|  |                 Single EventBus & PolicyPermissionEngine                     | |
|  +--------------------------------+---------------------------------------------+ |
|                                   |                                               |
|  +--------------------+  +--------v-----------+  +------------------------------+ |
|  | DeviceFabricService|  | RoomVoiceFabric    |  | RoomService & PresenceService| |
|  +---------+----------+  +--------+-----------+  +--------------+---------------+ |
+------------|----------------------|-----------------------------|-----------------+
             |                      |                             |
             v                      v                             v
+-----------------------+  +--------------------+  +--------------------------------+
|  Room Satellites      |  |  ESP32 / Micro     |  |  VENOM (Linux Infrastructure)  |
|  (Windows/Mac/Linux)  |  |  (Sensors & Relays)|  |  - Mosquitto MQTT Broker       |
|  - Microphones        |  |  - DHT22 / Relays  |  |  - Encrypted Backup Receiver   |
|  - Speakers           |  |  - Restricted MQTT |  |  - System Health Watchdog      |
+-----------------------+  +--------------------+  +--------------------------------+
```

## Explicit Anti-Patterns Forbidden by Phase 17
1. **Forbidden Classes**: `DeviceFabricV2`, `RoomBrain`, `HomeAgent`, `HomeAssistantBrain`, `SecondSatelliteRegistry`, `RoomVoiceCore`, `RemoteAgentRuntime`, `VenomBrain`.
2. **No Second Database**: Venom does NOT write to a separate SQLite database or execute independent migrations.
3. **No Second Voice Engine**: Audio captured in any room is streamed as an ephemeral utterance envelope to the central `VoiceCore` and destroyed immediately after synthesis.
4. **No Unauthenticated LAN RPC**: All node and satellite communications require cryptographic tokens, session validation, and strict capability gating.
