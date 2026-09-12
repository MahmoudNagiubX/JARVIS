# PHASE 18A.2 — TARGETED STABILIZATION FIXES

**Task:** `tasks/CLOUD_CODE_TASK_PHASE_18A2_STABILIZATION_FIXES.md`
**Mode:** Controlled stabilization / targeted fixes only — no Computer Use V2, no architecture change.
**Date:** 2026-09-12
**Prior audit:** `docs/audits/PHASE_18A1_BASELINE_AUDIT.md` (verdict `AUDIT_GATE_PASS_WITH_ROADMAP_GAPS`)

---

## 1. Exact starting HEAD

```text
Branch: main
HEAD:   54b67ba396ec45180f1b60ea472ef94c9ac181a9  ("fix: close phase 17 real network readiness")
```

Confirmed via `git rev-parse --show-toplevel` (`C:\Jarivs\00_final\jarvis`), `git status --short`, `git branch --show-current`, `git rev-parse HEAD` before any edit. Worktree was not perfectly clean: two untracked task files (`tasks/CLOUD_CODE_TASK_PHASE_18A1_BASELINE_AUDIT.md`, `tasks/CLOUD_CODE_TASK_PHASE_18A2_STABILIZATION_FIXES.md`) and one untracked report (`docs/audits/PHASE_18A1_BASELINE_AUDIT.md`) from the prior audit-only session — all expected and unrelated to any tracked file, so implementation proceeded per the task's explicit allowance ("Phase 18A.1 was intentionally audit-only").

## 2. Bootstrap anomaly — resolved first (F18A1-013 / GAP-0002)

Verified the repo-local `AGENTS.md` and `docs/source_of_truth/*` were missing (confirmed absent via directory listing). Copied the canonical pack **unchanged** from the parent-directory bootstrap source (`C:\Jarivs\AGENTS.md`, `C:\Jarivs\docs\source_of_truth\*`) into the actual git repository:

- `AGENTS.md`
- `docs/source_of_truth/00_JARVIS_START_HERE.md`
- `docs/source_of_truth/01_JARVIS_CORE_SOURCE_OF_TRUTH.md`
- `docs/source_of_truth/02_JARVIS_CURRENT_STATE.md`
- `docs/source_of_truth/03_JARVIS_GAP_REGISTER.md`
- `docs/source_of_truth/04_JARVIS_EXECUTION_ROADMAP.md`
- `docs/source_of_truth/05_JARVIS_DECISION_LOG.md`
- `docs/source_of_truth/06_ACTIVE_WORK_PACKET_PHASE_18A.md`

No second source-of-truth hierarchy was created; the parent-directory originals at `C:\Jarivs\` were left untouched. From this point the repo-local copies were read (mandatory order 1–8) and treated as authoritative for the rest of this task.

## 3. Exact ending worktree state

```text
Branch: main
HEAD:   54b67ba396ec45180f1b60ea472ef94c9ac181a9  (unchanged — no commit made)
```

```text
 M src/jarvis/agents/runtime/runtime.py
 M src/jarvis/computer/service.py
 M src/jarvis/devices/fabric.py
 M src/jarvis/devices/home/service.py
 M src/jarvis/tools/service.py
