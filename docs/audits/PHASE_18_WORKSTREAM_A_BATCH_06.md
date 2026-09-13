# PHASE 18 — WORKSTREAM A — BATCH 06
## OCR Runtime Purity + Reproducibility → Arabic Physical OCR Proof → Physical Recovery Validation

**Task:** `tasks/PHASE_18_WORKSTREAM_A_BATCH_06_MASTER_TASK.md` (pasted in full by the requester)
**Branch:** `feature/phase-18-computer-use-v2`
**Status:** Milestones 0, 1, and 2 complete and pushed.

Batch 05's independent verdict was `BATCH05_NEEDS_FIX` (R18B05-001/002/003). Batch 05's implementation was **not** rolled back - it remains the working base this batch hardens.

This is the single report for the whole batch; it is appended to, not duplicated, as later milestones complete.

---

## 1. Preflight

- Branch: `feature/phase-18-computer-use-v2` — confirmed exact match.
- Starting HEAD: `a5d37daca8b2c0af42b8356109d261b523b22d7f` — confirmed exact match (local `HEAD` and `origin/feature/phase-18-computer-use-v2` identical).
- `git status --short` — clean before any edit.
- `main` — unchanged (`origin/main` at `54b67ba396ec45180f1b60ea472ef94c9ac181a9`, untouched).
- No unexplained commits between the required starting HEAD and local `HEAD` (`git log --oneline` confirmed the exact expected Batch 05 chain: `81423ca`, `d569c06`, `2ac574f`, `a5d37da`).

---

## 2. Milestone 0 — BLOCKING independent-review closure

### R18B05-001 — offline-only production OCR initialization

**Problem confirmed:** `src/jarvis/computer/visual_ocr.py`'s `_default_reader_factory` (Batch 05) called `easyocr.Reader(["ar", "en"], gpu=False, verbose=False)` with no `download_enabled` argument (EasyOCR 1.7.2 defaults this to `True`) and no explicit `model_storage_directory`/`user_network_directory` (defaulting to `~/.EasyOCR`). A missing/corrupt model behind a read-only, no-approval capability could therefore trigger an HTTP download and an implicit cache write beneath the owner's home directory.

