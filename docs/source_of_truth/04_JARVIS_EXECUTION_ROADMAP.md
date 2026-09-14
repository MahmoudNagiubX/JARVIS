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

**Status (2026-09-13):** A.1 backend evaluation complete (`docs/audits/PHASE_18_WORKSTREAM_A1_UIA_BACKEND_EVALUATION.md`, backend locked by DEC-046). Batch 01 Milestones 1-3 complete: read-only semantic UIA foundation, canonical `computer.semantic.read` tool wiring, and bounded approval-gated `computer.semantic.act` (invoke/toggle/select) - `invoke` physically proven live on NIGHTFURY. See `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_01.md` for full evidence. Batch 02 complete (Milestones 0-2): Milestone 0 closed the 5 independent-review findings against Batch 01 (strong/weak identity, `list_windows` privacy filtering, fresh post-action re-observation, target-aware/time-bounded approval binding, disabled/offscreen/password fail-closed actuation checks). Milestone 1 added grounded native `SendInput` mouse (`move_to_element`/`left_click_element`) and bounded named-key keyboard input (`computer.pointer.act`/`computer.keyboard.key`), both physically proven live on NIGHTFURY (disposable Calculator). Milestone 2 added a deterministic `computer_use_v2` evaluation suite (17 cases, reuses the existing `EvaluationService`) and an opt-in physical acceptance runner (`scripts/phase18/computer_use_acceptance.py`) run 3x on NIGHTFURY. See `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_02.md`. Batch 03 complete (Milestones 0-2): Milestone 0 generalized target-aware/time-bounded approval binding beyond semantic actions to `computer.pointer.act` and window-targeted keyboard actions (R18B02-001/002/003), replaced the Edge Guest fixture with a fully JARVIS-owned native Win32 UIA fixture (`scripts/phase18/uia_fixture_host.py`) after the Batch 02 Notepad physical-test incident, and achieved the first all-three-pattern (invoke/toggle/select) physical proof, 3/3 each, on NIGHTFURY - GAP-0101 is now `RESOLVED` for the core semantic capability. Milestone 1 closed the long-standing GAP-0503 (approved-root file access confinement, fail-closed by default, verified junction/traversal escape resistance, sensitive-path deny list). Milestone 2 expanded native input (`right_click_element`/`double_click_element`/`scroll_element`, a 5-chord `computer.keyboard.chord` allowlist), grew the `computer_use_v2` evaluation suite to 24 cases, and achieved the first physical proof of a grounded click on NIGHTFURY's non-primary monitor (`NON_PRIMARY_MONITOR_PHYSICAL_PASS`, 3/3) - all through the same owned fixture, no owner app ever touched. See `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_03.md`. Batch 04 complete (Milestones 0-2, `PHASE18_COMPUTER_USE_BATCH04_PARTIAL`): Milestone 0 closed an independent-review finding against Batch 03's file-search traversal (replaced `Path.rglob()` + post-hoc filtering with a genuine pre-descent bounded walker; broadened `.env` sensitivity matching to the full `.env.*` wildcard family) - GAP-0503 now `RESOLVED_AFTER_REVIEW_HARDENING`. Milestone 1 added a reviewed, bounded `drag_element_to_element` action with genuine dual-target approval binding (same-window-only, deterministic bounded interpolation, guaranteed left-button release on partial failure), a second owned Win32 fixture (`scripts/phase18/uia_text_fixture_host.py`) with a real EDIT control and drag source/target buttons, and physically proved English/Arabic Unicode literal typing, Home/End/Backspace, Tab, and clipboard `ctrl+c`/`ctrl+z` - all 3/3 on NIGHTFURY. Found and fixed two real Win32 bugs via physical dogfooding (missing initial keyboard focus; a button-capture race in the first drag-detection design, resolved by subclassing) plus one pre-existing Phase-11-era bug (`computer.clipboard_read` silently required approval due to a missing permission rule). The `computer_use_v2` evaluation suite grew to 32 cases. Milestone 2 performed an evidence-first evaluation of two local OCR candidates (PaddleOCR, RapidOCR) in an isolated venv - both failed acceptance gates (PaddleOCR: reproducible PaddlePaddle CPU oneDNN executor crash; RapidOCR: Arabic recognition accuracy far under the required gate, plus an independently-reproduced undeclared `python-bidi` dependency risk) - concluding `OCR_BACKEND_EVALUATION_BLOCKED` with no production integration forced, per the task's own explicit instruction. See `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_04.md`. Paste, cross-window drag, file drag/drop, arbitrary hotkeys, file dialogs/write-move-copy-rename-delete, local visual OCR grounding (GAP-0103, blocked), autonomous multi-app recovery (GAP-0104), the full evaluation-suite real-app breadth (GAP-0105), and non-100%-DPI/secure-desktop physical proof (GAP-0106) all remain future/in-progress work.

**Batch 08 M0 status (2026-09-14):** the Workstream A evaluator now uses
sequence-aware normalized Levenshtein similarity. Corrected three-run physical
measurements of Candidates A, B, and the evaluation-only bounded
`combined_then_english` Candidate C were completed through the JARVIS-owned
OCR fixture. Candidate C failed its English-similarity and all-three-run warm
two-pass gates, so the exact result is
`OCR_BOUNDED_TWO_PASS_EVALUATION_NO_CHANGE`; DEC-048 remains unchanged and
M1/M2 are the next separately gated slices. The deterministic suite is at 48
cases after Batch 07.

**Batch 08 M1/M2 result (2026-09-14):** M1 added the bounded
`computer.visual.act` left-click path behind the existing approval and native
input authorities. M2 added a real fixture-authored visual button/status
postcondition and an allowlisted duplicate-target variant. The final offline
three-run physical receipt is `PARTIAL`: stale-target, duplicate-ambiguity,
approval-drift, and post-input-uncertainty safeguards are each 3/3, with zero
network attempts and exact child cleanup; the real happy-path click is 0/3
because the CPU-only host expires the visual reference during slow OCR/
revalidation before foreground-safe input can begin. The three-clean-run
gate is therefore false, GAP-0103 advances only to bounded visual actuation,
and no Batch 09 work starts. See
`docs/audits/PHASE_18_WORKSTREAM_A_BATCH_08.md`.

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
