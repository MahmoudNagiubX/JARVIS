# Current Distributed Architecture — Phase 17

## 1. Selected Topology: Option A (Nightfury Authoritative Core)
JARVIS Phase 17 implements **Option A**, enforcing exactly one authoritative core host with lightweight, specialized infrastructure nodes and satellites.

```
+-----------------------------------------------------------------------------------+
|                           NIGHTFURY (Authoritative Core)                          |
|                                                                                   |
|  +-------------------+  +--------------------+  +-------------------------------+ |
|  | Single SQLite DB  |  | Single VoiceCore   |  | Single AgentRuntime & LLM     | |
|  | (Single Writer)   |  | (Arbitration & TTS)|  | (RTX 4080 GPU Inference)      | |
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

## 2. Actual Node Roles & Boundaries
1. **NIGHTFURY (Windows Desktop — Core Authority)**:
   - **Database Authority**: Single-writer SQLite database with WAL mode and durable transactions.
   - **Voice Authority**: Single active `VoiceCore` owning session state, barge-in cancellation, and speech synthesis.
   - **Agent Authority**: Single active `AgentRuntime` managing reasoning turns, tool dispatch, and goal/mission execution.
   - **Inference Host**: Local NVIDIA RTX 4080 GPU running `Qwen-2.5-Coder-7B-Instruct` on loopback endpoint `127.0.0.1:11434`.
   - **Command Center Host**: Loopback-bound HTTP/WebSocket server (`127.0.0.1:8787`).

2. **VENOM (Linux x86_64 — Infrastructure Worker)**:
   - **Node Details**: `venom-server`, Ubuntu 24.04.4 LTS, Linux 6.8 kernel, interface `enp7s0`.
   - **MQTT Service**: Dedicated Mosquitto MQTT broker on `localhost:1883` restricted to LAN traffic.
   - **Backup Receiver**: Receives signed, encrypted SQLite database backup archives with atomic SHA-256 header verification.
   - **System Watchdog**: Reports storage utilization (GB/percentage) and service liveness via JSON health probe.
   - **Strict Boundaries**: Venom never runs an independent database writer, split-brain agent runtime, or uncoordinated LLM.

3. **Room Satellites & Micro-Controllers (ESP32)**:
   - **Satellites**: Capture audio utterances into ephemeral `RoomUtteranceEnvelope` records and play back synthesized `RoomPlaybackEnvelope` responses.
   - **ESP32 Devices**: Publish sensor telemetry to `jarvis/<owner>/<device>/state/<target>` and receive TTL-bounded commands on `jarvis/<owner>/<device>/command/<target>`.
