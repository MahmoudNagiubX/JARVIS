# PHASE 18A.1 — BASELINE AUDIT (AUDIT-ONLY)

**Task:** `tasks/CLOUD_CODE_TASK_PHASE_18A1_BASELINE_AUDIT.md`
**Mode:** AUDIT-ONLY — no code/test/doc changes were made to the repository as part of this audit. This file is the only artifact created.
**Audited HEAD:** `54b67ba396ec45180f1b60ea472ef94c9ac181a9` on `main` (`fix: close phase 17 real network readiness`) — matches the expected baseline exactly.
**Audit date:** 2026-09-12

---

## 1. Executive verdict

The JARVIS baseline at `54b67ba` is **structurally sound and largely trustworthy**. The single-authority architecture described in `AGENTS.md` / `01_JARVIS_CORE_SOURCE_OF_TRUTH.md` is real, not aspirational: every canonical domain (identity, permissions, approvals, audit, tools, memory, world state, missions, automation, notifications, device fabric, home, voice) has exactly one implementing service, wired once in `src/jarvis/bootstrap.py`, and every traced flow in this audit went through that one service with no bypass found. The documented test/build/security baseline reproduces exactly. Not-configured integrations (Home Assistant, MQTT, live Playwright, live email/calendar, external MCP) fail closed and truthfully — none was found faking success.

That said, this audit found **no P0** but **three P1 findings**, all genuine and all with concrete evidence:

1. A device-revocation path can silently fail to revoke the underlying credential while still reporting "revoked" (fail-open on a security-relevant control).
2. Home Assistant action "verification" is derived from an HTTP status code alone, not an independent state read-back — a direct instance of the pattern `AGENTS.md` §5 explicitly forbids.
3. The per-action `verified` flag computed by the tool/computer-action layer is discarded before it reaches the model-facing tool message, so JARVIS's own natural-language answer cannot currently hedge on an unverified action — undercutting the closed-loop VERIFY step system-wide, which matters directly for Computer Use V2.

None of these are exploitable on the happy path or found live in production use; all were found by tracing code, not by observing an incident. They are P1 because they sit on canonical authority/verification boundaries, not because they are currently causing harm.

