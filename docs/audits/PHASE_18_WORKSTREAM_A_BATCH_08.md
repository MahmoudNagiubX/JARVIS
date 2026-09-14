# Phase 18 Workstream A — Batch 08 Audit

**Status:** M0 complete with normal no-change result; M1/M2 pending

**Repository:** `MahmoudNagiubX/JARVIS`

**Branch:** `feature/phase-18-computer-use-v2`

## 1. M0 starting state and checkpoint

- Required starting HEAD: `295188efbab57c49ee06411d73e625cfe043f8d3`.
- Required origin feature HEAD: `295188efbab57c49ee06411d73e625cfe043f8d3`.
- `origin/main`: `54b67ba396ec45180f1b60ea472ef94c9ac181a9`.
- M0 evaluator checkpoint: `be1a5b2` (`test: close batch 07 OCR review follow-ups`).
- M0 push range: `295188e..be1a5b2` to `origin/feature/phase-18-computer-use-v2`.
- No branch switch, main merge, force push, dependency change, production OCR registration, or production source change was made.

## 2. M0 corrected scoring

`scripts/phase18/ocr_visual_acceptance.py::_char_recall()` now scores the
sequence-aware normalized similarity:

```text
1 - levenshtein(NFKC_and_collapsed_whitespace(expected),
               NFKC_and_collapsed_whitespace(actual))
    / max(len(expected_normalized), len(actual_normalized), 1)
```

Whitespace is collapsed to one space and surrounding whitespace is removed;
spaces remain part of the sequence. Empty/empty is `1.0`; empty/non-empty is
`0.0`. Exact matching uses the same normalized strings. The implementation is
evaluation-only and adds no dependency; production OCR text and routing are
unchanged.

Regression coverage includes exact, whitespace normalization, insertion,
deletion, substitution, transposition, anagram/order sensitivity, empty
inputs, and Arabic text.

## 3. M0 Candidate C

Candidate C is the runner-only `combined_then_english` comparison. It uses
only the already-reviewed local readers, in this order:

1. `Reader(["ar", "en"])`;
2. at most one `Reader(["en"])` pass after a deterministic Arabic/Latin
   script and confidence check.

The merge is deterministic: Arabic-bearing first-pass regions are never
replaced by the English pass; overlapping Latin regions use the higher
confidence result; non-overlapping English regions are appended. The output
records `source_pass` and bounded timing/provenance without exposing geometry.
All model paths are explicit and offline. Candidate C uses the union of the
three existing weights: `craft_mlt_25k.pth`, `arabic.pth`, and
`english_g2.pth`.

## 4. M0 physical evidence

All measurements below used the JARVIS-owned `uia_ocr_fixture_host.py` only,
the real production `computer.visual.read` path, the disposable evaluation
environment with EasyOCR `1.7.2`, CPU `torch 2.14.0+cpu`, CPU
`torchvision 0.29.0+cpu`, and explicit model/user-network directories. Each
candidate had three clean runs, exact child-PID cleanup, and a scoped socket
guard.

| Candidate | Model footprint | OCR completed | Arabic exact | English gate | Mixed gate | Warm latency gate | Network | Cleanup |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| A `combined_ar_en` | 298,553,044 bytes | 3/3 | 3/3 | 0/3 (`0.958` ready, `0.833` fixture) | 3/3 (`0.938`, Arabic preserved) | 0/3 (`3216.5`, `3319.0`, `3068.6` ms) | 0 attempts | 3/3 |
| B `english_only` | 98,296,327 bytes | 3/3 | 0/3 | 3/3 (exact) | 0/3 | 3/3 (`815.8`, `764.1`, `710.7` ms) | 0 attempts | 3/3 |
| C `combined_then_english` | 313,697,041 bytes | 3/3 | 3/3 | 0/3 (`0.833` fixture similarity) | 3/3 (`0.938`, Arabic preserved) | 0/3 (`4029.8`, `3047.6`, `4054.4` ms end-to-end) | 0 attempts | 3/3 |

For each run's cold and warm window observations and OCR-element cross-check,
the deterministic check requested one English second pass, for exactly two
passes per observation; there was no third reader/backend or dynamic download.
Representative merged output preserved first-pass Arabic text and identified
the English contribution by `source_pass`; observed text included correct
`مرحبا يا جارفيس` and `الإعدادات`, mixed `JARMIS الإعدادات`, and
`JARVIS OCR fixture ready`. Failed/low-quality English output was not hidden.

## 5. M0 decision

Candidate C failed the required English similarity and all-three-run warm
two-pass gates. Therefore the exact M0 outcome is:

`OCR_BOUNDED_TWO_PASS_EVALUATION_NO_CHANGE`

DEC-048 remains unchanged: production continues to use the accepted combined
EasyOCR reader for read-only visual OCR. The explicit
`DECISION_NEEDED_DEC048_OCR_ROUTING_CHANGE` stop condition was not reached.
M1 may proceed; M0 did not authorize any OCR routing change.

## 6. M0 verification

- `python -m pytest tests/test_phase_eighteen_batch07_ocr_evaluation.py tests/test_phase_eighteen_visual_ocr.py tests/test_phase_eighteen_ocr_reproducibility.py tests/test_phase_eighteen_owned_fixture.py -q` — **101 passed, 3 skipped, 5 subtests**.
- `python -m pytest tests -k "phase_eighteen or ocr" -q` — **327 passed, 3 skipped, 5 subtests**.
- `python -m pytest tests -q` — **842 passed, 3 skipped, 41 subtests**.
- `python -m compileall src tests scripts -q` — pass.
- `git diff --check` — pass.

The three skips are the expected optional `easyocr`, `torch`, and
`torchvision` checks in the repository's normal development environment; the
physical measurements used the disposable environment listed above.

## 7. Remaining Batch 08 work

M1 must add only the bounded `left_click_visual` action through the existing
ComputerActionService, with opaque visual-ref/source-window approval binding,
fresh OCR revalidation, fixed confidence handling, native one-click delivery,
and no model-facing geometry. M2 must extend the owned fixture and prove the
required A–E stale/ambiguous/drift/uncertain-input scenarios three clean times
each. Until those milestones complete, visual actuation is not implemented or
physically accepted.
