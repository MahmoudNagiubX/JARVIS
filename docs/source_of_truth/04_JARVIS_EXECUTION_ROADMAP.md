# JARVIS — EXECUTION ROADMAP

**Status:** CANONICAL WORK ORDER  
**Reviewed:** 2026-09-12

## 1. Phase numbering rule

Keep the historical Mega Phase chain. Officially, only **Phase 18** and **Phase 19** remain after the current Phase 17 code/network closure.

Do not create new Mega Phase numbers for every enhancement. Organize the remaining product work as workstreams inside Phase 18, then use Phase 19 for physical end-to-end acceptance/release.

## 2. Immediate next step — Phase 18A Baseline Audit & Stabilization Gate

**Goal:** establish a trustworthy clean baseline before adding the new capabilities.

### 18A.1 Baseline
- confirm canonical repo/branch/HEAD;
- record environment versions relevant to current tests;
- run focused + full Python tests;
- run frontend tests/build;
- run compile/static/whitespace/dependency checks available in repo;
- record justified skips/degraded dependencies.

### 18A.2 Structural audit
Search for:
- TODO/FIXME/HACK/TBD/placeholder paths;
- dead or duplicate services;
- multiple authorities/schedulers/event buses/VoiceCore/device fabric;
- direct controller/provider calls that bypass canonical services;
- broad `except`/swallowed failures/false success;
- unbounded loops/retries/payloads/context;
- stale compatibility branches and obsolete phase assumptions;
- duplicate validation/security logic;
- raw secrets or sensitive data persisted/logged;
- adapters that report success while not configured.

### 18A.3 Security/authority audit
Check:
- identity/device binding;
- permission/autonomy coverage;
- approval transaction binding and replay behavior;
- audit/event completeness;
- browser SSRF/redirect/injection protections;
- filesystem traversal/symlink boundaries;
- MCP schema sanitization/tool budgets;
- mission restart/idempotency;
- remote command expiry/idempotency;
- Home exactly-once approvals;
- secret/redaction rules.

### 18A.4 Flow audit
Trace representative flows end-to-end:
1. text → local model → safe tool → verified result;
2. consequential tool → approval → resume exactly once;
3. memory write/read/correction/delete;
4. mission pause/restart/resume;
5. browser read/research evidence;
6. bounded computer action;
7. automation trigger → mission/notification;
8. device/home request in configured and not-configured states.

### 18A.5 Documentation audit
- compare phase reports to current HEAD;
- mark old Master snapshots historical;
- remove/repair contradictory current docs only when evidence is clear;
- integrate this source pack;
- do not erase historical evidence.

### 18A.6 Audit output
Produce one reviewed report containing:
- baseline results;
- findings with Gap IDs;
- severity/priority;
- evidence/reproduction;
- fix recommendation;
- tests required;
- `FIX_NOW`, `ROADMAP`, or `NO_ACTION` disposition.

### 18A exit gate
- baseline green or every failure explicitly classified;
- no known P0 authority/security bypass;
- source pack integrated and current;
- Gap Register updated;
- no architecture rewrite performed merely for cleanup.

### 18A status — `COMPLETE` (2026-09-12)
- 18A.1 baseline audit: `docs/audits/PHASE_18A1_BASELINE_AUDIT.md` — verdict `AUDIT_GATE_PASS_WITH_ROADMAP_GAPS`, 0 P0 / 3 P1 / 8 P2 / 3 P3.
- 18A.2 targeted stabilization: `docs/audits/PHASE_18A2_STABILIZATION.md` — fixed the 7 approved findings (F18A1-013, 003, 001, 002, 009, 007, 012) with focused regression tests; full baseline remains green (530 Python passed / 0 skipped / 36 subtests, frontend 75 passed, build clean, npm high/critical audit 0, compileall pass, `git diff --check` pass).
- Source pack integrated into the repository (`AGENTS.md`, `docs/source_of_truth/*`), closing GAP-0001/GAP-0002/F18A1-013.
- All exit-gate conditions above are met. Deferred findings (F18A1-004, 005, 006, 008, 010, 011, 014) remain open and are scheduled into their designated workstreams below (mainly Workstream A for GAP-0503/F18A1-010, and Workstream H for the reliability/hardening items).
- No architecture rewrite, no new authority, no dependency changes, no local commit/push/merge performed as part of 18A.1 or 18A.2 (owner decides when/whether to commit the reviewed diff).
- Next candidate: **Workstream A — Computer Use V2**, per Section 3 below.

---

## 3. Phase 18 capability workstreams

Execute in this order unless new audit evidence changes priority.

### Workstream A — Computer Use V2
**Why first:** this is the largest gap between current JARVIS and the owner's desired general-purpose assistant.

Deliver:
- product-owned UIA target/inspection/action layer;
- benchmark `winapp ui` versus direct UIA implementation;
- semantic window/control grounding;
- bounded native mouse/keyboard/hotkey/paste/drag/drop;
- DPI/multi-monitor handling;
- visual/OCR/local-vision fallback;
- action verifier + recovery loop;
- kill/cancel support;
- repeatable computer-use evaluation suite.

Exit: JARVIS completes a defined multi-application NIGHTFURY task set repeatedly with truthful failures and no policy bypass.

