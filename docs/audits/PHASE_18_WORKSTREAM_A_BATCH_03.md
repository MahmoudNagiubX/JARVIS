# PHASE 18 — WORKSTREAM A — BATCH 03
## Approval/Fixture Hardening → File-Root Confinement → Input + Physical Evaluation Expansion

**Task:** `tasks/CLOUD_CODE_MASTER_PHASE_18_WORKSTREAM_A_BATCH_03.md`
**Branch:** `feature/phase-18-computer-use-v2`
**Status:** IN PROGRESS — Milestone 0 complete, Milestones 1/2 not yet started.

This is the single report for the whole batch (per Section 12 of the task file); it is appended to, not duplicated, as later milestones complete.

---

## 1. Starting state

- Branch: `feature/phase-18-computer-use-v2`
- Starting HEAD: `712a9ce033a49602884e2296122300b90acccb1b` (`docs: finalize phase 18 batch 02 report`) — matched the task file's expected starting HEAD exactly; branch was in sync with `origin/feature/phase-18-computer-use-v2`, no unexplained divergence.

---

## 2. Independent review findings against Batch 02

Six hardening findings identified after reviewing the actual Batch 02 GitHub commits, all addressed in Milestone 0 below:

| ID | Summary | Disposition |
| --- | --- | --- |
| R18B02-001 | Target-aware trusted approval was a semantic-only special case (`_semantic_actuation_actions`); `computer.pointer.act` (also `element_ref`-targeted) fell back to the generic, opaque `_approval_preview`. | Fixed — generalized to `_element_targeted_actions` (semantic invoke/toggle/select **and** pointer move/click), all sharing one trusted preview/binding path. |
| R18B02-002 | Semantic approval expiry was bounded by the hardcoded `ELEMENT_REF_TTL_SECONDS` module constant (45s), not the adapter's actually-configured TTL (clamped 15-60s). | Fixed — `resolve_actionable_target()` now returns the real `_ElementRefEntry.expires_at`; approval expiry is `min(10min, actual_reference_expiry)`, computed once at request time and never re-extended by later unrelated reads. |
| R18B02-003 | `computer.keyboard.key` (and literal `computer.keyboard.type` when it requests approval) targets an opaque `window_ref` with no trusted, human-understandable window identity in the approval preview. | Fixed — new `_window_targeted_actions` path builds a bounded window-target preview (title, process name, opaque ref) from a fresh `WindowsDesktopProvider.describe_window()` read, bound to an identity digest, revalidated on resume. |
| R18B02-004 | The Batch 02 Edge-Guest fixture is a multi-process shared browser, failed to reach page content at the existing bounded UIA depth, and is not worth retaining as the principal fixture. | Fixed — replaced entirely with a fully JARVIS-owned native Win32 fixture host (`scripts/phase18/uia_fixture_host.py`) exposing real Button/CheckBox/ListBox controls. |
| R18B02-005 | Acceptance runners must never attach to a pre-existing/similarly-titled window. | Fixed — every fixture launch carries a fresh UUID nonce in its title; the runner waits only for an *exact* title match and aborts on any collision (never "first similar title"). |
| R18B02-006 | Batch 02's final HEAD had 4 commits (3 implementation + 1 doc-only), and reports must not claim "exactly three". | Acknowledged — this batch's own final response will report exactly 4 commits (3 implementation + 1 final doc-only), matching Section 13 of the task file. |

---

## 3. Milestone 0 — Approval hardening + owned Win32 UIA fixture

**Commit:** `MILESTONE_0_COMMIT` (recorded in §3.7 below after push)

### 3.1 Generalized trusted target descriptors (R18B02-001)

- `ComputerActionService._semantic_actuation_actions` renamed/generalized to `_element_targeted_actions` — now includes `semantic_invoke`, `semantic_toggle`, `semantic_select`, `pointer_move_to_element`, `pointer_left_click_element` (any future element-targeted pointer action must be added to this same set).
- A new `_window_targeted_actions` set (`keyboard_action`, `keyboard_key`) gets an analogous, but window-shaped, trusted preview/binding path.
- Both paths reuse existing product-owned boundaries rather than inventing a second reference store or authority: element targets go through a new internal-only `RESOLVE_ELEMENT_TARGET` capability (wrapping the existing `resolve_actionable_target()` fail-closed check from Batch 02); window targets go through a new internal-only `RESOLVE_WINDOW_TARGET` capability (wrapping a new `WindowsDesktopProvider.describe_window()` method that reuses the *existing* `_window_refs` store — no second window-reference store). Neither internal capability is ever registered in any `ToolSpec`, so the model can never request them directly.

### 3.2 Actual-reference-expiry-bounded approval (R18B02-002)

