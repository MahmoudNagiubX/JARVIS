# Donor integration map

The selected spine is BMO/JARVIS. Donor systems are integration sources, not
additional architectural spines. No donor source code is copied into Phase 01.

| Product boundary | Primary source | Integration treatment | Phase |
|---|---|---|---|
| Core application/lifecycle | BMO `src/personal_ai_os/app.py` | Re-express composition behind `JarvisRuntime`; retain explicit startup/shutdown and reconciliation ideas | 01/02 |
| Identity and devices | BMO `identity/contracts.py`, `identity/service.py` | Adapt durable BMO service to `IdentityService`; preserve strict fields, scopes, capability binding, and credential rotation | 02 |
| Model gateway | BMO `model_gateway/contracts.py`, `gateway.py`, providers | Adapt provider-neutral generation/health concepts to `LLMRequest`/`LLMResponse`; model assets remain governed by local policy | 02 |
| Tool registry/execution | BMO `tools/contracts.py`, `registry.py`, `service.py` | Adapt catalog, risk, deadline, idempotency, sandbox, verification, and executor routing | 02 |
| Approval and audit | BMO tools models/service | Make approval and audit calls mandatory for consequential tool operations | 02 |
| Conversation executor | BMO `conversations/executor.py` | Add behind goal/event contracts; do not let it become authority owner | 02 |
| Windows device execution | BMO `satellites/windows` | Adapt typed command/capability protocol to `ComputerController` | 03 |
| Voice state/pipeline | BMO `voice/state.py`, `pipeline.py` | Adapt state transitions and local pipeline to `RealtimeVoiceSession`; retain barge-in as capability behavior | 03 |
| Agent orchestration | PersonalJarvis `jarvis/brain`, `missions`, `missions/workers` | Migrate narrow orchestration pieces behind goals, tools, events, and worker contracts; do not copy `BrainManager` wholesale | 02/03 |
| Rich event vocabulary | PersonalJarvis `jarvis/core/events.py`, `core/bus.py` | Use as behavior reference; normalize into the Phase 01 envelope and bus | 02 |
| Memory/wiki | PersonalJarvis `jarvis/memory`, `memory/wiki` | Adapt retrieval/curation ideas to `MemoryStore`; keep owner and audit context explicit | 03 |
| Computer use | PersonalJarvis computer-use modules | Adapt as a controller implementation with approval, device binding, and evidence | 03 |
| Tool orchestration/recovery | aceFelix `agent/core/orchestrator.py`, `error_recovery.py` | Extract sequencing, safe/unsafe concurrency, cancellation, and recovery as runtime behavior | 02 |
| Sandbox/path protection | aceFelix `agent/permissions`, `agent/core/sandbox` | Treat as implementation reference for policy adapters; BMO authority remains canonical | 02/03 |
| Realtime duplex voice | aceFelix `agent/voice/realtime_talk.py` | Adapt audio/VAD/interruption mechanisms behind voice contracts; never bypass common tool authority | 03 |
| File/session memory | aceFelix `agent/core/memory` | Use only where compatible with owner-scoped memory and future durable store | 03 |

## Phase 04 disposition

Phase 03 keeps memory, World State, goals, proactive rules, personalization,
and Venom descriptors product-owned. Phase 04 keeps computer, browser, device,
home, voice routing, communications, notifications, and capability contracts
product-owned. Microsoft UFO and Playwright MCP are adapter references only;
Home Assistant/MQTT and external communication providers are injected seams.
PersonalJarvis and aceFelix concepts were used only as read-only architectural
references; no model, provider SDK, or donor source was copied. The final
repository remains dependency-free and donor worktrees remain unmodified.

## Integration gates

Every migrated component must pass these gates:

1. It imports product contracts, not another donor's internal types.
2. It receives authenticated identity/device context where relevant.
3. It cannot execute consequential actions without permission, approval, and
   audit handling.
4. It emits normalized events with correlation and causation metadata.
5. It has an offline unit-test seam and does not force optional dependencies on
   the foundation package.
