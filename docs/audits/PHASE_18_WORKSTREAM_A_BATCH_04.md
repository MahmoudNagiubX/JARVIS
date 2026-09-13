# PHASE 18 — WORKSTREAM A — BATCH 04
## File-Search Boundary Hardening → Grounded Drag + Owned Text Fixture → Local Visual OCR Grounding

**Task:** `tasks/CLOUD_CODE_MASTER_PHASE_18_WORKSTREAM_A_BATCH_04.md`
**Branch:** `feature/phase-18-computer-use-v2`
**Status:** COMPLETE — `PHASE18_COMPUTER_USE_BATCH04_PARTIAL`. Milestones 0 and 1 fully green and physically proven; Milestone 2 concluded `OCR_BACKEND_EVALUATION_BLOCKED` (evidence-first evaluation complete, no production OCR integration - see Section 5).

This is the single report for the whole batch (per Section 11 of the task file); it is appended to, not duplicated, as later milestones complete.

---

## 1. Starting state

- Branch: `feature/phase-18-computer-use-v2`
- Starting HEAD: `7188c712563a9340112da1b86fcd218d71898af1` — matched the task file's expected starting HEAD exactly; branch was in sync with `origin/feature/phase-18-computer-use-v2`, `git status --short` clean, no unexplained divergence.

---

## 2. Independent review finding against Batch 03

Two hardening findings identified after independent review of the Batch 03 file-access confinement work, both addressed in Milestone 0 below:

| ID | Summary | Disposition |
| --- | --- | --- |
| R18B03-001 | `FileAccessPolicy.filter_search_results()` re-checked each candidate only *after* `Path.rglob()` had already been free to descend through a symlink/junction/reparse point before filtering happened — safe for model-visible output (a candidate outside the root was never *returned*), but not a genuine pre-descent traversal boundary, and no depth bound or live scan/result bounding existed during the walk itself. | Fixed — replaced with `FileAccessPolicy.iter_search_candidates(root, pattern)`, a bounded, iterative, pre-descent walker (see §3.2 below). |
| R18B03-002 | `_SENSITIVE_FILE_NAMES`'s exact-match set (`.env`, `.env.local`, `.env.development`, `.env.production`, `.env.test`) missed common variants such as `.env.staging`, `.env.development.local`, `.env.production.local`, `.env.test.local`, and any other `.env.<suffix>`. | Fixed — `.env`/`.env.*` is now matched as a wildcard family (excluding the explicitly-safe `.env.example` template), without over-matching `.environment` (see §3.3 below). |

---

## 3. Milestone 0 — File-search boundary hardening

**Commit:** `bdad0a96a25813414248be5cf06b445379c1956f`

### 3.1 Root cause

`_search_files()` (`src/jarvis/computer/service.py`) called `root.rglob(pattern)` and passed the resulting generator into `FileAccessPolicy.filter_search_results(root, candidates)`, which validated each candidate's *resolved* path only after `rglob()` had already been allowed to enumerate it. Because `rglob()` follows directory symlinks/junctions by default, the underlying OS-level directory walk could physically descend into a reparse point whose target lies outside the approved root before the per-candidate filter ever ran — the model never saw an out-of-root result (the filter denies it), but the traversal itself was not bounded at the directory level, had no depth limit, and had to materialize/iterate an effectively unbounded generator before bounds were applied per-candidate.

### 3.2 Pre-descent bounded walker (R18B03-001)

`FileAccessPolicy.filter_search_results()` was replaced by `FileAccessPolicy.iter_search_candidates(root, pattern)` (`src/jarvis/computer/file_access.py`) — an iterative (stack-based, not recursive), pre-descent walker:

1. **Classify before descending.** For every directory entry found via `os.scandir()`, `_is_reparse_point(path)` classifies it *before* any decision to enter it, using `os.lstat(path).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT` — verified empirically against a real `mklink /J` junction (see §3.4): the junction's `st_file_attributes` correctly carries the reparse-point bit, whereas `Path.is_symlink()` reports `False` for it and would have under-classified it as an ordinary directory. Classification fails closed: if `os.lstat()` itself raises `OSError`, the entry is treated as a reparse point (never descended).
2. **Default reparse policy: never follow directory reparse points at all**, even when the entry's target is still inside the approved root. This is deliberately stricter than "follow if still inside root" — simpler, deterministic, and avoids cycle/mount ambiguity entirely — per the task's own recommended simplification.
3. **File symlinks remain usable, narrowly.** A file (not directory) symlink is only returned as a match if its fully resolved target is still inside `root`, is genuinely a file (`Path.is_file()`), and passes the sensitivity policy — never trusted from its unresolved name alone.
4. **Canonicalize and re-verify containment for every real subdirectory before pushing it onto the walk stack** — `entry_path.resolve()` must land inside `root` (`relative_to(root)`), or the directory is never descended (fails closed, counted in the bounded `filtered` count).
5. **Sensitive subtrees are pruned, not filtered post-hoc** — a directory named `.ssh`/`.gnupg`/`.aws`/`.azure`/`.kube` is never descended, so no child (hidden or not) inside it can ever reach the output.
6. **Bounds are enforced live, one directory listing at a time** — `MAX_SEARCH_CANDIDATES_SCANNED` (5000, unchanged) and `MAX_SEARCH_MATCHES` (100, unchanged) are checked before each entry is processed, never after an unbounded list is built. A new `MAX_SEARCH_DEPTH = 32` bounds recursion depth.
7. **Cycle safety.** A bounded canonical-directory `visited` set (casefolded resolved path strings) is kept as defense in depth, even though a directory tree that never follows reparse points cannot itself be cyclic.

`_search_files()` in `service.py` now calls `self.file_access_policy.iter_search_candidates(root, pattern)` directly — it no longer constructs or passes a `Path.rglob()` generator at all. `ComputerActionService` still contains no traversal logic of its own; it only asks the policy for bounded candidates, matching the task's authority requirement.