### Workstream B — Browser Automation + Web Extraction V2
Deliver:
- live Playwright adapter behind `BrowserActionService`;
- DOM/accessibility-first interaction;
- bounded context/profile policy;
- upload/download/screenshot workflows;
- bounded HTTP + structured parser + main-content extraction;
- evidence/provenance integration;
- hostile-page/prompt-injection tests.

Exit: defined research and browser-action workflows succeed repeatedly with verified end states and no browser-to-authority escalation.

### Workstream C — Specialist Agent Delegation
Deliver:
- typed specialist task envelope;
- capability grants/scopes;
- planner/verifier contract;
- budgets/deadlines/cancellation;
- checkpoints/recovery;
- action receipts;
- no new authority.

Exit: orchestrator can delegate representative computer/browser/research/file tasks while all side effects still traverse canonical services.

### Workstream D — Personal Knowledge Vault
Start when Mahmoud supplies curated personal data.

Deliver:
- profile/preferences/entities/projects/history schema;
- import/onboarding/review UI or workflow;
- provenance/sensitivity/validity;
- inspect/edit/delete/supersede/conflict flow;
- secret separation;
- retrieval-quality evaluation.

Exit: owner can inspect and correct what JARVIS knows, and untrusted data cannot silently become owner truth.

### Workstream E — Personal Automation, Files & Communications
Deliver in practical slices:
- richer safe file/project operations;
- email provider;
- calendar provider;
- reminders/routines/briefings;
- recurring research;
- approval-aware background missions;
- notification policies.

Exit: selected real owner daily workflows operate end-to-end with secret isolation, approvals, verification, and restart safety.

### Workstream F — Voice / Ambient JARVIS
Engineering improvements can happen in Phase 18; physical acceptance remains Phase 19.

Deliver/improve:
- latency and stability;
- Egyptian Arabic behavior;
- better local TTS candidate evaluation;
- follow-up/barge-in robustness;
- proactive spoken notifications under policy;
- unified voice/action progress experience.

Do not reopen endless wake-word research without failing evidence.

### Workstream G — Distributed JARVIS / VENOM / Home readiness
Prepare code/configuration for real deployment without faking physical PASS:
- deployment tooling and rollback;
- Home Assistant adapter/config;
- MQTT security/config;
- ESP32 protocol implementation where hardware is available;
- room endpoint readiness;
- cross-device continuity tests.

Physical execution/evidence closes in Phase 19.

### Workstream H — Production Hardening, Evaluation & Controlled Improvement
This is the original Phase 18 production goal and runs throughout, with a final closure sweep:
- CI and regression gates;
- practical branch/governance hardening;
- watchdog/recovery;
- backup/restore proof;
- performance/resource regression;
- observability/diagnostics;
- security red team;
- self-evaluation metrics;
- controlled-improvement policy;
- release candidate checklist.

### Phase 18 exit gate
Phase 18 can close only when:
- all P0/P1 code/security gaps are resolved or explicitly owner-deferred;
- Computer Use V2 and Browser V2 meet defined benchmark gates;
- agent delegation is bounded and verified;
- personal/daily integrations selected by Mahmoud work end-to-end;
- production hardening gates pass;
- remaining failures are explicitly physical Phase 19 gates or optional P3 items.

---

## 4. Phase 19 — Final End-to-End Physical Acceptance & Release

Phase 19 does **not** redesign architecture. It proves the real product.

### Voice physical acceptance
- wake benchmark;
- English voice;
- Egyptian Arabic voice;
- mixed Arabic/English;
- TTS quality;
- follow-up;
- barge-in;
- Bluetooth duplex;
- privacy timeout;
- input/output device loss and recovery;
- offline voice loop;
- high-risk voice approval safety;
- acceptance-wizard debt.

### Distributed physical acceptance
- VENOM real deployment/reboot/reconnect;
- secure credentials/authentication;
- node loss/recovery;
- no duplicated authority;
- zero-touch startup.

### Home/device physical acceptance
When hardware/services are available:
- Home Assistant;
- MQTT broker/auth/ACL/reconnect;
- ESP32 enrollment/expiry/ack/state;
- stale retained-command safety;
- high-risk home approval behavior.

### Multi-room physical acceptance
- room binding;
- presence expiry;
- wake/STT/TTS path;
- correct-room response;
- interruption;
- reconnect/packet loss;
- same `VoiceCore`/`AgentRuntime` proof.

### Final JARVIS end-to-end scenarios
At minimum prove representative flows such as:
- “open app, find/edit/save something” using Computer Use V2;
- browser research → evidence → summary;
- long mission → checkpoint → restart → safe resume;
- scheduled reminder/briefing;
- email/calendar action with approval where required;
- personal-memory retrieval with owner correction;
- offline/degraded operation;
- device/home action when configured;
- voice → tool → verified result;
- cancellation/global stop during a long action.

### Phase 19 exit
Release status must be split truthfully:
- `CODE_ACCEPTANCE`
- `INTEGRATION_ACCEPTANCE`
- `PHYSICAL_ACCEPTANCE`
- `RELEASE_READY`

No single green test suite may substitute for all four.

## 5. Completion estimate in roadmap terms

From the current reviewed state:
- **Official Mega Phases remaining:** 2 — Phase 18 and Phase 19.
- **Immediate gate before feature expansion:** 1 — Phase 18A audit/stabilization.
- **Capability workstreams inside Phase 18:** A through H, with hardening running continuously rather than as eight unrelated rewrites.

The workstreams are execution organization, not new independent architectures.
