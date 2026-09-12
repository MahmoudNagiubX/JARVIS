# PHASE 18 — WORKSTREAM A — BATCH 02
## Semantic Safety Hardening → Grounded Native Input → Repeatable Computer-Use Evaluation

**Task:** `tasks/CLOUD_CODE_MASTER_PHASE_18_WORKSTREAM_A_BATCH_02.md`
**Branch:** `feature/phase-18-computer-use-v2`
**Status:** IN PROGRESS — Milestone 0 complete, Milestones 1/2 not yet started.

This is the single report for the whole batch (per Section 11 of the task file);
it is appended to, not duplicated, as later milestones complete.

---

## 1. Starting branch/HEAD

- Branch: `feature/phase-18-computer-use-v2`
- Starting HEAD: `2390ddc7aaa7be3596826027e4cd351d919643c8` (`feat: add bounded semantic UI actions`, Batch 01 Milestone 3)
- Branch was in sync with `origin/feature/phase-18-computer-use-v2` (no unexplained divergence) at the start of this batch.

---

## 2. Independent review findings (Batch 01)

Five findings against the code pushed in Batch 01, all closed in Milestone 0 below:

| ID | Summary | Disposition |
| --- | --- | --- |
| R18B01-001 | A missing/erroring `GetRuntimeId()` was hashed into a fake "strong" digest via `repr(())`, collapsing all weak-identity elements onto the same identity. | Fixed — explicit `identity_strength: strong\|weak` model; weak refs never actionable. |
| R18B01-002 | `list_windows()` returned raw `WindowsDesktopProvider.desktop_context()` output with no privacy filtering, leaking sensitive window titles/processes. | Fixed — denies the whole call when privacy mode is OFF; filters every window failing `PerceptionPrivacyPolicy.check_window()`. |
| R18B01-003 | Post-action verification (toggle/select/invoke) re-read the *same* pre-action pattern/control object, which can be stale/destroyed by the action itself. | Fixed — a full fresh re-resolution (`_reresolve`) plus a fresh `GetPattern()` call happens after every action; never the pre-action object. |
| R18B01-004 | Semantic approval preview showed only `semantic_invoke` + an opaque `element-<uuid>`; generic ~10 min approval expiry could outlive the ~45s element-ref TTL. | Fixed — target-aware bounded preview built from a fresh trusted read, approval refused up front for stale/weak/non-actionable targets, target-identity digest re-checked on `decide()`, expiry bounded by the element-ref TTL. |
| R18B01-005 | No explicit fail-closed check for disabled/offscreen/weak-identity targets immediately before actuation. | Fixed — `_reresolve_actuation_target()` denies weak identity, sensitive/password, disabled, and offscreen targets with typed codes before any pattern call. |

---

## 3. Milestone 0 — Semantic safety hardening

**Commit:** `MILESTONE_0_COMMIT` (recorded in Section 6.5 below after push)

### 3.1 Strong/weak identity (R18B01-001)

- `_runtime_id_identity()` (`semantic_uia.py`) returns `(digest, is_strong)`; a missing, empty, or exception-raising `GetRuntimeId()` now yields `(None, False)` — never a fabricated digest.
- `_ElementRefEntry.identity_strength: "strong" | "weak"` is stored per reference at observation time.
- `_reresolve()` branches: strong references match by RuntimeId digest equality; weak references match by a bounded composite (AutomationId + control_type + name + bounded ancestry), and a weak match must be **unique** in the bounded tree or resolution fails `uia_element_ambiguous`.
- `SemanticElementSnapshot.actionable: bool` is a new, minimal model-visible field (`actionable = is_strong and enabled and not offscreen and not is_password`). It never exposes RuntimeId, digest, or *why* — only whether the target is currently a legitimate actuation candidate.
- `_reresolve_actuation_target()` refuses weak identity with `uia_element_identity_weak` before any pattern is touched.

### 3.2 Privacy (R18B01-002)

- `list_windows()` now denies the entire call (`privacy_policy_denied`) when `PerceptionPrivacyPolicy.allows_metadata()` is false, instead of silently returning nothing/partial data.
- Every window is checked with `privacy_policy.check_window(process_name, title)`; a match is dropped from the result entirely (never returned, not even in redacted form) and only counted in a new `filtered_count`.
- `computer/service.py`'s `_semantic_list_windows` surfaces `filtered_count` to the model-facing `ComputerResult` payload alongside the (already filtered) window list.