Direct `inspect_file`/`open_file`/`open_folder` confinement via `FileAccessPolicy.evaluate()` is unaffected by this change (it still resolves and checks the real target path directly) and was not modified.

### 3.3 `.env.*` wildcard sensitivity (R18B03-002)

`_SENSITIVE_FILE_NAMES` no longer carries the individual `.env*` exact-match entries; a new `_is_env_secret_name(name_casefold)` helper matches `.env` or any `.env.<suffix>` (`name_casefold.startswith(".env.")`), explicitly excluding the safe template `.env.example`. Matching is anchored on the literal `.env` stem followed by nothing or a `.` separator, so `.environment` — which has no `.` immediately after `.env` — is never caught by this rule (verified by a dedicated test).

### 3.4 Empirical verification of pre-descent reparse classification

Before implementing, the reparse-point detection approach was verified against a real Windows junction (`cmd /c mklink /J`, temp directories only):

- `Path.is_symlink()` on the junction entry → `False` (junctions are not Win32 symlinks; using `is_symlink()` alone would under-classify them).
- `os.lstat(junction_path).st_file_attributes` → `1040` (`0x410` = `FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT`) → `& stat.FILE_ATTRIBUTE_REPARSE_POINT` correctly evaluates `True`.
- `os.scandir()`'s `DirEntry.is_dir(follow_symlinks=False)` on the same entry → `True` (the OS reports junctions as directory-shaped even without following), confirming the walker's "is this a directory or a file" branch and its "is this a reparse point" branch must be checked independently rather than assuming one implies the other.

This confirmed `st_file_attributes`'s reparse-point bit (not `is_symlink()`) is the correct pre-descent classifier on Windows, with a fallback to `Path.is_symlink()` when `st_file_attributes` is unavailable (non-Windows).

### 3.5 Tests

14 new tests added to `tests/test_phase_eighteen_file_access.py` (38 tests total in the file, all passing, all using only `tempfile.TemporaryDirectory()` fixtures — no owner files):

1. `test_search_does_not_follow_escape_link` (updated to the new API) — junction target outside root is not traversed.
2. `test_walker_never_yields_external_secret_even_transiently` — the external secret never appears even as a transient candidate.
3. `test_junction_directory_inside_root_is_not_descended` — a junction whose target is *inside* the root is still never descended (default no-follow policy).
4. `test_cycle_cannot_cause_unbounded_walk` — a self-referential junction cannot cause an unbounded walk.
5. `test_scan_count_bound_is_enforced` — `MAX_SEARCH_CANDIDATES_SCANNED` is enforced live.
6. `test_result_count_bound_is_enforced` — `MAX_SEARCH_MATCHES` is enforced live.
7. `test_sensitive_subtree_is_pruned` — an entire sensitive directory is pruned, including a hidden child name that never appears in output.
8. `test_normal_nested_search_still_succeeds` — ordinary multi-level nested search still works.
9. `test_env_staging_denied`, `test_env_development_local_denied`, `test_env_production_local_denied`, `test_env_test_local_denied` — `.env.*` variants denied.
10. `test_env_example_is_allowed` (already existing, re-verified) — safe template allowed.
11. `test_dot_environment_unaffected_by_env_wildcard_rule` — `.environment` is not caught by the `.env.*` rule.

### 3.6 Verification

- `python -m pytest tests/test_phase_eighteen_file_access.py -q` → **38 passed**.
- `python -m pytest tests -k "file_access or phase_eighteen" -q` → **205 passed, 515 deselected**.
- `python -m pytest tests -q` (full regression) → **720 passed, 36 subtests passed**.
- `python -m compileall src tests scripts -q` → clean, no errors.
- `git diff --check` → clean, no whitespace errors.
- `grep -rn "rglob" src/` → no remaining `rglob()` usage inside the confined file-search path (`src/jarvis/computer/`); the only other `rglob()` call sites in the repo (`desktop/assets.py`, `desktop/model.py`, `research/providers.py`) are unrelated, out-of-scope subsystems not governed by `FileAccessPolicy`.
- **Commit:** `bdad0a96a25813414248be5cf06b445379c1956f`
- **Push:** `feature/phase-18-computer-use-v2` (`7188c71..bdad0a9`) — pushed successfully.

---

## 4. Milestone 1 — Grounded drag + second owned fixture + evaluation breadth

**Commit:** `309c2d705fe37ce4c45307c190a16ed80d4f3497`

### 4.1 Drag architecture — dual-target, same-window-only, bounded interpolation

- New `ComputerCapability.POINTER_DRAG_ELEMENT_TO_ELEMENT` (`pointer_drag_element_to_element`), reachable through the existing `computer.pointer.act` tool as `action: "drag_element_to_element"` with exactly `source_element_ref`/`target_element_ref` (no raw coordinates, no path/trajectory, no duration, no file paths).
- `WindowsNativeInputAdapter.drag_element_to_element(source_element_ref, target_element_ref)` (`src/jarvis/computer/native_input.py`): both endpoints resolved through the exact same `resolve_actionable_target` machinery every other pointer action uses (`_ground_drag_pair` → `_resolve_grounded` twice). If the two endpoints' `window_ref` differ, refused with `drag_cross_window_not_supported` **before any input is sent** - cross-window drag is a deliberate, reviewed deferral (more consequential, harder to verify, file-transfer-bypass-adjacent), not an oversight. After the containing window is focused, both endpoints are **re-resolved a second time** (focus can change layout) before execution - the same pattern `_ground()` already uses for single-target actions.
- Execution (`_execute_drag`): move to source (`MOUSEEVENTF_MOVE|ABSOLUTE|VIRTUALDESK`) → `MOUSEEVENTF_LEFTDOWN` → `DRAG_INTERPOLATION_STEPS = 8` bounded, deterministic, linearly-interpolated internal move points (within the reviewed 4-12 range; no randomness, no "human simulation" jitter; intermediate points are never exposed to the model) → `MOUSEEVENTF_LEFTUP`. On any partial `SendInput` failure mid-sequence, a `finally` block guarantees the JARVIS-pressed left button is released (`MOUSEEVENTF_LEFTUP` sent even on the failure path) - proven by a dedicated unit test (`test_drag_partial_failure_releases_left_button`) that forces the first interpolation step to fail and asserts the very next `SendInput` call is the cleanup release. Generic drag stays `verified=False` (same honesty rule as generic click/scroll/double-click) - only an owned-fixture postcondition counts as verified evidence.

