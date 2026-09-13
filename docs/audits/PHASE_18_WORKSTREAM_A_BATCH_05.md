# PHASE 18 — WORKSTREAM A — BATCH 05
## Review Follow-Up Closure → OCR Backend Resolution / Read-Only Visual Grounding → Bounded Recovery & Replanning

**Task:** `tasks/PHASE_18_WORKSTREAM_A_BATCH_05_MASTER_TASK.md`
**Branch:** `feature/phase-18-computer-use-v2`
**Status:** IN PROGRESS — Milestone 0 complete, Milestones 1/2 not yet started.

This is the single report for the whole batch (per Section 7 of the task file); it is appended to, not duplicated, as later milestones complete.

---

## 1. Starting state

- Branch: `feature/phase-18-computer-use-v2`
- Starting HEAD: `24fbaffa43d60d83e5428ae93c62cfc112a776f0` (`docs: finalize phase 18 batch 04 report`) — matched the task file's expected starting HEAD exactly; branch was in sync with `origin/feature/phase-18-computer-use-v2`, `git status --short` clean, no unexplained divergence, `main` not checked out anywhere (single worktree confirmed).

---

## 2. Independent review findings against Batch 04

Two hardening findings identified after independent review of Batch 04's file-search walker and OCR benchmark, both addressed in Milestone 0 below:

| ID | Summary | Disposition |
| --- | --- | --- |
| R18B04-001 | `FileAccessPolicy.iter_search_candidates()` called `entries = list(os.scandir(current))` before enforcing `MAX_SEARCH_CANDIDATES_SCANNED` - the traversal security boundary (containment/reparse-safety) was already correct, but a single directory with far more entries than the budget would still be fully enumerated/materialized into a list before the per-entry budget check ever ran. | Fixed — replaced with a truly streaming walk that checks the budget *before* each `next()` call on the live `os.scandir()` iterator (see §3.1). |
| R18B04-002 | Batch 04's synthetic Arabic OCR benchmark fixtures were rendered with plain `ImageDraw.text()` and no complex-text/bidirectional shaping engine - Pillow's native `raqm` layout is not available on this machine, so the rendered Arabic glyphs were very likely disconnected/isolated-form and in logical (not visual/RTL) order, not real legible Arabic script. Batch 04's low RapidOCR Arabic recall may have been partly or wholly an artifact of a broken ground-truth image, not a true reflection of the provider's Arabic capability. | Fixed — the benchmark now proves a valid shaping path (PIL raqm, or `arabic_reshaper`+`python-bidi` as a raqm-free fallback) before treating an Arabic/mixed fixture as scorable, and fails closed (`FIXTURE_RENDERING_INVALID`, no score generated) otherwise (see §3.2). |

---

## 3. Milestone 0 — Batch 04 independent-review closure

**Commit:** `MILESTONE_0_COMMIT` (recorded in §3.4 below after push)

### 3.1 Truly streaming confined search (R18B04-001)

`FileAccessPolicy.iter_search_candidates()` (`src/jarvis/computer/file_access.py`) was restructured so the per-directory scan loop consumes `os.scandir()` directly as a live iterator, never `list(os.scandir(...))`:

```python
try:
    scandir_iterator = os.scandir(current)
except OSError:
    continue
with scandir_iterator:
    while True:
        if len(matches) >= MAX_SEARCH_MATCHES:
            return matches, filtered
        if scanned >= MAX_SEARCH_CANDIDATES_SCANNED:
            return matches, filtered
        try:
            entry = next(scandir_iterator)
        except StopIteration:
            break
        scanned += 1
        ...  # unchanged per-entry classification logic
```

The budget checks now run **before** each `next()` call, so once `MAX_SEARCH_CANDIDATES_SCANNED` is reached the walker never requests another directory entry at all - not from the current directory, and not from any other directory still on the traversal stack. `os.scandir()` is used as a context manager (`with scandir_iterator:`) so its underlying OS directory handle is always released, including on an early `return` mid-iteration. All existing per-entry logic (pre-descent reparse classification, canonical containment checks, sensitive-subtree pruning, `MAX_SEARCH_DEPTH`, `MAX_SEARCH_MATCHES`) is unchanged - only the outer per-directory consumption mechanics changed.

**Required regression test** (`tests/test_phase_eighteen_file_access.py::FileAccessPolicyStreamingScandirTests::test_scan_budget_stops_consuming_the_iterator_without_materializing_the_directory`): an instrumented fake `os.scandir()` iterator (`_CountingScandirIterator`) simulates a single directory with 5,000 lazily-generated entries and records exactly how many were pulled via `next()`. With the scan budget patched to 7, the test asserts the real walker consumed **exactly 7** entries - never fetching an 8th, and nowhere close to materializing all 5,000. A test that only checked `len(matches)` would not have caught the original defect (a fully-materialized 5,000-entry list could still yield only a few matches); this test instead proves the iterator itself was never over-consumed.

