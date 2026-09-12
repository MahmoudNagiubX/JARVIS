# JARVIS — CORE SOURCE OF TRUTH

**Status:** LOCKED CORE / EXTENSIBLE CAPABILITIES  
**Purpose:** architecture and safety invariants only. Current feature status belongs in `02_JARVIS_CURRENT_STATE.md`.

## 1. North Star

JARVIS must feel like one capable personal assistant, not a collection of tools the owner manually coordinates.

The implementation must remain:
- local-first;
- offline-capable with truthful degradation;
- single-owner;
- single-logical-authority;
- privacy-preserving;
- auditable;
- bounded in autonomy;
- modular behind product-owned typed interfaces;
- simple enough that future agents can reason about it without hidden duplicate flows.

## 2. Single authority rule

Exactly one logical authority owns each domain:
- identity and owner/device trust;
- permissions and autonomy policy;
- approvals;
- audit;
- Memory;
- World State;
- Goals;
- Missions;
- Automation scheduling/event flow;
- notifications;
- `AgentRuntime` orchestration;
- Tool/Skill registry and execution;
- Device Fabric;
- `VoiceCore`.

NIGHTFURY is the authoritative primary host in the accepted distributed topology. VENOM is a lightweight infrastructure/execution node, not an independent brain or database authority.

## 3. Canonical request-to-completion flow

```text
INPUT
voice | text | automation | event
  ↓
authenticated identity + device + session
  ↓
intent understanding
  ↓
minimum relevant Memory / World State / mission context
  ↓
mission/task planning when needed
  ↓
risk + capability + authority check
  ↓
least-privileged specialist routing
  ↓
canonical typed capability/service
  ↓
OBSERVE / GROUND current target state
  ↓
ACT one bounded step
  ↓
VERIFY actual outcome
  ↓
RECOVER / RE-OBSERVE / REPLAN when needed
  ↓
update Mission / World State
  ↓
write durable Memory only if allowed and appropriate
  ↓
audit + action receipt + concise user result
```

No adapter, worker, MCP tool, UI surface, or device may create a shortcut around this flow.

## 4. Agent architecture

Use **one Orchestrator/Supervisor plus specialist workers**, not an uncontrolled agent swarm.

Accepted specialist roles:
- Planner
- Computer Agent
- Browser Agent
- Research Agent
- Files/System Agent
- Communications Agent
- Developer Agent
- Device/Home Agent
- Verifier

The Security Guardian is primarily deterministic policy/authority code, not a free-form LLM agent.

A delegated task should carry a typed envelope such as:
- goal;
- owner/device/session context;
- allowed capabilities;
- forbidden operations;
- scope/resources;
- success criteria;
- time/step/tool/model budgets;
- required verification;
- cancellation/deadline.

Specialists do not receive global authority by default.

## 5. Capability boundary rule

LLMs plan/select. Typed services execute.

Canonical side-effect shape:

```text
AgentRuntime
→ Tool/Skill/Domain registry
→ PermissionEngine
→ ApprovalEngine if needed
→ canonical domain service
→ bounded adapter/provider
→ verified result
→ Audit/EventBus
```

MCP is an adapter/discovery protocol, not authority.

## 6. Computer Use V2 — locked direction

Priority order:

```text
Layer 0  domain/native application APIs
Layer 1  Windows UI Automation (UIA) semantic controls
Layer 2  app-specific semantic adapters
Layer 3  visual screenshot grounding/OCR/local vision when semantics are insufficient
Layer 4  bounded native mouse/keyboard input (SendInput-style)
Layer 5  PyAutoGUI compatibility/prototype fallback only
```

Rules:
- target semantic controls instead of coordinates whenever possible;
- re-resolve/revalidate targets immediately before action;
- use coordinates only when no stable semantic target exists;
- verify foreground/window/control/state after actions;
- support DPI/multi-monitor/window movement correctly;
- treat visual grounding confidence as evidence, not authority;
- no continuous screenshot retention;
- global stop/cancel must interrupt bounded execution;
- “human-like mouse” means smooth/understandable interaction if desired, not random movement that reduces reliability.