### 4.2 Dual-target approval binding

`ComputerActionService` (`src/jarvis/computer/service.py`) gained a new `_dual_target_actions` frozenset (containing only `pointer_drag_element_to_element`) and a `_drag_target_preview()`/`_resolve_drag_endpoint()` pair, deliberately **not** folded into the single-target `_element_target_preview()` - the task's own instruction was explicit that a two-target action must never be forced into a single-target digest.

- The approval preview shows bounded, trusted descriptions of **both** endpoints (`name`, `control_type`, `automation_id`, `window_ref`) plus the action name - never a single opaque digest standing in for two different targets.
- The identity binding is a composite `"source_digest|target_digest"` string. `decide()` re-resolves both endpoints on resume and, if the digest changed, splits the composite to identify **which** endpoint changed, returning the specific typed failure `drag_source_changed` or `drag_target_changed` (rather than one generic `approval_target_changed`) - proven by two dedicated `ApprovalHardeningTests` cases. If either endpoint cannot be re-resolved at all, the preview-building error (`drag_source_stale`/`drag_target_stale`/`uia_target_unavailable`) propagates as the refusal reason.
- Approval expiry is `min(10-minute default, source reference expiry, target reference expiry)` - the same "never outlive the actual target reference" rule Batch 02 established for single-target actions, now applied to both endpoints.
- `computer.pointer.act`'s tool schema (`src/jarvis/tools/registry.py`) gained `source_element_ref`/`target_element_ref` (bounded strings, `element-` prefix enforced) and the `drag_element_to_element` enum value; `element_ref` is no longer in the JSON Schema `required` list (validated per-action in the handler instead, matching the existing `scroll_element` pattern) so drag's two-ref shape and the other actions' one-ref shape can coexist in one schema.

### 4.3 Second owned fixture

`scripts/phase18/uia_text_fixture_host.py` - a second fully JARVIS-owned native Win32 process (ctypes + user32 only, no third-party GUI framework), following the exact same safety discipline as Batch 03's fixture: nonce-based exact-title matching (`JARVIS-CUV2-TEXT-FIXTURE-<uuid>`), no owner data, no network, no file dialogs. Layout: a real single-line `EDIT` control (initial text `JARVIS TEXT FIXTURE`), two `BUTTON` controls (`Drag Source`/`Drop Target`), and a status label (`drag:accepted`/`drag:rejected`).

Two real Win32 bugs were found and fixed via physical dogfooding of this new fixture (not fixed by inspection alone):

1. **No initial keyboard focus.** A plain top-level window (unlike a dialog template) never gives keyboard focus to any child control automatically - every keyboard scenario silently did nothing (typed text vanished, chords had no effect) because no control ever had focus at all. Fixed with an explicit `user32.SetFocus(_hwnd_edit)` call at fixture startup.
2. **Drag-detection capture race.** The first implementation used `WM_PARENTNOTIFY(WM_LBUTTONDOWN)` on the parent window to detect a press on the drag-source button and immediately call `SetCapture` on the parent. Empirically, `WM_PARENTNOTIFY` fired correctly, but the drag-source `BUTTON` control's own default window procedure re-captured the mouse for itself immediately afterward (its own built-in press/click tracking), silently winning the capture race - the parent's `WM_LBUTTONUP` handler never received the matching release. Fixed by **subclassing** the drag-source button's own window procedure (`SetWindowLongPtrW(GWLP_WNDPROC, ...)`, standard Win32 subclassing, no custom UIA provider): `WM_LBUTTONDOWN` is now intercepted and never forwarded to the original button proc at all, so the button never takes its own capture and the parent's capture is never contested.

A pre-existing scenario-ordering bug in the *physical acceptance runner itself* (not the fixture) was also found and fixed: the Tab focus-cycling test was originally sequenced before the `ctrl+a`/`ctrl+c`/`ctrl+z` chord tests, so by the time those chords ran, keyboard focus had already moved away from the Edit control to the "Drag Source" button and the chords had no effect. Reordered so Tab runs last among the text-fixture's keyboard scenarios.

### 4.4 English and Arabic literal typing

The existing literal-typing implementation (`_keyboard_action` / `WindowsNativeComputerController`, Phase 11-era) needed **no changes** - both English and Arabic Unicode text round-trip through the existing UTF-16-unit-chunked `KEYEVENTF_UNICODE` path exactly as designed. Physically proven: `JARVIS COMPUTER USE` (19 chars) and `مرحبا يا جارفيس` (15 chars) both typed via `computer.keyboard.type` and independently read back via `computer.semantic.read`'s `get_text` action (an independent path from the typing action's own self-report), with an exact string match both times, 3/3 clean iterations.

### 4.5 Other literal key/chord evidence

