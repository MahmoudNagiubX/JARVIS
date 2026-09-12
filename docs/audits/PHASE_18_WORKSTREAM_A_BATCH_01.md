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

---

## 3. Milestone 1 — Product-owned semantic UIA foundation (read-only)

### 3.1 Dependency

Added `computer-uia = ["uiautomation==2.0.29"]` to `pyproject.toml`'s `[project.optional-dependencies]`, matching the existing `dev`/`voice` group style exactly (a plain list of pinned exact-version strings). `comtypes` was **not** explicitly listed — `uiautomation` already owns that dependency relationship in its own package metadata, and no reproducibility evidence required overriding it. `pywinauto` and `winapp` were **not** added, per DEC-046/task instruction.

`WindowsUIAutomationAdapter.__init__` imports `uiautomation` inside a `try/except ImportError` at module scope (`src/jarvis/computer/semantic_uia.py`); when the import fails, `adapter.available` is `False` and every method returns `SemanticResult("failed", error_code="uia_not_available")` instead of raising — verified by a dedicated test that patches the module's optional import to `None` regardless of whether the package happens to be installed on the machine running the tests. JARVIS core was not otherwise touched by this milestone (the adapter is not yet wired into `bootstrap.py`/`ComputerActionService` - that is Milestone 2), so bootstrap import/start is unaffected either way.

### 3.2 Adapter architecture

New files:
- `src/jarvis/contracts/semantic_ui.py` - public, vendor-neutral contracts: `SemanticElementSnapshot`, `SemanticBounds`, `SemanticTreeNode`, `SemanticResult` (one status/output/error_code envelope, mirroring the existing `ComputerResult`/`HomeResult`/`BrowserResult` convention), `SemanticReferenceState`, and the `SemanticDesktopAdapter` Protocol - re-exported from `contracts/__init__.py` alongside the existing contract families.
- `src/jarvis/computer/semantic_uia.py` - the one concrete implementation, `WindowsUIAutomationAdapter`. The third-party `uiautomation` module is imported only here and never referenced anywhere else in the codebase; no raw COM object, `RuntimeId`, HWND, or coordinate leaves this module as a target identity - only `element-<uuid>` references and the normalized contracts above.

No second service authority was created. This milestone is a standalone, injectable adapter; it is not yet reachable from `AgentRuntime`/`ToolExecutionService`/`ComputerActionService` (Milestone 2 wires it behind `ComputerActionService`, per the locked architecture in the task file).

### 3.3 Reference model

- **Window references:** reused as-is. The adapter accepts an existing `window_ref` and resolves it through `WindowsDesktopProvider.validate_input_window(window_ref)` - the same existing, already-tested method that both validates/re-resolves the window (raising on expiry/change) **and** enforces the existing `PerceptionPrivacyPolicy` in one call. No parallel `uia-window-*` reference scheme was introduced, and no new method was added to `WindowsDesktopProvider`.
- **Element references:** new, product-owned, `element-<uuid>` opaque IDs. A private, provider-internal `_ElementRefEntry` (never exposed) stores the containing `window_ref`, `AutomationId`, control type, name hint, a bounded (max 6) ancestry-of-control-types hint, a SHA-256 digest of the live element's `GetRuntimeId()`, and an expiry timestamp. In-memory only, TTL-bounded (default 45s, clamped to 15-60s), count-bounded (max 1,000, oldest evicted first) - no durable DB rows, no Memory/World State persistence, matching the task's explicit prohibition.

### 3.4 Stale-target handling (the core safety property)