**Root-cause investigation (real EasyOCR 1.7.2 source, read directly - not assumed):** `Reader.__init__` unconditionally calls `Path(model_storage_directory).mkdir(parents=True, exist_ok=True)` and the same for `user_network_directory`, **regardless** of `download_enabled`. Both `getDetectorPath()` (detection model) and the recognition-model check compute an MD5 of any existing file and, only if `download_enabled` is `True`, call `download_and_unzip(...)` on a missing or checksum-mismatched file; with `download_enabled=False` both instead raise `FileNotFoundError` with **no** network call reached in either the missing or the corrupt case. This was verified by installing real EasyOCR 1.7.2 into a disposable isolated venv (never the project's own `.venv`) and reading `easyocr/easyocr.py` and `easyocr/config.py` directly.

**Fix implemented (`src/jarvis/computer/visual_ocr.py`):**
- `EasyOcrVisualAdapter` gained a `model_dir: str | None` constructor parameter (config-only, never a model-facing tool parameter), threaded from `JarvisConfig.ocr_model_dir` (new field, env var `JARVIS_OCR_MODEL_DIR`, no implicit home-directory fallback - an unset/empty value means "unavailable", never "use EasyOCR's own default") through `WindowsNativeComputerController.__init__`'s new `ocr_model_dir` parameter and `bootstrap.py`.
- A new `_models_ready()` method is called at the very top of both `ocr_window`/`ocr_element` (before any window validation or capture): it verifies `model_dir` is configured, that `<model_dir>/model` and `<model_dir>/user_network` both already exist as directories, and that both required model weight files (`OCR_DETECTION_MODEL_FILENAME = "craft_mlt_25k.pth"`, `OCR_RECOGNITION_MODEL_FILENAME = "arabic.pth"` - the exact two files a `Reader(["ar","en"], detect_network="craft")` construction needs, confirmed by reading `easyocr.config.detection_models["craft"]`/`recognition_models["gen1"]["arabic_g1"]` and `Reader.__init__`'s auto-detect branch directly) already exist as files. Only when all of that is true does the real `Reader()` ever get constructed - EasyOCR's own unconditional `mkdir` is therefore always a no-op against a directory JARVIS itself already required to exist, never a JARVIS-initiated cache creation. A test-injected fake `reader_factory` (the existing Batch 05 test pattern) bypasses this gate entirely, since it is never the real EasyOCR package.
- `_default_reader_factory` (now an instance method, since it needs `self.model_dir`) always passes `download_enabled=False` explicitly, plus the two explicit directories - never EasyOCR's own default resolution. A `FileNotFoundError` raised by EasyOCR's own MD5 check (corrupt/mismatched file) is caught and translated to the typed `visual_ocr_models_unavailable` result (new `_OcrModelsUnavailableError` marker), matching every other missing-model case - never a redownload attempt.
- No approval is requested merely because models are unavailable - `computer.visual.read` was already, and remains, a `_read_actions`-classified capability with no approval path at all.

**Provisioning boundary:** `scripts/setup/provision_easyocr_models.py` (new) is a standalone, never-imported-by-production CLI script. It downloads and MD5-verifies the same two model files from the same URLs EasyOCR's own downloader would use (recorded, not re-derived at runtime), into a directory the operator explicitly passes via `--model-dir` or `$JARVIS_OCR_MODEL_DIR` (no implicit home-directory default in the script either), and separately checks that the installed `easyocr`/`torch`/`torchvision` versions match the pinned reproducible ones. It is not registered as a tool, not triggered by OCR, and not triggered by core startup - grep-confirmed (`grep -rn "provision_easyocr_models" src/` finds only two docstring references, no import).

**Physical evidence (real EasyOCR, real download, real offline construction):** the provisioning script was actually run against a disposable scratch directory - it downloaded both files from GitHub, verified their MD5 checksums matched exactly (`2f8227d2...`/`993074555...`), and reported success. Then, in the same disposable isolated venv used for Batch 05's physical OCR proof (real EasyOCR 1.7.2, real CPU PyTorch 2.14.0), the **actual production** `EasyOcrVisualAdapter._default_reader_factory()` (not a mock) was invoked directly against that provisioned directory: it returned `_models_ready() == None` and constructed a real `easyocr.easyocr.Reader` instance in 2.08s with `download_enabled=False` and zero network activity. This is direct physical proof that the offline gate and the real EasyOCR package interoperate correctly, not just that the gate's own logic is internally consistent.

**Tests added (`tests/test_phase_eighteen_visual_ocr.py`, new `OfflineModelProvisioningTests` class, 8 tests):** production reader factory passes `download_enabled=False` plus explicit `model_storage_directory`/`user_network_directory` (via a fake stand-in for the `easyocr` module, recording the exact kwargs); `computer.visual.read` never constructs a `Reader` at all when the model directory is unconfigured (proven with an `_unreachable_reader` fake that raises `AssertionError` if ever called); no implicit home-directory fallback for an empty `model_dir`; fails closed when the model directory is absent; fails closed when a required model file is missing; `ocr_element` fails closed **before** any semantic resolution call (zero calls to the semantic adapter); a corrupt/checksum-mismatched model (simulated via a fake raising the exact `FileNotFoundError` real EasyOCR raises with `download_enabled=False`) fails closed without any redownload attempt; the existing test-injected-fake-reader pattern still bypasses the gate correctly (regression guard for every other Batch 05 test in this file). All 8 pass; each of these tests needs no real `easyocr` package installed.

### R18B05-002 — reproducible offline CPU runtime

**Investigation:** installed EasyOCR 1.7.2 fresh into a disposable isolated venv, plain PyPI, no alternate index configured. Resolved versions: `torch==2.14.0` (`torch.__version__ == "2.14.0+cpu"`, `torch.version.cuda is None`), `torchvision==0.29.0` (`"0.29.0+cpu"`). On this platform (Windows) and at these exact versions, PyPI's default wheel is itself CPU-only - no `--index-url` trick was needed or used. This confirms no decision change to DEC-048 is required; EasyOCR 1.7.2 on this exact CPU-only PyTorch/torchvision pair remains the accepted runtime.

**Fix:** `pyproject.toml`'s `computer-ocr` extra now pins `torch==2.14.0` and `torchvision==0.29.0` explicitly, alongside `easyocr==1.7.2` - not left to EasyOCR's own unpinned/broadly-constrained requirements, closing the drift risk (a future install silently resolving a different or CUDA-heavy runtime).

**Verification mechanism (dual, per the task's "test or script check"):** `scripts/setup/provision_easyocr_models.py`'s `_check_runtime_versions()` checks exact versions and `torch.version.cuda is None` as part of the one-time setup flow; `tests/test_phase_eighteen_ocr_reproducibility.py` (new) additionally provides a standing regression guard - one test (`test_pinned_versions_match_pyproject_extra`) always runs and needs no optional dependency installed; three more skip cleanly when `easyocr`/`torch`/`torchvision` are absent (the normal case for this repository's own `.venv`) and assert the exact pinned versions plus a genuinely CPU-only build when they are present. Run for real against the isolated venv with real packages installed: all 4 passed.

### R18B05-003 — one recovery budget per drag action

**Problem confirmed:** `drag_element_to_element()` called `_ground_drag_pair_with_recovery()` twice - once before focus, once again after focus (since focus can change layout) - and each call owned its own independent one-retry allowance, so a single drag request could consume up to two separate bounded recovery cycles, not the one-per-action contract the Batch 05 report claimed.

**Fix (`src/jarvis/computer/native_input.py`):** a new `_RecoveryBudget` dataclass (`used: bool = False`) is instantiated exactly once per `drag_element_to_element()` call and passed into **both** calls to `_ground_drag_pair_with_recovery`, which now takes it as a required parameter: it only retries when the first attempt failed for a recoverable-class error **and** `budget.used` is still `False`; either way it sets `budget.used = True` before returning if it recovers. The underlying `_ground_drag_pair()` method is unchanged. Single-target actions (`move_to_element`, etc.) each already called `_ground_with_recovery` exactly once per action - no change needed there.

**Tests added (`tests/test_phase_eighteen_native_input.py`, new `RecoveryBudgetScopeTests` class, 3 tests, plus a new `_ScriptedSemanticAdapter` fake supporting non-monotonic fail/succeed/fail sequences that the existing `_FlakyOnceDragSemanticAdapter` could not express):**
- pre-focus grounding needs and consumes the one recovery; the post-focus grounding's own transient failure afterward gets **no** second recovery and the drag ends in a clean typed failure (3 total resolve calls for the source ref: fail, recovered-success, fail-with-no-retry).
- when pre-focus grounding needs no recovery, the **unused** budget carries over and the post-focus grounding may still consume it (3 total resolve calls: success, fail, recovered-success) - proving the budget is genuinely shared, not independently reset per call site.
- the task's own "two sequential transient failures within one logical action" acceptance phrasing, reproduced directly: only one of the two is recovered, the drag ends in a clean typed failure.
- Pre-existing coverage already proves the remaining required scenarios unchanged: normal drag has zero recovery calls (`test_drag_revalidates_both_endpoints_after_focus`, exactly 2 resolve calls per endpoint); a policy denial never retries (`test_drag_non_recoverable_denial_never_retries`); once `SendInput` begins, recovery remains impossible (`test_drag_partial_injection_failure_after_recovered_grounding_still_never_retries`).

### 2.4 Milestone 0 verification

- `python -m pytest tests/test_phase_eighteen_visual_ocr.py tests/test_phase_eighteen_native_input.py -q` → **129 passed** (was 118 before this milestone; +8 offline-model tests, +3 budget-scope tests).
- `python -m pytest tests/test_phase_eighteen_ocr_reproducibility.py -q` → **1 passed, 3 skipped** in this repo's own `.venv` (no `computer-ocr` extra installed); **4 passed, 0 skipped** re-run directly inside the isolated evaluation venv with real `easyocr`/`torch`/`torchvision` installed.
- `python -m pytest tests -k "file_access or phase_eighteen or ocr" -q` → **281 passed, 3 skipped, 515 deselected**.
- `python -m pytest tests -k "config or bootstrap" -q` → **30 passed** (new `ocr_model_dir` config field does not break existing config/bootstrap behavior).
- `python -m pytest tests -q` (full regression) → **796 passed, 3 skipped, 36 subtests passed** in 237.26s (784 + 12 new: 8 offline-model tests, 3 recovery-budget-scope tests, 1 always-run reproducibility pin test; the 3 skips are the reproducibility suite's real-package checks, which correctly skip in this repository's own `.venv` and were separately confirmed to pass - 4/4 - inside the isolated evaluation venv with real `easyocr`/`torch`/`torchvision` installed).
- `python -m compileall src tests scripts -q` → clean, no errors.
- `git diff --check` → clean, no whitespace errors.

### 2.5 Static security review (per task Section 3, before continuing to Milestone 1)

- **Runtime network calls:** `grep -n "urllib\|requests\|socket\.\|http://\|https://\|urlopen\|urlretrieve" src/jarvis/computer/visual_ocr.py src/jarvis/computer/native_input.py src/jarvis/computer/service.py` → zero matches in executable code (one docstring line mentioning "requests UIAccess" in an unrelated Win32-input comment, not a network call). The only network code (`urllib.request.urlretrieve`) lives exclusively in `scripts/setup/provision_easyocr_models.py`, never imported by production.
- **Hidden cache writes:** production OCR code performs zero filesystem writes (`_models_ready()` only calls `.is_dir()`/`.is_file()`) - `grep -n "mkdir\|makedirs" src/jarvis/computer/visual_ocr.py` matches only a docstring sentence describing EasyOCR's own internal behavior, not a JARVIS-initiated write.
- **Second authority:** `git diff --stat src/jarvis/tools/registry.py src/jarvis/authority/permissions/engine.py` → empty; neither file was touched this milestone. No new permission/approval/authority path was introduced - the offline gate and the recovery-budget fix are both entirely inside existing execution-provider code.
- **Visual actuation:** no new action, capability, or code path was added this milestone - `computer.visual.read` remains exactly `ocr_window`/`ocr_element`, observation-only.
- **Recovery after side effect:** re-confirmed by direct inspection that every `_ground_with_recovery`/`_ground_drag_pair_with_recovery` call site in `native_input.py` still occurs strictly before its corresponding `_send_input(...)` call(s) - the budget-scoping change only threads a shared object between two grounding calls that were already both pre-`SendInput`; it does not move either call relative to injection.

No R18B05-001 boundary remains open. Milestone 0 is green.

**Commit:** `04904b3b8f5639bb566fa95bf8739364c54cc742`
**Push:** `feature/phase-18-computer-use-v2` (`a5d37da..04904b3`) — pushed.

---

## 3. Milestone 1 — Arabic/mixed physical OCR acceptance

### 3.1 Third owned fixture

`scripts/phase18/uia_ocr_fixture_host.py` (new) - a JARVIS-owned, standalone Win32 process (stdlib `ctypes`+`user32.dll` only, no third-party GUI framework), matching the exact safety discipline of the first two fixtures: fresh nonce window title (`JARVIS-CUV2-OCR-FIXTURE-<uuid>`), no network/clipboard/file-dialog calls, never imported by production. Unlike the first two fixtures it carries **no actuation surface at all** - every control is a plain STATIC/TextControl label, read only through `computer.visual.read` and, for cross-checking, `computer.semantic.read`. Labels:

- `"JARVIS OCR fixture ready"` (English)
- `"مرحبا يا جارفيس"` (Arabic-only, "Hello JARVIS")
- `"الإعدادات"` (Arabic-only, "Settings")
- `"JARVIS الإعدادات"` (mixed Latin+Arabic)
- `"JARVIS OCR FIXTURE"` (English-only, cross-check)

These are plain Python `str` literals containing real Arabic Unicode codepoints in ordinary logical order, passed straight through `SetWindowTextW`'s `LPCWSTR` marshaling - no reshaping/bidi library on the JARVIS side, deliberately, because a live Win32 STATIC control's own rendering already goes through Windows' own Uniscribe/DirectWrite shaping engine (the exact pipeline an *offline* PIL-rendered PNG, Batch 04/05's benchmark fixture, does not have without an explicit shaping library). A source-safety test (`tests/test_phase_eighteen_owned_fixture.py::OcrFixtureSourceSafetyTests::test_fixture_uses_real_arabic_unicode_not_a_latin_transliteration`) asserts every character in the Arabic-only labels falls in the Arabic Unicode block, guarding against an accidental future substitution.

Visually confirmed before any OCR was run: a real screenshot of the live fixture window shows all 5 labels rendered correctly, with both Arabic labels properly joined and right-to-left (the screenshot itself was deleted immediately after visual confirmation - not committed, not retained, contained only JARVIS-authored fixture text).

### 3.2 Physical acceptance runner

`scripts/phase18/ocr_visual_acceptance.py` (new) - mirrors `computer_use_acceptance.py`'s safety discipline (exact-nonce window matching, exact-PID `Popen.terminate()`/`wait()` cleanup, never an owner app) but drives the **real** `computer.visual.read` tool through a **real** production runtime (`create_runtime(JarvisConfig(ocr_model_dir=<provisioned dir>))`), never a fake reader. Each `computer.visual.read` call runs inside a scoped network guard (`socket.socket.connect` patched to raise if ever invoked, restored immediately after) - proving zero network access, not merely asserting the offline-gate logic looks correct in isolation. Results (including Arabic text) are always written to a UTF-8 JSON file, never printed to the console (the default `cp1252` codec cannot encode Arabic).

Run against the real, disposable-isolated-venv-provisioned model directory (via `scripts/setup/provision_easyocr_models.py`, real EasyOCR 1.7.2 / CPU PyTorch 2.14.0 / `uiautomation` 2.0.29 installed together in one isolated venv - never the project's own `.venv`), **3 clean iterations, no retry-until-green**:

| Label | Script | Exact match | Confidence | Notes |
|---|---|---|---|---|
| `مرحبا يا جارفيس` | Arabic-only | **3/3** | 0.745 | Recognized verbatim, byte-for-byte, every run. |
| `الإعدادات` | Arabic-only | **3/3** | 0.773 | Recognized verbatim, byte-for-byte, every run. |
| `JARVIS الإعدادات` | Mixed | 0/3 (whole string) | 0.608 | The Arabic portion (`الإعدادات`) recognized correctly inside the same region every run; only the Latin portion misread (`JARVIS`→`JARMIS`). |
| `JARVIS OCR fixture ready` | English | 0/3 | 0.465 | `JARVIS`→`JARMIS` (V/M confusion), rest correct. |
| `JARVIS OCR FIXTURE` | English (caps) | 0/3 | 0.151 | Multiple character-level misreads (`A`→`4`, `O`→an Arabic-indic digit, `X`→`S`). |

**This is honest, unmassaged evidence, not a failure of the milestone's actual goal.** The two pure-Arabic labels - the specific thing Batch 05's recommended follow-up flagged as unproven through a live GUI - are recognized perfectly, consistently, with good confidence, through the real production pipeline. The English-side character-level weakness is a genuine, now-directly-observed characteristic of EasyOCR's combined bilingual `arabic_g1` recognition network (which prioritizes the non-Latin script) - already an accepted trade-off under DEC-048 (whose own gates were normalized recall, not exact string match), not a regression, and not something this report retried or reshaped fixture content to hide.

**`ocr_element` crop-boundary finding:** cropping tightly to just the Arabic-greeting element's UIA bounds caused EasyOCR's own CRAFT text detector to segment the 3-word line into 2 separate regions (`"جارفيس"` at 0.998 confidence, `"مرحبا"` at 0.994 confidence) instead of one combined line - both fragments individually correct and higher-confidence than the whole-line detection, but the strict single-region exact-match check used for `ocr_window` above reports this as "no match" for `ocr_element`. This is a text-detection segmentation artifact of tight cropping, not a recognition-accuracy problem, and is recorded here rather than worked around.

**Latency:** each of the 3 runs constructs a brand-new runtime (never reusing a prior run's already-loaded model), so `ocr_window`'s reported 4.95-5.25s is a **cold** figure (one-time `Reader()` construction, independently measured at ~2.1s, plus first-call inference over 6 detected regions). The immediately-following `ocr_element` call within the *same* run (same already-loaded reader) completed in 250-276ms - genuine **warm** latency, comfortably under DEC-048's 3s gate.

**Model readiness / no-download proof:** `EasyOcrVisualAdapter._models_ready()` returned `None` (ready) before the first call in every run - the offline gate passed cleanly against the provisioned directory. `network_access_ever_attempted` was `false` across all 3 runs (the scoped `socket.socket.connect` guard was never triggered) - the acceptance runner's own JSON output records this directly, not an inferred claim.

### 3.3 Tests

`tests/test_phase_eighteen_owned_fixture.py`'s new `OcrFixtureSourceSafetyTests` class (10 tests): no owner-application dependency in either the fixture or the runner; no network/clipboard/file-dialog calls in the fixture; real Arabic Unicode (not a Latin transliteration) verified character-by-character; neither script imported by production bootstrap or anywhere under `src/`; the provisioning script is never actually `import`ed under `src/` (AST-checked, distinct from being merely documented in a docstring); both scripts parse as standalone dev scripts; exact-PID cleanup, never a broad `taskkill`; no owner clipboard ever read.

### 3.4 Verification

- `python -m pytest tests/test_phase_eighteen_owned_fixture.py -q` → **30 passed** (20 pre-existing + 10 new).
- `python -m pytest tests -k "file_access or phase_eighteen or ocr" -q` → **291 passed, 3 skipped, 515 deselected**.
- `python -m pytest tests -q` (full regression) → **806 passed, 3 skipped, 36 subtests passed** in 226.65s (796 + 10 new fixture-source-safety tests).
- `python -m compileall src tests scripts -q` → clean, no errors.
- `git diff --check` → clean, no whitespace errors.

GAP-0103 remains `PARTIAL` (still read-only, no visual actuation) - the previously-flagged missing unified live-GUI Arabic physical evidence gap is now closed. DEC-048 is unchanged (EasyOCR 1.7.2 remains accepted); its evidence entry is hardened with the offline/reproducibility/physical-Arabic details above.

**Commit:** `ddfc5b6b2dba4db3e220cb29817b6fd9301873ad`
**Push:** `feature/phase-18-computer-use-v2` (`04904b3..ddfc5b6`) — pushed.

---

## 4. Milestone 2 — physical bounded-recovery acceptance

### 4.1 Fourth owned fixture and its command channel

`scripts/phase18/uia_recovery_fixture_host.py` (new) - a JARVIS-owned, standalone Win32 process with one target BUTTON ("Recovery Target") and one status STATIC label. Unlike the first three fixtures, it accepts a small, explicit, deterministic command channel over its **own stdin** - the exact pipe the runner's own `subprocess.Popen(..., stdin=subprocess.PIPE)` created for this exact child process, never a network socket, named pipe, or any channel reaching an unrelated process:

- `MOVE` - relocates the target button by a fixed offset via `SetWindowPos`, keeping the same HWND (same UIA `RuntimeId`/identity).
- `REPLACE` - `DestroyWindow`s the current target button and creates a brand new one at the same position with the same visible name, but a genuinely different HWND/`RuntimeId`.

Both commands are handled by posting a custom `WM_APP_*` message onto the main window's own queue from a background stdin-reading thread - every actual UI mutation still happens on the GUI thread, same as any ordinary Win32 app. The runner never trusts the fixture's own status label as proof of what JARVIS did - only of what the fixture itself changed - and always independently confirms each command's effect via a real `computer.semantic.read` call before issuing the actual JARVIS action under test, so there is no uncontrolled process racing anywhere in either scenario below.

### 4.2 Physical scenarios (in `scripts/phase18/computer_use_acceptance.py`'s new `_run_recovery_fixture_scenarios`)

**Scenario A - relocation before input (stable identity, fresh bounds used):** get the target's `element_ref`, independently read its bounds, send `MOVE`, independently confirm (via `get_element` on the *same* `element_ref`) that it still resolves successfully and its bounds changed, then request+approve+execute a native `left_click_element` on that same ref. **3/3 runs:** the click completed, landed on the current (post-move) generation (`independent_status_readback == "clicked:gen0"` every time - the fixture only reports "clicked" when its *actual, currently-live* button receives a real `WM_COMMAND`, so this is physical proof the click was delivered to the relocated control, not a stale cached position).

**Scenario B - approval identity change (target replaced after request, before decide):** get the target's `element_ref`, request approval for a `left_click_element` on it (do not decide yet), send `REPLACE`, independently confirm the *old* `element_ref` now fails re-resolution, then decide (approve) the still-pending approval. **3/3 runs:** `decide()`'s own existing fresh re-check (`_element_target_preview`, unmodified by this batch) refused the approval outright (`decide_status == "denied"`, error code `uia_element_not_found` or `uia_element_stale` depending on exact timing - both are the raw resolution failure, not a recovery-leniency code) with the independent status label still reading `"ready:gen1"` (never `"clicked:..."`) - zero input delivered, no recovery leniency at the approval layer, confirmed live rather than only in fakes.

Both scenarios ran cleanly on the **first** attempt with no flakiness across 3 iterations - each is fully sequential (send command → poll-confirm its effect independently → only then issue the JARVIS action), so neither depends on winning a timing race.

### 4.3 What was deliberately left to deterministic evidence, and why

Per the task's own instruction ("retain deterministic injection for side-effect-failure cases that are unsafe or impossible to produce physically without ambiguity"):

- **A genuinely successful bounded-recovery cycle** (first grounding attempt fails for a transient reason against the *same* identity, the recovery attempt then succeeds) requires landing a live action's *internal* grounding calls inside a millisecond-scale window relative to an external fixture-side state change. Neither `MOVE` (never invalidates identity, so recovery is never even needed) nor `REPLACE` (permanently invalidates identity, so recovery can never succeed) can produce this physically without an uncontrolled race against a live UI. This exact contract is already proven deterministically and precisely (`RecoveryTests.test_stale_ref_recovers_via_one_bounded_retry`, `test_focus_race_recovers_via_one_bounded_retry`, Batch 05/06) with exact resolve-call counts.
- **Recovery-budget exhaustion for a drag** (two sequential transient failures within one action, only one recoverable) has the same millisecond-timing problem, doubled (it needs precise control over *both* the pre-focus and post-focus grounding calls). Already proven deterministically by Milestone 0's `RecoveryBudgetScopeTests` (3 tests) and `computer_use_v2` case `cuv2-46` (new this milestone, §4.4).
- **Consequential uncertainty** (a controlled partial/injection failure after `SendInput` has already begun) - the task explicitly names the existing deterministic injected-adapter harness as the right tool for this, since physically forcing a real mid-drag `SendInput` failure would require corrupting real OS input delivery, unsafe and unrepresentative. Already proven by `RecoveryTests.test_recovery_never_fires_after_sendinput_has_begun` and `test_drag_partial_injection_failure_after_recovered_grounding_still_never_retries`.

### 4.4 Evaluation suite

One new `computer_use_v2` case (46 total): `cuv2-46` proves the action-scoped recovery-budget contract (R18B05-003) through the real tool/service path (`computer.pointer.act` → approval → `decide_and_resume` → `_execute_controller`) using a scripted semantic fake that fails the drag source's pre-focus resolve, succeeds on the recovery attempt, then fails again on the post-focus resolve - the drag ends in a clean typed failure after exactly 3 resolve calls (never a 4th), proving the shared budget spans both grounding calls rather than resetting between them.

### 4.5 Tests

- `tests/test_phase_eighteen_owned_fixture.py`'s new `RecoveryFixtureSourceSafetyTests` class (8 tests): no owner-application dependency; no network/clipboard calls (docstring-stripped, matching the existing pattern); the command channel is scoped to the fixture's own stdin only (no named pipe, no `CreateFile`-based IPC); only `MOVE`/`REPLACE` are recognized; never imported by production bootstrap or anywhere under `src/`; parses as a standalone script; the runner's recovery-scenario function itself uses exact-PID cleanup.
- An existing test (`OwnedFixtureRunnerLogicTests.test_summary_never_includes_full_window_enumeration_or_owner_titles`) was updated to include a `recovery_fixture` entry in its fake run data, matching `_summarize`'s new required key - still passes, still proves no window enumeration/owner title ever reaches the persisted summary.
- `src/jarvis/evaluation/computer_use_v2.py`: 1 new case (`cuv2-46`, 46 total).

### 4.6 Verification

- `python -m pytest tests/test_phase_eighteen_owned_fixture.py -q` → **38 passed** (30 pre-existing + 8 new).
- `python -m pytest tests/test_phase_eighteen_evaluation_suite.py -q` → **7 passed** (all 46 `computer_use_v2` cases pass).
- `python -m pytest tests -k "file_access or phase_eighteen or ocr" -q` → **299 passed, 3 skipped, 515 deselected**.
- `python -m pytest tests -q` (full regression) → **814 passed, 3 skipped, 36 subtests passed** in 232.87s (806 + 8 new fixture-source-safety tests).
- `python -m compileall src tests scripts -q` → clean, no errors.
- `git diff --check` → clean, no whitespace errors.

GAP-0104 advances (remains `PARTIAL`, narrowly deepened further): the action-scoped recovery budget fix and its physical proof are complete; no autonomous multi-app replanning loop and no second planner/authority exist - full GAP-0104 closure remains out of scope. GAP-0105 grows from 45 to 46 evaluation cases and from 3 to 4 owned fixtures; still not the broad real-app matrix named in its original scope.

**Commit:** see the final commit-chain table in this report's closing section for the exact pushed SHA.
