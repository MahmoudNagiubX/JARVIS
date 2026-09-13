# PHASE 18 — WORKSTREAM A — BATCH 06
## OCR Runtime Purity + Reproducibility → Arabic Physical OCR Proof → Physical Recovery Validation

**Task:** `tasks/PHASE_18_WORKSTREAM_A_BATCH_06_MASTER_TASK.md` (pasted in full by the requester)
**Branch:** `feature/phase-18-computer-use-v2`
**Status:** IN PROGRESS — Milestone 0 complete, Milestones 1/2 not yet started.

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

**Commit:** see the final commit-chain table in this report's closing section for the exact pushed SHA (a self-referencing hash cannot be embedded before the commit itself is made).
