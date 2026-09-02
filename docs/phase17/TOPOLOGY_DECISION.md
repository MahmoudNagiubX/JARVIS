# Topology Decision — Option A (Nightfury Authoritative Core)

## Executive Summary
For JARVIS Mega Phase 17, **Option A** has been selected as the canonical network and execution topology:

- **NIGHTFURY (Primary Windows Desktop)**:
  - Authoritative Core Host.
  - Hosts the single authoritative SQLite database (`jarvis.db`) with single-writer WAL mode.
  - Hosts the single active `VoiceCore` instance and audio arbitration pipeline.
  - Hosts the single active `AgentRuntime`, `EventBus`, and identity/permission engine.
  - Executes local neural inference (Qwen-2.5-Coder-7B-Instruct on RTX 4080 GPU).
  - Hosts the loopback HTTP/WebSocket Command Center API (`127.0.0.1:8787`).

- **VENOM (Linux Infrastructure Node)**:
  - Lightweight Linux infrastructure worker (Ubuntu 24.04.4 LTS, x86_64, `venom-server`).
  - Runs the local Mosquitto MQTT broker (`localhost:1883`) with restricted access and topic prefix controls.
  - Receives encrypted/signed durable SQLite database backups with atomic SHA-256 header validation.
  - Runs local service watchdog and storage monitoring probes.
  - **Forbidden**: Venom does NOT host a secondary database writer, split brain runtime, duplicate VoiceCore, or divergent LLM agent.

## Evaluation Matrix
| Dimension | Option A (Selected: Authoritative Core on NIGHTFURY) | Option B (Dual Authority / Distributed Master) |
|---|---|---|
| Single Writer Safety | Guaranteed: 1 single SQLite writer on NIGHTFURY | High Risk: Split-brain, multi-master sync conflicts |
| Voice State Integrity | Guaranteed: 1 single VoiceCore with barge-in | Unsafe: Race conditions between simultaneous rooms |
| Privacy Boundary | Raw audio never persists; LAN isolated | Exposed across multiple distributed worker nodes |
| Operational Complexity | Low: Venom is a stateless/daemon worker | High: Distributed consensus, Raft/Paxos overhead |
| GPU Utilization | Maximum: RTX 4080 on NIGHTFURY handles all reasoning | Fragmented: Venom lacks local GPU for heavy LLMs |

## Routing Priority Order
Routing decisions across the multi-device fabric follow a strict, deterministic priority hierarchy:
1. **Explicit Target Request**: User specifies device target (e.g. `@desktop`). If the explicit target is offline or degraded, fail closed with `target_device_offline` (no silent fallback).
2. **Required Capability Gate**: Matches target against verified capabilities (`voice.input`, `voice.output`, `computer.input`, `home.control`).
3. **Device Health / Liveness**: Filter candidate devices by `status == "online"`.
4. **Owner Authorization**: Device owner ID must strictly match actor's `owner_id`.
5. **Deterministic Default Fallback**: Route to the local authoritative host (NIGHTFURY) or primary active room endpoint.