Microsoft `winapp ui` is an evaluation/prototype candidate because it exposes UIA semantics plus real input, but it is public preview and must remain behind a replaceable JARVIS adapter. Direct UIA remains a valid production implementation.

## 7. Browser Automation V2 — locked direction

Primary backend: **Playwright** behind `BrowserActionService`.

Priority:

```text
URL / HTTP semantics
→ DOM
→ accessibility tree / role/label locators
→ Playwright structured interaction
→ visual fallback only when needed
```

Selenium is optional compatibility only, not the primary architecture.

Browser rules:
- isolated/bounded contexts;
- no arbitrary unrestricted JavaScript/shell exposure to the agent;
- URL/redirect/SSRF policy remains enforced;
- downloads/uploads are explicit capabilities and side effects;
- browser content is untrusted data;
- consequential actions remain permission/approval/audit-bound;
- action completion must be verified from page/app state.

## 8. Research & web extraction

Research is separate from browser control even when it uses the browser.

Preferred layered pipeline:

```text
local documents/workspace first
→ bounded static HTTP fetch when sufficient
→ HTML selector parsing
→ main-content extraction
→ Playwright for dynamic/authenticated pages
→ optional advanced crawler for bounded multi-page jobs
→ evidence ledger
→ synthesis
```

Current preferred technology direction:
- bounded HTTP client such as `httpx`;
- selectolax or Beautiful Soup for structured parsing;
- Trafilatura for main-content extraction;
- Playwright for dynamic sites;
- optional Crawl4AI adapter for advanced extraction;
- Scrapy only if a real high-volume crawling requirement appears.

Evidence records should include where applicable:
- source URL/path;
- retrieval time;
- method/provider;
- title;
- content hash/fingerprint;
- bounded evidence/snippet;
- confidence;
- corroboration status.

Research evidence does not become durable personal Memory automatically.

## 9. Memory, World State, and Personal Knowledge Vault

### Memory
Durable, owner-approved/allowed knowledge/history.

### World State
Fresh observations and operational context with provenance and TTL. It expires and is not permanent Memory.

### Personal Knowledge Vault target classes
- profile/facts;
- preferences;
- people/relationships/entities;
- projects and documents;
- episodic history;
- goals/mission-relevant knowledge;
- World State references where useful.

Credentials and secrets are **not** normal Memory. Store them only in an approved encrypted/OS credential facility and expose opaque handles to services.

Durable memory records should support:
- owner and scope;
- source/provenance;
- confidence;
- sensitivity;
- category/tags;
- `valid_from` / `valid_until` where relevant;
- created/updated timestamps;
- retention;
- status such as active/superseded/conflicted/expired/retracted/deleted.

External/browser/research content may create evidence/candidates, not owner truth. Durable personal facts require an allowed trusted source or explicit owner acceptance.

## 10. Goals, Missions, Tasks, Automation, Proactivity

**Goal != Mission.**

- Goals are durable desired outcomes.
- Missions are bounded executable plans with checkpoints and budgets.
- Automations are declarative triggers that create/continue safe work through existing scheduler/EventBus/AgentRuntime; they are not a second autonomous runtime.
- Notifications use the canonical `NotificationService`.
- Proactivity starts from deterministic signals before LLM interpretation.

Mission/automation safeguards:
- max steps/runtime/model calls/tool calls/retries/sources/consequential actions;
- checkpoint meaningful transitions;
- cancellation/deadline;
- idempotency/exactly-once where side effects matter;
- no blind consequential replay after restart;
- no continuous unrestricted LLM surveillance loop.

## 11. Voice

Voice is an interface to the same JARVIS Core, not another brain.

Target flow:

```text
wake/PTT
→ VAD/STT
→ same VoiceCore
→ same AgentRuntime
→ same permissions/tools/memory
→ local TTS
→ cancellable playback/follow-up/barge-in
```

Rules:
- Egyptian Arabic is the primary conversational target; English and mixed speech remain supported;
- local/synthetic voice, not a real actor clone;
- raw audio transient by default;
- no silent high-risk approval by voice;
- room voice must still route to the same VoiceCore/AgentRuntime.