### 3.3 Fresh verification (R18B01-003)

- `invoke()`, `toggle()`, `select()` each call `self._reresolve(element_ref)` again *after* the pattern call, never trusting the pre-action `Control`/pattern object.
- A target that disappears post-action (closed dialog, navigation, stale, ambiguous, window gone) is reported as `succeeded, verified=False` with a bounded `verification_reason` (`target_disappeared_after_invoke`, `post_observation_unavailable`) — never an uncaught exception, never a fabricated `verified=True`.
- `toggle()`/`select()` additionally fetch a **fresh** pattern object (`_get_pattern(fresh_control, pattern_id)`) for the post-action state read; the pre-action pattern object/variable is never reused for that read. `pre_state`/`post_state` (renamed from Batch 01's `toggle_state_before`/`toggle_state_after`) are bounded receipt fields; no auto-retry is performed anywhere.

### 3.4 Approval target binding/TTL (R18B01-004)

- New `ComputerActionService._semantic_target_preview()` fetches a fresh, trusted snapshot through the **existing canonical read path** (`self.controller.execute(ComputerAction("semantic_get_element", ...))` — the same `semantic_get_element` capability the model already uses, not a new adapter method or a second authority).
- Before creating an approval for `semantic_invoke`/`semantic_toggle`/`semantic_select`, this preview is fetched; if the fetch fails or the target's `actionable` is `False`, approval creation is refused outright (typed `denied` result, no approval record minted, no execution).
- The preview shown to the approver is bounded and safe: `action`, `control_type`, `automation_id`, a name truncated to 80 chars, `window_ref`, `element_ref` — never text/value contents, never a raw parameter dump, never model-supplied text.
- A bounded identity digest (hash of `element_ref` + fresh `window_ref`/`control_type`/`automation_id`/`name`) is stored in `ComputerActionService._pending` alongside the existing pending-action tuple.
- On `decide()`, the same preview fetch runs again and the digest is recomputed; if it no longer matches (target renamed/replaced) the action is refused with `approval_target_changed` and never executes; if the re-fetch itself fails, a typed stale failure is returned instead.
- `approval_expires_at = min(now + 10 minutes, now + ELEMENT_REF_TTL_SECONDS)` for these three actions specifically (imported from `semantic_uia.ELEMENT_REF_TTL_SECONDS = 45`), so the approval can never legitimately outlive the element reference it targets.

### 3.5 Interactability (R18B01-005)

- `_reresolve_actuation_target()` fails closed, after a fresh re-resolution, on: weak identity (`uia_element_identity_weak`), password/sensitive (`uia_sensitive_value_denied`), disabled (`uia_target_not_interactable`), and offscreen (`uia_target_not_interactable`) — all before any pattern object is even fetched.
- Combined with 3.4, a non-actionable target is refused **twice**, independently: once at approval-creation time (preview refusal) and again at actuation time (defense in depth; no single code path is trusted).

### 3.6 Physical semantic acceptance

**Approach:** a disposable Microsoft Edge **Guest** window over a temporary local HTML fixture (`file://` URI under the OS temp directory; inert button/checkbox/two-option `<select>`/status label; no owner profile, no login, no internet), driven strictly through `computer.semantic.read` / `computer.semantic.act` with normal approval — `uiautomation` was never called directly for acceptance. The fixture and the Guest browser instance were both deleted/closed after the probe.

**Finding — Chromium content is unreachable at the adapter's current bounded depth.** `inspect_window`/`find_elements` walk at most `MAX_INSPECT_DEPTH = 5` levels from the top-level window. Live inspection showed that in a real Edge (Guest) window, all 5 levels are consumed by the browser's own UI-automation wrapper chrome (`WindowControl` → nested `PaneControl`s → tab bar / minimize-maximize-close buttons) before the actual rendered page (DOM) is ever reached — `find_elements` for `ButtonControl`/`CheckBoxControl`/`ComboBoxControl` on the fixture page returned zero matches, not because Chromium fails to expose `Invoke`/`Toggle`/`SelectionItem` patterns on its own controls, but because the fixture's controls are structurally deeper than the bound allows. This is a genuine, reproducible limitation of the existing (Batch 01) bounded-depth design when applied to Chromium-based browser content specifically, not a defect introduced by this milestone's hardening, and not in scope to change here (`MAX_INSPECT_DEPTH` is an existing architectural bound, not part of R18B01-001..005). Per the task's own explicit fallback instruction ("If Chromium does not expose the required pattern... try another safe local surface... if none works, keep code/test acceptance and mark physical acceptance pending rather than fabricate success"), this path was not force-fixed and no toggle/select success is claimed from it.

**Incident during the search for an alternative surface:** a second attempt used `notepad.exe` as a candidate disposable surface. Windows 11's in-box Notepad turned out to be a single-instance app that reuses an already-open window rather than spawning an independent disposable instance; the probe's launch attached to the owner's real, already-open Notepad window (which had an unsaved/"Modified" tab), and the read-only inspection call plus the probe's own cleanup left that window with a single blank tab, with the prior unsaved content very likely lost (Notepad's on-disk session-state file was observed rewritten to a 20-byte blank-tab-only state with no recoverable history). No actuation (`invoke`/`toggle`/`select`) was ever called against this window, and this was disclosed to the owner immediately and in full before any further work continued; the owner confirmed no material harm and directed that all further physical acceptance in this batch use only disposable, non-owner surfaces (Edge Guest, Calculator) and never touch Notepad or other in-box apps that might reuse a live owner session again. This is recorded as a real, if minor, incident for the record — see `SendFeedback` draft queued this session — and as a concrete argument for treating *any* Windows in-box app as a potentially non-disposable surface unless independently confirmed multi-instance beforehand.

**What was physically proven:**

- **`invoke`** — re-confirmed end-to-end through the *fully hardened* pipeline (this milestone's R18B01-001/003/004/005 code, not just Batch 01's) on a freshly launched, confirmed-not-already-running, disposable Calculator instance: `computer.semantic.read find_elements` located the "Seven" button (`automation_id="num7Button"`, `actionable=true`, strong identity); `computer.semantic.act invoke` correctly required approval, the target-aware preview was created and matched on decide, the action executed, and reported `succeeded, verified=false, verification_reason="generic_invoke_no_postcondition"` (honest, non-fabricated); an **independent** second `find_elements` call (not the action's own report) against `automation_id="CalculatorResults"` read back `"Display is 7"`, physically confirming the real effect. The disposable Calculator instance was then closed.
- **`toggle` / `select`** — **not physically re-demonstrated live this batch.** No safe, disposable, semantically-reachable `TogglePattern`/`SelectionItemPattern` control was found within this batch's time-boxed scope (Edge Guest fixture blocked by the depth limitation above; Calculator has no toggle-capable control per Batch 01's own finding; Notepad ruled unsafe by the incident above; no further owner-app exploration was attempted per the owner's directive). This remains **code/test acceptance only**: 9 deterministic `semantic_uia` unit tests plus 13 approval/architecture tests exercise toggle/select — including new tests added this milestone for fresh-post-action re-observation (a fake control whose `GetPattern()` mints a new, "freezes at fetch" pattern instance every call, proving the adapter fetches a genuinely fresh post-action pattern rather than reusing the pre-action reference or object identity) — but this is disclosed honestly as test evidence, not physical evidence (AGENTS.md §6).
- **Weak identity, disabled/offscreen/password denial, approval-target-changed, and approval-TTL binding** are all proven by deterministic unit/integration tests (fakes) only in this batch; no live weak-identity/disabled/offscreen Windows control was independently sourced for physical demonstration within scope.

### 3.7 Tests

New/updated test modules:

- `tests/test_phase_eighteen_semantic_uia.py` — 38 tests (was 22): added `list_windows` privacy-filtering tests (denied-process/denied-title filtering, `filtered_count`, privacy-mode-OFF denial), weak-identity tests (missing RuntimeId, raising RuntimeId, weak-ref actuation denial, weak-composite ambiguity), `actionable` field coverage (strong ref stays actionable), disabled/offscreen pre-actuation denial, and three fresh-post-action-observation tests (destroyed target → unverified not an exception; a "freezes at fetch" fake pattern proving a genuinely fresh `GetPattern()` call is used post-action, not the cached pre-action reference; provider raising after the action → `post_observation_unavailable`). Renamed `toggle_state_before`/`toggle_state_after` references to `pre_state`/`post_state`.
- `tests/test_phase_eighteen_semantic_actions.py` — 17 tests (was 13): added approval-preview-content test (bounded fields, no secrets/text/value/raw-parameter-dump), pre-approval refusal when the target read fails, target-changed-after-request-before-decide refusal (`approval_target_changed`), and approval-expiry-bounded-by-element-ref-TTL. Updated the password-control test: it now asserts refusal *before* approval creation (`uia_target_not_actionable`, no approval minted) rather than denial after approval, matching R18B01-004/005's fail-closed-earlier behavior.
- `tests/test_phase_eighteen_semantic_tool_path.py` — unchanged, still green (12 tests).

Results:

```text
python -m pytest tests -k "phase_eighteen" -q
85 passed, 515 deselected

python -m pytest tests -q
600 passed, 36 subtests passed

python -m compileall src tests -q
(clean)

git diff --check
(clean)
```

Frontend suite was not run for Milestone 0 (no frontend files touched; deferred to the final batch gate per Section 6.3 of the task file).

### 3.8 Commit

- **Files staged (explicit paths, no `git add .`):** `tasks/CLOUD_CODE_MASTER_PHASE_18_WORKSTREAM_A_BATCH_02.md`, `src/jarvis/computer/semantic_uia.py`, `src/jarvis/computer/service.py`, `src/jarvis/contracts/semantic_ui.py`, `tests/test_phase_eighteen_semantic_uia.py`, `tests/test_phase_eighteen_semantic_actions.py`, `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_02.md`.
- **Commit message:** `fix: harden semantic computer-use targets`
- **MILESTONE_0_COMMIT:** `f365d144180095e12699940fadf6a5331ad20690`

---

## 4. Milestone 1 — Grounded native input fallback

**Commit:** `MILESTONE_1_COMMIT` (recorded in Section 4.7 below after push)

### 4.1 Native input architecture

- New module `src/jarvis/computer/native_input.py` with `WindowsNativeInputAdapter` — an execution provider, not an authority, reachable only through `WindowsNativeComputerController` → `ComputerActionService`, exactly like `WindowsUIAutomationAdapter`.
- **No second input authority:** the shared low-level SendInput primitives (`_KEYBDINPUT`, `_INPUT_UNION`, `_INPUT`, `key_input()`) now live in `native_input.py` as the single canonical definition; `computer/service.py`'s existing literal-typing (`_keyboard_action`/`type_text`) and media-key (`_send_key`) code paths were left in place unchanged (public behavior preserved exactly, all pre-existing tests stayed green) rather than risk broad churn moving them, per the task's own explicit fallback allowance ("If moving existing code would create high-risk broad churn, keep the behavior in place").
- **Reused, not re-derived, actuation-grade grounding:** a new `resolve_actionable_target(element_ref)` method was added to `WindowsUIAutomationAdapter` (and the `SemanticDesktopAdapter` Protocol) that performs the exact same fail-closed checks `invoke`/`toggle`/`select` already use (`_reresolve_actuation_target` — strong identity, enabled, not offscreen, not sensitive) but takes no action itself. Native mouse/keyboard grounding calls this rather than re-implementing weak/disabled/offscreen/stale detection a second time, so there remains exactly one place in the codebase that decides whether a target may be actuated.
- Targeting pipeline for mouse (`_ground`): resolve target once (strong/actionable/fresh bounds) → validate + focus the containing window → confirm foreground → **resolve the target again** (focus can change layout) → confirm foreground once more → only then compute the click point. Every step fails closed with a typed code; nothing is retried automatically.

### 4.2 Mouse

- Exactly two actions, both element-ref-grounded, no raw coordinates ever accepted: `move_to_element`, `left_click_element`. Deliberately **not** implemented: raw coordinate move/click, right click, double click, drag/drop, wheel scroll (all explicitly out of scope this milestone).
- Coordinates are provider-internal only — the center of the freshly re-observed element's bounds, normalized to the **entire Windows virtual desktop** (`SM_XVIRTUALSCREEN`/`SM_YVIRTUALSCREEN`/`SM_CXVIRTUALSCREEN`/`SM_CYVIRTUALSCREEN`), never the primary monitor alone. `SendInput` uses `MOUSEEVENTF_MOVE|ABSOLUTE|VIRTUALDESK` for movement and an `LEFTDOWN`/`LEFTUP` batch for click; `SetCursorPos`/deprecated `mouse_event` are never used.
- A target whose center falls outside the reported virtual desktop is rejected before any `SendInput` call.
- **Verification is honest, not fabricated:** `move_to_element` reads `GetCursorPos` back and reports `verified=True` only when the pointer actually landed within a small pixel tolerance of the grounded target — meaning only "the pointer reached the target," never "the application reacted." `left_click_element` is **always** `verified=False` generically (SendInput delivery is never proof of the intended semantic effect); bounded evidence (`input_batch_accepted`, `pointer_target_verified`, `target_window_foreground`) is returned instead so a separate evaluator can independently judge a specific scenario.

### 4.3 Keyboard

- New bounded named-key action (`press_key`, exposed as `computer.keyboard.key`) with a fixed 14-key allowlist (`tab`, `enter`, `escape`, `space`, arrows, `home`, `end`, `page_up`, `page_down`, `backspace`, `delete`) plus exactly one reviewed modifier combination, `shift+tab` — no raw VK integer, no scan code, no Windows key, no Ctrl+Alt+Delete, no arbitrary hotkey string; unsupported keys/combinations are denied (`native_input_key_not_allowed`) before any injection is attempted.
- Existing literal `computer.keyboard.type` behavior was preserved exactly (unchanged code path, all pre-existing tests green) — this milestone did not touch it beyond sharing the low-level `_INPUT`/`_KEYBDINPUT` structures.
- **User-interference safety (7.5):** before injecting, `GetAsyncKeyState` is checked for Shift/Ctrl/Alt/Win; if the owner is physically holding one of these (and it isn't one of JARVIS's own intended modifiers for this call), the action fails safely with `native_input_modifier_state_unsafe` rather than attempting to "correct" real physical input. Any modifier JARVIS itself presses is released in a guaranteed `finally` block — proven by a test that fails the key-press injection deliberately after a successful modifier press and confirms the release call still happens.
- Grounded and foreground-checked like mouse input: the target window is validated, focused, and confirmed foreground both before pressing any modifier and again immediately before the key press itself; a foreground change in between blocks the injection (`window_focus_not_verified`).

### 4.4 Virtual desktop coordinate math

- `normalize_virtual_desktop_point(x, y, vleft, vtop, vwidth, vheight)` is a pure, independently unit-tested function mapping a virtual-desktop pixel to SendInput's `0..65535` absolute space, with the virtual desktop's own corners mapped to `0`/`65535` exactly (not the primary monitor's corners) — correctly handling a negative virtual-desktop origin (a monitor extending left/above the primary), a "second-monitor-like" coordinate, exact edges on both axes, a defensive one-pixel-wide/tall degenerate case (no division by zero), a zero-area virtual desktop, and out-of-bounds rejection.

### 4.5 UIPI handling

- JARVIS never elevates itself and never requests UIAccess (no code path does either). A partial/zero `SendInput` count is reported as the generic, honest `native_input_injection_failed` — the implementation does not claim "UIPI blocked" unless that is independently provable, matching the task's explicit instruction not to over-attribute injection failures.

### 4.6 Physical acceptance

Per the owner's direction after the Milestone 0 Notepad incident (§3.6), physical acceptance in this milestone used **only** the already-proven-disposable Calculator instance (confirmed not already running before launch), never Notepad or any other in-box app that might reuse a live owner session:

- **Element-grounded click:** `find_elements` located Calculator's "Seven" button; `computer.pointer.act left_click_element` correctly required approval, executed after approval, and reported `input_batch_accepted=true`, `pointer_target_verified=true` (independent `GetCursorPos` confirmation the pointer physically reached the target), `target_window_foreground=true`, and — correctly, honestly — `verified=false` for the generic click itself. A **separate**, independent `computer.semantic.read` call against `automation_id="CalculatorResults"` then read back `"Display is 7"`, physically proving the real effect occurred (not the action's own self-report).
- **Named key:** before the key press, an independent semantic read showed "Seven" with `focused=true` (left over from the click above). `computer.keyboard.key` with `key="tab"` correctly required approval and executed after approval. A **separate**, independent semantic re-read afterward showed "Seven" now `focused=false` and "Eight" now `focused=true` — physically proving Windows keyboard focus moved via the native Tab key press.
- The disposable Calculator instance was closed (`taskkill /IM CalculatorApp.exe`) after the probe; confirmed no `CalculatorApp` process remained.
- Every action in both scenarios went exclusively through `computer.pointer.act`/`computer.keyboard.key` with normal approval; `uiautomation`/raw `SendInput` was never called directly for acceptance (only inside the product adapter itself).

### 4.7 Tests

New test module `tests/test_phase_eighteen_native_input.py` — 37 tests across four groups matching Section 7.10 of the task file:

- **Coordinate math** (9 tests, pure function, no adapter): primary monitor origin, primary monitor far edge, negative virtual-desktop origin, second-monitor-like coordinate, exact edges on both axes, one-pixel-wide/tall defensive math, zero-area virtual desktop, out-of-bounds rejection (all four sides).
- **Mouse** (12 tests): weak ref denied, disabled denied, offscreen denied (no bounds), stale denied, containing-window-foreground-verified, target-revalidated-after-focus (asserts the semantic re-fetch happens exactly twice), SendInput-partial-count-is-failure, pointer-position-mismatch-not-verified, pointer-position-match-is-verified, left-click-never-generically-verified-true, left-click-input-delivery-failure, target-outside-virtual-desktop-denied.
- **Keyboard** (10 tests): allowlist enforced (unsupported key denied), raw-VK-like string denied, unreviewed modifier combo denied (e.g. shift+enter), plain named key succeeds, modifier-currently-held fails safely, JARVIS's own modifier does not trigger the interference check, JARVIS-generated modifier always released, modifier released even when the key injection itself fails (guaranteed-cleanup test), foreground-change-before-key-press blocks injection, SendInput-partial-is-failure.
- **Architecture** (6 tests): pointer move/click and keyboard key each require approval and execute exactly once through `ComputerActionService` → `PermissionEngine` → `ApprovalEngine`; audit/event records exist; both new tool schemas contain no raw x/y/HWND/VK/scan-code/filesystem fields and their `key` schema is exactly the bounded allowlist.

Results:

```text
python -m pytest tests -k "phase_eighteen or phase_eleven or phase_ten" -q
179 passed, 458 deselected

python -m pytest tests -q
637 passed, 36 subtests passed

python -m compileall src tests -q
(clean)

git diff --check
(clean)
```

### 4.8 Commit

- **Files staged (explicit paths, no `git add .`):** `src/jarvis/computer/native_input.py`, `src/jarvis/computer/service.py`, `src/jarvis/computer/semantic_uia.py`, `src/jarvis/contracts/computer.py`, `src/jarvis/contracts/semantic_ui.py`, `src/jarvis/tools/registry.py`, `src/jarvis/authority/permissions/engine.py`, `tests/test_phase_eighteen_native_input.py`, `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_02.md`, `docs/source_of_truth/02_JARVIS_CURRENT_STATE.md`, `docs/source_of_truth/03_JARVIS_GAP_REGISTER.md`, `docs/source_of_truth/04_JARVIS_EXECUTION_ROADMAP.md`.
- **Commit message:** `feat: add grounded native input fallback`
- **MILESTONE_1_COMMIT:** `b903de94140b21af10a9cfd3bbffe26a85106561`

---

## 5. Milestone 2 — Repeatable Computer Use V2 evaluation suite

**Commit:** `MILESTONE_2_COMMIT` (recorded in Section 5.7 below after push)

### 5.1 Deterministic evaluation suite

- `src/jarvis/evaluation/computer_use_v2.py` — a `computer_use_v2` `RegressionSuite`/`EvaluationCase` set (17 cases), registered through the existing `EvaluationService.register()` in `bootstrap.py`. No `ComputerUseEvaluationServiceV2` or any second evaluation authority was created.
- Every case runs without a GUI or live Windows dependency (fakes at the OS/provider boundary — either a fresh `create_runtime()` harness with a fake `SemanticDesktopAdapter`, or the real `WindowsUIAutomationAdapter`/`WindowsNativeInputAdapter` classes driven against a fake control tree/provider from `src/jarvis/evaluation/semantic_uia_fixtures.py`).
- The 17 cases map directly to the task's minimum list: canonical-authority routing, sensitive-window filtering, weak-identity actuation refusal, stale-target refusal, approval target-change binding, approval-required enforcement, fresh post-action verification (a "freezes at fetch" pattern fixture proving the post-action read is never the cached pre-action object), generic-invoke-stays-unverified, toggle/select fresh evidence, native-pointer grounding, native-key foreground grounding, no-raw-coordinates/no-raw-VK/no-filesystem-parameter schema checks, `verified` field survival, UI-text-cannot-self-authorize, and wrong-target-execution-count-zero across a negative-scenario battery.
- All 17 cases pass: `17/17 evaluation cases passed`.

### 5.2 Evaluation metrics

Metrics tracked per the task's list are all directly observable from each case's structure rather than invented: pass rate (`EvaluationRun.summary`, e.g. `17/17`), wrong-action/policy-bypass count (case 17's `invoke_calls == []` assertion across the negative-scenario battery), stale-target refusal (case 4), verified-success correctness (cases 8/9/15 — `verified` is checked against the actual honest value, never assumed), unverified-success count (case 8), re-observation count (case 5's approval preview re-fetch, case 7's fresh-pattern-object proof). No "confidence percentage" of any kind is invented anywhere in this suite.

### 5.3 Physical acceptance runner

`scripts/phase18/computer_use_acceptance.py` — a durable, explicit opt-in development script (never imported by `AgentRuntime`/production startup; only runs when invoked directly via `python scripts/phase18/computer_use_acceptance.py --runs N`).

Safety properties implemented directly in response to the Milestone 0 Notepad incident and the task's explicit requirements:
- refuses on non-Windows (`platform.system()` check, tested);
- Calculator scenario **refuses to run** if `CalculatorApp.exe` is already running (`tasklist` pre-check) rather than risk attaching to an owner's existing session the way the Milestone 0 probe accidentally did to Notepad;
- Edge Guest scenario uses only a temporary local HTML file it creates itself, deleted in a `finally` block even on failure, and `--guest` mode (never the owner's normal profile, no login, no internet dependency);
- window matching is title-based against each fixture's own known signature ("Calculator" / "JARVIS Computer Use V2 Acceptance Fixture"), never a bare enumeration dump — the full window list from `list_windows` is inspected in memory and discarded, never logged or persisted;
- the Edge button search is filtered by the fixture's own exact label ("Invoke Me") specifically because a bare `control_type=ButtonControl` search can otherwise match Edge's own chrome buttons (Minimize/Maximize/Close/tab-bar) within the adapter's bounded inspect depth — this was caught and fixed during this milestone's own development (see 5.4);
- both fixtures' processes are killed in `finally` blocks; confirmed via `Get-Process` after every run that no `CalculatorApp`/`msedge` process and no temp fixture file were left behind;
- every action goes through `computer.semantic.read`/`computer.semantic.act`/`computer.pointer.act`/`computer.keyboard.key` with normal approval — `uiautomation`/raw `SendInput` is never called directly from the script;
- the structured summary persists only bounded pass/attempt booleans and already-known-safe fixture labels (e.g. "Seven"/"Eight"/"CalculatorResults", all JARVIS-authored), never a raw UI dump.

### 5.4 Required repeated physical runs (3x, same session)

Run with `python scripts/phase18/computer_use_acceptance.py --runs 3` on NIGHTFURY. **First attempt caught a real bug**, disclosed rather than hidden: window matching originally required an exact `process_name` match, but Windows 11's in-box Calculator is hosted by the shared `ApplicationFrameHost.exe` process rather than exposing `CalculatorApp.exe` on its own top-level window — the first run therefore reported Calculator as "not found" 3/3 (a script bug, not a product regression) while an unfiltered Edge button search happened to match one of Edge's own chrome buttons rather than the fixture (also a script bug — no owner-visible harm occurred; the click landed on Edge's own UI, and Edge was closed immediately after by the script's own cleanup either way). Both were fixed (title-based window matching; exact-label button filtering) and the runner was re-run clean:

| Scenario | Result (3 runs) | Evidence |
| --- | --- | --- |
| Calculator: semantic invoke | 3/3 | `status=completed`, independent display read-back matched `"Display is 7"` all 3 times |
| Calculator: native left click | 3/3 | `pointer_target_verified=true`, `input_batch_accepted=true` all 3 times; generic click correctly `verified=false` |
| Calculator: native Tab key | 3/3 | independent focus read-back confirmed focus moved Seven→Eight all 3 times |
| Edge Guest: invoke | 0/3 | `not_found` — Chromium page content unreachable at the adapter's existing `MAX_INSPECT_DEPTH=5` bound (see 5.5) |
| Edge Guest: toggle | 0/3 | same reason |
| Edge Guest: select | 0/3 | same reason |

No wrong-target execution occurred in any run. No approval was bypassed. Every Calculator/Edge process and temp file was confirmed cleaned up after each run and after the full 3-run session.

### 5.5 Toggle/Select physical proof

Still **not** available this batch. The exact observed pattern set for the Edge Guest fixture's checkbox/select controls could not even be recorded, because `find_elements` does not reach them at all — `inspect_window` at depth 5 (the adapter's maximum) shows the entire budget consumed by Edge's own UI-automation wrapper chrome (`WindowControl` → nested `PaneControl`s → tab bar / window buttons) before the actual rendered page is reached (documented in Milestone 0, §3.6, reproduced identically here). Production code was **not** altered to force this test to pass, per the task's explicit instruction. `toggle`/`select` remain code/test-proven only; this is the single largest remaining gap in this batch's physical evidence.

### 5.6 Multi-monitor / DPI / secure-desktop evidence

- **Unit-level (already in Milestone 1):** `CoordinateMathTests` covers negative virtual-desktop X/Y origin, extended-desktop dimensions, exact edges, and degenerate one-pixel geometries.
- **Physical environment (recorded, not altered):** NIGHTFURY is a genuine two-monitor extended desktop — `SM_XVIRTUALSCREEN=-1920`, `SM_YVIRTUALSCREEN=0`, `SM_CXVIRTUALSCREEN=3840`, `SM_CYVIRTUALSCREEN=1080`, `SM_CMONITORS=2`, primary-monitor DPI 96 (100%). This is exactly the negative-origin/extended-dimension shape already unit-tested. No display setting was altered to obtain this reading.
- Calculator opened on the primary monitor by default in the physical runs above; no window-move capability exists in scope to force it onto the non-primary (negative-X) monitor, so a live click physically executed with a negative absolute coordinate was not separately re-demonstrated this batch. Recording `MULTI_MONITOR_PHYSICAL_PENDING` for that specific scenario — the topology evidence itself is real and positive, not pending.
- No non-100%-DPI monitor/config is available on NIGHTFURY; DPI physical proof stays partial per the task's own explicit allowance. No UIA bounding rectangle is ever manually rescaled anywhere in the code.
- Secure desktop/UIPI: unit/policy tests cover sensitive-window denial and truthful `native_input_injection_failed` reporting for partial/zero SendInput; the codebase never elevates, never requests UIAccess, and never claims "UIPI blocked" without independent proof. No UAC surface was deliberately triggered to "test" it.

### 5.7 Tests

New test module `tests/test_phase_eighteen_evaluation_suite.py` — 10 tests:
- suite registration (`computer_use_v2` present in `EvaluationService.suites()`);
- suite has ≥17 cases with unique IDs;
- all cases pass deterministically;
- no physical test runs by default (`subprocess.Popen` patched to raise if the deterministic suite ever tries to launch a real process — it doesn't);
- raw UI text not persisted (inspects the actual `evaluation_runs` row's `results_json`, bounds every string field);
- regression detection (the existing generic `EvaluationService` mechanism, exercised against a suite registered/re-registered under one name to force a pass→fail transition);
- physical runner script: refuses on non-Windows, never includes a full window enumeration in its summary, its HTML fixture is local/inert (no `http(s)://`), and its Edge-path lookup degrades honestly when Edge isn't found.

Results:

```text
python -m pytest tests -k "evaluation or phase_eighteen" -q
133 passed, 514 deselected

python -m pytest tests -q
647 passed, 36 subtests passed

python -m compileall src tests scripts -q
(clean)

git diff --check
(clean)

cd ui && npm test -- --run
14 test files, 75 passed

npm run build
built in 870ms

npm audit --audit-level=high
0 high/critical (2 pre-existing moderate, unrelated dev-dependency, exit 0)
```

### 5.8 Commit

- **Files staged (explicit paths, no `git add .`):** `src/jarvis/evaluation/computer_use_v2.py`, `src/jarvis/evaluation/semantic_uia_fixtures.py`, `src/jarvis/bootstrap.py`, `scripts/phase18/computer_use_acceptance.py`, `tests/test_phase_eighteen_evaluation_suite.py`, `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_02.md`, `docs/source_of_truth/02_JARVIS_CURRENT_STATE.md`, `docs/source_of_truth/03_JARVIS_GAP_REGISTER.md`, `docs/source_of_truth/04_JARVIS_EXECUTION_ROADMAP.md`.
- **Commit message:** `test: add computer-use evaluation suite`
- **MILESTONE_2_COMMIT:** recorded after push, see final response.

---

<!-- Sections 6 (final regression), 7 (security review), 8 (gap status),
     9 (manual dependencies), 10 (restrictions remaining), and 11
     (recommended Batch 03) follow after the Milestone 2 push and final
     batch gate. -->