No live `uiautomation` `Control` object is ever held across two calls - this is the key design decision that avoids the raw, inconsistent `comtypes.COMError` behavior the A1 evaluation found when a stale object is reused directly. Every re-resolution (`get_element`, `get_text_or_value`, `revalidate_reference`) instead **re-walks the bounded tree from the containing window** and accepts a live candidate **only when its RuntimeId digest matches the digest captured at observation time**. A same-named/same-AutomationId element with a different underlying identity is therefore never silently substituted - it is reported as `uia_element_stale`, never returned as if it were the original target. This exact scenario (window torn down and rebuilt with an impostor element sharing the original's `Name`/`AutomationId`) is a dedicated regression test (`test_stale_element_never_silently_resolves_to_different_element`).

Typed error codes implemented, translated from provider/window state (never a leaked COM exception string): `uia_not_available`, `uia_window_stale`, `uia_element_stale`, `uia_element_not_found`, `uia_element_ambiguous`, `uia_provider_unavailable`, `sensitive_window_denied`, `uia_sensitive_value_denied`, `uia_find_filter_required`.

### 3.5 Privacy

`inspect_window`/`find_elements`/`get_element`/`get_text_or_value`/`revalidate_reference` all resolve their containing window through `validate_input_window`, which enforces the existing `PerceptionPrivacyPolicy` before any tree access - a denied window returns `status="denied", error_code="sensitive_window_denied"` before a single UIA property is read. Password controls (`IsPassword` true) are separately denied at `get_text_or_value` time with `uia_sensitive_value_denied`, regardless of window sensitivity - covered by `test_password_sensitive_value_redacted`, which also asserts the actual secret value never appears anywhere in the result.

### 3.6 Live NIGHTFURY probe (real, not simulated)

Ran a throwaway script (outside the repo, deleted after use) that imports the real `WindowsUIAutomationAdapter`/`WindowsDesktopProvider` (no fakes) against disposable Calculator and the owner's pre-existing, untouched Notepad session (read-only inspection of already-open content, exactly as in the A1 evaluation - no new Notepad instance was created or needed this time, so none was closed):

| Operation | Result | Latency |
|---|---|---|
| `inspect_window` (Calculator, depth=3) | succeeded, 16 elements, not truncated | 93.9ms (first call, pays one-time COM init) |
| `find_elements(name="Seven")` | succeeded, exactly 1 match, `AutomationId=num7Button`, `supported_patterns=('Invoke',)` | 39.0ms |
| `get_element` (re-resolution) | succeeded | 31.9ms |
| `revalidate_reference` | `state=valid` | 27.9ms |
| `inspect_window` (Notepad, depth=2) | succeeded, 14 elements | 40.0ms |
| `find_elements` (Notepad, `DocumentControl`) | succeeded, 1 match | - |
| `get_text_or_value` (Notepad document) | succeeded, `text_length=376` (content not printed - owner data) | 46.3ms |
| `revalidate_reference` (bogus ref) | `state=not_found` | - |

The 376-character length exactly matches the same live document's length independently measured in the A1 evaluation report, cross-validating correctness again without ever printing the actual content. Warm per-call latency (27-46ms after the first call) matches the ~10-50ms range the A1 evaluation predicted for an in-process adapter. Calculator was closed via `Stop-Process` after the probe (the only disposable instance created); the owner's Notepad draft was never modified, typed into, or closed.

### 3.7 Tests

`tests/test_phase_eighteen_semantic_uia.py` - **17 tests, all passing**, entirely deterministic (a fake `_FakeControl`/`_FakeWindowProvider` seam; no real `uiautomation` package, GUI session, or Windows platform required for 16 of the 17 - the one dependency-unavailable test patches the module's optional import directly so it is deterministic regardless of what happens to be installed on the machine running it):

- `test_dependency_unavailable_reports_truthful_state`
- `test_window_ref_stale_returns_typed_result`, `test_sensitive_window_denied`
- `test_bounded_tree_depth`, `test_bounded_node_count`
- `test_find_by_automation_id`, `test_find_by_name_and_control_type`, `test_ambiguous_match_stays_ambiguous`, `test_find_requires_at_least_one_filter`
- `test_element_ref_expires`, `test_element_ref_reresolution_success`, `test_stale_element_never_silently_resolves_to_different_element`, `test_revalidate_reference_reports_explicit_states`
- `test_get_text_value_bounded`, `test_get_text_value_uses_value_pattern_fallback`, `test_password_sensitive_value_redacted`
- `test_no_raw_hwnd_or_com_object_in_public_snapshot`

### 3.8 Milestone 1 verification

| Check | Result |
|---|---|
| `pytest tests/test_phase_eighteen_semantic_uia.py -q` | **17 passed** |
| `pytest tests -k "phase_ten or phase_eleven or phase_eighteen" -q` | **93 passed, 1 skipped** (same pre-existing environment-dependent skip) |
| `pytest tests -q` (full) | **551 passed, 1 skipped, 36 subtests** (535 Milestone-0 baseline + 17 new - 1 environment skip) |
| `python -m compileall src tests -q` | PASS |
| `git diff --check` | PASS (no new trailing-whitespace note this time - no Markdown docs were touched) |
| Packaging metadata | validated via `tomllib.load("pyproject.toml")` - parses cleanly, `computer-uia` group present with the exact pin; no established repo packaging-validation command exists to run beyond this, per the task's instruction not to invent one |

Frontend re-run was not performed for this milestone - untouched, and the task marks a full frontend rerun optional here (required again at final batch completion).

### 3.9 Milestone 1 documentation

- `02_JARVIS_CURRENT_STATE.md`: "UIA semantic control tree/actions" row updated `PLANNED` → `PARTIAL` - semantic provider foundation now implemented (read-only), gated behind the optional `computer-uia` dependency, not yet reachable from any JARVIS tool path.
- `03_JARVIS_GAP_REGISTER.md`, GAP-0101: remains `PARTIAL`/`OPEN` - a foundation exists, but no canonical tool integration or actuation yet.
- `04_JARVIS_EXECUTION_ROADMAP.md`: Workstream A status note updated to record the foundation milestone complete.

Computer Use V2 is **not** claimed complete anywhere in this update.