- **Home/End:** proven via prepend/append markers (`H`/`E`) around the Arabic phrase - Home moves the caret to position 0 (marker prepended), End moves it to the end (marker appended), both independently confirmed via `get_text`.
- **Backspace:** proven via an exact one-character-shorter length check after one press.
- **Tab:** independent focus read-back (`focused: true` on "Drag Source" after Tab from the Edit control).
- **`ctrl+a`/`ctrl+c` (clipboard):** a known sentinel is written to the clipboard *first* (`computer.clipboard.write`) - the pre-existing owner clipboard content is never read, inspected, or logged at any point. The fixture's own known text is then select-alled and copied; the clipboard is independently read back and compared against the fixture's own known text (not the sentinel), proving `ctrl+c` genuinely changed the clipboard. The sentinel is written back afterward to avoid leaving fixture text sitting in the owner's clipboard.
- **`ctrl+z` (undo):** proven via an independent before/after text comparison showing the most recent edit (the Backspace above) was reverted.
- **No paste added.** Ctrl+V remains completely absent from every schema and every chord allowlist - unchanged from Batch 03's deferral, confirmed by an evaluation-suite regression case.

### 4.6 Incidental bug fix: `computer.clipboard_read` silently required approval

Found via physical dogfooding of the `ctrl+c` clipboard scenario (not a Batch 04 regression - this bug predates this batch): `ComputerActionService.CLIPBOARD_READ` was correctly listed in `_read_actions` (`risk_level: "read"`), but `PolicyPermissionEngine`'s rule list had no matching `computer.clipboard_read` entry, so it fell through to the generic `"computer."` `REQUIRE_APPROVAL` catch-all - unlike every one of its sibling read actions (`inspect_file`, `search_files`, `semantic_*`, etc.), which all have an explicit `ALLOW` rule. Fixed by adding the missing rule (`src/jarvis/authority/permissions/engine.py`). `computer.clipboard_write` is unaffected and correctly still requires approval (it is not in `_read_actions`/`_safe_actions`, so it is legitimately consequential). One pre-existing test (`tests/test_phase_eleven_agent_computer_tools.py::test_clipboard_read_is_one_approval_and_ephemeral_to_agent`, renamed to `test_clipboard_read_is_direct_and_ephemeral_to_agent`) asserted the buggy approval-required behavior as if it were intended; updated to assert the corrected direct-completion behavior while preserving every one of its original ephemeral-retention/no-secret-leak assertions unchanged.

### 4.7 Evaluation suite additions

The deterministic `computer_use_v2` suite (`src/jarvis/evaluation/computer_use_v2.py`) grew from 24 to 32 cases:

- `cuv2-24` (rewritten): paste absent everywhere; drag stays bounded/element-grounded only (`source_element_ref`/`target_element_ref` present, no raw position/path/duration fields) - replaces the now-obsolete "no drag anywhere" assertion, since Batch 04 deliberately adds a reviewed, bounded drag.
- `cuv2-25`: drag requires two-target approval binding (preview shows both `source.name`/`target.name`).
- `cuv2-26`: one drag target changing after approval is refused (`drag_target_changed`).
- `cuv2-27`: drag source/target from different windows is refused (`drag_cross_window_not_supported`), at request time, before any approval is even created.
- `cuv2-28`: generic drag stays unverified without a fixture postcondition (uses a fully injected `WindowsNativeInputAdapter` - the deterministic suite never delivers real `SendInput` to the actual desktop).
- `cuv2-29`: a partial drag injection failure still releases the left button (standalone injected adapter, forces the first interpolation move to fail).
- `cuv2-30`/`cuv2-31`: English/Arabic literal typing use the canonical path (schema-level and, for Arabic, a full round-trip through a fully injected native-input/window-provider harness).
- `cuv2-32`: clipboard verification never inspects an unknown owner value (schema-level: `computer.clipboard.read` takes no filter/selector parameter that could target "whatever is already there").

All 32 cases pass deterministically (`test_all_cases_pass_deterministically`), and the "no physical process spawned by default" guard (`test_no_physical_test_runs_by_default`, patches `subprocess.Popen` to raise) still passes - none of the new cases launch a real GUI process.

### 4.8 Tests

- `tests/test_phase_eighteen_native_input.py`: 8 new `DragTests` (bounded interpolation point count and flag sequence; both endpoints revalidated after focus; cross-window refused before any input; weak source/target refused before any input; partial-failure cleanup release; failure on `LEFTDOWN` itself needs no extra release; target-outside-virtual-desktop denial) plus 6 new `ApprovalHardeningTests` (dual-target preview content; successful dual-ref execution on approve; source-changed / target-changed typed refusals; cross-window refused at request time) plus 2 rewritten `ArchitectureTests` (paste/file-drop still absent everywhere; drag stays element-grounded-only with no raw position/path/duration field) - **78 tests total in the file, all passing** (was 65).
- `tests/test_phase_eighteen_owned_fixture.py`: extended the static safety checks (no owner-app dependency, no network/file-dialog calls, not imported by production, syntactically standalone) to also cover the new `uia_text_fixture_host.py`; updated the `_summarize()` unit test's fake run fixture to include the new `text_drag_fixture` key - **11 tests, all passing**.
- `tests/test_phase_eleven_agent_computer_tools.py`: updated the one clipboard-read test affected by the permission-engine fix (§4.6) - **5 tests, all passing**.
- `src/jarvis/evaluation/computer_use_v2.py`: 8 new cases (32 total).

### 4.9 Verification

