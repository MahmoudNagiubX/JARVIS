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
**Status:** `RESOLVED` (core semantic capability defined by this gap — see Batch 03 Milestone 2 note below; general Computer Use V2 breadth is not fully complete, see GAP-0102/0104/0105/0106)  
Current grounded control is intentionally narrow. Add product-owned UIA inspection/target/action contracts behind `ComputerActionService`.  
**Backend-selection subproblem:** `RESOLVED` — the A1 evaluation (`docs/audits/PHASE_18_WORKSTREAM_A1_UIA_BACKEND_EVALUATION.md`) is complete and DEC-046 locks the production backend (in-process `uiautomation`/`comtypes` adapter; `winapp ui` optional dev/eval tool only). Semantic UIA implementation work is now active under Phase 18 Workstream A, Batch 01. This gap remains `OPEN` overall until the semantic capability itself (not just the backend choice) is implemented and accepted — do not close it merely because the backend decision exists.  
**Batch 01 Milestone 1 (read-only foundation):** `PARTIAL` — `WindowsUIAutomationAdapter` (`src/jarvis/computer/semantic_uia.py`) implements bounded inspect/search/read/revalidate with stale-safe element references, behind the optional `computer-uia` dependency; proven live on NIGHTFURY (Calculator + Notepad).  
**Batch 01 Milestone 2 (canonical tool wiring):** `PARTIAL` — the six semantic read operations are now reachable from the real JARVIS tool path (`computer.semantic.read` → `ToolExecutionService` → `PolicyPermissionEngine` → `ComputerActionService` → adapter), proven live end-to-end on NIGHTFURY through the actual service path (not by calling `uiautomation` directly).  
**Batch 01 Milestone 3 (bounded semantic actions):** `PARTIAL` — `computer.semantic.act` (invoke/toggle/select) is wired through the same canonical path, defaults to consequential/approval-required (no global auto-allow), and never fabricates `verified=True` without independent evidence (toggle/select re-read state; generic invoke stays honestly unverified). `invoke` is physically proven on NIGHTFURY through the full approval-gated action path (Calculator "Seven": display read 0 before, 7 after, via an independent read-back — not the actuation's own self-report). `toggle`/`select` pattern-level correctness (including "state didn't change ⇒ verified false") is proven by 9 deterministic unit tests plus 13 approval/architecture tests, but not physically re-demonstrated live in this batch — NIGHTFURY's disposable Calculator/Notepad did not expose a convenient `TogglePattern`/`SelectionItemPattern` control. Recommend the owner/reviewer confirm this evidence is sufficient before considering GAP-0101 for `RESOLVED` - this batch intentionally leaves that final call to review rather than self-declaring it, consistent with the checkpoint workflow's "independent review before next slice" rule. GAP-0102 (mouse/keyboard), GAP-0103 (OCR/visual), GAP-0104 (multi-app recovery), GAP-0105 (evaluation suite), GAP-0106 (DPI/multi-monitor/secure-desktop) all remain `OPEN`, untouched by this batch. GAP-0503 remains `OPEN`, untouched.  
**Batch 02 Milestone 0 (independent-review hardening):** `PARTIAL` — see `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_02.md` §3. Closed 5 independent-review findings against Batch 01 (R18B01-001..005): explicit strong/weak identity model (weak refs never actionable), `list_windows` privacy filtering, fresh post-action re-observation (never the pre-action object), a target-aware/time-bounded semantic approval preview reusing the existing `semantic_get_element` read path (refuses approval creation for stale/weak/non-actionable targets; detects target drift on `decide()`; expiry bounded by the element-ref TTL), and explicit disabled/offscreen/password fail-closed checks before actuation. `invoke` re-confirmed physically through the fully hardened pipeline (disposable Calculator, independent read-back). `toggle`/`select` remain test-proven only — a disposable Edge Guest + local HTML fixture attempt found that Chromium page content sits deeper than the adapter's existing `MAX_INSPECT_DEPTH=5` bound (a pre-existing, undisturbed limitation, not touched this milestone), and no other safe disposable Toggle/SelectionItem surface was found in scope. GAP-0101 stays `OPEN`/`PARTIAL`; still not closed pending an eventual toggle/select physical demonstration and review of Milestones 1/2.  
**Batch 02 Milestone 2 (repeatable evaluation suite) — GAP-0101 final call for this batch:** still `OPEN`/`PARTIAL`, deliberately **not** `RESOLVED`. All other Section 8.10 closure preconditions are met (independent-review hardening closed, strong identity enforced, sensitive-window leak closed, fresh post-action observation exists, approvals are target-aware, invoke/toggle/select code paths green - 133 focused tests), but toggle/select physical proof remains unavailable: the Milestone 2 physical acceptance runner (`scripts/phase18/computer_use_acceptance.py`), run 3 times, again found the Edge Guest fixture's checkbox/select unreachable at the same pre-existing `MAX_INSPECT_DEPTH=5` bound (0/3 both scenarios), and no other safe disposable Toggle/SelectionItem surface was found. Per the task's explicit instruction ("If Toggle/Select physical proof remains unavailable, do not overclaim"), this is left open for the owner/reviewer.  
**Batch 03 Milestone 0 (owned Win32 UIA fixture):** the Edge Guest fixture was replaced with a fully JARVIS-owned native Win32 process (`scripts/phase18/uia_fixture_host.py`) exposing real Button/CheckBox/ListBox controls. Physical acceptance run 3 clean iterations: **invoke 3/3, toggle 3/3, select 3/3**, each with genuine independent evidence (invoke: independent status-label read-back; toggle: adapter's fresh post-state re-check + independent status-label read-back; select: adapter's fresh `IsSelected` re-check - the fixture's own status label cannot observe a programmatic list selection, a documented Win32 `LBN_SELCHANGE` limitation, disclosed rather than worked around). This is the first batch with all-three-pattern physical evidence. Status remains `OPEN`/`PARTIAL` rather than `RESOLVED` in this milestone specifically because the task sequences the GAP-0101 closure decision to Milestone 2 (Section 9.9 of the Batch 03 task), which re-validates through the expanded evaluation suite; see the Milestone 2 section of this gap entry once that runs.  
**Batch 03 Milestone 2 — GAP-0101 final call:** `RESOLVED` for the semantic capability defined by this gap (per the Batch 03 task's own Section 9.9 criterion: "If all 3 pass reliably 3/3: GAP-0101 may be marked RESOLVED for the semantic capability defined by that gap"). Re-run 3 more clean iterations in Milestone 2 alongside the expanded input scenarios: invoke/toggle/select again all 3/3 with the same independent evidence as Milestone 0. **This does not mean all of Computer Use V2 is complete** - see GAP-0102 (paste/drag-drop/richer hotkeys), GAP-0104 (autonomous multi-app recovery), GAP-0105 (full real-app evaluation breadth), and GAP-0106 (DPI/secure-desktop physical proof), all of which remain open/partial by design.

### GAP-0102 — Mouse and rich keyboard input are incomplete
**Status:** `PARTIAL`  
General mouse click/move/drag/drop and arbitrary bounded hotkeys/keys/paste are not supported by the current Phase 11 path. Add native bounded input only after target grounding and policy checks.  
**Batch 02 Milestone 1 (grounded native input fallback):** `PARTIAL` — added `WindowsNativeInputAdapter` (`src/jarvis/computer/native_input.py`), a bounded native `SendInput` execution provider reachable only through `ComputerActionService`. Mouse: `move_to_element`/`left_click_element` only, grounded exclusively by `element_ref` (never raw x/y/HWND), re-validated through the existing fail-closed `resolve_actionable_target` boundary both before and after focusing the containing window (focus can change layout), coordinates normalized against the full Windows virtual desktop (not just the primary monitor). Keyboard: a fixed 14-key named allowlist plus one reviewed `shift+tab` combination (`computer.keyboard.key`), with `GetAsyncKeyState`-based interference checks (fails safely if the owner is physically holding a modifier) and guaranteed release of any JARVIS-pressed modifier even on failure. Both new tools (`computer.pointer.act`, `computer.keyboard.key`) are consequential/approval-required with no auto-allow. Physically proven live on NIGHTFURY through the full approval-gated path on a disposable Calculator instance: native left-click on "Seven" (`pointer_target_verified: true` via independent `GetCursorPos` readback, generic click honestly reported `verified: false`, independent semantic read-back of the display showing "Display is 7" - not the action's own self-report) and native Tab key press (independent semantic read confirming keyboard focus moved from "Seven" to "Eight"). Still absent by design this milestone: raw coordinate move/click, right click, double click, drag/drop, wheel scroll, paste, richer hotkeys, OCR/visual fallback - see `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_02.md` §4.  
**Batch 03 Milestone 2 (input expansion):** `PARTIAL` — added `right_click_element`, `double_click_element`, `scroll_element` (bounded `direction`/`steps`, internally a signed multiple of `WHEEL_DELTA`, never a raw wheel delta) to `computer.pointer.act`, all reusing the exact same element-grounding pipeline as move/left-click. Added a very small, explicit named-chord surface (`computer.keyboard.chord`: `ctrl+a`/`ctrl+c`/`ctrl+f`/`ctrl+z`/`ctrl+y` only - no paste, no save, no Alt+F4, no Windows-key combination, no Ctrl+Alt+Delete, no arbitrary modifier+key parser), sharing its modifier-press/guaranteed-release sequencing with `computer.keyboard.key` rather than a second implementation. All physically proven live on NIGHTFURY through the owned Win32 fixture, 3/3 each (right-click/scroll: delivery evidence only, honestly unverified since a standard button/listbox has no observable reaction; double-click/chord: delivery confirmed, double-click additionally confirmed via independent status read-back). Paste, drag/drop, and richer/arbitrary hotkeys remain explicitly deferred (Sections 9.6/9.7 of the task) - GAP-0102 stays `PARTIAL` by design even with this milestone green.  
**Batch 04 Milestone 1 (grounded drag + literal text input breadth):** `PARTIAL`, a stronger partial - not resolved. Added exactly one new two-target action, `drag_element_to_element` (`computer.pointer.act`), grounded strictly by `source_element_ref`/`target_element_ref` (no raw coordinates, no path/trajectory, no duration) - both endpoints resolved through the same trusted `resolve_actionable_target` machinery as every other pointer action, restricted to the same trusted window (`drag_cross_window_not_supported` otherwise - cross-window drag is a deliberate, reviewed deferral, not an oversight, given its file-transfer-adjacent risk). The approval layer gained a genuine dual-target binding (`ComputerActionService._drag_target_preview`/`_dual_target_actions`): the preview shows both endpoints, a composite `"source_digest|target_digest"` identity binds both, and `decide()` distinguishes `drag_source_changed` vs `drag_target_changed` vs `drag_source_stale`/`drag_target_stale` rather than a generic refusal. Native execution (`WindowsNativeInputAdapter.drag_element_to_element`) re-resolves both endpoints again after focus, performs a bounded (`DRAG_INTERPOLATION_STEPS=8`, within the reviewed 4-12 range) deterministic linear interpolation between source and target - no randomness, no jitter, no intermediate points exposed to the model - and guarantees the JARVIS-pressed left button is released in a `finally` block on any partial `SendInput` failure (proven by a dedicated unit test forcing a mid-drag injection failure). Generic drag stays `verified=False` by the same honesty rule as generic click/scroll; only the owned fixture's real postcondition (`drag:accepted`) counts as verified evidence. A second owned Win32 fixture (`scripts/phase18/uia_text_fixture_host.py`) was added with a real EDIT control plus drag source/target buttons; physical acceptance (`scripts/phase18/computer_use_acceptance.py`), run 3 clean iterations, is **all 3/3**: grounded drag (`drag:accepted` independent status read-back), literal English typing, literal Arabic Unicode typing (`مرحبا يا جارفيس`, exact independent text read-back match - the existing literal typing implementation needed no changes), Home/End cursor-movement proof, Backspace, Tab focus-cycling, `ctrl+c` clipboard proof (a known fixture value, never a pre-existing owner clipboard value, verified actually landed on the clipboard), and `ctrl+z` undo. Two real bugs were found and fixed via this physical dogfooding, unrelated to the fixture's own drag/typing logic per se: (1) a plain top-level fixture window never gives keyboard focus to any child by default (fixed with an explicit `SetFocus` call at startup); (2) a standard BUTTON control's own default click-capture wins the race against a `WM_PARENTNOTIFY`-only parent-mediated drag design, so the drag-source button's window procedure is now subclassed to intercept `WM_LBUTTONDOWN` before the button's own default handling ever runs. A third, pre-existing (Phase 11-era) bug was also found and fixed: `computer.clipboard_read`'s inner `ComputerActionService` permission check had no explicit `ALLOW` rule despite being classified as a read action, so it silently required owner approval for every read unlike its sibling read actions - `PolicyPermissionEngine` now has the missing `computer.clipboard_read` rule (see `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_04.md` §4 for detail). Still explicitly absent/deferred, by design: paste (Ctrl+V unimplemented - live clipboard secrecy/ephemeral-transaction design remains future work), cross-window drag, file drag/drop, arbitrary hotkeys, OCR/visual actuation. GAP-0102 stays `PARTIAL`.

### GAP-0103 — Visual grounding/OCR/local vision not production-active
**Status:** `OPEN`  
On-demand GDI capture exists, but OCR/local vision/visual target selection remain provider work. Evaluate UIA first; visual fallback only when semantics fail.

### GAP-0104 — Action verification/recovery needs full multi-app implementation
**Status:** `PARTIAL`  
Build per-action verification, re-observation, stale-target recovery, moved-window handling, ambiguity handling, retry budgets, and explicit failure receipts.  
**Batch 02 (Milestones 0-2):** `PARTIAL` — per-action fresh re-observation (never the pre-action object), stale/ambiguous-target refusal, and typed failure receipts are all now proven (unit tests + the `computer_use_v2` evaluation suite's "wrong-target execution count remains zero in fixture cases" contract). Retry budgets remain intentionally absent (no auto-retry anywhere, by design - AGENTS.md closed-loop rule), and there is still no autonomous multi-app replanning/recovery loop. Do not read this as full GAP-0104 closure.  
**Batch 03:** `PARTIAL` (unchanged) — Milestone 0 generalized fresh re-observation/target-change refusal to element- and window-targeted actions alike (R18B02-001/003); still no autonomous multi-app replanning/recovery loop.

### GAP-0105 — Computer-use evaluation suite is missing
**Status:** `PARTIAL`  
Create repeatable NIGHTFURY tasks across Notepad, Explorer, Settings, Calculator, VS Code, terminal, browser, dialogs, clipboard, drag/drop, multi-window and failure recovery. Record success, steps, replans, wrong actions, latency, grounding source/confidence, and verification evidence.  
**Batch 02 Milestone 2:** `PARTIAL` — a deterministic, product-owned `computer_use_v2` suite (`src/jarvis/evaluation/computer_use_v2.py`, registered through the existing `EvaluationService`, no second evaluation authority) with 17 cases covering canonical-authority routing, privacy filtering, weak/stale-target refusal, approval target-change binding, fresh post-action verification, native-input grounding, bounded model-facing schemas, and wrong-target-count contracts - runnable without a GUI, all 17 passing. Plus an opt-in physical acceptance runner (`scripts/phase18/computer_use_acceptance.py`), explicitly not part of production startup, run 3 times in one session: Calculator scenarios (semantic invoke, native left click, native Tab key) passed 3/3 with independent read-back evidence each time; Edge Guest checkbox/select scenarios were honestly 0/3 (see GAP-0101 note above). This is a genuine foundation, **not** the full breadth of apps/failure modes named in this gap (Notepad, Explorer, Settings, VS Code, terminal, dialogs, drag/drop, multi-window remain uncovered) - do not read this as GAP-0105 closure.  
**Batch 03 Milestone 2:** `PARTIAL` — the suite grew from 17 to 24 deterministic cases (window-targeted trusted approval, file-root confinement, sensitive-path denial, path-resolution escape refusal, expanded pointer actions staying element-grounded, chord allowlist rejection, no-paste/no-drag-drop schema checks), all still fake/mock-based with no GUI dependency. The physical runner now exercises the owned Win32 fixture exclusively (no owner app anywhere) across a substantially wider scenario set - semantic invoke/toggle/select, native left/right/double-click, scroll, Tab-key focus, one named chord, and a non-primary-monitor click - all 3/3. This remains a single-fixture foundation, **not** the broad real-app matrix (Notepad, Explorer, Settings, VS Code, terminal, dialogs, multi-window) named in this gap's original scope - do not read this as full GAP-0105 closure.  
**Batch 04 Milestone 1:** `PARTIAL` — the deterministic suite grew from 24 to 32 cases, adding: two-target drag approval binding, drag target-change-after-approval refusal, drag cross-window refusal, generic drag stays unverified, a partial-drag-injection-failure releases the left button, English/Arabic literal-typing canonical-path checks, a clipboard-verification-never-inspects-unknown-owner-value contract, and a paste-absent/drag-stays-bounded schema check (replacing the now-obsolete "no drag anywhere" assertion, since a reviewed bounded drag now legitimately exists). A **second** owned Win32 fixture was added (`scripts/phase18/uia_text_fixture_host.py`, EDIT + two drag buttons + status label), and the physical runner now exercises both fixtures together in every run. Still a two-fixture foundation, not the broad real-app matrix named in this gap's original scope - do not read this as GAP-0105 closure.

### GAP-0106 — Multi-monitor/DPI/secure-desktop behavior needs explicit proof
**Status:** `PARTIAL`  
Computer Use V2 must handle DPI/window movement/multiple monitors and fail safely on secure/locked/UAC-style surfaces it cannot control.  
**Batch 02 Milestone 2:** `PARTIAL` — unit-level virtual-desktop coordinate math is proven for negative X/Y origins, extended-desktop dimensions, exact edges, and degenerate geometries (Milestone 1's `CoordinateMathTests`). NIGHTFURY's real topology was recorded (not altered): `SM_XVIRTUALSCREEN=-1920`, `SM_YVIRTUALSCREEN=0`, `SM_CXVIRTUALSCREEN=3840`, `SM_CYVIRTUALSCREEN=1080`, `SM_CMONITORS=2`, primary-monitor DPI 96 (100% scaling) - a genuine two-monitor extended-desktop machine, matching exactly the negative-origin/extended-dimension scenarios already unit-tested. No live click was separately re-demonstrated with the fixture explicitly positioned on the non-primary (negative-X) monitor this batch - Calculator opened on the primary monitor by default and no window-move capability exists in scope to relocate it; record `MULTI_MONITOR_PHYSICAL_PENDING` for that specific live-secondary-monitor click, not for the topology evidence itself. No non-100%-DPI monitor is available on NIGHTFURY, so DPI physical proof stays partial per the task's own explicit allowance. Secure-desktop/UIPI: policy/unit tests exist (sensitive-window denial, `native_input_injection_failed` for partial/zero SendInput), docs state UIPI can block higher-integrity targets and JARVIS does not bypass it (no elevation, no UIAccess anywhere in the code) - no UAC surface was deliberately triggered to "test" it, per the task's explicit prohibition.  
**Batch 03 Milestone 2 (non-primary monitor physical proof):** the `MULTI_MONITOR_PHYSICAL_PENDING` item above is now closed. The owned fixture host gained an evaluation-only `--x`/`--y` launch flag (never a general production window-move capability); the runner confirmed NIGHTFURY's real topology still shows a negative-X monitor (`x_origin=-1920, width=3840, monitor_count=2`), launched the fixture at `x_origin+100`, confirmed via semantic read that the target element's bounds were genuinely on the non-primary monitor (`x < 0`), and performed a grounded native left click there - independently verified via the fixture's own status read-back (`"invoked"`). Recorded `NON_PRIMARY_MONITOR_PHYSICAL_PASS` 3/3. DPI (no non-100% monitor available) and secure-desktop physical proof (no UAC surface deliberately triggered, per the task's prohibition) remain pending - `GAP-0106` stays `PARTIAL`, not `RESOLVED`.

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
**Status:** `RESOLVED_AFTER_REVIEW_HARDENING` (path-confinement scope only — see below)  
Current file/process operations are bounded and useful, but full safe project/file workflows need explicit roots, write/move/copy/rename/delete policies, verification, rollback/recycle-bin strategy, and sensitive-path exclusions.  
**Batch 03 Milestone 1 (approved-root file access confinement):** `RESOLVED` against the Batch 03 task's own closure criteria (Section 8.13) — all four existing path-requiring computer capabilities (`inspect_file`, `search_files`, `open_file`, `open_folder`) now go through one product-owned, fail-closed `FileAccessPolicy` (`src/jarvis/computer/file_access.py`, subordinate to `PolicyPermissionEngine`, no second authority): explicit owner-configured roots only (`JarvisConfig.file_access_roots` / `JARVIS_FILE_ACCESS_ROOTS`), denying the whole operation (`file_root_not_configured`) when unconfigured rather than falling back to any default; component-wise (never string-prefix) root containment, verified to correctly reject a sibling-prefix path (`Data` vs `Database`); `..`-traversal and directory-junction escape both verified denied through `Path.resolve()`'s real-target canonicalization, exercised empirically with an actual Windows junction (`mklink /J`), including through the real `ComputerActionService` execution path, not just at the policy-unit level; a component/filename-aware sensitive-path deny list (`.ssh`/`.gnupg`/`.aws`/`.azure`/`.kube`, private-key files, `.env*` except the deliberately-safe `.env.example`, browser `Login Data`/`Cookies`/`Web Data`) applied as defense in depth even nested under an approved root, with denied children silently omitted from search results (only a bounded `filtered_count`, never their names) rather than leaked. 26 tests (`tests/test_phase_eighteen_file_access.py`), including through the real service path with a `tempfile.TemporaryDirectory()` as the one explicit approved root. **File dialogs remain unimplemented** (deliberately, per the task) and write/move/copy/rename/delete/rollback/recycle-bin richness from this gap's original broader description remains future work — this resolution covers path-read confinement for the capabilities that exist today, not the full file-workflow scope; do not read `RESOLVED` as closing the entire original gap description.  
**Batch 04 Milestone 0 (independent-review hardening, R18B03-001/R18B03-002):** An independent review of Batch 03 found that `filter_search_results()` re-checked each candidate only *after* `Path.rglob()` had already been free to descend through a symlink/junction/reparse point before filtering happened — safe for model-visible output (nothing outside the root was ever returned) but not a genuine pre-descent boundary. `FileAccessPolicy.filter_search_results()` was replaced by `FileAccessPolicy.iter_search_candidates(root, pattern)`, a bounded, iterative, pre-descent walker: for every directory it is about to enter, it classifies the entry as a reparse point *before* descending (`os.lstat().st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT`, empirically verified against a real `mklink /J` junction — `Path.is_symlink()` alone reports `False` for a junction and would have under-classified it), and the default policy is to never descend a directory symlink/junction/reparse point at all, even when its target is still inside the approved root (deliberately stricter than "follow if still inside root" — simpler, deterministic, no cycle/mount ambiguity). A file symlink may still be returned, but only if its fully resolved target stays inside the root, is a real file, and passes the sensitivity policy. Candidate-scan (`MAX_SEARCH_CANDIDATES_SCANNED=5000`) and result (`MAX_SEARCH_MATCHES=100`) bounds are now enforced live, one directory listing at a time — an unbounded candidate list is never built first — plus a new `MAX_SEARCH_DEPTH=32` and a bounded canonical-directory `visited` set (defense in depth; a non-reparse directory tree cannot itself be cyclic once reparse points are never followed). Separately, `_SENSITIVE_FILE_NAMES`'s previous exact-match set (`.env`, `.env.local`, `.env.development`, `.env.production`, `.env.test`) missed variants such as `.env.staging`/`.env.development.local`/`.env.production.local`; it is now a wildcard rule (`.env` or `.env.<anything>`, excluding the safe `.env.example` template) matched on the literal `.env` stem followed by nothing or a `.` separator, so `.environment` is correctly unaffected. 14 new red-before-green tests added (junction-outside-root not traversed; secret never yielded even transiently; junction-inside-root still not descended; cyclic junction cannot cause an unbounded walk; scan-count bound enforced; result-count bound enforced; sensitive subtree pruned with no hidden child leaking; `.env.staging`/`.env.development.local`/`.env.production.local`/`.env.test.local` denied; `.env.example` allowed; `.environment` unaffected; normal nested search still succeeds) in `tests/test_phase_eighteen_file_access.py` (38 tests total in that file), all using only `tempfile.TemporaryDirectory()` fixtures. Direct `inspect_file`/`open_file`/`open_folder` confinement via `FileAccessPolicy.evaluate()` was not touched by this change and remains as previously verified. This hardening closes the specific traversal-boundary finding; it does not expand this gap's resolved scope beyond current read/open/search path confinement.

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
