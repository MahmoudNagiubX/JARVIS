# PHASE 18 WORKSTREAM A — BATCH 01

**Task:** `tasks/CLOUD_CODE_MASTER_PHASE_18_WORKSTREAM_A_BATCH_01.md`
**Mode:** Sequential milestone batch — checkpoint review corrections, semantic UIA foundation, canonical tool wiring, first bounded semantic actions.
**Date:** 2026-09-12

---

## 1. Starting branch/HEAD

```text
Branch: feature/phase-18-computer-use-v2
Starting HEAD: 4ca89820d550798223b4691e9b3b077e9388830e  ("docs: record phase 18 UIA backend evaluation")
```

Confirmed via `git rev-parse --show-toplevel`, `git branch --show-current`, `git rev-parse HEAD`, `git status --short`, `git log --oneline --decorate -5`, `git remote -v` before any change — matched the task's expected baseline exactly (two commits ahead of `main` at `54b67ba396ec45180f1b60ea472ef94c9ac181a9`). No unexplained divergence.

---

## 2. Milestone 0 — Checkpoint review corrections + backend decision lock

### 2.1 Review findings addressed

1. **Home Assistant brightness verification bug.** `HomeAssistantTransport._verify_state`'s `set_brightness` branch compared `attributes.get("brightness_pct")` against the outbound payload's `brightness_pct` key — but real Home Assistant light state only ever exposes brightness as `attributes["brightness"]` on the 0-255 scale; `brightness_pct` is a service-call-only convenience key, never a state attribute. The comparison as written would (almost) always evaluate `None == <percent>` and report `verified=False` even on a fully correct brightness change — the opposite failure mode from the earlier HTTP-status-only bug this same method was written to fix.
2. **Stale `AGENTS.md` active-work state.** §11 still named "Phase 18A — Baseline Audit & Stabilization" as the current gate, even though 18A.1, 18A.2, and the A.1 backend evaluation are all complete and the branch has already moved into Workstream A implementation.
3. **Unresolved backend decision.** DEC-018 (`winapp ui` is a *candidate*) and OPEN-001 (exact production UIA adapter still undecided) were both still open, despite the A1 evaluation and Git checkpoint already being complete — nothing had formally locked the backend choice this batch's milestones 1-3 depend on.

### 2.2 Brightness fix

`src/jarvis/devices/home/service.py::HomeAssistantTransport._verify_state`, `set_brightness` branch — rewritten to:

```text
desired_pct = data["brightness_pct"]        (the value actually sent, 0-100)
actual = attributes["brightness"]            (Home Assistant's real 0-255 state attribute)
expected_255 = round(desired_pct * 255 / 100)
verified = abs(actual - expected_255) <= 1
```

Missing `brightness` attribute, a non-numeric `brightness`/`brightness_pct` value (including `bool`, explicitly excluded despite being an `int` subclass), or a materially different value all return `False`. No uncertain case returns `True`.

**Tests** (`tests/test_phase_eighteen_stabilization.py`, 5 new, all passing):
- `test_home_assistant_brightness_verified_true_within_tolerance` — 50% request, actual `brightness=128` → `verified=True` (`round(50*255/100)=128`, exact match).
- `test_home_assistant_brightness_verified_false_when_materially_wrong` — 50% request, actual `brightness=10` → `verified=False`.
- `test_home_assistant_brightness_verified_false_when_attribute_missing` — no `brightness` key in attributes → `verified=False`.
- `test_home_assistant_brightness_verified_false_when_attribute_non_numeric` — `brightness="bright"` → `verified=False`.
- `test_home_assistant_brightness_readback_failure_cannot_produce_verified_true` — GET raises `OSError` → `status="succeeded"` (POST was accepted), `verified=False`.

No unrelated Home Assistant behavior was touched (the `turn_on`/`turn_off`/`set_temperature`/`set_color`/`trigger_scene` branches and the write-path exception handling from Phase 18A.2 are unchanged).

### 2.3 `AGENTS.md` correction

§11 "Active work" rewritten to state 18A.1/18A.2/A.1 are complete and the active program is Phase 18 Workstream A — Computer Use V2, with a pointer to `04_JARVIS_EXECUTION_ROADMAP.md`/`03_JARVIS_GAP_REGISTER.md` rather than duplicating roadmap detail.

### 2.4 DEC-046 — accepted UIA backend decision

Added to `docs/source_of_truth/05_JARVIS_DECISION_LOG.md` §1:

> **DEC-046** — Computer Use V2 semantic Windows control uses a product-owned in-process Python UIA adapter based on `uiautomation`/`comtypes`. Microsoft `winapp ui` remains optional developer/evaluation tooling and is not a production runtime dependency. Status `ACCEPTED_2026-09-12`.

- DEC-018 kept (per the task's explicit instruction) as historical candidate-evaluation context, with its status annotated `(historical context — see DEC-046)` rather than marked superseded/wrong, since DEC-046 reaches the *same* "not a core dependency" conclusion with real evaluation evidence rather than contradicting it.
- **OPEN-001** removed from §3's open-decisions table — resolved by DEC-046 (the resolution is recorded in DEC-046's own evidence column rather than as a separate note, to avoid duplicating the same fact in two places).
- No other decision in the log was touched.

### 2.5 Minimal Gap Register / Roadmap updates

- **`03_JARVIS_GAP_REGISTER.md`, GAP-0101:** added a "Backend-selection subproblem: `RESOLVED`" note (pointing to the A1 report and DEC-046) directly under the existing `OPEN` status, while explicitly keeping GAP-0101 itself `OPEN` — the gap is about the *capability*, not the backend choice, and is not closed by a decision alone.
- **`04_JARVIS_EXECUTION_ROADMAP.md`, Workstream A:** added a one-line status note ("A.1 backend evaluation complete... Semantic UIA implementation is now active — see `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_01.md`") directly under the workstream heading, without altering its existing "Deliver" list.
- GAP-0503 was not touched (remains `OPEN` — this milestone made no file-access change of any kind).

### 2.6 Milestone 0 verification

| Check | Result |
|---|---|
| `pytest tests/test_phase_eighteen_stabilization.py -q` | **20 passed** (15 pre-existing + 5 new brightness tests) |
| `pytest tests -q` | **535 passed, 0 skipped, 36 subtests** (530 baseline + 5 new) |
| `python -m compileall src tests -q` | PASS (exit 0) |
| `git diff --check` | one intentional-formatting note — see below |
| `npm test` (ui/) | **75 passed**, 14 files |
| `npm run build` (ui/) | clean, 68 modules transformed |
| `npm audit --audit-level=high` (ui/) | **0 high/critical** (2 pre-existing moderate dev-only advisories, unrelated, already documented in prior reports) |

**`git diff --check` note:** flagged one pre-existing line in `03_JARVIS_GAP_REGISTER.md` ("Current grounded control is intentionally narrow...") as trailing whitespace. Inspected directly: this line already ended in the file's established Markdown two-space hard-line-break convention before this milestone touched the file (this milestone only added a new line immediately after it, unchanged itself) — the same intentional-formatting situation already documented in `PHASE_18A2_STABILIZATION.md` and `PHASE_18_GIT_CHECKPOINT.md`. Not reformatted, not a regression, not blocking.

No unexplained failure occurred.