?? AGENTS.md
?? docs/audits/PHASE_18A1_BASELINE_AUDIT.md
?? docs/audits/PHASE_18A2_STABILIZATION.md
?? docs/source_of_truth/
?? tasks/CLOUD_CODE_TASK_PHASE_18A1_BASELINE_AUDIT.md
?? tasks/CLOUD_CODE_TASK_PHASE_18A2_STABILIZATION_FIXES.md
?? tests/test_phase_eighteen_stabilization.py
```

No commit, merge, push, branch creation/deletion, or history rewrite was performed. This is a reviewed diff left for owner approval, per Section 13 of the task file.

## 4. Files changed

| File | Change | Why |
|---|---|---|
| `AGENTS.md` (new, repo root) | copied unchanged | F18A1-013/GAP-0002 bootstrap |
| `docs/source_of_truth/*.md` (7 files, new) | copied unchanged | F18A1-013/GAP-0002 bootstrap |
| `src/jarvis/tools/service.py` | +15/-3 | F18A1-003 — add `verified` to `ToolCallResult`, propagate from handler results |
| `src/jarvis/agents/runtime/runtime.py` | +26/-15 | F18A1-003 — merge `verified` into `_bounded_tool_message`, both call sites |
| `src/jarvis/devices/fabric.py` | +8/-4 | F18A1-001 — reorder + stop swallowing credential-revocation failure |
| `src/jarvis/devices/home/service.py` | +43/-2 | F18A1-002 — independent state read-back; F18A1-009 — typed exception handling |
| `src/jarvis/computer/service.py` | +5/-1 | F18A1-007 — typed failure instead of raw `KeyError` |
| `tests/test_phase_eighteen_stabilization.py` (new) | +342 lines, 15 tests | regression coverage for all 6 code-level findings, including F18A1-012 |
| `docs/source_of_truth/03_JARVIS_GAP_REGISTER.md` | edited | Section 11.1 required updates |
| `docs/source_of_truth/02_JARVIS_CURRENT_STATE.md` | edited | Section 11.2 required updates |
| `docs/source_of_truth/04_JARVIS_EXECUTION_ROADMAP.md` | edited | Section 11.3 required updates |
| `docs/source_of_truth/05_JARVIS_DECISION_LOG.md` | **not touched** | no new architecture/product decision was made; all fixes implement already-locked decisions (DEC-012, DEC-013) |

Total production-code diff: **5 files, 77 insertions, 20 deletions** (`git diff --stat -- src/`). No file outside the seven approved-finding areas was touched.

## 5. Approved findings — root cause, fix, tests, status

### F18A1-013 — source-of-truth pack not inside repo
- **Root cause:** the canonical bootstrap pack was generated/placed at `C:\Jarivs\` (one directory above the actual git repository root, `C:\Jarivs\00_final\jarvis\`), so any agent following repo-relative mandatory-read-order paths would fail to find it.
- **Fix:** copied the pack unchanged into the repository (Section 2 above).
- **Tests:** none applicable (documentation-only); verified by directory listing before/after.
- **Status:** `RESOLVED`.

### F18A1-003 — `verified` signal dropped before the model-facing tool result
- **Root cause:** `ToolCallResult` (the value returned by `ToolExecutionService`) had no `verified` field at all — `_run_handler`'s successful-completion branch discarded `result.verified` (the domain `ToolResult`'s own field) after using it only for the audit record and event payload. `AgentRuntime._bounded_tool_message`, which builds the actual message the model sees, therefore had no verification signal to include even if it wanted to.
- **Fix:**
  - Added `verified: bool | None = None` to `ToolCallResult` (`src/jarvis/tools/service.py`). `None` means "not applicable" (denied/approval-required — no execution was attempted); `True`/`False` propagate the handler's own evidence for completed executions and for failures that followed an attempted action (e.g. `keyboard_target_changed`). Updated the three call sites that construct a post-execution `ToolCallResult` (`_run_handler`'s success and not-succeeded branches, `_finish_delegated`).
  - Updated `AgentRuntime._bounded_tool_message` (`src/jarvis/agents/runtime/runtime.py`) to accept an optional `verified` parameter and merge it into the serialized tool message — as a sibling key for dict outputs, or wrapped as `{"result": ..., "verified": ...}` for non-dict outputs — including inside the truncation fallback path, so the signal survives even when content is cut down. The two call sites in `resume()` and `_execute()` now pass `tool_result.verified`.
  - Backward compatible: calling `_bounded_tool_message(output, error_code)` with no `verified` argument (as the one pre-existing test does) is byte-identical to before this change.
- **Tests:** `tests/test_phase_eighteen_stabilization.py::test_verified_true_reaches_model_visible_tool_result`, `::test_verified_false_reaches_model_visible_tool_result`, `::test_bounded_tool_message_error_handling_and_backward_compatibility_are_preserved`, `::test_ephemeral_argument_and_output_redaction_is_unaffected_by_verified_propagation` (4 tests). The last test proves a secret ephemeral argument still never reaches durable `tool_calls.arguments_json`/`output_json` (still redacted to digest+keys), even though the live model-facing message legitimately still carries that turn's raw output plus the new `verified` field, exactly matching pre-existing ephemeral semantics.
- **Status:** `RESOLVED`.

### F18A1-001 — device revocation could swallow credential-revocation failure
- **Root cause:** `DeviceFabricService.revoke()` called `repository.upsert_device_fabric(updated)` (marking `device_fabric.status = REVOKED`) **before** `repository.revoke_device(...)` (which sets `credentials.revoked_at`, the column `IdentityService.authenticate()` actually checks), and wrapped the latter in `try: ... except Exception: pass`. A failure in the credential-revocation step was silently discarded while the method still recorded a `device.revoked` audit record and emitted `device.revoked`/`device.offline` events — a false-success pattern on a security-critical control.
- **Fix:** reordered so `repository.revoke_device(...)` runs **first**; its exception (if any) is no longer caught — it propagates, so `upsert_device_fabric` and the audit/event calls are never reached on failure (fail closed, matches `AGENTS.md` §6). No second revocation authority was introduced; the single `DeviceFabricService.revoke()` entry point is unchanged in shape.
- **Tests:** `tests/test_phase_eighteen_stabilization.py::test_device_revocation_propagates_credential_failure_and_reports_no_false_success` (forces `repository.revoke_device` to raise via a real enrolled device from `DeviceFabricService.enroll_device`, asserts the raise propagates, `device_fabric.status` stays non-revoked, and no `device.revoked` audit/event row exists; then proves the happy path still works once the failure is removed) and `::test_device_revocation_happy_path_still_succeeds` (confirms idempotent double-revoke is unaffected).
- **Status:** `RESOLVED`.

### F18A1-002 — Home Assistant verification was HTTP-status-only
- **Root cause:** `HomeAssistantTransport.execute()` set `verified = 200 <= status < 300` directly from the outbound POST's HTTP status, with no confirmation that the entity actually reached the intended state — a direct instance of the pattern `AGENTS.md` §5 forbids ("never report success from... a returned HTTP 200... alone").
- **Fix:** after a successful (2xx) POST, `execute()` now calls a new `_verify_state()` helper that performs exactly one bounded `GET /api/states/{entity_id}` read-back (no retry loop, no polling) and compares the returned `state`/`attributes` against the intended effect:
  - `turn_on`/`turn_off` → compare `state`.
  - `set_brightness`/`set_temperature` → compare the relevant attribute against the value sent.
  - `set_color`/`trigger_scene` → no deterministic, generically comparable state exists on the standard entity endpoint, so these are always reported `verified=False` rather than guessed — an honest "unverifiable" result, not an invented one.
  - Any read-back failure (non-2xx, network error, malformed body, non-dict payload) also yields `verified=False`, never `True`.
  - `status` stays `"succeeded"` when the POST was accepted (matching the existing codebase convention, e.g. `computer/service.py`'s audio-adjust path, of "succeeded but unverified" rather than reclassifying an accepted action as a hard failure); only the POST itself failing or raising produces `status="failed"`.
- **Tests:** `tests/test_phase_eighteen_stabilization.py::test_home_assistant_reports_verified_only_after_matching_independent_readback`, `::test_home_assistant_does_not_claim_verified_when_state_does_not_change`, `::test_home_assistant_does_not_claim_verified_when_readback_unavailable`, `::test_home_assistant_unverifiable_action_is_reported_truthfully` — the exact four scenarios the task specification required.
- **Status:** `RESOLVED`. Attached to `GAP-0302` (verifier independence) in the Gap Register as the Home Assistant instance closed; the general cross-domain verifier contract remains open (unchanged, out of scope here).

### F18A1-009 — Home write-path provider exceptions were not converted to typed failures
- **Root cause:** `HomeAssistantTransport.execute()` had no exception handling around `asyncio.to_thread(self._call, "POST", ...)`. `_call()`'s own `except urllib.error.HTTPError` only covers HTTP-level error responses (4xx/5xx), not connection-level failures (`URLError`, `OSError`, `TimeoutError` from a refused connection, DNS failure, or socket timeout) — those propagated uncaught out of the canonical Home action path, asymmetric with the read path (`HomeContextService.refresh`), which already degrades truthfully.
- **Fix:** wrapped the outbound POST call (and the new read-back call added for F18A1-002) in `try/except (urllib.error.URLError, OSError, TimeoutError)`, returning a typed `HomeResult("failed", {...}, f"home_assistant_unreachable:{exc.__class__.__name__}", False)` — no success is ever returned on this path, and the specific exception class is preserved in the error code for debugging without exposing any secret/token.
- **Tests:** `tests/test_phase_eighteen_stabilization.py::test_home_assistant_write_provider_exception_degrades_truthfully_at_transport_level` (transport-level, direct `OSError`) and `::test_home_action_service_boundary_never_leaks_uncaught_provider_exception` (full `HomeActionService.execute()` path with real permission/audit/approval services from the runtime and a registered `HomeEntityMapping`, proving the exception never escapes the canonical service boundary).
- **Status:** `RESOLVED`.

### F18A1-007 — `ComputerActionService.decide()` could raise raw `KeyError`
- **Root cause:** a missing or already-consumed entry in the in-memory `_pending` dict (restart, or a second `decide()` call after the first already popped it) raised a bare `KeyError(approval_id)`, which is only caught by the *generic* `except KeyError` blocks in `api/http.py`/`api/node_http.py` (shared with many unrelated routes) and otherwise surfaces as an opaque HTTP 500 — unlike the equivalent Browser (`browser_approval_unavailable`) and Home (`pending_action_unavailable_after_restart`) approval paths, which already return typed failures.
- **Fix:** the `pending is None or self.approvals is None` branch now returns `ComputerResult("failed", error_code="pending_action_unavailable_after_restart", verified=False, approval_id=approval_id)` — reusing the exact error-code convention already established by `HomeActionService.decide_approval`, per the task's explicit preference. No second approval engine was introduced. Every downstream caller (`bootstrap.py::resume_delegated_approval`, `api/core.py::decide_computer_action`) already handled a normal `ComputerResult` return value (via `asdict(...)`), so this is a strict improvement (200 OK with a truthful failed body, consistent with Browser/Home) rather than a new failure mode.
- **Tests:** `tests/test_phase_eighteen_stabilization.py::test_computer_decide_returns_typed_failure_for_missing_pending_approval` (approval ID that never existed) and `::test_computer_decide_returns_typed_failure_on_repeated_decide_after_consumed` (a real pending approval, decided once — consuming it — then decided again). Both assert a typed `"failed"` result with `verified=False` and the canonical error code, and that no action is executed. Confirmed the two existing tests that exercise `decide()` on a real/expired pending entry (`test_phase_four_integration.py`, `test_phase_eleven_final_remediation.py`) still pass unchanged.
- **Status:** `RESOLVED`.

### F18A1-012 — missing regression test for the real 2 MB browser page-size cap
- **Root cause:** the production 2,000,000-byte cap in `LocalBrowserController._fetch()` (`src/jarvis/browser/service.py`) is only reachable through the real `urllib.request.build_opener(...).open(...)` branch; every existing browser test uses the injectable-`fetcher` constructor argument, which bypasses that branch entirely (and therefore the cap) by design. No test exercised the real cap-enforcing code.
- **Fix:** test-only change, as required. No production behavior was altered (verified no failing test existed beforehand — the cap logic itself was already correct on inspection). Added a test that mocks `urllib.request.build_opener` to return a fake opener whose response streams an oversized body through the exact same `response.read(2_000_001)` / `len(body) > 2_000_000` check, and passes a permissive stub `url_policy` (avoiding real DNS resolution, keeping the test fast/offline/deterministic) so only the byte-cap logic is under test.
- **Tests:** `tests/test_phase_eighteen_stabilization.py::test_browser_fetch_enforces_two_megabyte_cap_on_the_real_production_path` — asserts `ValueError("page_too_large")` is raised, proving no silent truncation, no success-with-garbage, and no unbounded read.
- **Status:** `RESOLVED` (regression coverage added; existing behavior confirmed correct, unchanged).

## 6. Deferred findings — explicitly not touched in this task

Per Section 5 of the task file, these remain open roadmap items; no code for them was inspected for modification beyond what was already read during Phase 18A.1:

| Finding | Status | Notes |
|---|---|---|
| F18A1-004 | `OPEN` (roadmap) | NotificationService durability |
| F18A1-005 | `OPEN` (roadmap, = GAP-0803) | SQLite lock/contention hardening |
| F18A1-006 | `OPEN` (roadmap, = GAP-0303) | mission restart/approval reconciliation redesign |
| F18A1-008 | `OPEN` (roadmap) | atomic automation trigger claim |
| F18A1-010 | `OPEN` (roadmap, = GAP-0503) | general file-root confinement / sensitive-path policy — explicitly **not** touched; no file/system access was expanded or narrowed in this task |
| F18A1-011 | `OPEN` (`NO_ACTION`/docs cleanup candidate) | outer `ToolSpec` risk metadata cleanup |
| F18A1-014 | `OPEN` (docs) | historical Master archive location unresolved |

## 7. Verification — commands and results

All commands run from `C:\Jarivs\00_final\jarvis` (frontend commands from `ui/`) using the same system Python (3.14.6, with `PYTHONPATH=src`) and Node (v24.19.0) / npm (11.17.0) environment as the Phase 18A.1 audit.

| Command | Result | Notes |
|---|---|---|
| `python -m pytest tests/test_phase_eighteen_stabilization.py -v` | **PASS** — 15 passed | focused new-fix regression suite, run first in isolation |
| `python -m pytest tests -q` | **PASS** — 530 passed, 0 skipped, 36 subtests | full suite; 515 pre-existing (18A.1 baseline run) + 15 new. The one previously-justified skip (`test_focus_window_revalidates_ephemeral_reference`) again did not trigger — same environment-dependent condition documented in 18A.1, not a regression. |
| `python -m pytest tests -k "phase_two or phase_four or phase_eleven or phase_fifteen or phase_seventeen" -q` | **PASS** — 182 passed, 348 deselected, 11 subtests | focused regression across every domain touched by this task (tool execution, computer actions, device fabric, browser, home/MQTT/ESP32) |
| `python -m compileall src tests -q` | **PASS** — exit 0 | |
| `git diff --check` | **PASS** — exit 0 | no whitespace errors |
| `npm test` (in `ui/`) | **PASS** — 75 passed, 14 files | unchanged from 18A.1 baseline (frontend was not touched) |
| `npm run build` (in `ui/`) | **PASS** — 68 modules transformed, clean | unchanged |
| `npm audit --audit-level=high` (in `ui/`) | **PASS** — exit 0, 0 high/critical | 2 pre-existing *moderate* dev-only advisories (`@vitest/mocker`/`vitest`, GHSA-82fw-gwwq-j7x9) noted in 18A.1, unrelated to this task, untouched |

No stop condition (task Section 14) was encountered: no locked decision required redesign, no second authority was needed for any fix, no fix required a real credential/secret, no unrelated tracked file was unsafe to edit, no test exposed a broader architectural defect outside the approved scope, and the source-of-truth copies were identical (byte-for-byte copy), not divergent.

## 8. Manual gates

**None.** No owner API key, OAuth credential, SSH credential, Home Assistant token, MQTT credential, or personal data was requested, required, or fabricated. All Home Assistant test coverage uses the existing `HomeAssistantTransport(request=<injected callable>)` seam with fully synthetic, offline, deterministic responses — no live provider, no network egress, no secret of any kind.

## 9. Architecture/security regression check

Explicitly verified against the diff (`git diff -- src/`), per task Section 10:

| Check | Result |
|---|---|
| Zero `shell=True` added | **confirmed** — `git diff -- src/ \| grep "shell=True"` returns nothing |
| Zero `os.system` added | **confirmed** — same check, no `os.system(` occurrences |
| No raw secret persistence introduced | **confirmed** — the one new persistence-adjacent test (`test_ephemeral_argument_and_output_redaction_is_unaffected_by_verified_propagation`) proves redaction is unchanged; no fix touches secret/credential storage |
| No new permission/approval bypass | **confirmed** — F18A1-001/007/009 all make failure handling *stricter* (fail closed instead of silently succeeding or crashing); F18A1-002 makes verification *stricter* (requires independent evidence instead of trusting HTTP status); F18A1-003 only adds a read-side field, no control-flow change to any permission/approval/audit call |
| No UI/backend direct side-effect bypass | **confirmed** — no UI code was touched; all fixes are inside canonical services (`ToolExecutionService`, `AgentRuntime`, `DeviceFabricService`, `HomeAssistantTransport`/`HomeActionService`, `ComputerActionService`) |
| No new duplicate authority | **confirmed** — no new class/service/registry was created; `DeviceFabricService.revoke()` remains the single device-revocation entry point, `ComputerActionService.decide()`/`HomeAssistantTransport.execute()` remain the single respective canonical paths |
| No false `verified=True` path introduced | **confirmed** — every change in this task either removes a false-`verified=True` path (F18A1-002) or propagates an already-computed truthful value further (F18A1-003); no new code path sets `verified=True` without underlying evidence |
| No unbounded retry/poll loop | **confirmed** — `_verify_state()` makes exactly one bounded GET call, no loop, no retry, reusing the same 5-second timeout as every other `_call()` use |
| No hidden broad exception swallow on security-critical paths | **confirmed** — F18A1-001 *removes* the one broad swallow found in this task's scope (`devices/fabric.py`'s bare `except Exception: pass`); the two new `except` blocks added (F18A1-002/009) are narrowly scoped to `(urllib.error.URLError, OSError, TimeoutError)` and always return a typed failure, never a success |
| No arbitrary architecture expansion | **confirmed** — diff is 5 production files, 77 insertions / 20 deletions; no new package, no new top-level service, no dependency change |

## 10. Final recommendation for Computer Use V2

All seven approved findings are fixed and tested; no P0 exists; the full baseline (Python + frontend) is green; canonical docs are updated. Workstream A — Computer Use V2 — **may start**, with one explicit carry-forward restriction already noted in the 18A.1 audit and unaffected by this task: **F18A1-010/GAP-0503** (unconfined `computer.inspect_file`/`search_files`/`open_file`/`open_folder` access, auto-approved with no root confinement or sensitive-path denylist) remains open and was explicitly out of scope for 18A.2 per the task's "do not expand file/system access during this task" constraint. Computer Use V2 must not widen file/system access before that gap is addressed in its own designated workstream slice.

---

`STABILIZATION_PASS`

```text
Starting HEAD: 54b67ba396ec45180f1b60ea472ef94c9ac181a9
Ending HEAD: 54b67ba396ec45180f1b60ea472ef94c9ac181a9 (unchanged; no commit made)
Files changed: 5 production files (src/jarvis/tools/service.py, src/jarvis/agents/runtime/runtime.py, src/jarvis/devices/fabric.py, src/jarvis/devices/home/service.py, src/jarvis/computer/service.py) + 1 new test file (tests/test_phase_eighteen_stabilization.py, 15 tests) + repo-local source-of-truth pack (8 files, new) + 3 canonical docs updated (02/03/04) + this report
Focused tests: 15/15 passed (new stabilization suite); 182/182 passed, 11 subtests (cross-domain regression: phase_two/four/eleven/fifteen/seventeen)
Full Python: 530 passed, 0 skipped, 36 subtests
Frontend: Vitest 75 passed; build clean; npm audit --audit-level=high 0 high/critical
Security checks: all 10 checks in Section 9 confirmed clean
Findings closed: F18A1-013, F18A1-003, F18A1-001, F18A1-002, F18A1-009, F18A1-007, F18A1-012 (7/7 approved)
Findings deferred: F18A1-004, F18A1-005, F18A1-006, F18A1-008, F18A1-010, F18A1-011, F18A1-014 (unchanged, roadmap)
Manual owner action required now: none
May Computer Use V2 start: YES_WITH_EXPLICIT_RESTRICTIONS
Report: docs/audits/PHASE_18A2_STABILIZATION.md
```
