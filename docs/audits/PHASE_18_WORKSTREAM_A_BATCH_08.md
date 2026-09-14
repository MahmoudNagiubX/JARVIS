# Phase 18 Workstream A — Batch 08 Audit

**Status:** M0 and M1 complete; M2 implemented with bounded refusal/uncertainty evidence, but the real happy-path physical click remains pending

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

## 7. Historical milestone scope

M1 must add only the bounded `left_click_visual` action through the existing
ComputerActionService, with opaque visual-ref/source-window approval binding,
fresh OCR revalidation, fixed confidence handling, native one-click delivery,
and no model-facing geometry. M2 must extend the owned fixture and prove the
required A–E stale/ambiguous/drift/uncertain-input scenarios three clean times
each. Until those milestones complete, visual actuation is not implemented or
physically accepted.

## 8. M1 bounded visual actuation

M1 added one production action, `computer.visual.act`, for the existing
`left_click_visual` capability. The action stays behind the existing
`ComputerActionService`, `PermissionEngine`, durable approval engine, audit,
and `WindowsNativeInputAdapter` boundaries. It accepts only an opaque
window-origin `visual_ref`; the private OCR binding retains source identity,
text digest, confidence, spatial continuity, and expiry, while model-facing
results and approval previews contain no OCR geometry or raw coordinates.

The action path is:

```text
computer.visual.read -> opaque visual_ref -> computer.visual.act
-> target-aware approval -> fresh OCR/source revalidation
-> foreground verification -> one native move + one left-down/left-up batch
```

Element-origin visual references remain denied in favor of semantic UIA
targeting. A changed source, changed text, stale reference, low confidence,
or ambiguous same-text target fails closed before input. Native delivery is
always reported unverified; no automatic retry occurs after the input batch
begins. The deterministic evaluation suite now contains 53 cases (`cuv2-49`
through `cuv2-53` cover approval, stale content, ambiguity, source drift, and
post-input uncertainty).

M1 implementation was pushed in commit `3291c44`.

## 9. M2 owned-fixture visual-actuation evidence

M2 extended the existing `scripts/phase18/uia_ocr_fixture_host.py` with one
real Win32 `BUTTON` labelled `GO` and a fixture-owned `STATIC` status label.
The parent handles the button's real `WM_COMMAND`/`BN_CLICKED` notification;
the status changes from `VISUAL STATUS READY` to `VISUAL STATUS APPLIED` only
after a delivered click. The duplicate-target mode creates a second real
`GO` button and is allowlisted only through
`scripts/phase18/owned_fixture_process.py`. No IPC, network, clipboard,
owner-application dependency, or fixture-side `SendInput` was added.

The physical runner uses exact nonce-title plus provider-verified child-PID
ownership, terminates only the returned child, and confirms exact-title window
absence. It forwards only opaque refs from `computer.visual.read` to
`computer.visual.act`; raw OCR text and bounds remain transient. The visual
reference TTL is 30 seconds, the upper end of the reviewed 15-30 second range,
and is never extended by approval or revalidation.

Final physical command (isolated offline EasyOCR environment):

```text
python scripts/phase18/ocr_visual_acceptance.py --visual-actuation --runs 3 --candidate combined_ar_en --model-dir <provisioned-model-dir> --out <temporary-json>
```

Final three-run result from the temporary JSON receipt:

| Scenario | Result | Independent evidence |
|---|---:|---|
| A happy visual left click | 0/3 | `visual_ref_expired` during the slow CPU OCR/approval revalidation path; no native input or status change |
| B stale visual target | 3/3 | old ref refused with `window_ref_expired`; zero input; recreated fixture status stayed ready |
| C duplicate visual labels | 3/3 | two OCR matches; `visual_target_ambiguous`; zero input; status stayed ready |
| D approval target drift | 3/3 | recreated same-title child refused old approval with `window_ref_expired`; no migration; zero input |
| E post-input uncertainty | 3/3 | injected adapter recorded two batches (one move, one partial click); `native_input_injection_failed`; exactly one click-batch attempt |

Across all three runs the scoped network guard recorded zero attempts and
all owned fixture children exited with exact-title cleanup confirmed. The
required `three_clean_physical_iterations` gate is false solely because A is
not physically green. A separate host diagnostic also showed that the
evaluation session cannot verify foreground activation for the owned fixture;
the production path correctly refuses rather than sending input to an
uncertain target.

## 10. Final Batch 08 verification and verdict

- focused M1/M2 tests: **240 passed, 5 subtests** (fresh behavior run);
- full repository suite: **880 passed, 3 skipped, 41 subtests** (fresh run on
  the final production/test code; the three skips are the expected optional
  OCR-package checks in the normal interpreter);
- `python -m compileall src tests scripts -q`: pass;
- `git diff --check`: pass;
- final verdict: `PARTIAL` - bounded OCR-grounded visual left-click is
  implemented and its stale/ambiguity/drift/uncertainty safeguards are
  physically evidenced, but the real happy-path 3/3 click-delivery and
  independent status gate remains `PHYSICAL_PENDING`.

No Batch 09 work is started. DEC-048 remains unchanged.