- `WindowsUIAutomationAdapter.resolve_actionable_target()` now also returns `reference_expires_at` — the real, per-adapter-configured `_ElementRefEntry.expires_at` (respecting the adapter's actual `element_ref_ttl_seconds`, clamped 15-60s), never the hardcoded `ELEMENT_REF_TTL_SECONDS=45` constant.
- `WindowsDesktopProvider.describe_window()` likewise returns the real `_WindowHandle.expires_at` for window targets.
- `ComputerActionService.execute()` computes `expires_at = min(now + 10min, reference_expires_at)` **once**, at approval-creation time, and stores it directly in the pending-approval record and the durable `ApprovalRequest`. Nothing later re-reads or recomputes it — an unrelated subsequent read of the same target (e.g. a UI "polling" the element again) cannot retroactively extend an already-created approval's deadline. Verified by `test_polling_preview_does_not_extend_pending_approval` and, with a non-default 15s TTL, `test_pointer_approval_bounded_by_actual_fifteen_second_ttl`.

### 3.3 Trusted window-target preview (R18B02-003)

- New `WindowsDesktopProvider.describe_window(window_ref)`: re-reads the *live* title/class/process (never trusts the stored fingerprint alone), denies privacy-sensitive windows via the existing `PerceptionPrivacyPolicy`, and detects identity drift (title/class/process changed since the ref was issued → `window_ref_changed`) by comparing against the stored `_WindowHandle`. Returns a bounded preview (`window_ref`, `title`, `process_name`, `expires_at`) plus an internal `identity_digest` (hash of process id + title fingerprint + window class) — never a raw PID/HWND to the model.
- `computer.keyboard.key`'s approval preview: `{"action", "window_title", "process_name", "window_ref", "key", "modifiers"?}`.
- `computer.keyboard.type` (literal typing)'s approval preview now *also* carries the trusted window title/process alongside the existing bounded `text_length`/`text_digest` — the raw typed text is still never in durable approval data (existing ephemeral-argument behavior unchanged).
- On resume, the window descriptor is re-fetched and the identity digest re-compared exactly like the element path; a window that became stale/sensitive/changed refuses before any injection.

### 3.4 Owned native Win32 UIA fixture host (R18B02-004)

- New `scripts/phase18/uia_fixture_host.py` — a standalone `ctypes`/`user32.dll` Win32 GUI process (no new GUI framework dependency), never imported by production JARVIS startup. Layout: a Static ready label, a `BS_PUSHBUTTON` ("Invoke Target"), a `BS_AUTOCHECKBOX` ("Toggle Target"), a `LISTBOX` (Alpha/Beta/Gamma), a second focusable button, and a Static status label the fixture itself updates (`invoked`, `toggle:on`/`toggle:off`, `selected:<item>`) — all standard Win32 controls, UIA-accessible out of the box with no custom UIA provider needed.
- The window title always carries a caller-supplied nonce (`JARVIS-CUV2-FIXTURE-<uuid>`).
- **Two real bugs were found and fixed during this milestone's own physical testing** (not merely unit-tested — genuinely caught live):
  1. Every WinAPI call initially used ctypes' default (32-bit `int`) argument/return marshaling, which silently truncated/overflowed 64-bit `HWND`/`LRESULT`/`WPARAM`/`LPARAM` values on this x64 machine, crashing `DefWindowProcW` on the very first unhandled message. Fixed by explicitly declaring `argtypes`/`restype` for every WinAPI call (`_configure_prototypes()`), matching the rigor already used elsewhere in the codebase (`perception/windows.py`).
  2. The checkbox handler double-toggled: `BS_AUTOCHECKBOX` already flips its own check state before delivering `BN_CLICKED` (true both for a real click and for UIA's `TogglePattern.Toggle()`, which drives the control the same way) — the fixture's original code then called `BM_SETCHECK` again inside the handler, toggling it right back. Every physical toggle attempt reported `toggle:off` instead of alternating until this was found and fixed (remove the redundant `BM_SETCHECK` call; just reflect the already-current state).
- One genuine platform limitation was found and *not* worked around: a plain Win32 `ListBox`'s `LBN_SELCHANGE` notification is documented to fire only for a real user click/key, not for a programmatic `LB_SETCURSEL` — and UIA's default `SelectionItemPattern.Select()` implementation drives selection this way. The fixture's own status-label mechanism therefore cannot observe a semantic `select()` call. This is disclosed honestly rather than patched around; the independent confirmation for `select` instead comes from the semantic adapter's own fresh post-action re-observation (`select()` re-resolves the element and re-reads a **new** `SelectionItemPattern`'s `IsSelected` — R18B01-003), which is itself a genuine independent read, just not through this one fixture's status text.

### 3.5 Runner rewrite: exact nonce, exact-PID cleanup, no owner app (R18B02-004/005)

`scripts/phase18/computer_use_acceptance.py` was rewritten to drop Calculator and Edge entirely:

- `_find_exact_fixture_window()` waits only for a window whose title exactly equals the nonce title generated for that run; if more than one window matches (collision), it aborts (`fixture_title_collision`) rather than guessing.
- Cleanup uses only `Popen.terminate()` + `Popen.wait()` (+ `kill()` fallback) against the *exact* child PID this run launched, followed by a `poll()`-based liveness confirmation recorded in the output (`fixture_child_confirmed_exited`) — no `taskkill /IM` or any other broad image-name kill anywhere in the script.
- The structured summary/output contains only scenario names, pass/attempt ratios, and bounded verification booleans — never a full window enumeration, an owner window title, or raw UI content.

### 3.6 Physical semantic acceptance (3 clean iterations)

Run via `python scripts/phase18/computer_use_acceptance.py --runs 3` on NIGHTFURY, entirely through `computer.semantic.read`/`computer.semantic.act` with normal approval — `uiautomation` was never called directly for acceptance, and no owner application/window was ever touched.

| Scenario | Result (3 runs) | Independent evidence |
| --- | --- | --- |
| Invoke ("Invoke Target" button) | 3/3 | `verified=false` (honest — generic invoke has no built-in postcondition), independent status read-back = `"invoked"` all 3 times |
| Toggle ("Toggle Target" checkbox) | 3/3 | `verified=true` (adapter's own fresh post-state re-check), independent status read-back = `"toggle:on"` all 3 times |
| Select ("Beta" list item) | 3/3 | `verified=true`, adapter's own fresh `IsSelected` re-check = `true` all 3 times (the fixture's own status label does not update for select — §3.4 — so this is the adapter's independent re-observation, not the label) |
| Fixture child process confirmed exited | 3/3 | `Popen.poll()` non-`None` after `terminate()`/`wait()` in every run |

**This is the first batch with genuine, repeatable, all-three-pattern (Invoke/Toggle/SelectionItem) physical evidence for Computer Use V2** — Batch 01 had `invoke` only (Calculator); Batch 02 additionally could not get `toggle`/`select` physical evidence at all (Chromium depth limitation). See §8 (Gap status) for the resulting GAP-0101 call.

### 3.7 Tests

New/updated test modules:

- `tests/test_phase_eighteen_native_input.py` — new `ApprovalHardeningTests` class (8 tests): pointer click receives a trusted element preview with no raw `parameters` dump; pointer approval is identity-bound and executes on decide; pointer approval refuses execution when the target's observed identity changes; approval is bounded by an actual (non-default, 15s) reference TTL; an unrelated later read of the same target does not extend an already-created approval's deadline; `computer.keyboard.key` approval includes a trusted window title/process; keyboard-key approval refuses when the window becomes stale; literal-typing approval carries the trusted window plus a text length/digest, never raw text.
- `tests/test_phase_eighteen_owned_fixture.py` (new file, 11 tests): the runner contains no broad `taskkill`/`/IM` outside its own explanatory docstring; neither the runner nor the fixture host references any owner application (Notepad/Edge/Chrome/Calculator/Explorer); the fixture host makes no network or file-dialog calls; the fixture is not imported anywhere under `src/` (including `bootstrap.py`); both scripts are syntactically standalone (no package-relative imports); the runner's window-matching logic rejects an exact-title collision and never falls back to a merely-similar title; the summary never contains a raw window/ref dump; cleanup uses `proc.terminate()`/`proc.wait()`.
- `tests/test_phase_eighteen_evaluation_suite.py` — the old `PhysicalRunnerScriptTests` (Batch 02, Calculator/Edge-specific) was trimmed to just the platform-refusal check; its other concerns are now covered, more thoroughly, by the new file above.
- Five **pre-existing** tests (from Phase 4 and Phase 11, predating even Batch 01) broke as a direct, expected consequence of R18B02-003 now validating window targets *before* approval creation: `test_phase_four_integration.py`, `test_phase_eleven_agent_computer_tools.py`, `test_phase_eleven_final_remediation.py`, `test_phase_eighteen_stabilization.py`. Each used a synthetic, never-actually-registered `"window-good"`-style `window_ref` (or, in one Phase 4 case, a `keyboard_action` parameter shape that predates even the current handler's real contract) purely to exercise generic approval-lifecycle behavior unrelated to window-target validation. Fixed by either switching those specific assertions to a non-window/element-targeted consequential action (`clipboard_write`, decoupling them from R18B02-003 entirely, since that was never their real concern) or teaching the two hand-rolled fake `ComputerController` test doubles to answer the new internal `resolve_window_target`/`resolve_element_target` capabilities with a realistic descriptor **without** counting them toward the "action executed" assertions those tests make (the internal capability is a read-only pre-check, not itself the side-effecting action).

Results:

```text
python -m pytest tests -k "phase_eighteen" -q
148 passed, 515 deselected

python -m pytest tests -q
663 passed, 36 subtests passed

python -m compileall src tests scripts -q
(clean)

git diff --check
(clean)
```

Frontend was not run for Milestone 0 (no frontend files touched; deferred to the final batch gate, matching Batch 02's own precedent).

### 3.8 Commit

- **Files staged (explicit paths, no `git add .`):** `tasks/CLOUD_CODE_MASTER_PHASE_18_WORKSTREAM_A_BATCH_03.md`, `src/jarvis/computer/service.py`, `src/jarvis/computer/semantic_uia.py`, `src/jarvis/contracts/computer.py`, `src/jarvis/perception/windows.py`, `src/jarvis/evaluation/computer_use_v2.py`, `scripts/phase18/uia_fixture_host.py`, `scripts/phase18/computer_use_acceptance.py`, `tests/test_phase_eighteen_native_input.py`, `tests/test_phase_eighteen_owned_fixture.py`, `tests/test_phase_eighteen_evaluation_suite.py`, `tests/test_phase_eighteen_semantic_actions.py`, `tests/test_phase_eighteen_stabilization.py`, `tests/test_phase_eleven_agent_computer_tools.py`, `tests/test_phase_eleven_final_remediation.py`, `tests/test_phase_four_integration.py`, `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_03.md`, and any minimally-updated `docs/source_of_truth/*` files.
- **Commit message:** `fix: harden computer target approvals and fixtures`
- **MILESTONE_0_COMMIT:** `e4bfbcc077ae479504a8d4226e009a291ac93927`

---

## 4. Milestone 1 — GAP-0503 file-root confinement

**Commit:** `MILESTONE_1_COMMIT` (recorded in §4.6 below after push)

### 4.1 One product-owned file access policy

- New `src/jarvis/computer/file_access.py` — `FileAccessPolicy`, subordinate to `PolicyPermissionEngine` (no second permission authority). Answers exactly one question per concrete path: is it within an approved root, not sensitive, and not an escape?
- Wired into `WindowsNativeComputerController.__init__` (`file_access_policy` parameter, defaulting to a policy with **no roots** — fail-closed) and used by `_open_path`, `_inspect_file`, `_search_files` (now instance methods, no longer `@staticmethod`, since they need `self.file_access_policy`).
- `JarvisConfig.file_access_roots: tuple[str, ...] = ()` (new field) / `JARVIS_FILE_ACCESS_ROOTS` env var (platform path-separator-delimited), following the existing config conventions exactly — no second config subsystem. `bootstrap.py` constructs the policy once via `FileAccessPolicy.from_config_roots(config.file_access_roots)`.
- No manual owner action was required or requested: physical acceptance uses only a `tempfile.TemporaryDirectory()` as its approved root, per the task's explicit instruction.

### 4.2 Root model

- Roots are normalized once (`Path(...).expanduser().resolve()`), deduplicated (case-insensitively, verified with a trailing-backslash variant of the same path), and bounded to `MAX_ROOTS = 20`.
- A root must not itself be a bare drive (`C:\`), the user's home directory, or one of `AppData`/`LocalAppData`/`ProgramData`/`Windows`/`Program Files`/`Program Files (x86)`/`Users` sitting directly under a drive root — approving any of these would defeat confinement entirely (Section 8.2 of the task). Verified: `FileAccessPolicy.from_config_roots(("C:\\", str(Path.home())))` yields zero roots.
- Containment is **component-wise** (`Path.relative_to()`), never string-prefix. Verified empirically: an approved root `...\Data` correctly does **not** match a sibling `...\Database` — the classic prefix-confusion bug the task specifically calls out.

### 4.3 Sensitive path policy (defense in depth)

Applied to every resolved path regardless of which approved root it falls under:

- Directory-name-aware: `.ssh`, `.gnupg`, `.aws`, `.azure`, `.kube` anywhere in the path's components (catches e.g. `<root>\.ssh\id_rsa` and the `.ssh` directory itself).
- Exact-filename-aware: `.env`, `.env.local`, `.env.development`, `.env.production`, `.env.test`, and the browser secret stores `Login Data`/`Cookies`/`Web Data` — **`.env.example` is deliberately absent** and stays allowed (verified by test), matching the task's explicit instruction not to deny a deliberately-safe template.
- Suffix/stem-aware: `.pem`/`.key`/`.pfx`/`.p12`/`.ppk`, and `id_rsa`/`id_ed25519`/`id_ecdsa`/`id_dsa` regardless of extension.
- Substring-aware for classic OS credential/security store locations (`...\Windows\System32\config\...`, `...\Microsoft\Credentials\...`, `...\Microsoft\Protect\...`, `...\Microsoft\Crypto\...`).
- A sensitive child encountered during search is silently omitted from `matches` and only contributes to a bounded `filtered_count` — its name is never surfaced.

### 4.4 Path resolution / escape resistance

- Every path is `Path(...).expanduser().resolve()`d **before** containment/sensitivity checks — on Windows, `resolve()` follows symlinks *and* directory junctions to their real target (via the OS's `GetFinalPathNameByHandleW`-backed resolution built into CPython's `pathlib`), so a link that physically points outside an approved root is denied regardless of how it was reached.
- **This was verified empirically, not just asserted**: created a real Windows directory junction (`mklink /J`, which — unlike a symlink — does not require elevated/Developer-Mode privilege) from inside an approved root to an outside directory, confirmed `Path.resolve()` correctly resolves it to the real (outside) location, and confirmed the policy denies both the junction target file and the junction directory itself — through both the policy directly and the real `ComputerActionService` execution path.
- `..`-traversal is denied the same way (resolution normalizes it away, then containment fails against the *real* target).

### 4.5 Search behavior

- `_search_files` now: validates the root through the policy (denies if outside/unconfigured/not-a-directory), then re-checks **every individual candidate** yielded by `root.rglob(pattern)` (resolve + containment + sensitivity) rather than trusting the bulk traversal alone — this is what makes the junction-escape-in-search case above safe even though `rglob` itself happily walks into the junction.
- Bounded: `MAX_SEARCH_MATCHES = 100` (existing bound, preserved) and a new `MAX_SEARCH_CANDIDATES_SCANNED = 5000` defensive cap against runaway/circular-link traversal.
- Deterministic typed denials: unconfigured → `file_root_not_configured`; root outside approved roots → `file_path_outside_allowed_root`; no schema `"bypass"`/`"allow_external"`/`"unsafe"` flag exists anywhere.

### 4.6 Tests

New test module `tests/test_phase_eighteen_file_access.py` — 26 tests:

- **Root confinement** (8): file/folder inside an allowed root; sibling-prefix-confusion denied; `..`-traversal denied after resolve; absolute path outside denied; no-roots-configured fails closed; duplicate-root normalization; forbidden broad roots (`C:\`, home directory) rejected at construction.
- **Link/reparse** (2): junction-target escape denied; search does not follow an escape junction into its results (both gracefully skip if junction creation is unavailable in a given CI environment, per the task's own allowance).
- **Sensitive paths** (6): `.ssh/id_rsa` denied; `.env` denied; `.env.example` allowed; browser `Login Data` denied; normal `.py`/`.txt` files allowed; a sensitive child is omitted from search with a bounded `filtered_count`.
- **Integration, through the real `ComputerActionService` → controller path** (10): `inspect_file`/`search_files`/`open_file`/`open_folder` all honor the policy; search excludes `.env` while including normal/nested files; outside-root denials for each of the four capabilities; canonical `computer.permission_checked` audit still recorded even for a denied file action; a completely unconfigured runtime denies every path-requiring action; the junction-escape case reproduced through the real service path (not just the policy unit).

No pre-existing test broke — none of the current test suite previously exercised these four capabilities' real path-confinement behavior (confirmed by running the full suite before and after this milestone's change with identical pass counts aside from the new tests).

Results:

```text
python -m pytest tests -k "computer or file or phase_eighteen" -q
193 passed, 496 deselected

python -m pytest tests -q
688 passed, 36 subtests passed

python -m compileall src tests scripts -q
(clean)

git diff --check
(clean)
```

### 4.7 GAP-0503

Marked `RESOLVED` (path-confinement scope only) per the task's own Section 8.13 closure criteria — see the Gap register update in §9 below for the exact scoping language (this does **not** mean file dialogs, write/move/copy/rename/delete, or rollback/recycle-bin support exist; none of that was in this milestone's scope and none of it was implemented).

### 4.8 Commit

- **Files staged (explicit paths, no `git add .`):** `src/jarvis/computer/file_access.py`, `src/jarvis/computer/service.py`, `src/jarvis/config.py`, `src/jarvis/bootstrap.py`, `tests/test_phase_eighteen_file_access.py`, `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_03.md`, `docs/source_of_truth/02_JARVIS_CURRENT_STATE.md`, `docs/source_of_truth/03_JARVIS_GAP_REGISTER.md`, `docs/source_of_truth/04_JARVIS_EXECUTION_ROADMAP.md`, `docs/source_of_truth/05_JARVIS_DECISION_LOG.md`.
- **Commit message:** `fix: confine computer file access to approved roots`
- **MILESTONE_1_COMMIT:** `a21ae23d1aa81aa507b0d2b3527a7cfe513a2bc4`

---

## 5. Milestone 2 — Input expansion + owned-fixture evaluation + multi-monitor physical proof

**Commit:** `MILESTONE_2_COMMIT` (recorded in §5.6 below after push)

### 5.1 Extended pointer actions

- `computer.pointer.act` gained three new `action` enum values, all reusing the exact same element-grounding (`_ground()`) pipeline as `move_to_element`/`left_click_element` - never a second targeting implementation:
  - `right_click_element` — move + `MOUSEEVENTF_RIGHTDOWN`/`RIGHTUP`. Never assumes a context menu opened merely because input was delivered; stays honestly unverified.
  - `double_click_element` — move + two full left-click pairs (down/up ×2) in one bounded `SendInput` batch. Exactly one double-click sequence, never an arbitrary click count; no timing is ever exposed to the model.
  - `scroll_element` — new bounded `direction` (`up`/`down`) and `steps` (1-5) parameters; internally a signed multiple of `WHEEL_DELTA=120` via `MOUSEEVENTF_WHEEL` — never a raw wheel delta from the model. Reports delivery evidence only, never a generic "content changed" claim.
- All three (plus the existing two) are in `ComputerActionService._element_targeted_actions`, so they automatically get the full R18B02-001 trusted-preview/approval-binding treatment from Milestone 0 — no separate approval path was written for them.

### 5.2 Named chord surface

- New `computer.keyboard.chord` tool with a five-entry allowlist: `ctrl+a`, `ctrl+c`, `ctrl+f`, `ctrl+z`, `ctrl+y`. Deliberately excludes paste (`ctrl+v`), save (`ctrl+s`), `alt+f4`, any Windows-key combination, and Ctrl+Alt+Delete — verified by test that none of these ever reach the allowlist or the schema.
- `WindowsNativeInputAdapter.press_key`/`press_chord` were refactored to share one `_press_key_sequence`/`_ground_window` implementation — modifier-interference checking, press/release sequencing, and guaranteed cleanup are now written once, not duplicated for the chord path.
- Chord actions are window-targeted (`_window_targeted_actions`), getting the same R18B02-003 trusted window-title/process preview as `computer.keyboard.key`.

### 5.3 Owned-fixture evaluation suite expansion

The `computer_use_v2` deterministic suite grew from 17 to **24** cases (`src/jarvis/evaluation/computer_use_v2.py`), still entirely fake/mock-based with no GUI dependency (verified: `subprocess.Popen` is patched to raise in `test_no_physical_test_runs_by_default`, and it still passes). New cases: window-targeted approval preview is trusted (title/process, no raw parameter dump); file-root confinement (inside allowed vs. outside denied); sensitive-path denial (`.env`); path-resolution escape refusal (a `..`-escape — the real junction-based proof deliberately stays in the dedicated `test_phase_eighteen_file_access.py` unit tests, since creating a real junction requires spawning a subprocess, which this deterministic suite must never do); right-click/double-click/scroll all still refuse for a weak-identity target (proving they stay element-grounded, not a separate code path); the chord allowlist rejects `ctrl+v` (requested, approved, then denied at execution by the adapter's own allowlist check — not a naive "immediately denied" assumption); and no `paste`/`drag`/`drop` substring exists anywhere in any computer tool's schema.

### 5.4 Owned fixture host improvements + physical acceptance (3 clean iterations)

- Added an evaluation-only `--x`/`--y` launch flag to `scripts/phase18/uia_fixture_host.py` for the non-primary-monitor scenario (never a general production window-move capability).
- **A second real bug was found and fixed during this milestone's own physical testing**: the fixture's message loop never called `IsDialogMessageW`, which Win32 requires for Tab-key focus-cycling between `WS_TABSTOP` children to work at all on a plain (non-dialog) top-level window — every Tab-key test reported focus never moved until this was found (via a targeted before/after-focus debug probe) and fixed.
- The acceptance runner (`scripts/phase18/computer_use_acceptance.py`) was extended to exercise every new scenario, plus a dedicated non-primary-monitor scenario: confirms NIGHTFURY's real virtual-desktop topology (recorded, never altered), launches the fixture positioned on the negative-X monitor, confirms via semantic read that the target element's bounds are genuinely there (`x < 0`), and performs one grounded native left click, independently verified via the fixture's own status read-back.

Run via `python scripts/phase18/computer_use_acceptance.py --runs 3` on NIGHTFURY — see the full table in §6 below. Every scenario passed 3/3 after the two fixes above; no retry-until-green was used (the first run, before the `IsDialogMessageW` fix, honestly reported `native_key_tab: 0/3` and was fixed, then re-run cleanly — not hidden).

### 5.5 Tests

New/updated tests:

- `tests/test_phase_eighteen_native_input.py` — new `ExpandedPointerActionTests` (8 tests: right-click element-grounded/denied-for-weak-identity, double-click sends exactly two click pairs, scroll sends a correctly-signed bounded wheel delta up/down, out-of-range steps/invalid direction denied, offscreen-target denial) and `ChordTests` (5 tests: allowed chord succeeds, every unlisted chord in a representative forbidden list is denied, owner-held-modifier fails safely, JARVIS's own modifier is always released, chord is window- not element-grounded). `ArchitectureTests` gained 6 more tests: right-click/double-click/scroll/chord each require approval and execute exactly once through the real `ComputerActionService`; the chord schema contains no paste/arbitrary-hotkey capability; no computer tool's schema contains `drag`/`drop`/`paste` anywhere.
- `src/jarvis/evaluation/computer_use_v2.py` — 7 new deterministic cases (§5.3 above), `tests/test_phase_eighteen_evaluation_suite.py` unaffected (still passes with the larger case count).
- `tests/test_phase_eighteen_owned_fixture.py` — updated fake summary shape for the new `non_primary_monitor` field; all existing safety checks (no broad `taskkill`, no owner-app dependency, no full window enumeration, exact-PID cleanup) still pass against the expanded runner.

Results:

```text
python -m pytest tests -k "evaluation or phase_eighteen" -q
194 passed, 514 deselected

python -m pytest tests -q
708 passed, 36 subtests passed

python -m compileall src tests scripts -q
(clean)

git diff --check
(clean)

cd ui && npm test -- --run
14 test files, 75 passed

npm run build
built in 835ms

npm audit --audit-level=high
exit 0 (2 pre-existing moderate, unrelated dev-dependency)
```

### 5.6 Commit

- **Files staged (explicit paths, no `git add .`):** `src/jarvis/computer/native_input.py`, `src/jarvis/computer/service.py`, `src/jarvis/contracts/computer.py`, `src/jarvis/tools/registry.py`, `src/jarvis/authority/permissions/engine.py`, `src/jarvis/evaluation/computer_use_v2.py`, `scripts/phase18/uia_fixture_host.py`, `scripts/phase18/computer_use_acceptance.py`, `tests/test_phase_eighteen_native_input.py`, `tests/test_phase_eighteen_owned_fixture.py`, `tests/test_phase_eighteen_evaluation_suite.py`, `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_03.md`, `docs/source_of_truth/02_JARVIS_CURRENT_STATE.md`, `docs/source_of_truth/03_JARVIS_GAP_REGISTER.md`, `docs/source_of_truth/04_JARVIS_EXECUTION_ROADMAP.md`.
- **Commit message:** `feat: expand grounded input and computer-use evaluation`
- **MILESTONE_2_COMMIT:** `5aaa69c927f79adf0e4485e5a94dbd19e207683d`

---

## 6. Physical results table (all runs, all milestones, owned fixture only)

| Scenario | Milestone | Runs | Result | Independent evidence |
| --- | --- | --- | --- | --- |
| Semantic invoke | 0 & 2 | 3/3 + 3/3 | PASS | Fixture status label reads `"invoked"` every time |
| Semantic toggle | 0 & 2 | 3/3 + 3/3 | PASS | Adapter fresh post-state re-check `true`; status label `"toggle:on"` |
| Semantic select | 0 & 2 | 3/3 + 3/3 | PASS | Adapter fresh `IsSelected` re-check `true` (fixture label can't observe it — documented `LBN_SELCHANGE` limitation) |
| Native left click | 2 | 3/3 | PASS | `pointer_target_verified` via real `GetCursorPos`; status label `"invoked"` |
| Native right click | 2 | 3/3 | delivered, honestly unverified | `input_batch_accepted=true`; no status change expected (no context menu assumed) |
| Native double click | 2 | 3/3 | PASS | Status label `"invoked"` (both underlying clicks landed) |
| Native scroll | 2 | 3/3 | delivered, honestly unverified | `input_batch_accepted=true`; no "content changed" claim |
| Native Tab key (focus) | 2 | 3/3 (0/3 before the `IsDialogMessageW` fix, disclosed not hidden) | PASS | Independent focus read-back: Invoke Target → Toggle Target |
| Native chord (`ctrl+c`) | 2 | 3/3 | delivered | No observable effect on this fixture expected or claimed |
| Non-primary-monitor click | 2 | 3/3 | **`NON_PRIMARY_MONITOR_PHYSICAL_PASS`** | Target bounds confirmed `x<0`; status label `"invoked"` |
| Fixture child process cleanly exited | 0 & 2 | 3/3 each | PASS | `Popen.poll()` non-`None` after `terminate()`/`wait()` |

No scenario was retried to force a pass. The one honest failure (Tab key, 0/3, before the fixture bug was found and fixed) is recorded above rather than hidden.

## 7. Final tests

At final branch HEAD (`5aaa69c927f79adf0e4485e5a94dbd19e207683d`):

```text
python -m pytest tests -q
708 passed, 36 subtests passed

python -m compileall src tests scripts -q
(clean)

git diff --check
(clean)

cd ui && npm test -- --run
14 test files, 75 passed

npm run build
built in 835ms

npm audit --audit-level=high
exit 0 (2 pre-existing moderate vitest/mocker advisories, unrelated dev-dependency, no high/critical)
```

## 8. Security review

Explicit checklist (Section 11 of the task file), each verified directly against the final diff/code:

**Authority:** one `ComputerActionService`, one `PolicyPermissionEngine`, one `DurableApprovalEngine`, no direct tool→adapter bypass — all unchanged/reused, no second instance created anywhere.

**UI targeting:** no weak-identity action (`uia_element_identity_weak` denial, reused by every element-targeted action including the three new pointer actions); no stale-target action; pointer approval is target-bound (R18B02-001, `_element_targeted_actions`); window-key/chord approval is target-bound (R18B02-003, `_window_targeted_actions`); approval cannot outlive the actual reference (`min(10min, reference_expires_at)`, computed once); no polling-TTL-extension bug (verified by `test_polling_preview_does_not_extend_pending_approval`).

**Native input:** no raw x/y in any model schema (checked programmatically); no raw HWND; no raw VK/scancode (`computer.keyboard.key`'s `key` is a closed enum, `computer.keyboard.chord`'s `chord` is a closed 5-entry enum); no arbitrary hotkey string; no `ctrl+v` anywhere (grepped + evaluation-suite case); no drag/drop (grepped, not implemented); no UIAccess/elevation request anywhere in the code; a partial/zero `SendInput` count is always reported as the generic, honest `native_input_injection_failed`.

**Files:** no default unrestricted disk access (fail-closed with zero configured roots); no string-prefix root comparison (component-wise `Path.relative_to`, verified sibling-prefix-confusion resistant); link/junction escape addressed (verified empirically with a real Windows junction, both directly and through the real service path); sensitive-path deny list exists and is applied as defense in depth; no file-dialog automation exists; no path-policy bypass (all four capabilities route through the one policy, no "unsafe"/"bypass" schema flag anywhere).

**Physical test safety:** no Notepad, no Edge/Chrome dependency (both fully removed as fixtures after Batch 02's incident); no broad process-name kill anywhere in the runner (verified: `taskkill` appears only in the module docstring's own explanation of what it deliberately does not do); exact-PID-only cleanup (`Popen.terminate()`/`wait()`/`poll()`); unique nonce title per run; a title collision aborts rather than guesses; no owner window was ever enumerated-and-acted-on (only the runner's own exact-nonce-matched fixture); no owner document was touched; no secrets appear in any changed file (grepped; the one match was a benign hardcoded test string, `"super-secret-literal-text"`, used only to prove raw text is never persisted in an approval preview).

## 9. Gap state (final, this batch)

| Gap | Status | Note |
| --- | --- | --- |
| GAP-0101 (general Windows semantic UI control) | `RESOLVED` (core semantic capability) | invoke/toggle/select all physically proven 3/3 twice (Milestones 0 and 2) via the owned fixture; broader Computer Use V2 breadth continues under the gaps below |
| GAP-0102 (mouse/keyboard) | `PARTIAL` | right-click/double-click/scroll/one chord added and physically proven; paste, drag/drop, arbitrary hotkeys remain deliberately absent |
| GAP-0103 (OCR/visual) | `OPEN` | untouched this batch |
| GAP-0104 (multi-app recovery) | `PARTIAL` | generalized fresh re-observation/target-change refusal to element- and window-targeted actions alike; still no autonomous multi-app replanning loop |
| GAP-0105 (evaluation suite) | `PARTIAL` | 24-case deterministic suite plus a 3x-run opt-in physical runner across 10 scenario types; still a single-fixture foundation, not the broad real-app matrix named in the gap's original scope |
| GAP-0106 (DPI/multi-monitor/secure-desktop) | `PARTIAL` | non-primary-monitor physical click now proven (`NON_PRIMARY_MONITOR_PHYSICAL_PASS`); non-100%-DPI and secure-desktop physical proof remain pending (no suitable hardware/UAC-trigger, per the task's own explicit allowance) |
| GAP-0503 (file-root confinement) | `RESOLVED` (path-confinement scope) | all four existing path-requiring capabilities confined; write/move/copy/rename/delete and file dialogs remain unimplemented and out of this scope |

## 10. Manual dependencies

`NONE`. No API key, account, or token was needed anywhere in this batch. GitHub push auth was already configured (all three milestone pushes succeeded without any credential prompt or failure). File access policy is intentionally unconfigured/fail-closed by default after this batch — the owner can configure personal `JARVIS_FILE_ACCESS_ROOTS` later when real file workflows are started; the owner was not asked to choose roots during implementation, matching Section 14 of the task file. No `OPTIONAL_PHYSICAL_MULTI_MONITOR_STEP` was needed this batch either — NIGHTFURY's real 2-monitor topology let the runner test the non-primary monitor itself, with no owner assistance required.

## 11. Incident-safety changes (carried forward from Batch 02, reinforced this batch)

- Batch 02's incident (a supposed disposable Notepad probe attached to the owner's live single-instance Notepad session, likely losing one unsaved tab) directly motivated this entire batch's Milestone 0 fixture replacement. From this batch forward, Notepad/Edge/Chrome/VS Code/terminal/Explorer/Calculator/any owner-installed application is never used as a physical acceptance fixture — only the fully JARVIS-owned `uia_fixture_host.py`.
- No broad `taskkill /IM ...` exists anywhere in the runner; cleanup is always exact-PID `terminate()`/`wait()`/liveness-confirmation.
- Every fixture launch carries a fresh random nonce in its window title; the runner waits only for an exact title match and aborts on any collision, never falling back to "first similar title" — directly closing the class of bug that let the Notepad incident happen (attaching to a window that merely *looked* like the intended target).
- Two additional, unrelated real bugs were found and fixed during this batch's own physical testing (both disclosed in §3.4/§5.4 above, neither hidden): 64-bit ctypes marshaling truncation in the fixture host's WinAPI calls, and a missing `IsDialogMessageW` call that silently broke Tab-key focus-cycling. Both are evidence the "run it for real, don't just unit-test it" discipline this batch followed is doing its job.

## 12. Recommended next batch

In priority order:

1. **Broaden the evaluation suite toward its originally-named real-app breadth (GAP-0105)** — carefully, using only disposable/owner-safe fixtures informed directly by the Batch 02 Notepad incident; the owned Win32 fixture pattern from this batch is a template for adding more fixture *types* (e.g. a second owned fixture exercising a text-edit control) rather than reusing owner apps.
2. **Paste, drag/drop, richer/arbitrary-but-still-bounded hotkeys (GAP-0102 remainder)** — paste specifically needs a design for how an approval preview can be trustworthy without ever exposing live clipboard contents (Section 9.6 of this batch's task already reasons through why it was deferred).
3. **Autonomous multi-app recovery/replanning (GAP-0104 remainder)** — still no auto-retry or cross-application recovery loop; any design here must preserve the "no auto-retry after uncertain action" invariant this batch (and Batch 02) both depended on.
4. **Non-100%-DPI and secure-desktop physical demonstrations (GAP-0106 remainder)** when suitable hardware/config becomes available — do not fabricate or force these.
5. **File write/move/copy/rename/delete and file-dialog automation** — GAP-0503's original broader scope, deliberately deferred; should build directly on this batch's `FileAccessPolicy` rather than a parallel mechanism, and file-dialog automation specifically remains blocked pending a separate, deliberate design review (per the original GAP-0503 task language).
6. **OCR/visual fallback (GAP-0103)** only after the above, per the existing roadmap ordering.