- `python -m pytest tests -k "native_input or owned_fixture or evaluation or phase_eighteen" -q` → **220 passed, 514 deselected**.
- `python -m pytest tests -q` (full regression) → **734 passed, 36 subtests passed**.
- `python -m compileall src tests scripts -q` → clean, no errors.
- `git diff --check` → clean, no whitespace errors.
- **Physical acceptance** (`scripts/phase18/computer_use_acceptance.py --runs 3`, both owned fixtures together, real Windows desktop, NIGHTFURY): **all scenarios 3/3**, including every Batch 03 scenario (unaffected/still green) and every new Batch 04 scenario:

  | Scenario | Result |
  | --- | --- |
  | Semantic invoke/toggle/select (fixture 1, unaffected) | 3/3 each |
  | Native left/right/double click, scroll (fixture 1, unaffected) | 3/3 each |
  | Native Tab key, named chord (fixture 1, unaffected) | 3/3 each |
  | Non-primary-monitor click (fixture 1, unaffected) | 3/3 |
  | Grounded drag (`drag:accepted`, fixture 2) | 3/3 |
  | Literal English typing (fixture 2) | 3/3 |
  | Literal Arabic Unicode typing (fixture 2) | 3/3 |
  | Home/End marker proof (fixture 2) | 3/3 |
  | Backspace (fixture 2) | 3/3 |
  | Tab focus-cycling (fixture 2) | 3/3 |
  | `ctrl+c` clipboard proof (fixture 2) | 3/3 |
  | `ctrl+z` undo (fixture 2) | 3/3 |
  | Both fixtures' child processes confirmed exited (exact-PID cleanup) | 3/3 |

  During dogfooding, a real Windows OS-level `SetForegroundWindow` foreground-activation race was also observed and characterized: a background process spawning a fresh top-level window can be denied foreground activation depending on exact input-history timing, unrelated to JARVIS or fixture code. The runner's `_approve_and_run` helper now retries only this specific mechanical precondition (`window_focus_not_verified`, up to 4 attempts with a short delay) before giving up - never retrying a semantic action's actual outcome, and the final reported status is always the true last attempt's result.
- **Commit:** `309c2d705fe37ce4c45307c190a16ed80d4f3497`
- **Push:** `feature/phase-18-computer-use-v2` (`bdad0a9..309c2d7`) — pushed successfully.

