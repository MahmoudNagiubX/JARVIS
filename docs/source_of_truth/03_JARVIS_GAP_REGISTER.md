# JARVIS — GAP REGISTER

**Status:** CANONICAL OPEN-WORK REGISTER  
**Reviewed:** 2026-09-12

> A gap is not automatically a bug. It may be missing capability, production debt, physical acceptance, configuration, or documentation drift. `02_JARVIS_CURRENT_STATE.md` owns capability status; this file owns what still needs work.

## 1. Priority meanings

- **P0:** must be resolved/gated before broad new feature work.
- **P1:** core product capability or security/reliability gap required for the target JARVIS experience.
- **P2:** important productization/integration/physical gap after the core capability path is stable.
- **P3:** optional/future enhancement; do not block core completion.

## 2. P0 — stabilization gate

### GAP-0001 — Canonical documentation/state drift
**Status:** `RESOLVED`  
**Problem:** the 2026-09-05 Master still says Phase 17 HOLD at `db3f61a`, while current `main` is `54b67ba` with the network-readiness closure.  
**Resolution:** this source pack separates historical archive from current truth and records the current HEAD; the pack was copied unchanged into the actual git repository (`AGENTS.md` and `docs/source_of_truth/*` at repo root) during Phase 18A.2 (2026-09-12), closing finding F18A1-013.  
**Gate:** met — pack is committed inside the repository; future agents must treat these repo-local copies as authoritative, not the parent-directory (`C:\Jarivs\`) originals, which remain unmodified as the historical bootstrap source.

### GAP-0002 — No permanent agent bootstrap contract at repo root
**Status:** `RESOLVED`  
**Problem:** current reviewed root had no `AGENTS.md` (Phase 18A.1 found the canonical pack living one directory above the actual repo root, at `C:\Jarivs\` instead of `C:\Jarivs\00_final\jarvis\` — finding F18A1-013).  
**Resolution:** the generated `AGENTS.md` and `docs/source_of_truth/*` pack were copied unchanged into the git repository during Phase 18A.2 (2026-09-12). Do not create a second source-of-truth hierarchy; the parent-directory copies were left untouched but are no longer authoritative.

### GAP-0003 — Current HEAD needs a fresh Phase 18 baseline audit before feature expansion
**Status:** `RESOLVED`  
**Problem:** current tests are green, but a green suite does not prove absence of dead paths, duplicate flows, stale docs, swallowed errors, missing configuration truth, hidden authority bypasses, or debt outside tested scenarios.  
**Resolution:** Phase 18A.1 produced `docs/audits/PHASE_18A1_BASELINE_AUDIT.md` (evidence-based audit; 0 P0, 3 P1, 8 P2, 3 P3 findings). Phase 18A.2 (`docs/audits/PHASE_18A2_STABILIZATION.md`, 2026-09-12) fixed the seven approved findings — see GAP-0003A through GAP-0003D below and the GAP-0302 update in Section 5. Every remaining finding is preserved below as an explicit open gap; none was silently dropped.  
**Exit:** met — reviewed finding report exists; every finding has a Gap ID and a disposition (`FIX_NEXT` and now fixed, or `ROADMAP`, or `NO_ACTION`).

### GAP-0003A — F18A1-001: device revocation could swallow credential-revocation failure
**Status:** `RESOLVED` (Phase 18A.2, 2026-09-12)  
**Problem:** `DeviceFabricService.revoke()` wrapped `repository.revoke_device(...)` in a bare `except Exception: pass`, so a failure to revoke the underlying credential (the one `IdentityService.authenticate()` actually checks via `credentials.revoked_at`) could be silently swallowed while `device_fabric.status` was already `REVOKED` and a `device.revoked` audit/event was still recorded — a false-success pattern on a security-critical control.  
**Resolution:** reordered to revoke the credential first and let a failure propagate (fail closed, no second authority introduced); `device_fabric` status and the `device.revoked` audit/event are now written only after credential revocation succeeds. `src/jarvis/devices/fabric.py::DeviceFabricService.revoke`.  
**Tests:** `tests/test_phase_eighteen_stabilization.py::test_device_revocation_propagates_credential_failure_and_reports_no_false_success`, `::test_device_revocation_happy_path_still_succeeds`.

### GAP-0003B — F18A1-003: verified signal dropped before reaching the model-facing tool message
**Status:** `RESOLVED` (Phase 18A.2, 2026-09-12)  
**Problem:** `ToolCallResult` carried no `verified` field, so `AgentRuntime._bounded_tool_message` could not include the handler's own verification evidence — the model (and therefore JARVIS's own natural-language answer) could not distinguish a verified action from an unverified one, undercutting the closed-loop VERIFY rule in `AGENTS.md` §5.  
**Resolution:** added `verified: bool | None` to `ToolCallResult` (propagated from the domain `ToolResult.verified` for completed and attempted-then-failed executions; `None` when no execution was attempted, e.g. denied/pending) and merged it into `AgentRuntime._bounded_tool_message`'s output, surviving truncation. `src/jarvis/tools/service.py`, `src/jarvis/agents/runtime/runtime.py`.  
**Tests:** `tests/test_phase_eighteen_stabilization.py::test_verified_true_reaches_model_visible_tool_result`, `::test_verified_false_reaches_model_visible_tool_result`, `::test_bounded_tool_message_error_handling_and_backward_compatibility_are_preserved`, `::test_ephemeral_argument_and_output_redaction_is_unaffected_by_verified_propagation`.

### GAP-0003C — F18A1-007 / F18A1-009: computer/home failure paths did not degrade truthfully
**Status:** `RESOLVED` (Phase 18A.2, 2026-09-12)  
**Problem:** `ComputerActionService.decide()` raised a raw `KeyError` for a missing/stale in-memory pending approval instead of a typed failure, surfacing as an opaque HTTP 500 (F18A1-007); `HomeAssistantTransport`'s write path had no exception handling around the outbound HTTP call, so a provider disconnect/timeout escaped as an uncaught exception (F18A1-009).  
**Resolution:** `ComputerActionService.decide()` now returns `ComputerResult("failed", error_code="pending_action_unavailable_after_restart", verified=False, ...)`, matching the existing Browser/Home convention. `HomeAssistantTransport.execute()` now catches `URLError`/`OSError`/`TimeoutError` around the outbound call and returns a typed `home_assistant_unreachable:<ExceptionClass>` failure. `src/jarvis/computer/service.py`, `src/jarvis/devices/home/service.py`.  
**Tests:** `tests/test_phase_eighteen_stabilization.py::test_computer_decide_returns_typed_failure_for_missing_pending_approval`, `::test_computer_decide_returns_typed_failure_on_repeated_decide_after_consumed`, `::test_home_assistant_write_provider_exception_degrades_truthfully_at_transport_level`, `::test_home_action_service_boundary_never_leaks_uncaught_provider_exception`.

### GAP-0003D — F18A1-012: browser 2 MB page-size cap had no regression test
**Status:** `RESOLVED` (Phase 18A.2, 2026-09-12)  
**Resolution:** test-only change (no production behavior changed). Added a regression test exercising the real production fetch path (not the injected-fetcher test bypass) proving the existing 2,000,000-byte cap raises `page_too_large` rather than truncating or succeeding with a partial body.  
**Tests:** `tests/test_phase_eighteen_stabilization.py::test_browser_fetch_enforces_two_megabyte_cap_on_the_real_production_path`.

## 3. P1 — Computer Use V2

### GAP-0101 — No general Windows semantic UI control
**Status:** `OPEN`  
Current grounded control is intentionally narrow. Add product-owned UIA inspection/target/action contracts behind `ComputerActionService`.  
**Backend-selection subproblem:** `RESOLVED` — the A1 evaluation (`docs/audits/PHASE_18_WORKSTREAM_A1_UIA_BACKEND_EVALUATION.md`) is complete and DEC-046 locks the production backend (in-process `uiautomation`/`comtypes` adapter; `winapp ui` optional dev/eval tool only). Semantic UIA implementation work is now active under Phase 18 Workstream A, Batch 01. This gap remains `OPEN` overall until the semantic capability itself (not just the backend choice) is implemented and accepted — do not close it merely because the backend decision exists.  
**Batch 01 Milestone 1 (read-only foundation):** `PARTIAL` — `WindowsUIAutomationAdapter` (`src/jarvis/computer/semantic_uia.py`) implements bounded inspect/search/read/revalidate with stale-safe element references, behind the optional `computer-uia` dependency; proven live on NIGHTFURY (Calculator + Notepad). Not yet wired into `ComputerActionService`/`ToolRegistry` (Milestone 2) and no actuation exists yet (Milestone 3) — the gap stays `OPEN` overall.

### GAP-0102 — Mouse and rich keyboard input are incomplete
**Status:** `OPEN`  
General mouse click/move/drag/drop and arbitrary bounded hotkeys/keys/paste are not supported by the current Phase 11 path. Add native bounded input only after target grounding and policy checks.

### GAP-0103 — Visual grounding/OCR/local vision not production-active
**Status:** `OPEN`  
On-demand GDI capture exists, but OCR/local vision/visual target selection remain provider work. Evaluate UIA first; visual fallback only when semantics fail.

### GAP-0104 — Action verification/recovery needs full multi-app implementation
**Status:** `OPEN`  
Build per-action verification, re-observation, stale-target recovery, moved-window handling, ambiguity handling, retry budgets, and explicit failure receipts.

### GAP-0105 — Computer-use evaluation suite is missing
**Status:** `OPEN`  
Create repeatable NIGHTFURY tasks across Notepad, Explorer, Settings, Calculator, VS Code, terminal, browser, dialogs, clipboard, drag/drop, multi-window and failure recovery. Record success, steps, replans, wrong actions, latency, grounding source/confidence, and verification evidence.

### GAP-0106 — Multi-monitor/DPI/secure-desktop behavior needs explicit proof
**Status:** `OPEN`  
Computer Use V2 must handle DPI/window movement/multiple monitors and fail safely on secure/locked/UAC-style surfaces it cannot control.

## 4. P1 — Browser + web extraction

### GAP-0201 — Live Playwright action adapter is not active in default runtime
**Status:** `OPEN`  
Implement real click/type/select/navigation/screenshot capability behind existing `BrowserActionService`, preserving URL policy, approvals, audit, and offline composition.

### GAP-0202 — Browser upload/download workflows are missing
**Status:** `OPEN`  
Add bounded file selection/download destinations, explicit capability/risk rules, progress/result verification, and sensitive-path protection.

### GAP-0203 — Production web extraction stack needs implementation
**Status:** `OPEN`  
Add bounded static fetch + structured HTML parser + main-content extraction, with Playwright only when dynamic/authenticated rendering is required. Keep optional advanced crawling behind an adapter.

### GAP-0204 — Real-world prompt-injection/red-team matrix needs expansion
**Status:** `OPEN`  
Phase 15 closed schema/URL/security gaps, but the live browser/extraction stack must be tested against hostile page text, hidden instructions, poisoned metadata, download traps, cross-origin/redirect abuse, and attempts to exfiltrate secrets or escalate tools.

### GAP-0205 — Browser session/profile policy needs product decision and implementation
**Status:** `OPEN`  
Define isolated ephemeral contexts versus explicitly approved persistent owner profiles. Cookies/tokens must stay out of Memory/audit/model-visible data.

## 5. P1 — Agent delegation and execution quality

### GAP-0301 — Specialist roster is product direction, not yet a fully formalized runtime contract
**Status:** `OPEN`  
Worker seams already exist, but formalize typed task envelopes, least-privilege capability grants, budgets, deadlines, cancellation, checkpointing, and verifier handoff without creating new authorities.

### GAP-0302 — Verifier role must be independent from “action returned success”
**Status:** `OPEN` (Home Assistant instance `RESOLVED` — see below; general cross-domain verifier contract remains open)  
For computer/browser/device/communications actions, define verification evidence that can prove the requested post-condition.  
**F18A1-002 (Phase 18A.2, 2026-09-12):** `HomeAssistantTransport.execute()` previously set `verified` from the outbound HTTP status alone (`200 <= status < 300`), a direct instance of this gap. Fixed: verification now requires an independent, bounded (single-attempt, no polling) state read-back via `GET /api/states/{entity_id}` compared against the intended effect for `turn_on`/`turn_off`/`set_brightness`/`set_temperature`; `set_color`/`trigger_scene` have no deterministic comparable state and are honestly reported as unverified rather than guessed. `src/jarvis/devices/home/service.py::HomeAssistantTransport._verify_state`. Tests: `tests/test_phase_eighteen_stabilization.py::test_home_assistant_reports_verified_only_after_matching_independent_readback`, `::test_home_assistant_does_not_claim_verified_when_state_does_not_change`, `::test_home_assistant_does_not_claim_verified_when_readback_unavailable`, `::test_home_assistant_unverifiable_action_is_reported_truthfully`. The broader gap (a general cross-domain verifier contract for computer/browser/communications) remains open.

### GAP-0303 — Long-running mission recovery/idempotency needs Phase 18 stress testing
**Status:** `OPEN`  
Mission restart semantics are implemented, but run crash/restart/timeout/duplicate-event/concurrent-resume scenarios must be included in production hardening.

### GAP-0304 — Live developer worker adapter is not configured
**Status:** `OPEN/P2`  
The DeveloperWorkerGateway/provider seams exist; a safe live repository/developer worker remains optional until a bounded adapter is selected and tested. Runtime must not depend on AntiGravity/Google auth.

## 6. P1 — Personal intelligence expansion

### GAP-0401 — Mahmoud Personal Knowledge Vault onboarding is not built
**Status:** `OPEN`  
Phase 16 memory semantics are strong, but the richer curated personal profile/preferences/people/projects/history import/edit/review workflow is new enhancement work.

### GAP-0402 — Personal data correction/review UX needs productization
**Status:** `OPEN`  
Expose owner-friendly inspect/edit/delete/supersede/conflict handling without bypassing canonical MemoryService.

### GAP-0403 — Secret references for external integrations need one standardized boundary
**Status:** `OPEN/P2`  
A secure local credential store exists in voice/productization history, but future email/browser/home integrations need a consistent opaque secret-handle contract. Never place credentials in Memory.

### GAP-0404 — Retrieval quality for a larger personal vault needs evaluation
**Status:** `OPEN/P2`  
Measure relevance, cross-project isolation, recency/validity, sensitivity, context byte budgets, and incorrect-memory rate after real owner data is onboarded.

## 7. P1/P2 — Communications, files, and daily automation

### GAP-0501 — Live email integration missing
**Status:** `OPEN`  
`CommunicationsHub` exists, but default runtime is local in-memory; no live email provider is claimed.

### GAP-0502 — Calendar integration missing
**Status:** `OPEN`  
No current calendar capability was found in repository review. Add only through a typed provider with read/write distinction, permissions, approvals, and secret isolation.

### GAP-0503 — File/system capability is narrower than target JARVIS experience
**Status:** `OPEN`  
Current file/process operations are bounded and useful, but full safe project/file workflows need explicit roots, write/move/copy/rename/delete policies, verification, rollback/recycle-bin strategy, and sensitive-path exclusions.

### GAP-0504 — Personal recurring workflows need real owner recipes
**Status:** `OPEN/P2`  
Automation foundations exist. Build real daily/weekly reminders, briefings, recurring research, file/communication workflows only after provider capabilities are live.

### GAP-0505 — Notification prioritization/delivery channels need owner tuning
**Status:** `OPEN/P2`  
Canonical notifications exist; future work should add quiet/cooldown/priority/delivery policies without creating another notification authority.

## 8. P2 — Voice and ambient experience

### GAP-0601 — Full physical voice acceptance unfinished
**Status:** `PHYSICAL_PENDING`  
Required: wake reliability; English; Egyptian Arabic; mixed language; follow-up; barge-in; Bluetooth duplex; offline loop; device-loss recovery; privacy timeout; voice-approval safety.

### GAP-0602 — Current Arabic TTS is not proven Egyptian quality
**Status:** `OPEN/PHYSICAL_PENDING`  
Select/benchmark a better local Egyptian or acceptable Arabic voice only under legal/licensing and hardware constraints. Do not clone a real actor.

### GAP-0603 — Acceptance wizard debt
**Status:** `OPEN/P2`  
Historical backlog records mismatch between 8/10 backend PASS and UI behavior that may effectively require 10/10, plus non-Wake button-state debt.

### GAP-0604 — Speaker verification
**Status:** `OPTIONAL/P3`  
Not implemented and not required to claim current voice functionality. If added later, treat as a separate identity signal, not sole authority for dangerous actions.

## 9. P2 — Distributed/Home/physical fabric

### GAP-0701 — Physical VENOM deployment not completed
**Status:** `BLOCKED/PHYSICAL_PENDING`  
Code/provisioning path is ready, but real deployment/authentication evidence is not complete.

### GAP-0702 — Home Assistant live integration not configured
**Status:** `NOT_CONFIGURED`  
Requires local HA connection, scoped credentials, entity allowlist, state verification, approval policy, disconnect/recovery tests.

### GAP-0703 — MQTT live broker not configured
**Status:** `NOT_CONFIGURED`  
Requires authentication, ACLs, bounded namespace, retained-message safety, reconnect behavior, and physical evidence.

### GAP-0704 — ESP32 physical nodes not run
**Status:** `PHYSICAL_PENDING`  
Requires unique device identity, provisioned credentials, capability manifest, command IDs, expiry, ack/result, LWT/availability, and stale-command tests.

### GAP-0705 — Multi-room physical voice not accepted
**Status:** `PHYSICAL_PENDING`  
Room endpoint code must be proven with real microphones/speakers, routing, interruption, correct-room TTS, presence expiry, packet loss/reconnect, and one-VoiceCore invariant.

### GAP-0706 — Phone/mobile endpoint is not implemented/verified
**Status:** `PLANNED/P3`  
Cross-device architecture permits future clients; no physical phone client is currently claimed.

## 10. P1/P2 — Production hardening and governance

### GAP-0801 — GitHub CI/required checks not configured
**Status:** `OPEN`  
Add a minimal deterministic CI gate for supported tests/build/static/security checks.

### GAP-0802 — Branch protection / commit signing governance debt
**Status:** `OPEN/P2`  
Current audit records unprotected/unsigned governance. Choose practical controls that do not block solo development unnecessarily.

### GAP-0803 — Recovery/watchdog/startup fault matrix needs final hardening
**Status:** `OPEN`  
Exercise model failure, provider failure, DB lock/corruption scenarios, node loss, browser failure, voice asset loss, restart during mission, and degraded UI truth.

### GAP-0804 — Backup/restore proof needs current production validation
**Status:** `OPEN/P2`  
Backup foundations exist; Phase 18 must prove restore integrity and owner-data safety on the current schema.

### GAP-0805 — Performance/resource regression gate missing
**Status:** `OPEN/P2`  
Track startup, local-model latency, context size, memory use, UI responsiveness, voice latency, browser/computer action latency, and resource ceilings on NIGHTFURY.

### GAP-0806 — Security red-team/secret-retention audit needs Phase 18 execution
**Status:** `OPEN`  
Cover prompt injection, SSRF, path traversal, symlink escape, auth/session, permission escalation, approval replay, command expiry, secret logs, malicious MCP schemas, malicious device metadata, and browser downloads.

### GAP-0807 — Controlled improvement/self-evaluation needs production boundaries proven
**Status:** `OPEN/P2`  
Evaluation and controlled-improvement services exist historically; final production policy must prohibit uncontrolled core self-modification and require owner/review gates for code changes.

## 11. P2/P3 — UI / UX expansion

### GAP-0901 — New Tony-Stark-style capability screenshots have not yet been mapped
**Status:** `WAITING_FOR_OWNER_INPUT`  
When received, map each visual idea to a real backend capability and state. Do not implement decorative fake telemetry.

### GAP-0902 — Rich action/progress receipts across all specialists need consistency
**Status:** `OPEN/P2`  
The Command Center should project mission/action state, verification, approvals and degraded causes using one coherent contract.

### GAP-0903 — Camera/multimodal ambient perception remains architecture-only
**Status:** `OPTIONAL/P3`  
Continuous camera/screen surveillance is not allowed by default. Add only explicit on-demand/privacy-gated use cases.

## 12. Historical gaps already resolved — do not reopen without regression evidence

### Phase 14 — `RESOLVED`
Closed issues included:
- desktop session expiration/refresh;
- approval `run_id` projection;
- async chat cancellation;
- run-scoped tool activity;
- research evidence projection;
- notification filters/settings truth;
- notification source/time residual;
- 30-second active-chat false failure;
- approval failed-submit button state.

### Phase 15 — `RESOLVED`
Closed issues included:
- `file://`/SSRF/redirect browser policy;
- raw typed secrets in browser approvals;
- MCP schema prompt injection/sanitization;
- current NIGHTFURY capability reconciliation;
- browser read path not model-facing;
- lack of a real built-in MCP-backed workspace skill;
- Arabic/mixed MCP relevance and bounded schema/tool budgets.

These closures do **not** mean live Playwright/full browser automation exists; that is a separate new gap.

### Phase 16 — `RESOLVED`
Closed issues included:
- future-valid memories retrievable too early;
- untrusted browser/research content becoming durable Memory;
- repeated mission approval request for the same step;
- proactive findings bypassing canonical notifications;
- asymmetric project scope between Memory and World State.

### Phase 17 pre-`54b67ba` network readiness gaps — `RESOLVED` in code
Current HEAD closes:
- shared trusted-LAN policy and explicit bounded CIDR override;
- Windows satellite trusted-LAN Core URL support;
- zero-touch desktop node-server startup;
- real VENOM local package/venv/import-smoke provisioning path;
- VENOM heartbeat device binding;
- authenticated detailed health;
- concurrent Home approval exactly-once claim.

Physical VENOM/Home/MQTT/ESP32/room acceptance is still open and is listed above separately.

## 13. Audit rule

When Phase 18A finds a new issue:
1. assign a new Gap ID;
2. record evidence path/test/reproduction;
3. classify priority and status;
4. name the owning canonical service;
5. state whether a locked decision is affected;
6. define an objective exit gate;
7. do not solve it by creating a duplicate authority.
