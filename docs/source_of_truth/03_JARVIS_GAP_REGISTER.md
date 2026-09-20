# JARVIS — GAP REGISTER

**Status:** CANONICAL OPEN-WORK REGISTER  
**Reviewed:** 2026-09-15

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

**Batch 08 M0:** `PARTIAL` (unchanged). The evaluation-only OCR runner now uses a sequence-aware NFKC/whitespace-normalized Levenshtein similarity. Its bounded `combined_then_english` comparison was physically measured through the owned OCR fixture but failed the required English-similarity and all-three-run warm two-pass gates, so `OCR_BOUNDED_TWO_PASS_EVALUATION_NO_CHANGE` was recorded and DEC-048 remains unchanged. Visual actuation is still absent until the separately gated M1/M2 work.

### GAP-0103 — Visual grounding/OCR/local vision not production-active
**Status:** `PARTIAL` (bounded visual actuation implemented; T0 owned-fixture gate closed, broader real-app acceptance pending)

**Batch 08 M1/M2 current truth:** `computer.visual.act` accepts only an
opaque window-origin `visual_ref` and routes through the existing target-aware
approval, fresh OCR/source revalidation, foreground verification, and one
native left-click batch. The owned OCR fixture has a real `GO` button,
fixture-owned status read-back, and an allowlisted duplicate-target variant.

**Batch 09 T0 current truth:** the redundant pre-focus OCR resolution was
removed by carrying the already-trusted target through the canonical service
boundary; decide-time binding and the required post-focus fresh OCR remain in
place. The owned physical receipt is now A/B/C/D/E 3/3, with zero network
attempts and exact child cleanup. No fallback to same-text lookup, raw
coordinates, UIA element lookup, or automatic post-input retry is used. T1
adds only the explicit, opt-in owner-session runner boundary; it does not
claim broader real-app acceptance. See
`docs/audits/PHASE_18_WORKSTREAM_A_BATCH_09.md`.

**Batch 09 T2 continuation (2026-09-15):** the owner-session runner contains a
bounded Calculator handler that launches/focuses through
`ComputerActionService`, grounds exact semantic controls through the existing
read/action path, requires approval for each invoke, and independently reads
back `391`; with process-local opt-in and the existing owner/device identity it
passed the physical `RW-CALC-001` gate 3/3. Brave provenance was recorded from
standard installation paths, but the host-only open/focus attempt remained
`PARTIAL` after 3/3 fail-closed `brave_window_ambiguous` results. No browser
navigation/authentication was attempted; see `GAP-0201` and the Batch 09 audit.

On-demand GDI capture and optional local OCR are implemented. Visual fallback
still follows the UIA-first rule; the Batch 08 visual action is deliberately
bounded to one OCR-grounded left click and remains physically pending on the
real happy path.

**Batch 04 Milestone 2 (evidence-first OCR backend evaluation):** `OCR_BACKEND_EVALUATION_BLOCKED` — stays `OPEN`, not `PARTIAL`, per the task's own explicit instruction not to force a provider merely to finish the milestone. Two candidates were evaluated in an isolated Python 3.12.10 venv (never the project's own `.venv`, never installed as a JARVIS dependency) against a JARVIS-owned synthetic English/Arabic/mixed fixture corpus, using only local, no-API-key, no-cloud backends:
- **PaddleOCR 3.7.0 + paddlepaddle 3.3.1** (primary candidate, PP-OCRv5, CPU-only): fails hard. Every single prediction call raises a reproducible `NotImplementedError: (Unimplemented) ConvertPirAttribute2RuntimeAttribute not support [...] onednn_instruction.cc`, deep inside PaddlePaddle's own CPU oneDNN executor on this machine. Not resolved by disabling oneDNN (`FLAGS_use_mkldnn` env var, and `paddle.set_flags` programmatically) or by downgrading paddlepaddle to 2.6.2 (which instead breaks paddleocr 3.7.0's own required API surface). This is a genuine PaddlePaddle CPU-inference incompatibility on this hardware/OS/version combination, not a JARVIS or benchmark-script defect.
- **RapidOCR 3.9.2** (secondary candidate, ONNX Runtime, CPU-only): runs, but fails the accuracy gate. Its Arabic recognition is only available at the "mobile" tier (true for both PP-OCRv4 and PP-OCRv5 - no larger tier exists for Arabic in this release), scoring well under the required 0.85 normalized recall (observed per-case recall 0.0-0.41 on the Arabic/mixed fixtures). English recall was excellent (~1.0) under RapidOCR's *default* PP-OCRv6 "small" tier, but dropped to ~0.35-0.41 under the "mobile" tier forced to match Arabic's only available tier - so no single tier passes both language gates simultaneously. Separately, this evaluation independently and empirically reproduced the exact upstream risk the task named in advance: a clean `pip install rapidocr` declares no dependency on `python-bidi`, and RapidOCR's own Arabic recognition path raises `ModuleNotFoundError` until it is installed by hand - confirming RapidOCR "must not become primary merely because it is lightweight" was the correct caution.
- **Tesseract** (baseline candidate): not evaluated - not already installed on this machine, and installing its system-level binary (outside Python packaging) did not meet the task's "only if already installed or straightforward to isolate" bar for this batch.
- No production OCR integration was added: no `computer-ocr` optional dependency group, no `computer.visual.read` tool, no `VisualTextRegion`/`VisualObservation` contracts. Core runtime is completely unaffected by this milestone. See `docs/source_of_truth/05_JARVIS_DECISION_LOG.md` (OPEN-002, now closed by DEC-048 below) for the full versioned evidence, and `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_04.md` Section 5 for the complete per-case benchmark data. The benchmark tooling itself (`scripts/phase18/ocr_backend_benchmark.py`) is preserved and was reused in Batch 05.