**One process/documentation finding surfaced immediately and is reported separately from the P0–P3 register:** the canonical `AGENTS.md` and `docs/source_of_truth/*` files this task instructs an agent to read are **not actually inside the JARVIS git repository**. They live one directory above the repo root (`C:\Jarivs\AGENTS.md`, `C:\Jarivs\docs\source_of_truth\`), while the repo root is `C:\Jarivs\00_final\jarvis\`. `03_JARVIS_GAP_REGISTER.md` (GAP-0002) already predicted this exact problem and marked itself `RESOLVED_BY_SOURCE_PACK, verify after repo integration` — this audit's verification shows that integration did **not** happen; the gap should be reopened, not treated as resolved.

## 2. Exact repository baseline

| Property | Value |
|---|---|
| Repo path | `C:\Jarivs\00_final\jarvis` |
| Remote | `https://github.com/MahmoudNagiubX/JARVIS.git` |
| Branch | `main`, up to date with `origin/main` |
| HEAD | `54b67ba396ec45180f1b60ea472ef94c9ac181a9` — matches expected baseline |
| Worktree | Clean except one untracked file: `tasks/CLOUD_CODE_TASK_PHASE_18A1_BASELINE_AUDIT.md` (the task file itself — expected) |
| Python (`.venv`) | 3.12.13 (satisfies `pyproject.toml` `requires-python >= 3.11`) |
| Python (system) | 3.14.6 |
| Node | v24.19.0 |
| npm | 11.17.0 |

**Repo-location anomaly (see §10):** `AGENTS.md` and `docs/source_of_truth/*` are not present under this repo root at all; they exist only at `C:\Jarivs\` (one level above). All other evidence in this report is cited relative to the true repo root, `C:\Jarivs\00_final\jarvis`.

## 3. Verification command/results table

| Command | Result | Counts | Notes |
|---|---|---|---|
| `python -m pytest tests -k phase_seventeen -q` (system Python) | PASS | 79 passed, 436 deselected | Exact match to documented Phase 17 focused baseline |
| `python -m pytest tests -k "phase_thirteen or phase_fourteen or phase_fifteen or phase_sixteen" -q` | PASS | 218 passed, 297 deselected, 11 subtests | Exact match to documented Phase 13–16 regression |
| `python -m pytest tests -q` (full suite) | PASS | 515 passed, 0 skipped, 36 subtests | See discrepancy note below |
| `.venv/Scripts/python.exe -m unittest discover -s tests -v` (TESTING.md's dependency-free path) | Environment-limited | 413 ran, 1 failure, 10 errors | `.venv` lacks `pip`/`pytest`/`numpy`; all 10 errors are `ModuleNotFoundError` for dev/voice extras, not code defects. Audit-only run installed nothing. Not the faithful regression signal — the system-Python pytest run above is. |
| `npm test` (vitest, `ui/`) | PASS | 75 passed, 14 files | Exact match |
| `npm run build` (`ui/`) | PASS | 68 modules transformed, clean | Exact match |
| `npm audit --audit-level=high` (`ui/`) | PASS | exit 0, 0 high/critical | 2 new **moderate** dev-only advisories (`@vitest/mocker`/`vitest`, GHSA-82fw-gwwq-j7x9) since the original Phase 17 audit — does not affect the high-severity gate; see §12 (NO_ACTION). |
| `python -m compileall src tests -q` | PASS | exit 0 | Exact match |
| `git diff --check` | PASS | exit 0 | Exact match |

**Discrepancy vs. `02_JARVIS_CURRENT_STATE.md`'s claimed baseline (514 passed / 1 justified skip / 36 subtests):** actual result was 515 passed / 0 skipped. Root cause identified precisely: `tests/test_phase_ten_active_perception.py::test_focus_window_revalidates_ephemeral_reference` calls `self.skipTest("no active Windows window")` only when no window is in the foreground; on this audit session a window was in the foreground, so the test executed (and passed) instead of skipping. This is exactly the "justified skip" the current-state doc names — **environment-dependent, not a regression.** The suite is fully green either way.

**Stop conditions (task §17): none encountered.** No merge conflict, no destructive-mutation requirement, no missing secret/API key blocked any check, repo state is clean and reproducible.

## 4. Architecture/authority findings

Single-authority confirmation is based on direct code tracing (bootstrap wiring in `src/jarvis/bootstrap.py`) performed across the security audit and three independent end-to-end trace passes, all of which went through exactly one instance of each service with no duplicate found:

| Domain | Canonical implementation | Confirmed single-instance? |
|---|---|---|
| Identity/device | `authority/identity/service.py::IdentityService` | Yes |
| Permissions | `authority/permissions/engine.py::PolicyPermissionEngine` | Yes |
| Approvals | `authority/approvals/service.py::DurableApprovalEngine` | Yes |
| Audit | `authority/audit/service.py::DurableAuditService` | Yes |
| AgentRuntime | `agents/runtime/runtime.py::AgentRuntime` | Yes |
| ToolRegistry/ToolExecutionService | `tools/registry.py`, `tools/service.py::ToolExecutionService` | Yes |
| ComputerActionService | `computer/service.py::ComputerActionService` | Yes |
| BrowserActionService | `browser/service.py::BrowserActionService` (+ `LocalBrowserController`; `PlaywrightBrowserController` exists but is never instantiated by bootstrap) | Yes |
| Memory | `memory/service.py::DurableMemoryService` | Yes |
| World State | `world_state/service.py::DurableWorldStateService` | Yes |
| Goals/Missions | `goals/engine.py::DurableGoalEngine`, `missions/service.py::MissionService` | Yes |
| EventBus | `bus.py::InMemoryEventBus` | Yes |
| BackgroundScheduler | `scheduler/service.py::BackgroundScheduler` | Yes |
| NotificationService | `notifications/service.py::NotificationService` | Yes (single instance; **not durable** — see F18A1-004) |
| DeviceFabricService | `devices/fabric.py::DeviceFabricService` | Yes (see F18A1-001 for a defect within it, not a duplicate-authority issue) |
| VoiceCore | `voice/core.py::VoiceCore` | Yes — `VoiceCore.process_transcript` calls the same `AgentRuntime.process_text` used by the text path (confirmed by direct code read, `voice/core.py:262`) |

**Architecture observation (not a bypass):** device identity data lives in two places — the legacy `devices`/`credentials` tables (written by `IdentityService`/`repository.revoke_device`) and the newer `device_fabric` table (written by `DeviceFabricService`/`repository.upsert_device_fabric`). `IdentityService.authenticate` is the sole authority actually consulted to mint sessions, and it reads `credentials.revoked_at` — so there is still one logical authority for the security-relevant decision. But the two tables must stay in sync for `DeviceFabricService`'s revocation to be authoritative in practice, and nothing enforces that beyond the (currently defective) call in F18A1-001. Recommend treating `device_fabric` and `devices`/`credentials` as one logically-owned pair going forward rather than two independently-writable stores.

No case was found of a model/worker calling an adapter directly, UI invoking a side effect without backend authority, or an MCP/browser/device path bypassing permission/approval/audit.

## 5. Security/data-retention findings

Confirmed with code + tests (see full evidence in §11 register for the two P1/P2 items below):

- Owner/device/session binding, least-privilege checks, consequential approval, owner/device/transaction-bound approval resume, exactly-once resume, and fail-closed ambiguity handling: all **CONFIRMED** with direct evidence (`authority/identity/service.py`, `authority/permissions/engine.py`, `tools/service.py`, `persistence/repositories.py` CAS updates).
- Browser URL scheme restriction, SSRF/redirect protection (per-hop re-validation), and the untrusted-content-cannot-become-Memory firewall: **CONFIRMED** (`browser/policy.py`, `memory/policy.py:_untrusted_sources`), including a direct test injecting literal "SYSTEM:"/"disable approvals" payloads that are correctly rejected.
- MCP schema sanitization/tool-budget bounds (depth ≤8, ≤64 properties, ≤32 enum values, ≤16KB total): **CONFIRMED** (`mcp/models.py`).
- No unrestricted shell: **CONFIRMED** — zero `shell=True`/`os.system` occurrences anywhere in `src/jarvis` (verified directly by this audit); all `subprocess` calls use fixed argv lists against an explicit allowlist.
- Secrets/sensitive data not durably persisted: **CONFIRMED** — `MemoryPolicy` blocks credential-like content and forbids `SECRET` sensitivity outright; sensitive tool arguments use `argument_retention=EPHEMERAL` (digest/keys only, never raw values); raw screenshots/frames are never written to disk in `perception/`.
- Distributed/device commands (ESP32) are typed, TTL-bound, and reject already-expired commands at parse time; satellite transport is replay-safe by content fingerprint.
- Not-configured integrations cannot report verified success: **CONFIRMED with code** — default bootstrap wires `HomeActionService(None, ...)` and an unconfigured `RestrictedMQTTTransport()`; both fail closed (`home_service_unavailable`, `mqtt_not_configured`) rather than faking success.

**New findings from this pass:**
- **F18A1-001** (P1, security) — device revocation can silently fail to revoke the underlying credential while reporting success. See §11.
- **F18A1-010** (P2, security) — `computer.inspect_file`/`search_files`/`open_file`/`open_folder` are auto-ALLOWed with no root confinement or sensitive-path denylist. Already tracked as GAP-0503; this audit attaches concrete evidence.

## 6. Correctness/reliability findings

- **F18A1-002** (P1) — `HomeAssistantTransport.execute` derives `verified` from HTTP status alone, not a state read-back.
- **F18A1-003** (P1) — the computed `verified` flag is dropped before reaching the model-facing tool message.
- **F18A1-004** (P2) — `NotificationService` is entirely in-memory; no `notifications` table exists, only `notification_delivery_attempts`. All active/undismissed notifications are lost on restart.
- **F18A1-005** (P2) — no `sqlite3.OperationalError`/lock-contention handling anywhere in `persistence/db.py` (no `busy_timeout`, no WAL, no retry). Matches existing GAP-0803.
- **F18A1-006** (P2) — mission restart reconciliation (`reconcile_missions`) unconditionally fails every in-flight mission on every process start, including ones merely `WAITING_APPROVAL` with no side effect yet taken, and leaves the associated approval row orphaned in `pending` state.
- **F18A1-007** (P2) — `ComputerActionService.decide()` raises a bare untyped `KeyError` (surfacing as HTTP 500) for a pending approval no longer in its in-memory store, unlike Browser/Home which return typed failures.
- **F18A1-008** (P2) — `AutomationService`'s duplicate-trigger defense is a non-atomic cooldown-window check, not an atomic per-event claim; a race is possible, especially with the allowed `cooldown_seconds=0` configuration.
- **F18A1-009** (P2) — `HomeActionService`/`HomeAssistantTransport` write path has no exception handling around the outbound HTTP call, unlike the read path in the same file.
- **F18A1-012** (P3) — the real, correct 2MB browser fetch cap (`page_too_large`) has no regression test.

Full evidence for every finding is in §11.

## 7. Capability truth matrix

Cross-checked against `02_JARVIS_CURRENT_STATE.md`'s claims by reading actual code (not docs). **No mismatch was found** between the doc's claims and the code for any capability area reviewed.

| Capability | Status | Evidence |
|---|---|---|
| Local model/runtime | IMPLEMENTED | `models/gateway.py::ModelGateway`, wired `bootstrap.py:295` |
| Text conversation/orchestration | IMPLEMENTED | `agents/runtime/runtime.py::AgentRuntime` |
| Tool/skill execution | IMPLEMENTED | `tools/service.py::ToolExecutionService` |
| Computer control | PARTIAL | `computer/service.py` — bounded action set only; no general mouse/hotkeys (matches GAP-0101/0102) |
| Grounded desktop interaction | IMPLEMENTED (bounded) | `perception/desktop.py`, `perception/windows.py` |
| Perception/OCR/vision | PLANNED (seam only) | `perception/service.py`; no OCR/vision-model import anywhere in `src/jarvis` |
| Browser automation | PARTIAL (local HTTP/HTML only) | `browser/service.py::LocalBrowserController` wired; `PlaywrightBrowserController` exists, returns `playwright_adapter_not_configured`, never instantiated |
| Web research/extraction | IMPLEMENTED foundation | `research/service.py`, `research/providers.py` |
| MCP | IMPLEMENTED foundation / external NOT_CONFIGURED | `mcp/registry.py` — only product-owned local providers registered |
| Memory | IMPLEMENTED | `memory/service.py::DurableMemoryService` |
| World State | IMPLEMENTED | `world_state/service.py::DurableWorldStateService` |
| Goals | IMPLEMENTED | `goals/engine.py::DurableGoalEngine` |
| Missions | IMPLEMENTED (fail-closed restart, not resume — see F18A1-006) | `missions/service.py::MissionService` |
| Automation | IMPLEMENTED foundation (see F18A1-008) | `automation/service.py::AutomationService` |
| Notifications/proactivity | IMPLEMENTED foundation (not durable — F18A1-004) | `notifications/service.py`, `proactive/service.py` |
| Communications | IMPLEMENTED foundation, local channel only | `communications/hub.py::CommunicationsHub` |
| Files/system | PARTIAL | Bounded open/inspect/search only via `ComputerActionService` (see F18A1-010) |
| Developer worker seams | NOT_CONFIGURED/PARTIAL | `developer/service.py::DeveloperWorkerGateway` returns `developer_cli_not_available` |
| Voice | IMPLEMENTED (code), routes into same runtime | `voice/core.py::VoiceCore` → `AgentRuntime.process_text` |
| Device Fabric | IMPLEMENTED | `devices/fabric.py::DeviceFabricService` (see F18A1-001) |
| VENOM | IMPLEMENTED (code) / PHYSICAL_PENDING | `nodes/venom.py`; capability registered `available=False, reason="not_probed"` |
| Home Assistant/MQTT | NOT_CONFIGURED, fails closed | `bootstrap.py` wires `transport=None`; confirmed no false success |
| ESP32 | PHYSICAL_PENDING (protocol code exists) | `devices/home/service.py` parse/format functions exist; no live broker |
| Room/multi-device fabric | IMPLEMENTED code / PHYSICAL_PENDING | `devices/room/service.py`, `voice/fabric.py` |
| Command Center/UI | IMPLEMENTED (not independently re-verified against `ui/` source in this pass) | — |
| Production hardening/CI/recovery/backup | PARTIAL | `persistence/backup.py::SQLiteBackupService` wired; CI config not inspected in this pass; DB-lock handling gap (F18A1-005) |

## 8. End-to-end trace matrix

Nine representative flows were traced through actual code by three independent passes (with consistent results). Summary:

| # | Flow | Canonical path confirmed | Gaps found |
|---|---|---|---|
| 1 | Safe local tool call | `AgentRuntime` → `ToolExecutionService` → `PolicyPermissionEngine` → handler → audit/event | `verified` computed but stripped before the model-facing message (F18A1-003) |
| 2 | Approval-required tool action | Same + `DurableApprovalEngine` → paused run → `AgentRuntime.resume` (atomic CAS) → `decide_and_resume` | None — best-covered path in the repo |
| 3 | Bounded computer action | `ComputerActionService` → inner risk re-evaluation (authoritative, stricter than outer `ToolSpec` metadata — F18A1-011) → native SendInput with foreground re-check | `verified=False` honestly returned but dropped before reaching user-facing text (F18A1-003); pending-approval `KeyError` on restart (F18A1-007) |
| 4 | Browser read/research | `BrowserActionService` → `BrowserURLPolicy` (per-hop redirect validation) → bounded fetch → `ResearchService` evidence ledger | Live Playwright/upload/download intentionally not active (GAP-0201/0202, confirmed truthful, not a gap in this audit) |
| 5 | Memory CRUD | `DurableMemoryService` → `MemoryPolicy` firewall → dedup/supersede → audit/event; retrieval filters by status/validity at query time | None found |
| 6 | Mission approval + restart | `MissionService` → atomic CAS resume; restart → `reconcile_missions` fails all in-flight missions unconditionally | Orphaned approval rows, no distinction between "mid-step" and "merely waiting on owner" (F18A1-006) |
| 7 | Automation/proactive notification | `AutomationService` (EventBus-subscribed) / `ProactiveService.detect` → canonical `NotificationService.create` | Non-atomic cooldown dedup (F18A1-008); `NotificationService` itself not durable (F18A1-004) |
| 8 | Configured vs not-configured Home action | Both branches inside `HomeActionService.execute`; not-configured fails closed (`transport=None`) | Configured-branch verification is HTTP-status-only (F18A1-002); write path lacks exception handling (F18A1-009) |
| 9 | Voice → central runtime | `VoiceCore.process_transcript` → same `AgentRuntime.process_text`; voice never silently approves (`APPROVAL_REQUIRED_MESSAGE`, never calls `resume`) | None — DEC-031/AGENTS §6 invariant holds in code; physical STT/TTS providers are the hardware boundary where code-tracing correctly stops |

## 9. Edge-case/failure-mode coverage summary

Full case-by-case detail is in the underlying working notes; headline results:

**Well covered (test evidence found):** process crash/restart (runs/missions), duplicate submit (`client_message_id` dedup), repeated approval submit, concurrent resume, stale target/window/session (foreground TOCTOU recheck), provider timeout, malformed external payload, oversized payload/context, unavailable model/provider, partial execution then verification failure, browser redirect/target change, expired command, user cancellation, stale World State, invalid/superseded Memory.

**Not covered / no evidence found:**
- DB lock/error — no test, no handling code (F18A1-005).
- Process crash/restart for **pending computer-action approvals specifically** — no test found for a fresh `ComputerActionService` against a pre-existing pending row (F18A1-007).
- Duplicate automation trigger under race conditions — code path exists but is not atomic and untested for the race itself (F18A1-008).
- Provider disconnect on the Home **write** path — no exception handling exists to test (F18A1-009).
- "Incorrect success reporting" as a named regression test — the `verified` field convention is the intended guard, but no test asserts against a false-success regression by name, and two live instances of the pattern were found (F18A1-002, F18A1-003).
- Degraded startup signal for a scheduler whose jobs are all failing — no aggregate health surface found (noted, not filed as a separate finding; low severity).

## 10. Documentation conflicts/stale-state findings

- **Repo-location anomaly:** `AGENTS.md` and `docs/source_of_truth/*` live at `C:\Jarivs\`, not inside the repo (`C:\Jarivs\00_final\jarvis\`). GAP-0002 claims `RESOLVED_BY_SOURCE_PACK, verify after repo integration` — verification shows integration did not happen. See F18A1-013.
- The "2026-09-05 Master" historical archive that `AGENTS.md`/`00_JARVIS_START_HERE.md` designate as the fallback historical-truth source could not be located anywhere under `C:\Jarivs` (searched to depth 3). See F18A1-014.
- Explicitly verified as **NOT** stale/contradictory: no doc treats the pre-`54b67ba` Phase 17 HOLD as current (only as a historical "base commit" pointer inside docs rewritten at `54b67ba`); `docs/phase17/PHASE17_ACCEPTANCE.md` explicitly states Phase 18/19 physical work was not started; `docs/phase17/HOME_ASSISTANT_ADAPTER.md` and `docs/audits/MEGA_PHASE_17_REVIEW.md` both describe HA/MQTT/VENOM as `NOT_CONFIGURED`/truthfully-reporting, never as "live."
- `docs/architecture/*` (58 files) sampled without contradiction against current code.

## 11. P0/P1/P2/P3 finding register

No P0 findings.

```text
Finding ID: F18A1-001
Existing Gap ID: NEW (touches identity/device authority integrity, no prior gap names it)
Priority: P1
Category: security
Evidence: src/jarvis/devices/fabric.py:412-416 (DeviceFabricService.revoke — upsert_device_fabric() succeeds and sets status=REVOKED, then `try: self.repository.revoke_device(device_id, now) except Exception: pass`, then unconditionally emits "device.revoked"/"device.offline" audit+events); src/jarvis/persistence/repositories.py:201-210 (revoke_device is the only call that sets `credentials.revoked_at`); src/jarvis/authority/identity/service.py:160 (authenticate() gates solely on `stored["revoked_at"] is not None`)
Actual behavior: If repository.revoke_device() raises for any reason (DB error, lock contention — see F18A1-005, which shows no busy_timeout/retry exists), the exception is silently discarded. device_fabric.status is already REVOKED and the method reports success via audit/event regardless, but credentials.revoked_at — the column IdentityService.authenticate actually checks — is never set.
Expected behavior: A device reported as revoked through the canonical DeviceFabricService authority should be unable to authenticate. Per AGENTS.md's fail-closed rule, a failure to complete a security-critical action should not be swallowed and reported as success.
Risk: A device whose revocation silently partially failed continues to be able to authenticate and act with owner authority, while the audit trail and Command Center falsely show it revoked.
Canonical owner/service: DeviceFabricService (identity/device authority per AGENTS.md §3)
Locked decision affected: no direct DEC-ID, but undermines the identity/device authority invariant in AGENTS.md §6 ("fail closed on ambiguous identity")
Recommended disposition: FIX_NEXT
Tests required: a test that makes repository.revoke_device() raise and asserts DeviceFabricService.revoke() either propagates the failure (does not report "device.revoked") or the device_fabric status update is rolled back to match
Physical proof required: no
Manual owner action required: no
```

```text
Finding ID: F18A1-002
Existing Gap ID: GAP-0302 (Verifier role must be independent from "action returned success")
Priority: P1
Category: correctness
Evidence: src/jarvis/devices/home/service.py (HomeAssistantTransport.execute): `verified = 200 <= status < 300`
Actual behavior: A Home Assistant write action's `verified` flag is set purely because the outbound HTTP POST returned 2xx. No follow-up read of `/api/states` (which the same class already implements via list_entities) confirms the entity actually reached the requested state.
Expected behavior: Per AGENTS.md §5 ("Never report success from...a returned HTTP 200...alone") and DEC-013, verification must reflect real target state.
Risk: JARVIS can truthfully claim a device changed state when Home Assistant accepted the request but the physical device failed, was offline, or ignored it. (Currently unreachable in the default bootstrap, which wires transport=None — see §7 — so this is a live code defect, not a live production incident.)
Canonical owner/service: HomeActionService / HomeAssistantTransport
Locked decision affected: yes — DEC-013
Recommended disposition: FIX_NEXT
Tests required: a test asserting `verified` derives from a post-action state read-back, not HTTP status; a test for HA returning 200 with no actual state change
Physical proof required: yes, for final physical acceptance; the code-level fix itself does not require live hardware
Manual owner action required: no
```

```text
Finding ID: F18A1-003
Existing Gap ID: NEW
Priority: P1
Category: correctness
Evidence: src/jarvis/agents/runtime/runtime.py:_bounded_tool_message (signature and all call sites pass only `tool_result.output`/`error_code`, never `tool_result.verified`); src/jarvis/tools/service.py (ToolCallResult carries `verified` only into the audit record and event payload); src/jarvis/tools/registry.py (register_computer_tools.execute_action keeps `verified` as a sibling field of the result dict, never merged into the model-visible output)
Actual behavior: When a tool/computer action completes with verified=False (e.g. type_text, volume changes), the model that generates the next assistant turn has no way to know the action was unverified, and will describe it with the same confidence as a fully-verified action. The true value is preserved for audit/events/API but is invisible exactly where the user-facing sentence is produced.
Expected behavior: Per AGENTS.md §5 and Core Source of Truth §18 item 9, the model-facing tool result should carry a machine-readable unverified indicator so JARVIS's own answer can hedge rather than assert.
Risk: This is the most direct, currently-live gap between the documented closed-loop VERIFY invariant and what the owner actually reads/hears — and it matters specifically for Computer Use V2, whose entire design (Core Source of Truth §6) depends on verified-vs-unverified action feedback.
Canonical owner/service: AgentRuntime / ToolExecutionService
Locked decision affected: no DEC-ID directly, but undercuts enforceability of AGENTS.md §5 in practice
Recommended disposition: FIX_NEXT
Tests required: a test asserting that when a tool result has verified=False, the bounded tool message contains a machine-readable unverified indicator
Physical proof required: no
Manual owner action required: no
```

```text
Finding ID: F18A1-004
Existing Gap ID: NEW (related: GAP-0505, GAP-0803)
Priority: P2
Category: reliability
Evidence: src/jarvis/notifications/service.py (NotificationService holds Notification objects only in an in-process dict); persistence schema contains only a `notification_delivery_attempts` table, no `notifications` table; tests/test_phase_sixteen_proactivity_automation.py's own restart test comments that it uses a "fresh in-memory notification store" — proactive-sourced notifications only appear to survive restart because they are re-derived from the separately-durable Finding record, not because NotificationService itself persists them
Actual behavior: Any notification not sourced from a durable Finding (e.g. one created directly by AutomationService's "notification" action) is permanently lost on any process restart with no trace and no truthful degraded signal.
Expected behavior: NotificationService is a canonical, product-owned authority per AGENTS.md §3; its state should be durable like its sibling authorities (Memory, World State, Missions, Approvals are all SQLite-backed).
Risk: An owner-facing alert can silently vanish on a crash/restart.
Canonical owner/service: NotificationService
Locked decision affected: no
Recommended disposition: ROADMAP
Tests required: a restart test creating a non-Finding-sourced notification and asserting it is retrievable (or an explicit documented-loss decision if durability is deliberately deferred)
Physical proof required: no
Manual owner action required: no
```

```text
Finding ID: F18A1-005
Existing Gap ID: GAP-0803 (explicitly names "DB lock/corruption scenarios")
Priority: P2
Category: reliability
Evidence: src/jarvis/persistence/db.py (sqlite3.connect with no timeout=/PRAGMA busy_timeout/WAL mode; Database.transaction() serializes only intra-process via a Python RLock); zero occurrences of sqlite3.OperationalError/DatabaseError handling anywhere in src/jarvis; zero test references to busy_timeout/"database is locked"
Actual behavior: Any cross-process lock contention (accidental double-launch, a concurrent backup job, an external tool opening the DB file) raises an unhandled exception rather than retrying/degrading gracefully.
Expected behavior: Per DEC-006 and GAP-0803, lock/contention should be exercised and handled.
Risk: A real but currently untested failure mode, surfacing as an opaque error at the API boundary.
Canonical owner/service: persistence/db.py:Database
Locked decision affected: no (hardening under an already-locked decision)
Recommended disposition: ROADMAP (already tracked; this audit narrows it to a concrete, currently-empty code/test surface)
Tests required: forced-lock-contention test asserting a typed degraded response
Physical proof required: no
Manual owner action required: no
```

```text
Finding ID: F18A1-006
Existing Gap ID: GAP-0303 (mission recovery/idempotency stress testing)
Priority: P2
Category: reliability
Evidence: src/jarvis/persistence/repositories.py:reconcile_missions (unconditionally fails every running/waiting/waiting_approval mission on every process start with error_code="process_restarted"); src/jarvis/bootstrap.py (calls it on every start, not only after an unclean shutdown)
Actual behavior: A mission that was merely WAITING_APPROVAL (owner had not yet decided; no side effect had occurred) is failed identically to a mission that crashed mid-consequential-step. The ApprovalRequest row created for that step is never cancelled — it remains `pending` indefinitely and could later be "decided" with no effect.
Expected behavior: A mission blocked purely on an owner decision, with no side effect yet taken, is a safe state across a clean restart and should not be treated identically to a genuinely interrupted step; at minimum the associated approval row should be explicitly closed in the same operation.
Risk: Low-to-moderate — no incorrect side effect occurs (conservative direction is correct per DEC-029), but legitimate pending approvals are silently discarded on every restart, and orphaned approval rows accumulate in the audit trail.
Canonical owner/service: MissionService / DurableApprovalEngine
Locked decision affected: touches DEC-029 (current behavior is conservative in the right direction, just imprecise)
Recommended disposition: ROADMAP
Tests required: a test asserting a reconciled WAITING_APPROVAL mission's approval row is also transitioned out of pending
Physical proof required: no
Manual owner action required: no
```

```text
Finding ID: F18A1-007
Existing Gap ID: NEW (related: GAP-0303)
Priority: P2
Category: reliability
Evidence: src/jarvis/computer/service.py (ComputerActionService.decide: `pending = self._pending.get(approval_id); if pending is None...: raise KeyError(approval_id)`); contrast src/jarvis/browser/service.py:decide (returns typed BrowserResult(failed, "browser_approval_unavailable")) and src/jarvis/devices/home/service.py:decide_approval (returns "pending_action_unavailable_after_restart", with dedicated tests)
Actual behavior: ComputerActionService keeps pending computer-action approvals in an in-memory dict that does not survive restart, and unlike Browser/Home, its decide() raises a bare untyped KeyError in that case (or on a second decide after the first already popped the entry), surfacing as an opaque HTTP 500 at the API boundary.
Expected behavior: Consistent with Home/Browser, decide() should return a typed failure (e.g. "pending_action_unavailable_after_restart") rather than an unhandled exception.
Risk: No silent success occurs, but the failure UX is worse than the equivalent, already-fixed Home/Browser paths.
Canonical owner/service: ComputerActionService
Locked decision affected: no
Recommended disposition: FIX_NEXT
Tests required: a restart-recovery test mirroring the existing Home pattern; a repeated-decide test asserting a typed failure, not KeyError
Physical proof required: no
Manual owner action required: no
```

```text
Finding ID: F18A1-008
Existing Gap ID: NEW (related: GAP-0303 — "duplicate-event...scenarios must be included in production hardening")
Priority: P2
Category: correctness
Evidence: src/jarvis/automation/service.py (cooldown check compares `datetime.now(UTC) - rule.last_run_at` against `cooldown_seconds` before the DB write that updates `last_run_at` later in `_run()`; `cooldown_seconds=0` is an accepted configuration)
Actual behavior: Two near-simultaneous events for the same rule can both read the same `last_run_at` and pass the cooldown check before either write persists, causing duplicate mission creation or duplicate notifications for one logical trigger.
Expected behavior: Per DEC-029 ("idempotency/exactly-once where side effects matter"), the automation trigger path should use an atomic per-event/per-rule claim, comparable to the CAS pattern already used elsewhere in the codebase (claim_paused_run, decide_with_claim).
Risk: Duplicate consequential side effects from what the owner perceives as one automation firing.
Canonical owner/service: AutomationService
Locked decision affected: yes — DEC-029
Recommended disposition: ROADMAP
Tests required: a concurrency test firing the same event twice near-simultaneously at a rule with a small/zero cooldown, asserting only one run/mission/notification results
Physical proof required: no
Manual owner action required: no
```

```text
Finding ID: F18A1-009
Existing Gap ID: NEW (related: GAP-0702)
Priority: P2
Category: reliability
Evidence: src/jarvis/devices/home/service.py (HomeAssistantTransport.execute and HomeActionService.execute's write branch have no try/except around the outbound HTTP call); contrast src/jarvis/home/service.py:HomeContextService.refresh (wraps the read call in try/except → truthful "_unavailable")
Actual behavior: A connection drop mid-write (URLError, timeout, connection refused) propagates as an unhandled exception rather than the typed HomeResult("failed", error_code="home_service_unavailable") pattern already used one call away in the same file.
Expected behavior: Write-path provider disconnects should degrade as truthfully as the read path.
Risk: A mid-action HA outage produces an opaque exception instead of the existing, already-implemented truthful failure code.
Canonical owner/service: HomeActionService / HomeAssistantTransport
Locked decision affected: no
Recommended disposition: FIX_NEXT
Tests required: a test making HomeAssistantTransport's HTTP call raise mid-write, asserting a typed failure rather than a propagated exception
Physical proof required: no
Manual owner action required: no
```

```text
Finding ID: F18A1-010
Existing Gap ID: GAP-0503
Priority: P2
Category: security
Evidence: src/jarvis/computer/service.py (_open_path, _inspect_file, _search_files resolve any absolute filesystem path with only exists/is-file/is-dir checks and a 1MB read cap); src/jarvis/authority/permissions/engine.py (unconditional ALLOW rules for computer.inspect_file/search_files/open_file/open_folder, no approval gate)
Actual behavior: These four actions can read/open any path reachable by the OS process user, auto-approved with no owner confirmation, no root confinement, and no sensitive-path denylist (e.g. SSH keys, browser profile/cookie stores, credential files).
Expected behavior: Per Core Source of Truth §16 and GAP-0503, file reads should be confined to explicit approved roots and exclude sensitive paths.
Risk: An LLM-directed tool call, auto-approved, could read arbitrary sensitive files on the host disk.
Canonical owner/service: ComputerActionService via PermissionEngine
Locked decision affected: no (implements the DEC-011/DEC-012 boundary correctly; the gap is in policy scope, not an authority bypass)
Recommended disposition: ROADMAP (already tracked under GAP-0503; this audit attaches concrete evidence)
Tests required: root-confinement + sensitive-path-denylist tests for all four actions
Physical proof required: no
Manual owner action required: no
```

```text
Finding ID: F18A1-011
Existing Gap ID: NEW
Priority: P3
Category: docs
Evidence: src/jarvis/tools/registry.py (ToolSpec risk_level="safe", requires_approval=False for computer.window.control/computer.keyboard.type/computer.clipboard.write) vs. src/jarvis/computer/service.py (ComputerActionService independently classifies these as risk="consequential" and requires approval — the actually-enforced, tested gate)
Actual behavior: The outer tool-schema layer labels these actions "safe" and pre-approved while the inner, authoritative service treats them as consequential. The system behaves correctly today only because the inner gate is authoritative (confirmed by tests) — this is a metadata inconsistency, not a bypass.
Expected behavior: ToolSpec.risk_level should reflect actually-enforced risk, or carry the same kind of clarifying comment already used for browser tools in authority/permissions/engine.py.
Risk: A future engineer trusting risk_level as ground truth could misjudge the effect of changing permission rules or tool metadata.
Canonical owner/service: tools/registry.py + computer/service.py
Locked decision affected: no
Recommended disposition: NO_ACTION (cosmetic; a comment fix, not a Phase 18A action item)
Tests required: none
Physical proof required: no
Manual owner action required: no
```

```text
Finding ID: F18A1-012
Existing Gap ID: NEW
Priority: P3
Category: reliability
Evidence: src/jarvis/browser/service.py:_fetch (`body = response.read(2_000_001); if len(body) > 2_000_000: raise ValueError("page_too_large")`); zero test references to page_too_large/2_000_000 in tests/
Actual behavior: A real, correct oversized-page bound exists and fails closed with a specific error code, but nothing in the suite exercises it.
Expected behavior: Every real bound/failure-mode path should have at least one regression test.
Risk: Low today, but silently regressable by a future refactor with nothing failing red.
Canonical owner/service: BrowserActionService / LocalBrowserController
Locked decision affected: no
Recommended disposition: FIX_NEXT (cheap, low-risk test to add)
Tests required: a test injecting a >2MB fetcher response and asserting a failed page_too_large result, not truncated/garbage success
Physical proof required: no
Manual owner action required: no
```

```text
Finding ID: F18A1-013
Existing Gap ID: GAP-0002 (should be reopened — currently marked RESOLVED_BY_SOURCE_PACK)
Priority: P2
Category: docs/config
Evidence: docs/source_of_truth/* and AGENTS.md exist only at C:\Jarivs\ (one level above this repo root, C:\Jarivs\00_final\jarvis\); confirmed absent by direct directory listing of this repo's docs/ tree
Actual behavior: This task's own mandatory read order names these files as repo-relative paths (e.g. `docs/source_of_truth/00_JARVIS_START_HERE.md`); they do not exist at that path inside the actual git repository. GAP-0002 already anticipated exactly this and marked itself resolved "verify after repo integration" — that verification now shows integration did not happen.
Expected behavior: The canonical bootstrap pack should be committed inside the JARVIS repository, per GAP-0002's own stated exit gate.
Risk: A future agent operating with a different working-directory assumption than this session's could fail the mandatory read order silently, or read a stale copy if one is later placed inside the repo without deprecating the outer one.
Canonical owner/service: repository documentation structure
Locked decision affected: no
Recommended disposition: FIX_NEXT (copy/commit the pack into the repo root, and decide which location is authoritative going forward)
Tests required: none (documentation-only)
Physical proof required: no
Manual owner action required: no — this is a repo-hygiene commit, not a credential/account gate
```

```text
Finding ID: F18A1-014
Existing Gap ID: NEW
Priority: P3
Category: docs
Evidence: no file matching "JARVIS_ULTRA_COMPLETE_MASTER_DEVELOPMENT_CONTEXT_2026-09-05" found anywhere under C:\Jarivs (searched to depth 3)
Actual behavior: AGENTS.md/00_JARVIS_START_HERE.md designate this file as the fallback historical-truth source, but it is not locatable in the current environment.
Expected behavior: A file named as a canonical fallback reference should be reachable, or the reference should be removed/updated if it was never checked in.
Risk: Low — this audit never needed to consult it, since no current-vs-historical conflict arose. Purely a dangling-reference hygiene issue.
Canonical owner/service: repository documentation structure
Locked decision affected: no
Recommended disposition: NO_ACTION / ROADMAP (owner should confirm whether the file exists elsewhere or the reference should be removed)
Tests required: none
Physical proof required: no
Manual owner action required: no
```

**Severity summary:** P0: 0 · P1: 3 (F18A1-001, 002, 003) · P2: 8 (F18A1-004 through 010, 013) · P3: 3 (F18A1-011, 012, 014)

## 12. False positives / NO_ACTION items

- **`ToolSpec.risk_level` vs. inner `ComputerActionService` gate mismatch** (F18A1-011) — looked like a possible permission bypass at first glance; confirmed the inner gate is authoritative and tested, so no bypass exists. Recorded as a P3 docs nit, not a security finding.
- **npm audit moderate advisories** (`@vitest/mocker`/`vitest`, GHSA-82fw-gwwq-j7x9) — dev-only test tooling, does not affect the documented high-severity production gate, which remains 0 vulnerabilities. NO_ACTION for this audit; worth a routine `npm update` pass in normal maintenance, not a Phase 18A item.
- **Broad `except Exception` at ~18 files** — sampled directly by this audit. All but one (`devices/fabric.py`, filed as F18A1-001) convert the exception into a typed failure result, a truthful degraded state, or an explicitly logged error code; several intentionally re-raise after cleanup (`desktop/lifecycle.py`). These are NOT findings — they are the correct implementation of "fail truthfully," not swallowed errors.
- **`research/service.py` per-source `except Exception: continue`** — skips one unreadable research source while continuing the batch; appropriate for a best-effort multi-source evidence gather, not a defect.
- **TODO/FIXME/HACK/TBD/XXX/NotImplementedError** — a direct repo-wide grep by this audit found **zero** matches anywhere in `src/`. This is a genuinely clean result, stated for balance rather than omitted.
- **`shell=True`/`os.system`** — zero matches anywhere in `src/`, confirmed directly.
- **`proactive/service.py` reaching into `self.notifications._items.values()`** — a private-attribute reach-through between two nominally separate services, noted by one trace pass. It is read-only introspection into the canonical service's own state (not a second writer, not a bypass), so it is not filed as a numbered finding — recommended as a minor P3 cleanup candidate if `NotificationService` gains a public listing method during the F18A1-004 fix.

## 13. Manual Dependency Register

```text
Manual Gate ID: MAN-001
Capability: Live email provider integration
Status: NEEDED_IN_LATER_WORKSTREAM
Why manual action is required: requires the owner's real email account + provider credential (OAuth/app password)
Expected workstream/phase: Phase 18 Workstream E
Credential/data/device type needed: email provider OAuth token or app-specific password
Secure destination expected by current architecture: encrypted/OS credential facility (opaque handle, never Memory) per Core Source of Truth §9
Can implementation continue before this is provided? yes — CommunicationsHub foundation and local in-memory channel already exist and are testable without it
Notes / exact repo evidence: no email/SMTP/IMAP code found anywhere under src/jarvis; GAP-0501 confirms
```

```text
Manual Gate ID: MAN-002
Capability: Calendar provider integration
Status: NOT_NEEDED_YET
Why manual action is required: no calendar capability exists yet; needs the owner's provider/account choice first (OPEN-004 in the decision log)
Expected workstream/phase: Phase 18 Workstream E
Credential/data/device type needed: calendar provider API credential (provider TBD)
Secure destination expected by current architecture: same opaque-credential-handle boundary as MAN-001
Can implementation continue before this is provided? yes
Notes / exact repo evidence: GAP-0502; confirmed by repo grep — no calendar code found
```

```text
Manual Gate ID: MAN-003
Capability: Physical VENOM deployment (authenticated SSH access)
Status: BLOCKING_CURRENT_WORK for Workstream G only (does not block Workstream A/Computer Use V2)
Why manual action is required: non-interactive SSH authentication to venom-server is currently unavailable
Expected workstream/phase: Phase 19 physical acceptance (code/provisioning path is Phase 17-complete)
Credential/data/device type needed: SSH key or credential for venom-server
Secure destination expected by current architecture: OS-level SSH credential store, not Memory/repo
Can implementation continue before this is provided? yes
Notes / exact repo evidence: docs/phase17/PHASE17_ACCEPTANCE.md — "venom-server at 192.162.1.33 ... non-interactive SSH authentication was unavailable"
```

```text
Manual Gate ID: MAN-004
Capability: Home Assistant live integration
Status: NOT_NEEDED_YET
Why manual action is required: requires a local HA instance + long-lived access token + entity allowlist decisions
Expected workstream/phase: Phase 18 Workstream G / Phase 19 physical acceptance
Credential/data/device type needed: Home Assistant long-lived access token
Secure destination expected by current architecture: opaque credential handle via the HomeActionService boundary
Can implementation continue before this is provided? yes — HomeActionService reports NOT_CONFIGURED truthfully without it. Note F18A1-002 should be fixed before this integration goes physically live.
Notes / exact repo evidence: GAP-0702; docs/phase17/HOME_ASSISTANT_ADAPTER.md describes truthful empty-state when unconfigured
```

```text
Manual Gate ID: MAN-005
Capability: MQTT broker / ESP32 physical nodes
Status: NOT_NEEDED_YET
Why manual action is required: requires a real broker, ACL/auth config, and physical ESP32 hardware provisioning
Expected workstream/phase: Phase 18 Workstream G / Phase 19 physical acceptance
Credential/data/device type needed: MQTT broker credentials + per-device ESP32 provisioning secrets
Secure destination expected by current architecture: same opaque-credential boundary; topic scheme already defined in docs/phase17/MQTT_ESP32_PROTOCOL.md
Can implementation continue before this is provided? yes
Notes / exact repo evidence: GAP-0703/GAP-0704; confirmed MQTT reports NOT_CONFIGURED without a publisher
```

```text
Manual Gate ID: MAN-006
Capability: Mahmoud's curated Personal Knowledge Vault data (profile/preferences/people/projects/history)
Status: NOT_NEEDED_YET
Why manual action is required: onboarding schema/workflow is explicitly PLANNED and waits on owner-supplied curated personal data (not a credential)
Expected workstream/phase: Phase 18 Workstream D
Credential/data/device type needed: owner-authored personal data
Secure destination expected by current architecture: canonical MemoryService with provenance/sensitivity/scope fields
Can implementation continue before this is provided? yes — Phase 16 Memory semantics already support it structurally
Notes / exact repo evidence: GAP-0401/GAP-0402; no "Personal Knowledge Vault" concept found anywhere in this repo's docs — confirms it is genuinely new/unbuilt
```

```text
Manual Gate ID: MAN-007
Capability: Full physical voice acceptance (Egyptian Arabic TTS quality, wake reliability, barge-in, Bluetooth duplex)
Status: NOT_NEEDED_YET for Workstream A; relevant to Phase 19
Why manual action is required: requires physical microphone/speaker hardware and human judgment of TTS/STT quality (physical/human evidence per DEC-013, not a secret)
Expected workstream/phase: Phase 19
Credential/data/device type needed: none — hardware + human acceptance
Secure destination expected by current architecture: n/a
Can implementation continue before this is provided? yes
Notes / exact repo evidence: docs/deferred/PHASE13_PHYSICAL_ACCEPTANCE_BACKLOG.md; GAP-0601/GAP-0602
```

## 14. Proposed Gap Register updates (proposal only — canonical Gap Register not edited)

- **Reopen GAP-0002** ("No permanent agent bootstrap contract at repo root") — currently marked `RESOLVED_BY_SOURCE_PACK, verify after repo integration`. This audit's verification shows the pack is not integrated into the repository. Propose status `OPEN` until `AGENTS.md`/`docs/source_of_truth/*` are actually committed inside `C:\Jarivs\00_final\jarvis\`.
- **New gap** for F18A1-001 (device revocation credential-swallow) — propose `GAP-0002B` or next available P1 ID under a new "Identity/Device integrity" section.
- **New gap** for F18A1-003 (verified flag dropped before model) — propose linking under GAP-0302 as a named sub-item, since it is the concrete mechanism behind "verifier role must be independent from returned success."
- **Attach evidence** from F18A1-002, F18A1-010 to the existing GAP-0302 and GAP-0503 respectively (no new Gap ID needed, evidence only).
- **New gap** for F18A1-004 (NotificationService non-durability) — propose under the P1/P2 "Production hardening and governance" section alongside GAP-0803.
- **New gaps** for F18A1-006, 007, 008, 009 — propose grouping under GAP-0303 ("Long-running mission recovery/idempotency needs Phase 18 stress testing") as named sub-items, since all four are restart/race/exception-handling gaps in that same family.

## 15. Recommended stabilization order

1. **F18A1-013** — commit the source-of-truth pack into the repo (cheap, unblocks future zero-context agents from silently failing the mandatory read order).
2. **F18A1-003** — restore the `verified` signal into the model-facing tool message. This is a precondition for Computer Use V2's own closed-loop design, not just a general hygiene fix.
3. **F18A1-001** — fix the swallowed device-revocation exception (small, localized, security-relevant).
4. **F18A1-002, F18A1-009** — fix Home Assistant write-path verification and exception handling together (same file, same class).
5. **F18A1-007** — align `ComputerActionService.decide()`'s failure typing with Browser/Home (small, mechanical).
6. **F18A1-004, F18A1-005, F18A1-006, F18A1-008** — schedule as Phase 18 Workstream H (Production Hardening) stress-testing items; none blocks Workstream A directly.
7. **F18A1-010** — fold into Workstream A or E file/system hardening work (already tracked as GAP-0503).
8. **F18A1-011, F18A1-012, F18A1-014** — low-cost cleanup, any time.

## 16. Final gate verdict

**`AUDIT_GATE_PASS_WITH_ROADMAP_GAPS`**

> `MAY_WORKSTREAM_A_COMPUTER_USE_V2_START: YES_AFTER_P1_FIXES`

Rationale: the baseline is green, reproducible, and the single-authority architecture holds under direct tracing — no P0, and no bypass was found that grants unauthorized access, exposes secrets, or corrupts durable authority. However, **F18A1-003** (the `verified` flag being dropped before it reaches the model/user) sits directly on the mechanism Computer Use V2 is designed to depend on (Core Source of Truth §6: "verify foreground/window/control/state after actions" as evidence the owner can actually see reflected in JARVIS's answers). Recommend closing F18A1-003 (and ideally F18A1-001, as general authority-integrity hygiene) before or in the earliest slice of Workstream A, rather than building a larger verification-dependent feature on top of a verification signal that currently doesn't reach the surface it's meant to inform. The remaining P2/P3 findings are legitimate roadmap items and do not block Workstream A.

---

*Audit method note: this report synthesizes five parallel evidence-gathering passes (baseline/tests; security/data-retention; capability matrix + end-to-end traces, run twice independently for cross-checking; edge cases + documentation + manual dependencies) plus direct supplementary greps performed after one debt-scan pass failed on an account-level rate limit before completing. No repository file other than this report was created or modified.*