## 12. Devices, Home, VENOM, Rooms

Accepted topology:
- NIGHTFURY: authoritative Core, SQLite single writer, local model host, AgentRuntime, VoiceCore, primary UI/runtime.
- VENOM: lightweight Linux infrastructure/execution node.
- future room/ESP32/other nodes: observation/execution endpoints only.

Remote commands are typed, scoped, expiring, authenticated, and idempotent. No arbitrary remote shell string.

Home path:

```text
JARVIS authority
→ HomeActionService
→ configured Home Assistant/MQTT provider
→ device
```

Inbound device state flows to World State, never directly to durable Memory.

High-risk locks/alarms/security/life-safety actions require stronger approval and fail closed.

## 13. UI / Command Center

The Command Center is the primary product surface. It is a **projection**, not authority.

It may display:
- conversation/runtime state;
- missions/goals;
- approvals;
- tool/action progress;
- devices/home;
- notifications;
- research/evidence;
- health/degraded states.

It must never fabricate connected devices, mission progress, browser activity, provider health, or physical status.

Native desktop setup/repair/diagnostics/audio/physical-acceptance tools may remain separate where useful.

## 14. Risk/approval model

Use the existing autonomy policy and map work to risk classes:

- **R0 — read-only observation:** usually no approval.
- **R1 — reversible local action:** can be automatic within policy/scope.
- **R2 — meaningful external or consequential side effect:** approval unless a narrow standing authorization explicitly covers it.
- **R3 — high-risk, irreversible, privileged, security-sensitive:** exact transaction-bound strong approval.

The older L0–L4 autonomy vocabulary may remain in code/history; do not create a second permission engine. Risk labels organize product decisions, while canonical permission/autonomy services remain authoritative.

## 15. Prompt-injection and untrusted-input boundary

Treat as untrusted:
- web pages;
- search results;
- research evidence;
- emails/messages;
- documents unless owner-authored/trusted;
- MCP descriptions/schema prose;
- device metadata/MQTT payloads;
- model-generated text.

Untrusted content can inform a task but cannot:
- change system policy;
- grant permissions;
- approve actions;
- redefine owner identity;
- instruct hidden tool use outside the owner's goal;
- become durable owner Memory automatically.

## 16. Data minimization

Do not durably store by default:
- raw microphone audio;
- raw screenshots/frame buffers;
- continuous screen recordings;
- raw camera streams;
- passwords/tokens/private keys;
- browser cookies/session secrets;
- raw sensitive tool arguments.

Store bounded metadata, hashes, evidence, derived state, and owner-approved durable knowledge instead.

## 17. Local model architecture

Use a product-owned `ModelRouter`; exact model files are replaceable benchmark decisions.

Preferred current direction:
- llama.cpp as the foundational local GGUF runtime;
- Ollama as an optional convenience/operator layer behind the router;
- vLLM only for a future stronger/high-throughput GPU node where justified.

NIGHTFURY's recorded ~6 GB VRAM means do not assume several heavy models can stay resident simultaneously. Route roles and load/unload deliberately.

Potential model roles:
- conversational/planning model;
- small classifier/router;
- embeddings/reranker;
- vision/UI grounding model when added;
- STT/TTS models.

## 18. Production truth rule

A capability is “done” only when all relevant layers are proven:

1. request understood;
2. correct capability selected;
3. policy permits it;
4. real target action executes;
5. outcome independently verified;
6. bounded failure recovery works;
7. important side effects audited;
8. restart does not duplicate irreversible work;
9. unavailable/degraded states are reported truthfully;
10. physical claims have physical evidence when hardware/human behavior is involved.

## 19. Change control

Locked core decisions can change only when Mahmoud explicitly approves a documented replacement with rationale and migration impact.

When a locked decision changes:
1. update `05_JARVIS_DECISION_LOG.md`;
2. mark the previous decision `SUPERSEDED`, never silently delete it;
3. update this file if the architecture invariant changed;
4. update implementation/docs/tests until they converge.