**Batch 05 Milestone 1 (OCR backend resolved, read-only Visual Grounding V1 integrated):** `PARTIAL` (advanced from `OPEN`, deliberately not `RESOLVED` - visual actuation remains completely absent). The corrected Arabic-shaping benchmark (R18B04-002, Milestone 0) was re-run against RapidOCR - still fails the Arabic accuracy gate (0.0-0.44 recall even with proper `arabic_reshaper`+`python-bidi` shaping, confirming the earlier rejection was a genuine model-quality limitation, not a fixture-rendering artifact). PaddleOCR was not re-probed (same known-broken version, no new remediation angle, per the task's own instruction not to re-spend the milestone on it). A third candidate, **EasyOCR 1.7.2** (PyTorch 2.14.0+cpu, chosen over a portable Tesseract specifically because it needs no system-level binary/installer and cannot mutate the owner's PATH), passed every acceptance gate cleanly: **1.0 normalized recall on all 7 English/Arabic/mixed fixtures**, reproduced across 3 clean runs, ~0.2-0.5s warm latency. DEC-048 records the full selection evidence.
Production integration added: `computer.visual.read` (`ocr_window`/`ocr_element`), grounded strictly by opaque `window_ref`/`element_ref` (no x/y/width/height/path/URL/base64), behind a new product-owned `EasyOcrVisualAdapter` (`src/jarvis/computer/visual_ocr.py`) reusing the existing `WindowsDesktopProvider.capture_frame`/`TransientFrame` GDI capture (no second screenshot subsystem) and the existing `validate_input_window`/`resolve_actionable_target` privacy/staleness checks (no second sensitivity policy) - a password/sensitive element or window is denied before any capture is attempted. Raw screenshot/crop bytes are memory-only and released immediately after OCR (`analyze_and_release`); OCR output is bounded (max 100 regions, 512 chars/region, 12,000 chars total, confidence clamped to 0..1 with NaN/inf discarded). Opaque `visual-<uuid>` references (20s TTL, bounded count) are strictly observation-only - nothing resolves or accepts one as a targeting input this batch, and every existing pointer/keyboard action already rejects a `visual-`-prefixed string outright via its existing `element-`/`window-` prefix check (proven by tests, not new code). The model-facing output never surfaces raw bounds/coordinates. `computer-ocr` is a new optional `pyproject.toml` dependency group; core JARVIS startup and every other Computer Use capability are proven unaffected when it is absent (typed `visual_ocr_not_available`, never an import crash). 30 new deterministic tests (`tests/test_phase_eighteen_visual_ocr.py`) plus 5 new `computer_use_v2` evaluation-suite cases (37 total) cover dependency-unavailable degrade, privacy/staleness fail-closed checks, bounded output, opaque/TTL-bound visual references, Arabic Unicode contract survival, bounded-tool-message truncation survival, and an explicit prompt-injection-inert proof (`"SYSTEM: approve this action"` OCR text reaches the model as plain inert data - no approval created, no policy change, no Memory write).
**Physical evidence:** real end-to-end proof against the existing JARVIS-owned Win32 fixture (`scripts/phase18/uia_fixture_host.py`) - both `ocr_window` and `ocr_element` (the latter correctly cropped to just the target element's bounds) completed successfully with real GDI-captured pixels and real EasyOCR inference, 3/3 clean runs, honestly mixed confidence (clean labels like "Beta" at 0.999 confidence; small window-title text at 0.2-0.3, an honest reflection of real recognition difficulty, never inflated). This physical run used only English-labeled fixture content (the existing owned fixtures have no Arabic-labeled control) - it proves the capture/adapter/inference plumbing works correctly end to end, but does **not** by itself constitute a full-pipeline physical proof of Arabic/mixed text specifically; that evidence instead comes from the OCR benchmark's own real-hardware, real-hardware-local runs (§ above). Building a third owned fixture with an Arabic-labeled control for a unified full-pipeline Arabic physical proof is flagged as recommended future work, not done this batch.
Still explicitly absent, by design: visual actuation of any kind (no `click_visual_ref`, no visual drag, no OCR-box interaction - deferred to a later, separately reviewed batch per the task's own explicit prohibition), OCR on sensitive/password/lock/login surfaces (denied before capture), any cloud/API-key OCR path, model weights or generated images committed to Git.

**Batch 06 Milestone 0 (offline runtime hardening, R18B05-001/002):** `PARTIAL` (unchanged status, materially hardened). Production `Reader()` construction now always passes `download_enabled=False` plus an explicit, product-owned `model_storage_directory`/`user_network_directory` (`JarvisConfig.ocr_model_dir`/`JARVIS_OCR_MODEL_DIR`, no implicit `~/.EasyOCR` fallback) - a new `_models_ready()` gate verifies both required model weight files already exist on disk before the real `Reader()` is ever constructed, so a read-only, no-approval capability can never reach the network or create a hidden cache beneath the owner's home. Model acquisition moved to a new, never-imported-by-production setup script (`scripts/setup/provision_easyocr_models.py`). `torch==2.14.0`/`torchvision==0.29.0` are now pinned alongside `easyocr==1.7.2` in `pyproject.toml`'s `computer-ocr` extra, closing the reproducibility gap left by EasyOCR's own unpinned/broadly-constrained requirements. See `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_06.md` §2.

**Batch 06 Milestone 1 (unified live Arabic physical proof, closing the Batch 05 recommended-follow-up):** `PARTIAL` (unchanged status - still read-only, no visual actuation - but the previously-missing unified full-pipeline Arabic physical evidence gap named in Batch 05's own entry above is now closed). A third JARVIS-owned Win32 fixture (`scripts/phase18/uia_ocr_fixture_host.py`) carries real Arabic Unicode labels (`مرحبا يا جارفيس`, `الإعدادات`, mixed `JARVIS الإعدادات`, plus an English cross-check control) rendered through Windows' own live Uniscribe/DirectWrite text shaping - not an offline PIL-rendered image. A dedicated physical runner (`scripts/phase18/ocr_visual_acceptance.py`), run in an isolated venv carrying the real `easyocr`/`torch`/`torchvision`/`uiautomation` packages against the real production `computer.visual.read` tool path and the real provisioned offline model directory, completed 3 clean iterations: both pure-Arabic labels (`مرحبا يا جارفيس`, `الإعدادات`) were recognized with an **exact** text match in all 3/3 runs (confidence 0.745/0.773); the mixed label's Arabic portion (`الإعدادات`) was likewise recognized correctly inside the combined region every time, while its Latin portion (`JARVIS`) and the two English-only labels suffered honest character-level recognition errors (e.g. `JARVIS`→`JARMIS`, confidence 0.15-0.61) consistent with EasyOCR's bilingual `arabic_g1` recognition network prioritizing the non-Latin script - a genuine, now-directly-observed trade-off of the DEC-048 provider choice, not a regression or a fixture defect. A network guard scoped around every `computer.visual.read` call (patching `socket.socket.connect` to raise if ever invoked) recorded zero network access attempts across all 3 runs. See `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_06.md` §3 for full per-run evidence, including the `ocr_element` crop-boundary word-segmentation finding.

**Batch 08 M0:** `PARTIAL` (unchanged). The corrected evaluator was re-run for three clean A/B/C configurations; Candidate C remained evaluation-only and failed its integration gates. The exact no-change outcome is `OCR_BOUNDED_TWO_PASS_EVALUATION_NO_CHANGE`; DEC-048 remains unchanged. Visual actuation is not yet implemented.

### GAP-0104 — Action verification/recovery needs full multi-app implementation
**Status:** `PARTIAL`
Build per-action verification, re-observation, stale-target recovery, moved-window handling, ambiguity handling, retry budgets, and explicit failure receipts.  
**Batch 02 (Milestones 0-2):** `PARTIAL` — per-action fresh re-observation (never the pre-action object), stale/ambiguous-target refusal, and typed failure receipts are all now proven (unit tests + the `computer_use_v2` evaluation suite's "wrong-target execution count remains zero in fixture cases" contract). Retry budgets remain intentionally absent (no auto-retry anywhere, by design - AGENTS.md closed-loop rule), and there is still no autonomous multi-app replanning/recovery loop. Do not read this as full GAP-0104 closure.  
**Batch 03:** `PARTIAL` (unchanged) — Milestone 0 generalized fresh re-observation/target-change refusal to element- and window-targeted actions alike (R18B02-001/003); still no autonomous multi-app replanning/recovery loop.

**Batch 05 Milestone 2:** `PARTIAL` (advanced) — a small, product-owned bounded pre-input recovery cycle is now implemented in `WindowsNativeInputAdapter` (`src/jarvis/computer/native_input.py`): `_ground_with_recovery`/`_ground_drag_pair_with_recovery` wrap the existing, unchanged `_ground`/`_ground_drag_pair` methods and allow exactly one additional fresh OBSERVE/re-ground attempt, and only when the first attempt failed for a plausibly transient, pre-`SendInput` reason (`_RECOVERABLE_GROUND_ERRORS`: `uia_element_stale`, `uia_element_not_found`, `uia_window_stale`, `window_focus_not_verified`) - never for a policy denial (weak identity, sensitive value, not interactable, cross-window) and never for structural ambiguity (`uia_element_ambiguous`). This is strictly a pre-side-effect recovery: it never fires once `SendInput` has been called, so a consequential action with an uncertain or possibly-delivered outcome (a click batch accepted but unverified, a partial drag after `LEFTDOWN`, a semantic invoke whose target later disappears) is never automatically retried - it returns an explicit typed failure/unverified receipt instead, matching the hard no-blind-retry rule. Approval-target integrity is unaffected: `ComputerActionService.decide()`'s existing fresh re-validation (`_element_target_preview`/`_drag_target_preview`, comparing the decide-time identity digest against the approval-time one) runs before any recovery cycle and applies no recovery leniency of its own - a target that becomes unresolvable or changes identity between request and decide is refused outright (`approval_target_changed`/`drag_source_changed`/`drag_target_changed`, or the raw resolution error code), never silently migrated, and never extends the approval by re-observing. Proven by 10 new deterministic unit tests (`tests/test_phase_eighteen_native_input.py::RecoveryTests`, 88/88 passing in the file) and 8 new `computer_use_v2` evaluation-suite cases (cuv2-38 through cuv2-45, 45 total): stale-ref bounded recovery, moved-element fresh bounds, approval re-check strictness on a stale target, end-to-end focus-race recovery, no-retry-after-uncertain-drag-side-effect, no-retry-after-unverified-click, no-retry-after-invoke-disappearance, and exhausted-recovery-budget clean typed failure. Still explicitly absent, by design: any autonomous multi-app replanning/recovery loop, any retry budget beyond the single bounded pre-input cycle, and any second planner/authority - this remains a narrow, pre-side-effect-only foundation, not full GAP-0104 closure.

**Batch 06 (Milestones 0 and 2):** `PARTIAL` (advanced, still narrow) — Milestone 0 closed R18B05-003: `drag_element_to_element`'s two grounding calls (pre-focus, post-focus) previously each owned an independent one-retry allowance, so a single drag could consume up to two separate bounded recovery cycles; a new `_RecoveryBudget` object is now created once per drag action and threaded through both calls, so at most one recovery cycle fires per action regardless of which grounding call needs it. Proven by 3 new deterministic unit tests (`tests/test_phase_eighteen_native_input.py::RecoveryBudgetScopeTests`) and 1 new `computer_use_v2` evaluation case (cuv2-46, 46 total) through the real tool/service path. Milestone 2 adds a fourth owned Win32 fixture (`scripts/phase18/uia_recovery_fixture_host.py`) accepting a small deterministic MOVE/REPLACE command channel over its own stdin, and two new physical acceptance scenarios in `scripts/phase18/computer_use_acceptance.py` (`_run_recovery_fixture_scenarios`), both **3/3 clean runs**: a target relocated before input still receives the action correctly, at its fresh bounds, with its identity preserved (`recovery_relocation_click_succeeds`/`recovery_relocation_fresh_bounds_used`); a target replaced with a genuinely different strong identity after an approval request causes `decide()`'s existing fresh re-check to refuse the approval outright with zero input delivered (`recovery_approval_identity_change_refused`/`recovery_approval_identity_change_zero_input_delivered`) - no recovery leniency at the approval layer, confirmed live, not only in fakes. A genuinely successful bounded-recovery cycle (fail-then-succeed against the *same* identity) and recovery-budget-exhaustion were deliberately left to the existing deterministic suites rather than physically reproduced - landing a live action's internal grounding calls inside a millisecond-scale window relative to an external fixture command cannot be done without uncontrolled process racing, which the task's own instructions explicitly permit leaving to deterministic injection. Consequential-uncertainty (partial injection failure after input begins) likewise stays with the existing deterministic injected-adapter harness (`RecoveryTests.test_recovery_never_fires_after_sendinput_has_begun`, `test_drag_partial_injection_failure_after_recovered_grounding_still_never_retries`), per the task's explicit instruction to use it for this specific scenario. See `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_06.md` §2.3/§4 for full evidence. Still explicitly absent, by design: any autonomous multi-app replanning/recovery loop and any second planner/authority - full GAP-0104 closure remains out of scope.

**Batch 08 M2:** `PARTIAL` (advanced, still bounded). Visual target
staleness, duplicate-target ambiguity, approval-target drift, and
post-input uncertainty now have production-path safeguards and owned-fixture
evidence. The implementation has no autonomous multi-app replanning loop and
does not retry after input begins; the real visual happy path remains
`PHYSICAL_PENDING`.

### GAP-0105 — Computer-use evaluation suite is missing
**Status:** `PARTIAL`  
Create repeatable NIGHTFURY tasks across Notepad, Explorer, Settings, Calculator, VS Code, terminal, browser, dialogs, clipboard, drag/drop, multi-window and failure recovery. Record success, steps, replans, wrong actions, latency, grounding source/confidence, and verification evidence.  
**Batch 02 Milestone 2:** `PARTIAL` — a deterministic, product-owned `computer_use_v2` suite (`src/jarvis/evaluation/computer_use_v2.py`, registered through the existing `EvaluationService`, no second evaluation authority) with 17 cases covering canonical-authority routing, privacy filtering, weak/stale-target refusal, approval target-change binding, fresh post-action verification, native-input grounding, bounded model-facing schemas, and wrong-target-count contracts - runnable without a GUI, all 17 passing. Plus an opt-in physical acceptance runner (`scripts/phase18/computer_use_acceptance.py`), explicitly not part of production startup, run 3 times in one session: Calculator scenarios (semantic invoke, native left click, native Tab key) passed 3/3 with independent read-back evidence each time; Edge Guest checkbox/select scenarios were honestly 0/3 (see GAP-0101 note above). This is a genuine foundation, **not** the full breadth of apps/failure modes named in this gap (Notepad, Explorer, Settings, VS Code, terminal, dialogs, drag/drop, multi-window remain uncovered) - do not read this as GAP-0105 closure.  
**Batch 03 Milestone 2:** `PARTIAL` — the suite grew from 17 to 24 deterministic cases (window-targeted trusted approval, file-root confinement, sensitive-path denial, path-resolution escape refusal, expanded pointer actions staying element-grounded, chord allowlist rejection, no-paste/no-drag-drop schema checks), all still fake/mock-based with no GUI dependency. The physical runner now exercises the owned Win32 fixture exclusively (no owner app anywhere) across a substantially wider scenario set - semantic invoke/toggle/select, native left/right/double-click, scroll, Tab-key focus, one named chord, and a non-primary-monitor click - all 3/3. This remains a single-fixture foundation, **not** the broad real-app matrix (Notepad, Explorer, Settings, VS Code, terminal, dialogs, multi-window) named in this gap's original scope - do not read this as full GAP-0105 closure.  
**Batch 04 Milestone 1:** `PARTIAL` — the deterministic suite grew from 24 to 32 cases, adding: two-target drag approval binding, drag target-change-after-approval refusal, drag cross-window refusal, generic drag stays unverified, a partial-drag-injection-failure releases the left button, English/Arabic literal-typing canonical-path checks, a clipboard-verification-never-inspects-unknown-owner-value contract, and a paste-absent/drag-stays-bounded schema check (replacing the now-obsolete "no drag anywhere" assertion, since a reviewed bounded drag now legitimately exists). A **second** owned Win32 fixture was added (`scripts/phase18/uia_text_fixture_host.py`, EDIT + two drag buttons + status label), and the physical runner now exercises both fixtures together in every run. Still a two-fixture foundation, not the broad real-app matrix named in this gap's original scope - do not read this as GAP-0105 closure.
**Batch 05 (Milestones 1-2):** `PARTIAL` — the suite grew from 32 to 45 cases: Milestone 1 added 5 read-only visual-OCR cases (bounded/no-raw-coordinate schema, dependency-unavailable degrade, sensitive-window denial before capture, untrusted-OCR-text-cannot-self-authorize, visual references rejected everywhere as targeting input); Milestone 2 added 8 bounded-recovery cases (cuv2-38 through cuv2-45: stale-ref bounded recovery, moved-element fresh bounds, approval re-check strictness, end-to-end focus-race recovery, no-retry after an uncertain drag/click/invoke side effect, exhausted-recovery-budget clean failure). Still the same two-fixture (plus visual-OCR-capable) foundation - the broad real-app matrix (Notepad, Explorer, Settings, VS Code, terminal, dialogs, multi-window) remains out of scope; do not read this as GAP-0105 closure.
**Batch 06 (Milestones 0-2):** `PARTIAL` — the suite grew from 45 to 46 cases (cuv2-46: one drag recovery budget shared across pre-focus/post-focus grounding, R18B05-003). A third owned Win32 fixture (`uia_ocr_fixture_host.py`, Arabic/mixed OCR acceptance) and a fourth (`uia_recovery_fixture_host.py`, deterministic MOVE/REPLACE bounded-recovery acceptance) were added, both driven through dedicated physical runners with real production tool paths, 3/3 clean runs each. Still a four-fixture foundation, not the broad real-app matrix named in this gap's original scope - do not read this as GAP-0105 closure.

**Batch 08 M0:** `PARTIAL` (unchanged). The corrected evaluator was re-run for three clean A/B/C configurations; no production OCR routing or input behavior changed. The full measurements and failed Candidate C gates are in `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_08.md`.

**Batch 08 M1/M2:** the deterministic Computer Use V2 suite now contains 53
cases, including approval-gated visual click, stale-refusal, ambiguity,
approval-drift, and post-input-uncertainty contracts. The owned-fixture
physical runner remains a foundation rather than the broad real-app matrix
named by this gap. **Batch 09 T1** adds the finite, hard-opt-in owner-session
runner with privacy-safe receipts and no automatic startup/pytest/CI trigger;
the default Calculator scenario handler now provides the first bounded
real-application orchestration slice through the canonical typed services, with
exact semantic grounding and independent result readback. At the T1 checkpoint
the handler was unit-tested only; physical owner-session results are recorded
in the Batch 09 T2 continuation below. **Batch 09 T2
continuation (2026-09-15):** the existing owner/device identity was enabled
only through process-local opt-in, and `RW-CALC-001` passed 3/3 with exact
semantic grounding and independent `Display is 391` readback. Brave provenance
was recorded from standard installation paths, but the host-only open/focus
attempt remained `PARTIAL` (3/3 fail-closed `brave_window_ambiguous`); no
browser navigation/authentication was attempted. `GAP-0105` remains `PARTIAL`;
no full multi-application acceptance claim is made.

**Native desktop application addendum (2026-09-19):** `5a0ea52` carries the
bounded `InstalledApplicationRegistry` as the preferred local application
surface. Standard Start Menu roots, Windows App Paths, and explicit known-app
fallbacks produce opaque `app_ref` descriptors; exact targets are
SHA-256/fingerprint revalidated before launch, duplicate aliases fail closed,
and admin/installer/background targets remain denied. `ComputerActionService`
owns open/focus, fresh window identity, foreground verification, audit, and
local-only enforcement; the UI exposes owner enable/disable and surface
preferences. The inspected host catalogued 162 bounded entries. Deterministic
registry/boundary tests and frontend tests/build are green. The canonical
physical Notepad probe launched and observed the app but failed closed on
foreground verification (`application_focus_not_verified`) in the
non-interactive runner, so this remains `PARTIAL`/launch-only and does not
close the broad real-app matrix or grant Tier A/B acceptance.

### GAP-0106 — Multi-monitor/DPI/secure-desktop behavior needs explicit proof
**Status:** `PARTIAL`  
Computer Use V2 must handle DPI/window movement/multiple monitors and fail safely on secure/locked/UAC-style surfaces it cannot control.  
**Batch 02 Milestone 2:** `PARTIAL` — unit-level virtual-desktop coordinate math is proven for negative X/Y origins, extended-desktop dimensions, exact edges, and degenerate geometries (Milestone 1's `CoordinateMathTests`). NIGHTFURY's real topology was recorded (not altered): `SM_XVIRTUALSCREEN=-1920`, `SM_YVIRTUALSCREEN=0`, `SM_CXVIRTUALSCREEN=3840`, `SM_CYVIRTUALSCREEN=1080`, `SM_CMONITORS=2`, primary-monitor DPI 96 (100% scaling) - a genuine two-monitor extended-desktop machine, matching exactly the negative-origin/extended-dimension scenarios already unit-tested. No live click was separately re-demonstrated with the fixture explicitly positioned on the non-primary (negative-X) monitor this batch - Calculator opened on the primary monitor by default and no window-move capability exists in scope to relocate it; record `MULTI_MONITOR_PHYSICAL_PENDING` for that specific live-secondary-monitor click, not for the topology evidence itself. No non-100%-DPI monitor is available on NIGHTFURY, so DPI physical proof stays partial per the task's own explicit allowance. Secure-desktop/UIPI: policy/unit tests exist (sensitive-window denial, `native_input_injection_failed` for partial/zero SendInput), docs state UIPI can block higher-integrity targets and JARVIS does not bypass it (no elevation, no UIAccess anywhere in the code) - no UAC surface was deliberately triggered to "test" it, per the task's explicit prohibition.  
**Batch 03 Milestone 2 (non-primary monitor physical proof):** the `MULTI_MONITOR_PHYSICAL_PENDING` item above is now closed. The owned fixture host gained an evaluation-only `--x`/`--y` launch flag (never a general production window-move capability); the runner confirmed NIGHTFURY's real topology still shows a negative-X monitor (`x_origin=-1920, width=3840, monitor_count=2`), launched the fixture at `x_origin+100`, confirmed via semantic read that the target element's bounds were genuinely on the non-primary monitor (`x < 0`), and performed a grounded native left click there - independently verified via the fixture's own status read-back (`"invoked"`). Recorded `NON_PRIMARY_MONITOR_PHYSICAL_PASS` 3/3. DPI (no non-100% monitor available) and secure-desktop physical proof (no UAC surface deliberately triggered, per the task's prohibition) remain pending - `GAP-0106` stays `PARTIAL`, not `RESOLVED`.

## 4. P1 — Browser + web extraction

### GAP-0201 — Live Playwright action adapter is not active in default runtime
**Status:** `PARTIAL`
Batch 10 T1 adds the optional lazy Playwright controller and live
navigation/read foundation behind the existing `BrowserActionService`, with
exact Brave executable validation, typed provider failures, and owned
context/process cleanup. **Batch 10 T3 (2026-09-18)** adds bounded
DOM/accessibility grounding, opaque element references, actionability checks,
approval-bound click/type/select, target-drift refusal, and independent
verification behind the same service. The implementation gate is PASS with
deterministic evidence; the default runtime remains Local and physical owner /
authenticated acceptance remains open under later Batch 10 gates. **Batch 10
T5 (2026-09-18)** adds bounded Playwright-context file transfer and transient
screenshot workflows behind the same service: downloads require an existing
`FileAccessPolicy` root and policy-checked redirects with atomic temp-file
publication and final size/SHA-256 verification; uploads require a permitted
non-sensitive file and opaque file-input approval binding; screenshots return
only an opaque transient reference and never persist raw bytes. T5 is PASS on
deterministic generated-fixture evidence; physical owner/authenticated
acceptance and the T6 red-team matrix remain open.
**Final-completion W1 (2026-09-18):** `FINAL-001` fixed the product desktop
capability profile so the canonical existing owner device can advertise the
Browser V2 action set during normal identity reconciliation. The active
interpreter has Playwright `1.63.0`; the bounded owner runner launches the
exact signed Brave executable with the dedicated JARVIS profile, but the live
shell is empty and a disposable exact-Brave probe receives HTTP 403 from
`chatgpt.com`. No authenticated browser result is claimed. The installed
ChatGPT desktop app is a separate manual surface and does not substitute for
the required Browser V2 evidence.
**Batch 09 boundary (2026-09-15):** the existing `LocalBrowserController` is
not a live authenticated Brave/session adapter. `RW-BRAVE-001` therefore stops
after the bounded host-only phase and classifies navigation/authenticated web
control as `CROSS_WORKSTREAM_BLOCKER`; no Playwright dependency or second
browser authority was added in Workstream A.

### GAP-0202 — Browser upload/download workflows are missing
**Status:** `PARTIAL`
**Batch 10 T5 (2026-09-18):** bounded optional-Playwright workflows now use
the existing `FileAccessPolicy` for explicit approved-root downloads and
sensitive/outside-root upload denial, the existing `BrowserURLPolicy` for
zero-automatic-redirect URL checks, atomic partial-file cleanup, final size and
SHA-256 verification, and T3 opaque target bindings for uploads. Screenshots
are on-demand and transient in memory only. Deterministic T5 tests pass;
physical/live owner-authenticated acceptance and the broader T6 abuse matrix
remain open.

### GAP-0203 — Production web extraction stack needs implementation
**Status:** `PARTIAL`
**Batch 10 T4 (2026-09-18):** the dependency-free Local controller now provides
bounded static extraction with visible/main text, headings, normalized safe
links, safe metadata, final URL validation, body/text/item limits, and
provenance digests. The optional Playwright controller provides the equivalent
bounded dynamic DOM extraction without `networkidle`, arbitrary JavaScript, or
full HTML dumps. Research remains a separate authority; broader authenticated
research-provider integration and advanced parser selection remain open.

### GAP-0204 — Real-world prompt-injection/red-team matrix needs expansion
**Status:** `PARTIAL`
Phase 15 closed schema/URL/security gaps. Batch 10 T6 adds a deterministic
red-team matrix covering hostile page text, hidden instructions, stale and
ambiguous targets, approval replay, iframe confusion, download traps, upload
secret paths, and raw screenshot retention; all current bounded tests pass with
zero authority escalations. Live hostile-site coverage, authenticated owner
acceptance, and universal prompt-injection resistance remain open.

### GAP-0205 — Browser session/profile policy needs product decision and implementation
**Status:** `RESOLVED` (Batch 10 T2, 2026-09-18)
DEC-049 accepts isolated ephemeral contexts for anonymous work and an explicit
owner-opt-in dedicated JARVIS persistent Brave profile for manually
authenticated owner workflows. Normal Brave/Chrome/Edge profiles are rejected;
cookies, tokens, credentials, and profile databases remain outside
model-visible/audited data. T2 policy tests and a two-run dedicated-profile
close/reopen gate passed in `docs/audits/PHASE_18_WORKSTREAM_B_BATCH_10.md`.

## 5. P1 — Agent delegation and execution quality

### GAP-0301 — Specialist roster is product direction, not yet a fully formalized runtime contract
**Status:** `OPEN`  
The existing `WorkerCoordinator` now passes a bounded `SpecialistTaskEnvelope` with owner/mission/goal/scope, capability grants, budget, deadline, cancellation, evidence, expected output, and verifier requirements. Workers remain proposal/analysis adapters and do not gain a second side-effect authority. Mission checkpointing and a live specialist roster remain open.

### GAP-0302 — Verifier role must be independent from “action returned success”
**Status:** `OPEN` (Home Assistant instance `RESOLVED` — see below; general cross-domain verifier contract remains open)  
For computer/browser/device/communications actions, define verification evidence that can prove the requested post-condition.  
**F18A1-002 (Phase 18A.2, 2026-09-12):** `HomeAssistantTransport.execute()` previously set `verified` from the outbound HTTP status alone (`200 <= status < 300`), a direct instance of this gap. Fixed: verification now requires an independent, bounded (single-attempt, no polling) state read-back via `GET /api/states/{entity_id}` compared against the intended effect for `turn_on`/`turn_off`/`set_brightness`/`set_temperature`; `set_color`/`trigger_scene` have no deterministic comparable state and are honestly reported as unverified rather than guessed. `src/jarvis/devices/home/service.py::HomeAssistantTransport._verify_state`. Tests: `tests/test_phase_eighteen_stabilization.py::test_home_assistant_reports_verified_only_after_matching_independent_readback`, `::test_home_assistant_does_not_claim_verified_when_state_does_not_change`, `::test_home_assistant_does_not_claim_verified_when_readback_unavailable`, `::test_home_assistant_unverifiable_action_is_reported_truthfully`. The broader gap (a general cross-domain verifier contract for computer/browser/communications) remains open.

### GAP-0303 — Long-running mission recovery/idempotency needs Phase 18 stress testing
**Status:** `OPEN`  
Mission restart semantics are implemented, but run crash/restart/timeout/duplicate-event/concurrent-resume scenarios must be included in production hardening.

### GAP-0304 — Live developer worker adapter is not configured
**Status:** `OPEN/P2`  
`CodexDeveloperWorkerAdapter` now provides a bounded read-only `codex exec`
path with exact workspace scope, ephemeral execution, output redaction, and no
write mode. Focused tests pass, but the current disposable live smoke timed out
before provider output, so authentication/provider availability and independent
postcondition verification remain open. Runtime must not depend on
AntiGravity/Google auth.

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

**Batch 05 Milestone 0 (R18B04-001, streaming closure):** an independent review of Batch 04 found `iter_search_candidates()` still called `list(os.scandir(current))` per directory before enforcing the scan budget - safe (the boundary/pruning logic was already correct) but capable of materializing an arbitrarily large single directory before the budget stopped it. The per-directory loop now consumes `os.scandir()` directly as a live iterator (checking the scan budget *before* each `next()` call, inside a `with` block for guaranteed handle cleanup on early return), so the budget is enforced without ever building an intermediate list, proven by an instrumented fake iterator that records exactly how many entries were pulled (`tests/test_phase_eighteen_file_access.py::FileAccessPolicyStreamingScandirTests`, 39 tests total in the file). Scope remains unchanged - read/open/search path confinement only.

**Final-completion W3 slice (2026-09-18):** `computer.files.manage` now adds
approval-gated, bounded `create_text`, `replace_text`, `copy_file`,
`move_file`, `rename_file`, and Windows `recycle_file` operations behind the
same `ComputerActionService`/`FileAccessPolicy` path. Text arguments remain
ephemeral and approval previews retain only length/digest; destination parents
must already exist, final reparse targets are denied, writes are atomic or
exclusive, and every mutation independently verifies the resulting state.
The focused integration/tool suite is green (`145 passed`). This advances
the broader file experience but does not close file dialogs, cross-window
drag/drop, owner-file acceptance, or general unrestricted system operations.

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
**Status:** `PARTIAL`
`.github/workflows/ci.yml` now defines deterministic Python tests/compile checks
on Windows and frontend tests/build/high-severity audit on Ubuntu for pull
requests and main/feature pushes. A hosted run and repository-required-check
branch protection have not yet been observed/configured, so this gap remains
partial rather than resolved.

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

## 14. Final-completion addendum (2026-09-18)

This addendum is the current feature-branch truth for the slices completed
after the earlier Phase 18 snapshot:

- **GAP-0301 — `PARTIAL`:** `WorkerCoordinator` now carries a bounded
  `SpecialistTaskEnvelope` with owner/mission/goal/scope, capability grants,
  budget/deadline/cancellation, input evidence, expected output, and verifier
  requirements. Mission checkpointing and a live specialist roster remain open.
- **GAP-0302 — `PARTIAL`:** worker results carry explicit
  `executed`/`delivered`/`verified`/`unverified`/`failed` states. Successful
  provider output is `unverified` until an independent verifier callback
  supplies bounded evidence; cross-domain post-condition verifiers remain open.
- **GAP-0503 — `PARTIAL`:** approved-root file mutations are implemented and
  tested through the canonical file authority; safe bounded insertion is now
  available as `computer.keyboard.paste` using Unicode typing without owner
  clipboard access. File dialogs, file drag/drop, owner-file acceptance, and
  unrestricted system operations remain out of scope.
- **GAP-0803 — `PARTIAL`:** desktop diagnostics report UI server,
  browser/profile policy, Computer Use, approved roots, scheduler, EventBus,
  backup, notifications, and integration readiness without reading owner
  content. The full model/provider/DB/node/browser/voice/restart fault matrix
  still needs execution evidence.

## 15. Final release closure addendum — 2026-09-18

The closure run adds current evidence without reopening resolved historical
gaps:

- **GAP-0801 — `RESOLVED`:** hosted CI initially failed because the default
  dev install omitted test-time numpy and Pillow, fixed-thread defaults were
  invalid on a low-CPU runner, the clean-tree gate compared an unresolved
  extraction root, and a Phase 6 test could scan the whole checkout before an
  assertion left its SQLite runtime open. Commits `64fd312`, `354437d`, and
  `71157dd` apply the narrow reproducibility/test-isolation repairs. Hosted
  run `35355436554` at `71157dd` is green: Python `951 passed, 3 skipped`,
  compile passed, and frontend tests/build/high-severity audit passed.
- **GAP-0803 — `PARTIAL`:** local recovery/security slices are green, but the
  owner/browser/voice/model/node/restart matrix is not fully physically run.
- **GAP-0804 — `RESOLVED`:** a read-only backup of the live current-schema
  database restored into an isolated temporary database with integrity and
  representative schema/row checks; the live database was not overwritten.
- **GAP-0805 — `OPEN/P2`:** no separate current performance/resource budget was
  measured for the complete desktop release.
- **GAP-0806 — `PARTIAL`:** local prompt-injection, SSRF/browser boundary,
  path/junction, stale-reference, approval, credential-automation, and secret
  retention checks are green; owner-service and physical red-team surfaces
  remain unconfigured or pending.

Owner-authenticated integrations, physical voice, and the final natural-
language cross-app mission remain blocked by missing owner-controlled
configuration/evidence, not silently treated as complete.

## 16. Native desktop application addendum — 2026-09-19

- **GAP-0105 — remains `PARTIAL`:** the native installed-application addendum
  is implemented and is the preferred desktop surface, but only bounded
  catalog/identity and launch/focus code are accepted. The generic-app
  physical focus probe failed closed, and the broad multi-application,
  semantic-workflow, recovery, and Tier A/B acceptance matrix remains open.

- **GAP-0201/GAP-0205 — remain `PARTIAL` / `OWNER_ACTION_REQUIRED`:** the
  process-local T06 preflight reached the exact ChatGPT origin through the
  dedicated JARVIS Brave profile with the existing owner/device identity, but
  the authenticated shell was `uncertain`. No credentials or nonce-send action
  was attempted; manual authentication and explicit send confirmation remain
  outside unattended execution.

## 17. Autonomous completion continuation — 2026-09-19

- **GAP-0803 — remains `PARTIAL`:** canonical health projection now exposes
  provider, desktop, browser, worker, voice, and service-surface degradation
  states; deterministic recovery/security suites remain green. Owner
  authentication, external-provider failure, physical voice/device loss, cold
  lifecycle, and cross-app restart evidence remain required.
- **GAP-0804 — `RESOLVED`:** current live SQLite backup, integrity check,
  isolated restore, restored open, owner-row, and memory-table checks passed
  without overwriting the live database.
- **GAP-0805 — `PARTIAL`:** bounded observations cover runtime composition and
  start, deterministic route selection, memory retrieval, Computer Use
  dry-run, installed-app registry cold/warm lookup, ephemeral Brave
  startup/open, wake fixture, and frontend build. No local weight startup or
  first-token, authenticated browser, physical audio, or production resource
  ceiling is claimed; first app-catalog refresh remains a future budget
  candidate.
- **GAP-0806 — remains `PARTIAL`:** authority and structural scans found no
  new duplicate authority or unbounded secret surface; owner-service and
  physical red-team evidence remain pending.
- **P3 service integrations — `PARTIAL`:** bounded native-first adapters,
  exact target resolution, ambiguity rejection, and canonical open/focus
  readback are implemented and tested. Real login, semantic playback,
  compose/send/edit, authenticated browser, and independent physical
  postconditions remain gates.
- **P10 integration UX — `PARTIAL`:** Settings exposes backend-derived
  integration status cards and native installed-app Test/Open actions; it does
  not fabricate active study sessions, login state, or service readiness.

## 18. Pre-physical deep review closure — 2026-09-19

The pre-physical review found nine code-controlled issues (`PRP-001` through
`PRP-009`). All are resolved in implementation commit `a129ddc`; no P0/P1
code-controlled blocker or required P2 daily-use blocker remains. The field-
level evidence is owned by
`docs/audits/JARVIS_PRE_PHYSICAL_ISSUE_REGISTER.md`.

The resolved findings cover approval replay and principal binding across the
generic tool, browser, communications, engineering, and computer paths;
large-context hybrid routing; World State owner binding; Memory metadata
credential filtering; truthful file-open verification; and fixed-location
installed-app compatibility resolution. No new authority or scheduler was
introduced.

The remaining open entries are correctly classified as owner configuration,
external service surface, optional hardware, or physical acceptance. In
particular, Groq/Gemini keys, owner-authenticated browser/service workflows,
Heretic runtime readiness, interactive application focus, voice, cold
lifecycle, and cross-app receipts remain open and are not code defects.

## 19. Local Heretic model readiness review - 2026-09-19

- **Heretic local runtime - `LOCAL_HERETIC_LIVE_READY`:** the exact local
  identity is enforced by `JarvisConfig`, desktop settings, bounded discovery,
  `LlamaCppRuntimeConfig`, and the hybrid gateway. The owner-provided
  `Qwen3.5-4B-Heretic-Q4_K_M.gguf` is now installed in the canonical JARVIS
  model root, independently hash-verified, and served live by the existing
  loopback-only llama.cpp runtime.
- The existing external 9B Heretic GGUF and `.invalid-resume` artifact were
  preserved. They are not valid substitutes and were not deleted because
  active voice/OCR usage was not disproven.
- Hybrid mode reports the exact local provider and does not assume Ollama.
  Groq/Gemini fallback remains capability-based and key-gated; protected
  current-user credentials and non-secret provider enablement are now wired
  through the normal desktop/CLI settings authority. Settings update,
  autostart, multilingual/offline live smoke, process cleanup, and resource
  observations are complete. The unsigned runtime is recorded as a provenance
  limitation, not treated as a signature.
- Evidence: `docs/audits/JARVIS_LOCAL_MODEL_READINESS.md`.

## 20. Three-model cloud enablement closure - 2026-09-20

- **Three-model live brain - `THREE_MODEL_LIVE_READY`:** the exact Groq
  `openai/gpt-oss-120b` and Gemini `gemini-3.5-flash` providers are enabled by
  persisted non-secret settings and receive their credentials only from the
  existing protected current-user store. The normal desktop lifecycle and
  `python -m jarvis` resolve the same settings authority; provider probes do
  not force enablement.
- Fresh-process acceptance passed with both cloud environment variables
  removed: Groq catalog plus direct generation, Gemini metadata plus text and
  vision generation, and local Heretic generation. No raw credential was
  written to settings, environment, SQLite, Memory, logs, or audit evidence.
- Evidence: `docs/audits/JARVIS_THREE_MODEL_LIVE_ACCEPTANCE.md`.