GAP-0102 advances from `PARTIAL` to a stronger `PARTIAL` (not resolved - paste, cross-window drag, and arbitrary hotkeys remain intentionally absent). GAP-0105 advances with a second owned fixture and 8 new evaluation cases, remaining `PARTIAL` (still a two-fixture foundation, not the broad real-app matrix named in the gap's original scope).

---

## 5. Milestone 2 — Local Visual Grounding / OCR V1 evaluation (blocked, no production integration)

**Commit:** `7ff4ce28de82de4f73f0cacc7fda5ca1bb6923a5`

**Verdict: `OCR_BACKEND_EVALUATION_BLOCKED`.** Per the task's own explicit instruction ("do not force a provider merely to finish the milestone"), no OCR backend was integrated into production. No `computer-ocr` optional dependency group, no `computer.visual.read` tool, no `VisualTextRegion`/`VisualObservation` contracts, no OCR-owned fixture mode were added - core JARVIS runtime and every previously-green milestone are completely unaffected by this milestone. This section documents the evidence-first evaluation that produced this verdict.

### 5.1 Evaluation environment

Per the task's instruction, benchmarking was performed in an **isolated** temporary venv, never the project's own `.venv` and never as an installed JARVIS dependency - two separate venvs (one per candidate, to avoid one candidate's transitive dependencies masking a real missing-dependency finding in the other - see §5.3), both built from the project-compatible Python 3.12 interpreter already present on this machine (`C:\Users\mahmo\AppData\Local\Python\pythoncore-3.12-64`, resolving to Python 3.12.10 - the project's `requires-python = ">=3.11"` and its own `.venv` both target 3.12), on NIGHTFURY. Both venvs and all downloaded model caches were deleted after the evaluation; nothing from either venv reached the repository.

### 5.2 Benchmark corpus and methodology

`scripts/phase18/ocr_backend_benchmark.py` (preserved, evaluation-only, never imported by production) generates seven JARVIS-owned synthetic fixture images using an already-installed Windows system font (Segoe UI - never copied into the repository):

- English: `JARVIS COMPUTER USE`, `Open Settings`, `Save Draft`
- Arabic: `مرحبا يا جارفيس`, `الإعدادات`, `حفظ`
- Mixed: `JARVIS الإعدادات`

Accuracy is scored as **normalized character recall** (NFKC-normalized, whitespace-collapsed, order-insensitive multiset character overlap - never byte-perfect glyph comparison, per the task's own accuracy-gate wording), matching the gate thresholds: English ≥0.90, Arabic ≥0.85, mixed ≥0.80. Generated images are deleted immediately after each benchmark run; none are committed.

### 5.3 Candidate 1 (primary): PaddleOCR 3.7.0 + paddlepaddle 3.3.1 (PP-OCRv5, CPU) — FAILS

Installed via `pip install paddlepaddle==3.3.1 paddleocr==3.7.0` (~0.77 GB venv + ~0.23 GB model cache under `~/.paddlex/official_models`, downloaded from Hugging Face on first use, cached thereafter - never committed). `PaddleOCR(lang=..., ocr_version="PP-OCRv5", ...)` initializes successfully and downloads/caches the PP-OCRv5 mobile recognition + detection models for both `en` and `ar`. **Every single `.predict()` call, for every one of the 7 fixture images, on both the English and Arabic engines, raises the identical error:**

```
NotImplementedError: (Unimplemented) ConvertPirAttribute2RuntimeAttribute not support
[pir::ArrayAttribute<pir::DoubleAttribute>]
(at ..\paddle\fluid\framework\new_executor\instruction\onednn\onednn_instruction.cc:118)
```

This is a crash deep inside PaddlePaddle's own compiled C++ CPU inference executor (its new "PIR"/Paddle-IR execution path interacting with its oneDNN-accelerated operator kernels) - not a JARVIS or benchmark-script defect, and not fixable from application code. Three independent remediation attempts were made, all unsuccessful:

1. Disabling oneDNN via the documented `FLAGS_use_mkldnn=0` environment variable - error persists identically.
2. Disabling oneDNN programmatically via `paddle.set_flags({'FLAGS_use_mkldnn': False})` before model load - error persists identically (the exported inference graph appears to already bake in oneDNN-fused operators at export time, unaffected by a client-side runtime flag).
3. Downgrading to `paddlepaddle==2.6.2` (the last pre-"PIR" release) - this instead breaks paddleocr 3.7.0's own required API surface (`AttributeError: 'paddle.base.libpaddle.AnalysisConfig' object has no attribute 'set_optimization_level'`), since paddleocr 3.7.0 requires the newer paddle 3.x API. The two packages' version requirements are tightly coupled; there is no working paddle-3.x-API-compatible version that avoids the oneDNN crash on this machine.

**Verdict: PaddleOCR fails acceptance gates 3 and 4 (English/Arabic fixture text usable) outright - zero successful predictions across the entire corpus.** Gates 1/2 (local, no cloud/API key) are technically met; the candidate is disqualified regardless since it cannot produce any output at all.

### 5.4 Candidate 2 (secondary): RapidOCR 3.9.2 (ONNX Runtime, CPU) — FAILS the accuracy gate

Installed via `pip install rapidocr==3.9.2` in a **separate, clean** venv (~0.30 GB + ~57 MB bundled/cached models under the package's own `models/` directory - never committed) specifically to test the task's own named risk without contamination from PaddleOCR's transitive dependencies (PaddleOCR's install had incidentally pulled in `python-bidi` as a transitive dependency of `paddlex`, which would have silently masked the exact finding below).

- **Confirmed the task's named upstream risk, empirically, from a clean install.** `pip show rapidocr` lists `Requires: colorlog, numpy, omegaconf, opencv_python, Pillow, pyclipper, PyYAML, requests, Shapely, six, tqdm` - **no `python-bidi`**. Constructing an Arabic-language `RapidOCR` engine succeeds, but every single prediction call raises `ModuleNotFoundError: Required dependency 'python-bidi' is not installed. Install it with: pip install python-bidi`. This exactly matches the task's advance caution ("a recent RapidOCR upstream issue reports Arabic recognition on a fresh install can fail because an RTL python-bidi runtime dependency is missing from declared dependencies"). Separately, RapidOCR's default `onnxruntime` inference engine is *also* not a declared/pinned dependency - a clean `pip install rapidocr` alone cannot run any engine at all without a manual `pip install onnxruntime` too.
- **After manually installing both `onnxruntime` and `python-bidi`:** recognition runs without crashing, but accuracy fails the gate. RapidOCR's only available Arabic recognition tier - for **both** PP-OCRv4 and PP-OCRv5, confirmed by probing every `(OCRVersion, ModelType)` combination programmatically - is `"mobile"` (no `"server"`/`"small"`/`"medium"` Arabic model exists in this release). Recall on the Arabic fixtures via this tier ranged **0.0-0.412** per case, far below the required 0.85. The mixed-text fixture (`JARVIS الإعدادات`) scored 0.267. English recall via the *same* `"mobile"` tier (the only tier where both languages are simultaneously available) was also weak (0.353-0.412 on the longer phrase, though two short common-word fixtures scored 1.0 on this order-insensitive metric). By contrast, RapidOCR's **default** configuration (PP-OCRv6 "small", English/Chinese only - no Arabic support at that tier at all) recognized `JARVIS COMPUTER USE` perfectly (`('JARVIS', 'COMPUTER', 'USE')`), confirming the poor score is specific to the smaller Arabic-capable tier, not a general RapidOCR or fixture-image defect.

**Verdict: RapidOCR fails accuracy gate 4 (Arabic ≥0.85) and effectively gate 3 as well (English ≥0.90 only achievable in a config with no Arabic support) - no single configuration passes both language gates simultaneously.** Gates 1/2/9 (local, no API key, deterministic provider seam mockable) would otherwise be met.

### 5.5 Candidate 3 (baseline): Tesseract — not evaluated

Not already installed on this machine (`where tesseract` found nothing, no `Tesseract-OCR` install directory under Program Files), and installing its system-level binary is outside Python packaging entirely - it did not meet the task's own conditional bar ("only as a baseline if already installed or straightforward to isolate"). Not evaluated this batch; may be reconsidered in a future batch if a reviewer wants baseline comparison data.

### 5.6 Decision

Per Section 8 of the task ("If no candidate passes: Milestone 2 may finish as `OCR_BACKEND_EVALUATION_BLOCKED` with no unsafe production integration - do not force a provider merely to finish the milestone"): **no backend was integrated.** `docs/source_of_truth/05_JARVIS_DECISION_LOG.md` OPEN-002 records this as an **open, evidence-backed evaluation result** - not an accepted/locked decision, since no candidate was actually selected. GAP-0103 remains `OPEN` (not advanced to `PARTIAL`), with the full evidence trail recorded against it. The benchmark tooling (`scripts/phase18/ocr_backend_benchmark.py`) is preserved, with its own module docstring recording the exact verdict, so a future batch can re-run it against a newer PaddleOCR/PaddlePaddle release (the oneDNN bug may be fixed upstream) or an additional candidate without re-deriving this evaluation from scratch.

### 5.7 Tests and verification

- 5 new static safety tests (`OcrBenchmarkSourceSafetyTests` in `tests/test_phase_eighteen_owned_fixture.py`): the benchmark script is never imported by production bootstrap or anywhere under `src/`, deletes its generated images after running, is a syntactically standalone script, and uses only the JARVIS-owned synthetic fixture strings named above - **16 tests total in the file, all passing** (was 11).
- `python -m pytest tests/test_phase_eighteen_owned_fixture.py -q` → **16 passed**.
- `python -m pytest tests -q` (full regression) → **739 passed, 36 subtests passed**.
- `python -m compileall src tests scripts -q` → clean, no errors.
- `git diff --check` → clean, no whitespace errors.
- Frontend gate (`npm test -- --run`, `npm run build`, `npm audit --audit-level=high` in `ui/`) — run for completeness even though no frontend code was touched by this milestone (no OCR UI surface exists since no backend was integrated): **75/75 tests passed**, build succeeded, `npm audit --audit-level=high` exits clean (2 pre-existing moderate-severity `vitest`/`@vitest/mocker` dev-dependency advisories, below the `high` threshold, unrelated to and unchanged by this batch).
- **Commit:** `7ff4ce28de82de4f73f0cacc7fda5ca1bb6923a5`
- **Push:** `feature/phase-18-computer-use-v2` (`309c2d7..7ff4ce2`) — pushed successfully.

GAP-0103 stays `OPEN` (not `PARTIAL`) - the evaluation itself is complete and thorough, but no visual/OCR capability exists in the product. No DEC-048 was added to the decision log (no backend was accepted); OPEN-002 was updated in place with the full evidence instead, per the task's own instruction not to manufacture an accepted decision when no candidate passes.

---

## 6. Final regression (at final HEAD)

- Branch: `feature/phase-18-computer-use-v2`, in sync with `origin/feature/phase-18-computer-use-v2` after every push, no unexplained divergence at any point in the batch.
- Final HEAD: `7ff4ce28de82de4f73f0cacc7fda5ca1bb6923a5` (`docs: record visual OCR backend evaluation`) plus this report-finalization commit.
- `python -m pytest tests -q` → **739 passed, 36 subtests passed**.
- `python -m compileall src tests scripts -q` → clean, no errors.
- `git diff --check` → clean, no whitespace errors.
- Frontend gate (`ui/`: `npm test -- --run`, `npm run build`, `npm audit --audit-level=high`) → **75/75 tests passed**, build succeeded, audit clean at the `high` threshold (2 pre-existing moderate `vitest` dev-dependency advisories, unrelated to this batch).
- `git diff 7188c712563a9340112da1b86fcd218d71898af1...HEAD --stat`: **18 files changed** (before this report-finalization commit), **4,274 insertions, 84 deletions** - matches the three implementation/evaluation commits plus the task file itself (`tasks/CLOUD_CODE_MASTER_PHASE_18_WORKSTREAM_A_BATCH_04.md`, committed alongside Milestone 0 per the established Batch 02/03 pattern). No unexplained untracked files anywhere in the working tree at any checkpoint in this batch.

---

## 7. Final security review (Section 9 of the task)

**File boundary:** no `Path.rglob()` (or any other unbounded traversal) remains in the confined search path (`src/jarvis/computer/file_access.py`/`service.py`) - the pre-descent walker enforces containment/reparse-safety before descending into every directory; no directory outside the approved root is ever descended (verified: junction-outside-root, junction-inside-root-still-not-descended, cyclic-junction tests); no `.env.*` secret variant leaks (`.env.staging`/`.env.development.local`/`.env.production.local`/`.env.test.local` all denied); `.env.example` allowed; every test uses only `tempfile.TemporaryDirectory()`, never an owner file/path.

**Drag:** `computer.pointer.act`'s schema carries no raw coordinate/path/duration field anywhere (verified by a dedicated architecture test); both `source_element_ref`/`target_element_ref` are resolved through the same strong-identity `resolve_actionable_target` pipeline every other action uses; same-trusted-window is enforced (`drag_cross_window_not_supported`, refused before any approval is even created); the approval preview and identity binding cover both endpoints (never collapsed to one digest); the composite binding's TTL is `min` of both endpoints' actual reference expiry; a changed source or target after approval is refused with a specific typed reason (`drag_source_changed`/`drag_target_changed`); a partial `SendInput` failure mid-drag guarantees the JARVIS-pressed left button is released (dedicated unit test); cross-window drag and file drag/drop remain completely absent from the codebase.

**Text fixture:** both owned fixtures clean up via exact-PID `Popen.terminate()`/`wait()` (never a broad `taskkill`, confirmed by the existing static source check plus `fixture_child_confirmed_exited` physical evidence, 3/3 for both fixtures every run); both carry a fresh UUID nonce in their window title; no owner application is ever touched (both are fully JARVIS-owned native Win32 processes); the clipboard test writes a known sentinel *before* ever reading the clipboard and never inspects/logs whatever the clipboard held beforehand; paste (Ctrl+V) remains completely absent from every schema and chord allowlist, confirmed by a regression evaluation case.

**Visual/OCR:** no production integration exists at all this batch (`OCR_BACKEND_EVALUATION_BLOCKED`) - therefore every visual/OCR-specific requirement (local-only, optional dependency, core starts without OCR, no raw image persistence, no Memory write, no sensitive-window OCR, no raw coordinate input, no visual actuation, no prompt-injection authority, no cloud API/key, no secrets) is trivially satisfied by absence. No model weights, caches, or generated fixture images were committed to Git at any point (both evaluation venvs and all downloaded model caches lived entirely outside the repository, under the session's temp scratchpad, and were deleted after benchmarking - confirmed by an explicit repository-wide search for `.onnx`/`.pdmodel`/`.pdiparams` files immediately before finalizing this report, with zero matches).

**Authority:** exactly one `ComputerActionService`, one `PolicyPermissionEngine`, one `DurableApprovalEngine`, one audit authority throughout this entire batch - no second instance of any of these was created. The one production code change to a shared authority (`PolicyPermissionEngine`'s missing `computer.clipboard_read` rule) closes a real correctness gap rather than adding a second authority or bypass; it was found via physical dogfooding, is narrowly scoped (one rule, one sibling-consistent effect), and is covered by an updated regression test. No OCR provider adapter exists yet, so "OCR provider is only an adapter, never a second authority" has nothing to violate this batch - noted as a hard requirement for whichever future batch does add one.

---

## 8. Final gap state

| Gap | Status | Note |
| --- | --- | --- |
| GAP-0101 | `RESOLVED` | Unchanged this batch - core semantic capability (invoke/toggle/select) locked in Batch 03 Milestone 2. Broader Computer Use V2 breadth remains split across the gaps below. |
| GAP-0102 | `PARTIAL` (stronger) | Grounded drag added this batch (Milestone 1), physically proven 3/3. Paste, cross-window drag, and arbitrary hotkeys remain intentionally absent. |
| GAP-0103 | `OPEN` | Milestone 2 evaluated two OCR candidates end-to-end; both failed acceptance gates on this machine (`OCR_BACKEND_EVALUATION_BLOCKED`). No visual/OCR capability exists in the product. Full evidence in §5 above and `05_JARVIS_DECISION_LOG.md` OPEN-002. |
| GAP-0104 | `PARTIAL` | Unchanged this batch - no autonomous multi-app replanning/recovery loop exists; per-action fresh re-observation and typed-failure receipts remain proven from Batch 02. |
| GAP-0105 | `PARTIAL` (stronger) | Evaluation suite grew from 24 to 32 cases; a second owned Win32 fixture added; physical runner now exercises both fixtures together. Still a two-fixture foundation, not the broad real-app matrix named in the gap's original scope. |
| GAP-0106 | `PARTIAL` | Unchanged this batch - non-primary-monitor physical proof remains closed from Batch 03; DPI and secure-desktop physical proof remain pending. |
| GAP-0503 | `RESOLVED_AFTER_REVIEW_HARDENING` | Milestone 0 closed the independent-review traversal-boundary finding (pre-descent bounded walker, `.env.*` wildcard sensitivity). Scope remains read/open/search path confinement only - write/move/copy/rename/delete/file-dialog richness from the gap's original broader description remains future work, unchanged. |

---

## 9. Manual dependencies / owner action required

**NONE.** No API key, OAuth flow, credential, owner file, personal root, display-setting change, or UAC prompt was requested or required anywhere in this batch. The PaddleOCR/RapidOCR package installs and Hugging Face model downloads performed during Milestone 2's evaluation are normal, disposable development/evaluation setup in an isolated temporary venv (per the task's own explicit framing: "OCR model downloads/package installation are normal development setup, not owner secrets") - both venvs and every downloaded model file were deleted after the evaluation; nothing from them persists in the repository, the project's own `.venv`, or anywhere the owner would need to clean up. No production dependency group (`computer-ocr` or otherwise) was added to `pyproject.toml`, so `pip install`/`uv sync` behavior for the project is completely unchanged by this batch.

---

## 10. Restrictions remaining (unchanged or newly explicit)

- **Paste (Ctrl+V) remains unimplemented** - live clipboard secrecy and an ephemeral-paste-transaction design remain deliberately deferred future work (Milestone 1, §4.5).
- **Cross-window drag remains unsupported** - `drag_cross_window_not_supported` is a deliberate, reviewed deferral pending a separate design for the file-transfer-bypass risk it would introduce (Milestone 1, §4.1).
- **File drag/drop and file-dialog automation remain completely absent** - no such capability exists anywhere in the codebase.
- **Arbitrary hotkeys remain absent** - only the existing small, reviewed named-key/chord allowlists exist; nothing expanded this batch.
- **No visual/OCR capability exists in the product** - Milestone 2 concluded `OCR_BACKEND_EVALUATION_BLOCKED`; both evaluated candidates (PaddleOCR, RapidOCR) failed acceptance gates on this machine, documented in full in §5. No `computer.visual.read` tool, no visual references, no visual actuation of any kind exists.
- **Broad real-app evaluation breadth remains outstanding** - the physical acceptance runner exercises two JARVIS-owned fixtures only, not the Notepad/Explorer/Settings/VS Code/terminal/dialogs/multi-window matrix named in GAP-0105's original scope.
- **Autonomous multi-app recovery/replanning remains absent** - GAP-0104 untouched this batch.
- **DPI scaling and secure-desktop physical proof remain pending** - GAP-0106 untouched this batch (no non-100%-DPI monitor or UAC-triggering surface was available/appropriate to test).

---

## 11. Recommended next batch

1. **A real OCR candidate re-evaluation, or an explicit pivot.** Milestone 2's blocker is concrete and specific (PaddlePaddle's CPU oneDNN executor bug; RapidOCR's Arabic-tier accuracy gap) - a future batch could productively: (a) re-run `scripts/phase18/ocr_backend_benchmark.py` against a newer PaddleOCR/PaddlePaddle release once the oneDNN bug is plausibly fixed upstream, (b) evaluate whether RapidOCR's English-only "small"/"medium" tiers could serve as an English-only OCR fallback while Arabic OCR stays explicitly unsupported (a narrower, honestly-scoped capability rather than an all-or-nothing gate), or (c) evaluate a genuinely different third candidate not named in this batch's task.
2. **Ephemeral paste transaction design.** GAP-0102's most consequential remaining gap - a deliberate design for binding an approval to live clipboard content without ever persisting it, addressing the exact concern this batch (and Batch 03 before it) repeatedly deferred.
3. **Cross-window drag, with its own dedicated review.** Given this batch's dual-target approval-binding infrastructure already exists, extending it to a reviewed cross-window case (with explicit file-transfer-bypass mitigations) is now a narrower, more tractable design problem than it was before Milestone 1.
4. **Broader real-app physical evaluation breadth** (GAP-0105) - a batch specifically aimed at exercising JARVIS against a curated set of real, disposable Windows applications (or a wider variety of owned fixtures covering menus, dialogs, and multi-window scenarios) would meaningfully advance the gap's original scope beyond the two-fixture foundation that exists today.

---

**Do not merge to main.**

GAP-0503 updated from `RESOLVED` (path-confinement scope) to `RESOLVED_AFTER_REVIEW_HARDENING` (same scope — read/open/search path confinement only; file write/dialogs remain out of scope and unimplemented).