### 3.2 Arabic OCR fixture validity (R18B04-002)

`scripts/phase18/ocr_backend_benchmark.py` was substantially hardened:

- **Rendering diagnostics recorded on every run:** Pillow version, selected font path, `PIL.features.check_feature("raqm")` availability and version, `arabic_reshaper`/`python-bidi` package availability, the layout engine actually used per fixture (`plain_pil_no_shaping_needed` for English, `pil_raqm` or `arabic_reshaper+python_bidi` for Arabic/mixed, or `null` when rendering was refused), and the exact normalized scoring method description - all under a new `rendering_diagnostics`/`scoring_method` block in the JSON result.
- **Priority-ordered shaping path for Arabic/mixed fixtures:** (1) PIL's native `raqm` layout engine (`ImageFont.truetype(..., layout_engine=ImageFont.Layout.RAQM)`, `direction="rtl"` for pure-Arabic fixtures) when available; (2) `arabic_reshaper.reshape()` (contextual Arabic letter-joining - each base letter mapped to its correct isolated/initial/medial/final presentation form) followed by `bidi.algorithm.get_display()` (Unicode Bidi Algorithm visual reordering, correctly handling mixed LTR+RTL runs) when raqm is unavailable; (3) if neither path is available, the fixture's rendering is refused outright.
- **Fail-closed, no silent scoring:** a fixture whose rendering could not be proven valid is marked `FIXTURE_RENDERING_INVALID` in the result (with the specific reason) and is **never** run through an OCR backend or scored - it is reported as a distinct status, not a low/zero accuracy number that could be misread as a real provider failure.
- **Ground truth never changed:** the string used for accuracy scoring (`expected_text`) is always the original semantic Unicode text (e.g. base-form Arabic letters), never the reshaped/presentation-form glyphs used only for rendering the image - proven by a dedicated test asserting no Arabic Presentation Forms codepoint (U+FB50-FDFF, U+FE70-FEFF) ever appears in the scored `expected` string.
- **Empirically verified the shaping fix is real, not cosmetic:** in a small isolated venv, `arabic_reshaper.reshape("مرحبا يا جارفيس")` correctly mapped each base letter to its context-appropriate presentation form (e.g. U+0645 → U+FEE3), and `get_display()` correctly reversed each word's letter order for RTL while leaving a Latin run (`"JARVIS "` in the mixed fixture) in its normal left-to-right position - confirming this is genuine complex-text shaping, not a no-op.
- **Environment reality on this machine:** neither `raqm` (Pillow 12.3.0 here has no bundled libraqm) nor `arabic_reshaper`/`python-bidi` is installed in the environment that runs the test suite, so Arabic/mixed fixtures currently and correctly render as `FIXTURE_RENDERING_INVALID` when exercised locally - proven by a dedicated functional test. English fixtures are entirely unaffected (they never needed shaping) and continue to render normally. The actual re-benchmark against a real OCR backend (in a dedicated isolated venv with `arabic_reshaper`+`python-bidi` installed) happens in Milestone 1.
- Generated fixture images remain temporary (deleted after every run); no fonts, shaping libraries, or generated images are committed to the repository.

### 3.3 Tests

- `tests/test_phase_eighteen_file_access.py`: 1 new test (`FileAccessPolicyStreamingScandirTests`) - **39 tests total in the file, all passing** (was 38).
- `tests/test_phase_eighteen_owned_fixture.py`: 1 new static safety test plus a new `OcrBenchmarkRenderingTests` class (3 functional tests exercising the real `render_fixture_images()` function - English fixtures always render; Arabic/mixed fixtures fail closed without a proven shaping path on this machine; the scored ground-truth text is never a reshaped presentation form) - **20 tests total in the file, all passing** (was 16).

### 3.4 Verification

- `python -m pytest tests/test_phase_eighteen_file_access.py -q` → **39 passed**.
- `python -m pytest tests/test_phase_eighteen_owned_fixture.py -q` → **20 passed**.
- `python -m pytest tests -k "file_access or phase_eighteen" -q` → **229 passed, 515 deselected**.
- `python -m pytest tests -q` (full regression) → **744 passed, 36 subtests passed**.
- `python -m compileall src tests scripts -q` → clean, no errors.
- `git diff --check` → clean, no whitespace errors.
- **Commit:** `MILESTONE_0_COMMIT`
- **Push:** `feature/phase-18-computer-use-v2` — recorded after push.
