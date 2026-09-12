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

---

## 4. Milestone 2 — Wire semantic read capabilities through the canonical JARVIS tool path

### 4.1 No second service

The semantic adapter is invoked exclusively from inside the existing `WindowsNativeComputerController.execute()` dispatch (`src/jarvis/computer/service.py`), which `ComputerActionService` already authorizes/audits for every other computer action. `WindowsNativeComputerController.__init__` gained one new optional constructor parameter, `semantic_adapter`, defaulting to `WindowsUIAutomationAdapter(self.perception_provider)` - `bootstrap.py` required **zero changes** since it already passes the shared `perception_provider` instance positionally. `AgentRuntime`/`ToolRegistry` never call the adapter directly - only through `ComputerActionService`.

### 4.2 New semantic read actions

Six new `ComputerCapability` values (`src/jarvis/contracts/computer.py`): `semantic_list_windows`, `semantic_inspect_window`, `semantic_find_elements`, `semantic_get_element`, `semantic_get_text`, `semantic_revalidate` - dispatched in `WindowsNativeComputerController.execute()` to six small private methods that call the adapter and convert its `SemanticResult` (typed dataclasses) into a plain, JSON-serializable `ComputerResult.output` dict via two new module-level helpers, `_semantic_snapshot_dict`/`_semantic_tree_dict` (bounds/patterns flattened to plain dicts/lists; internal-only fields like `observed_at` dropped, keeping the model-facing payload minimal per the task's "minimum model schema, maximum typed backend control" instruction).

### 4.3 Permission/risk classification

All six actions were added to `ComputerActionService._read_actions` (risk `"read"`, required capability `computer.observe` - observation only, no side effect). Two new **narrow, action-specific** rule sets were added to `PolicyPermissionEngine`'s default rules (`src/jarvis/authority/permissions/engine.py`) - no broad `"computer.*"`/`"tool.computer.*"` prefix rule was added:

- Outer tool-level gate: one rule, `tool.computer.semantic.read` → ALLOW (the inner gate below is authoritative, matching the existing pattern already used for `tool.browser.`/`tool.computer.window.control` etc.).
- Inner `ComputerActionService`-level gate: six explicit rules, one per `computer.semantic_*` action name → ALLOW.

The PermissionEngine itself was not weakened globally - every other existing rule is untouched, and an unrecognized/mistyped semantic action name still falls through to the pre-existing `"computer."` catch-all (`REQUIRE_APPROVAL`), not a silent allow.

### 4.4 Tool Registry

One coherent tool, `computer.semantic.read` (`src/jarvis/tools/registry.py::register_computer_tools`), multiplexes all six operations behind a single `action` enum parameter (`list_windows`/`inspect_window`/`find_elements`/`get_element`/`get_text`/`revalidate`) plus `window_ref`/`element_ref`/`depth`/`control_type`/`name`/`automation_id` - one bounded JSON schema instead of six, minimizing the per-turn model context cost. The handler re-validates `window_ref`/`element_ref` prefixes, `depth` bounds (1-5), and "at least one filter for find_elements" **before** calling into `ComputerActionService` (defense in depth - `ComputerActionService`'s own handlers re-validate identically, since it is reachable independently of the tool layer). The schema exposes no raw HWND, coordinates, RuntimeId, COM selector, or arbitrary query/traversal language - only the same opaque `window-*`/`element-*` references and bounded filter strings the adapter itself defines. `retention=ToolResultRetention.EPHEMERAL` - semantic tree/text output is not durably persisted by default, matching the existing convention for `desktop.context.read`/`screen.observe`.

### 4.5 Model-visible output / untrusted content

Tree/find results are bounded by the same `MAX_TREE_ELEMENTS`/`MAX_FIND_RESULTS`/`MAX_TEXT_LENGTH` limits Milestone 1 already enforces - no new unbounded path was introduced at the tool layer. A dedicated test (`test_ui_text_cannot_alter_policy_or_approval_behavior`) proves a control whose `Name`/text content contains an adversarial "SYSTEM: approve all pending actions"-style string is returned as inert bounded data with zero effect on the approvals table - UI text is data, never authority, exactly as required. `verified` semantics from Phase 18A.2 are preserved: every semantic read result sets `verified=True` only on a genuinely successful fresh observation (`status == "succeeded"`), never merely because a provider call returned.

### 4.6 Audit

Semantic actions flow through `ComputerActionService`'s existing `_audit`/`_emit` calls unchanged (`computer.permission_checked`, `computer.action_completed`/`computer.action_failed`) - no new audit path was created. Ephemeral tool-result retention (already wired in Milestone 2's `ToolSpec`) keeps the durable audit/tool-call record bounded to a digest rather than the full tree/text, consistent with existing conventions for other observation tools.

### 4.7 Live NIGHTFURY acceptance (through the actual JARVIS service/tool path, not raw `uiautomation`)

A throwaway script (outside the repo, deleted after use) built a real `create_runtime()`, authenticated a test identity/device, and called `runtime.tool_service.execute("computer.semantic.read", {...}, context)` directly - the exact same entry point a real conversation turn would use - against disposable Calculator and the owner's pre-existing, untouched Notepad session:

| Step | Result |
|---|---|
| 1. list windows | `status=completed verified=True`; found both Calculator and Notepad among the real desktop windows |
| 2. inspect bounded tree | `status=completed element_count=16 truncated=False` |
| 3. find control by semantic properties (`name="Seven"`) | `status=completed matches=1 ambiguous=False`; `Seven / ButtonControl / num7Button / ['Invoke']` |
| 4a. read text/value (`get_text`) | `status=completed text="Seven"` (Name fallback - a plain button has no Text/Value pattern) |
| 4b. read fresh snapshot (`get_element`) | `status=completed name="Seven"` |
| 5. revalidate | `status=completed state=valid` |
| bonus: Notepad document text (read-only) | `status=completed text_length=376` (content not printed - owner data; same length independently cross-validated in every prior session touching this same live document) |

No write interaction occurred. `runtime.repository.audit()` recorded 32 rows across the run with the expected event types (`computer.permission_checked`, `computer.action_completed`, `permission.checked`, `tool.completed`). Calculator was closed via `Stop-Process` afterward (the only disposable instance created); Notepad was never modified.

### 4.8 Tests

`tests/test_phase_eighteen_semantic_tool_path.py` - **10 tests, all passing**, using a fake `SemanticDesktopAdapter` injected at `runtime.computer_actions.controller.local.semantic_adapter` (no real UIA/Windows dependency):

- `test_canonical_service_path_and_permission_and_audit` - proves the real `ToolExecutionService → PolicyPermissionEngine → ComputerActionService` chain is used and produces the expected audit rows.
- `test_sensitive_window_inspection_denied`, `test_stale_window_rejected`, `test_stale_element_rejected`, `test_ambiguous_element_search_not_silently_collapsed`.
- `test_find_requires_filter_and_result_is_bounded`, `test_tree_result_is_bounded_in_model_tool_message` (asserts the actual `AgentRuntime._bounded_tool_message` output stays within `MAX_TOOL_MESSAGE_CHARS` and carries the `verified` field).
- `test_ui_text_cannot_alter_policy_or_approval_behavior`, `test_semantic_tool_schema_has_no_filesystem_parameters`.
- `test_end_to_end_through_agent_runtime_tool_message` - the required `ToolRegistry/ToolExecutionService → ComputerActionService → fake SemanticDesktopAdapter → bounded result → AgentRuntime tool message` chain, with a mocked model gateway proposing the `computer.semantic.read` tool call and consuming its bounded result in the next turn.

**Regression fix found and applied during this milestone:** the default `WindowsUIAutomationAdapter(self.perception_provider)` construction inside `WindowsNativeComputerController.__init__` initially assumed every `perception_provider` exposes a `.privacy_policy` attribute - two pre-existing `test_phase_ten_active_perception.py` tests construct the controller with a lightweight fake provider that doesn't. Fixed with a defensive fallback (`getattr(window_provider, "privacy_policy", None) or PerceptionPrivacyPolicy()`) in `semantic_uia.py`; both tests pass again and the full suite was re-run clean afterward.

### 4.9 Milestone 2 verification

| Check | Result |
|---|---|
| `pytest tests/test_phase_eighteen_semantic_uia.py -q` | 17 passed (unchanged from Milestone 1) |
| `pytest tests/test_phase_eighteen_semantic_tool_path.py -q` | **10 passed** |
| `pytest tests -k "phase_eighteen" -q` | **47 passed** |
| `pytest tests -q` (full) | **562 passed, 0 skipped, 36 subtests** (552 Milestone-1 baseline + 10 new) |
| `python -m compileall src tests -q` | PASS |
| `git diff --check` | PASS |

Frontend re-run was not performed for this milestone - untouched (required again at final batch completion).

### 4.10 Milestone 2 canonical state update

- `02_JARVIS_CURRENT_STATE.md`: "UIA semantic control tree/actions" row updated to record the tool path as implemented and proven live; explicitly states no semantic actuation exists yet.
- `03_JARVIS_GAP_REGISTER.md`, GAP-0101: remains `OPEN` overall; added a "Batch 01 Milestone 2" `PARTIAL` note.
- `04_JARVIS_EXECUTION_ROADMAP.md`: Workstream A status note extended to record Milestone 2 complete.

---

## 5. Milestone 3 — First bounded semantic UI actions

### 5.1 Semantic actions implemented

Three `WindowsUIAutomationAdapter` methods (`src/jarvis/computer/semantic_uia.py`): `invoke`, `toggle`, `select` - `InvokePattern`/`TogglePattern`/`SelectionItemPattern` only. `ValuePattern.SetValue`/text write, mouse/keyboard, drag/scroll injection, and OCR/visual fallback are explicitly **not** implemented - deferred per the task, not merely undocumented. Each method reuses the exact same stale-safe re-resolution (`_reresolve`) Milestone 1 built for reads, plus one new actuation-only gate (`_reresolve_actuation_target`): a password-marked control is denied (`uia_sensitive_value_denied`) **before** any pattern is even checked, let alone invoked.

### 5.2 Actuation contract (as implemented)

```text
opaque element_ref
→ re-resolve containing window_ref (existing WindowsDesktopProvider authority, privacy-checked)
→ re-walk bounded tree, accept only on RuntimeId-digest match (stale/ambiguous -> refuse, never act)
→ password/sensitive check (deny before pattern check)
→ confirm the required pattern (Invoke/Toggle/SelectionItem) is actually present -> uia_pattern_unsupported otherwise
→ ComputerActionService risk classification (consequential, since these three actions are
   deliberately absent from _read_actions/_safe_actions) -> PermissionEngine -> ApprovalEngine
→ perform exactly one pattern call (Invoke() / Toggle() / Select())
→ re-observe (fresh snapshot + pattern-specific state re-read)
→ typed, honest verified signal (never fabricated)
→ audit via the existing ComputerActionService path
```

No retry loop exists anywhere in this path - a failed/unverified action is returned as-is; nothing "tries again" automatically.

### 5.3 Risk/approval policy

`SEMANTIC_INVOKE`/`SEMANTIC_TOGGLE`/`SEMANTIC_SELECT` were deliberately **not** added to `ComputerActionService._read_actions` or `_safe_actions`, so `execute()`'s existing risk computation (`"consequential"` for anything in neither set) applies unchanged - and `PolicyPermissionEngine.evaluate()` already short-circuits any `risk_level == "consequential"` straight to `REQUIRE_APPROVAL` **before** consulting the rules list, so this holds for every action name, typo-proof, with no per-action rule needed (unlike the read actions in Milestone 2, which each needed an explicit ALLOW rule). No global "all computer.\* safe" rule was added - the opposite: these three actions are approval-required by construction, not by an addable/removable rule. The new outer `computer.semantic.act` tool follows the exact same two-layer pattern already established for `computer.keyboard.type`/`computer.window.control` (outer `risk_level="safe"`/ALLOW is non-authoritative registry metadata; the inner `ComputerActionService` gate is what actually enforces approval) - documented explicitly in a code comment this time, addressing the minor doc-consistency note (F18A1-011) the Phase 18A.1 audit raised about the *existing* instances of this same pattern.

### 5.4 Supported patterns - verification semantics

- **Invoke:** always returns `verified=False` on success - there is no generic, provider-independent way to confirm an arbitrary `Invoke()` achieved its semantic intent (a button might open a dialog, submit a form, do nothing visible, etc.). This is stated as a design decision, not a gap: "invoke often remains unverified generically... acceptable because the model now receives explicit `verified=False`" (task §11.7), and Phase 18A.2's F18A1-003 fix means that flag now actually reaches the model.
- **Toggle:** reads `ToggleState` before, calls `Toggle()`, reads `ToggleState` after; `verified = (before != after)`. Proven with both a state-changing fake and a "stuck" fake that leaves state unchanged (`verified=False` in that case) - both directions tested.
- **Select:** calls `Select()`, then re-reads `IsSelected`; `verified = IsSelected`. Proven with both a normal fake (becomes selected) and a "stuck" fake (`verified=False`).

None of the three ever reports `verified=True` from "the pattern call returned" alone - every verified value comes from an independent property re-read after the call.

### 5.5 Target privacy / sensitive controls / file dialogs

Password controls are denied before any pattern check (§5.1). No file-dialog-specific behavior was added - per the task's explicit "prefer deny/defer over clever bypasses," a file dialog's controls are just ordinary elements to this milestone's generic invoke/toggle/select (still requiring approval, and Milestone 1's read path already refuses to expose any path-entry `set_value`/text-write capability at all, which does not exist anywhere in this adapter). No UAC/secure-desktop automation was attempted or is possible through this path - a locked/secure desktop window is unreachable the same way any other window becomes stale (`WindowsDesktopProvider.validate_input_window` fails), returning a typed failure, never a hang or a fake success.

### 5.6 Recovery

Exactly the bounded, no-retry recovery the task specifies: a failed pre-action revalidation returns a typed stale/ambiguous failure without acting; a provider exception during the pattern call is caught and translated to `uia_action_failed:<ExceptionClassName>` (never a leaked raw COM string) without a retry; an unverified-but-executed result is returned as `succeeded, verified=False` rather than being silently retried. No blind double-invoke/double-click behavior exists anywhere in this code.

### 5.7 Tests

**Adapter-level** (`tests/test_phase_eighteen_semantic_uia.py`, +9 tests, **26 total, all passing**): `test_invoke_calls_pattern_and_is_never_verified_true_generically`, `test_invoke_unsupported_pattern_returns_typed_failure`, `test_invoke_on_password_control_denied_before_pattern_check`, `test_invoke_on_stale_element_never_acts`, `test_invoke_on_ambiguous_reresolution_never_acts`, `test_toggle_verified_true_when_state_actually_changes`, `test_toggle_verified_false_when_state_does_not_change`, `test_select_verified_true_when_selected`, `test_select_verified_false_when_not_selected`.

**Approval/architecture-level** (`tests/test_phase_eighteen_semantic_actions.py`, **13 tests, all passing**): `test_invoke_requires_canonical_approval`, `test_toggle_and_select_also_require_approval`, `test_approved_invoke_executes_exactly_once_on_repeated_decide`, `test_denied_approval_never_acts`, `test_stale_pending_action_cannot_execute`, `test_invoke_unsupported_pattern_typed_failure_after_approval`, `test_invoke_on_password_control_denied_after_approval`, `test_toggle_verified_true_end_to_end`, `test_toggle_verified_false_end_to_end`, `test_select_verified_end_to_end`, `test_invoke_generic_action_never_verified_true`, `test_action_travels_through_computer_action_service_with_audit`, `test_no_filesystem_action_introduced`.

**Regression fix found and applied during this milestone:** `test_approved_invoke_executes_exactly_once_on_repeated_decide` initially exposed a real (though non-unsafe) rough edge - `computer.semantic.act` used `DURABLE` argument retention, so a second `decide_and_resume` on an already-consumed approval silently re-entered the full permission/approval flow and minted a **new** approval request instead of failing cleanly (confirmed via direct inspection: the actuation itself was never called twice - `fake_adapter.invoke_calls` stayed length 1 - so this was never an unsafe double-execution, only a confusing repeat-decide UX). Fixed by switching `computer.semantic.act` to `argument_retention=ToolResultRetention.EPHEMERAL`, exactly matching `computer.keyboard.type`/`computer.window.control`'s existing convention - a second decide now hits the same already-tested `ephemeral_arguments_unavailable` typed failure those tools already rely on, rather than a fresh, confusing approval-required response.

### 5.8 NIGHTFURY physical acceptance

Through the actual `computer.semantic.act`/`computer.semantic.read` tool path (not raw `uiautomation`), against disposable Calculator:

| Step | Result |
|---|---|
| Read Calculator display before | `"Display is 0"` |
| Find "Seven" (`ButtonControl`, `num7Button`, patterns=`['Invoke']`) | 1 match |
| `computer.semantic.act` invoke on Seven | `approval_required` (confirms approval-by-default holds even for a plain number button) |
| Approve via `decide_and_resume` (normal owner/test path) | `completed`, `verified=False` (honest - matches §5.4) |
| Read Calculator display after (independent read-back, not the actuation's own report) | `"Display is 7"` - **the real, physical effect is confirmed** |
| Audit trail | 36 rows; `computer.permission_checked`, `computer.action_completed`, `permission.checked`, `tool.completed` all present |

**Toggle/Select were not physically re-demonstrated live in this batch, disclosed honestly:** Calculator's `TogglePaneButton` (the one plausible on-screen toggle-like control) only exposes `InvokePattern` on this NIGHTFURY build, not `TogglePattern` - confirmed live during this probe, matching the earlier A1 evaluation's finding on the same control. No other convenient, safe, disposable `TogglePattern`/`SelectionItemPattern` control was found on Calculator/Notepad within this batch's scope. Per AGENTS.md §6 ("physical PASS requires physical evidence; tests/mocks are not physical evidence"), this report does **not** claim physical acceptance for `toggle`/`select` - only code/test acceptance (§5.7). Calculator was closed via `Stop-Process` after the probe (the only disposable instance created; its display showing "7" is a harmless, reversible artifact of a disposable instance, not owner data). Notepad's owner draft was not opened or touched in this milestone's live probe.

### 5.9 Milestone 3 verification

| Check | Result |
|---|---|
| `pytest tests/test_phase_eighteen_semantic_uia.py -q` | **26 passed** |
| `pytest tests/test_phase_eighteen_semantic_actions.py -q` | **13 passed** |
| `pytest tests -k "phase_eighteen or phase_eleven or phase_nine or phase_four or phase_two" -q` | **166 passed** |
| `pytest tests -q` (full) | **584 passed, 0 skipped, 36 subtests** (562 Milestone-2 baseline + 9 + 13 new) |
| `python -m compileall src tests -q` | PASS |
| `git diff --check` | PASS |
| `cd ui && npm test && npm run build && npm audit --audit-level=high` | deferred to the final batch-wide rerun (§6), per the task's explicit instruction that frontend is rerun once at final completion even though untouched throughout this batch |

### 5.10 Milestone 3 documentation

- `02_JARVIS_CURRENT_STATE.md`: UIA row updated to record bounded actuation (invoke physically proven; toggle/select test-proven only), and explicitly lists what remains unimplemented (set_value, mouse/keyboard, OCR, multi-app recovery, eval suite).
- `03_JARVIS_GAP_REGISTER.md`, GAP-0101: added a Milestone 3 note. **Left as `OPEN`/`PARTIAL`, not marked `RESOLVED`** - the evidence is strong for `invoke` (physical) and thorough for `toggle`/`select` (test-only), but this report defers the final "is this gap now resolved" call to the owner/independent reviewer per the checkpoint workflow's own "independent review before next slice" rule, rather than self-declaring closure. GAP-0102 (mouse/keyboard), GAP-0103 (OCR/visual), GAP-0104 (multi-app recovery), GAP-0105 (evaluation suite), GAP-0106 (DPI/multi-monitor/secure-desktop), and GAP-0503 (file-access confinement) are all confirmed untouched and remain `OPEN`.
- `04_JARVIS_EXECUTION_ROADMAP.md`: Workstream A status note extended to record all three milestones complete and names independent commit review as the next gate.

Computer Use V2 is **not** claimed complete. Physical acceptance is claimed **only** for the one specific `invoke` scenario actually demonstrated, not generally.

---

## 6. Final full regression (after all three milestones)

| Check | Result |
|---|---|
| `pytest tests -q` | **584 passed, 0 skipped, 36 subtests** |
| `python -m compileall src tests -q` | PASS |
| `git diff --check` | PASS with one intentional-Markdown-formatting note (documented per-milestone above, not reformatted) |
| `npm test` (ui/) | **75 passed**, 14 files |
| `npm run build` (ui/) | clean, 68 modules |
| `npm audit --audit-level=high` (ui/) | **0 high/critical** (2 pre-existing moderate dev-only advisories, unrelated) |

Explicit security regression checks against the full three-milestone diff (`git diff main...HEAD`):

| Check | Result |
|---|---|
| No `shell=True` added | confirmed (grep clean) |
| No `os.system` added | confirmed (grep clean) |
| No raw COM/UIA object in model-facing output | confirmed - `_semantic_snapshot_dict`/`_semantic_tree_dict` convert every dataclass to plain dict/list/str/bool/int before it reaches `ComputerResult.output`; `test_no_raw_hwnd_or_com_object_in_public_snapshot` asserts this at the contract level |
| No raw HWND accepted from model input | confirmed - both tool schemas (`computer.semantic.read`, `computer.semantic.act`) only accept opaque `window-*`/`element-*` string references, never an integer handle or coordinates |
| No direct adapter bypass of `ComputerActionService` | confirmed - the adapter is only ever called from inside `WindowsNativeComputerController.execute()`, which only `ComputerActionService._execute_controller` invokes |
| No new duplicate authority | confirmed - one `ComputerActionService`, one `PolicyPermissionEngine`, one `DurableApprovalEngine`, one `WindowsUIAutomationAdapter` implementation; no `ComputerActionServiceV2`/second permission or approval engine/alternate model-to-UIA path was created |
| No silent approval bypass | confirmed - `semantic_invoke`/`semantic_toggle`/`semantic_select` are absent from `_read_actions`/`_safe_actions`, so `risk_level="consequential"` applies unconditionally; `test_invoke_requires_canonical_approval`/`test_toggle_and_select_also_require_approval` prove this directly |
| No automatic repeat on uncertain action | confirmed - no retry/loop code was added anywhere in this batch; an unverified result is returned once, as-is |
| No filesystem authority expansion | confirmed - `inspect_file`/`search_files`/`open_file`/`open_folder` were not touched; neither new tool schema contains a path-shaped parameter (`test_semantic_tool_schema_has_no_filesystem_parameters`, `test_no_filesystem_action_introduced`) |
| No `ValuePattern` write exposed | confirmed - `set_value`/`SetValue` do not appear anywhere in the implementation, only in a docstring explaining they are deliberately absent |
| No arbitrary mouse/keyboard expansion | confirmed - grep for mouse/`SendInput`/click-related additions across the full diff returns nothing; the existing bounded `SendInput` keyboard path from earlier phases is untouched |
| No secret persistence | confirmed - no credential/API-key/token value appears anywhere in the diff (checked per-commit before each commit; see §2-§5) |
| No owner-data acceptance test mutation | confirmed - every live probe either read the owner's pre-existing Notepad session without modification, or acted only on disposable Calculator/blank-window instances created and torn down by this batch itself |

---

## 7. Gaps closed / partial / open

| Gap | Status after this batch |
|---|---|
| GAP-0101 (general Windows semantic UI control) | `OPEN`/`PARTIAL` - backend decision resolved (DEC-046); read foundation, canonical tool wiring, and bounded invoke/toggle/select actuation all implemented and test-green; `invoke` physically proven, `toggle`/`select` test-proven only. Left open for independent review before any closure claim. |
| GAP-0102 (mouse/rich keyboard input) | `OPEN`, untouched |
| GAP-0103 (visual grounding/OCR) | `OPEN`, untouched |
| GAP-0104 (action verification/recovery, multi-app) | `OPEN`, untouched - this batch's recovery is bounded to the single-action stale/ambiguous/unsupported-pattern cases already covered, not the broader multi-app recovery loop GAP-0104 describes |
| GAP-0105 (computer-use evaluation suite) | `OPEN`, untouched - this batch's tests are unit/integration + two manual NIGHTFURY probes, not the repeatable evaluation program GAP-0105 describes |
| GAP-0106 (DPI/multi-monitor/secure-desktop proof) | `OPEN`, untouched |
| GAP-0503 (file-root confinement / sensitive-path policy) | `OPEN`, untouched - explicitly verified not widened anywhere in this batch |

---

## 8. Manual dependencies

**None required.** No API key, OAuth credential, Home Assistant token, MQTT credential, SSH credential, or personal data was requested, required, or used anywhere in this batch. The one local package installation (`uiautomation==2.0.29` into the environment used to run tests/probes on NIGHTFURY) required no secret - it is a public PyPI package, matching the task's explicit allowance ("If `computer-uia` installation is required locally for physical probe, normal package installation is allowed... No secret is needed").

---

## 9. Exact restrictions carried forward

- **F18A1-010 / GAP-0503** remains open. This batch did not widen `inspect_file`, `search_files`, `open_file`, or `open_folder`; introduced no semantic file-picker automation; set no path values in any file dialog; invoked no Open/Save confirmation action; and used no UIA capability as a backdoor around file permissions. Neither `computer.semantic.read` nor `computer.semantic.act`'s schema contains a path-shaped parameter. **Any future slice that adds semantic file-dialog interaction must resolve GAP-0503 first**, not route around it through a semantic element reference.
- No `ValuePattern`/`set_value` text-write capability was added - explicitly deferred (§5.1).
- No mouse/keyboard/coordinate input capability was added or expanded - the existing bounded `SendInput` keyboard-text path from earlier phases is unchanged; no new input surface exists.
- No OCR/visual fallback was added.
- No second `ComputerActionService`/`PermissionEngine`/`ApprovalEngine`/audit path/model-to-UIA shortcut was created at any point across all three milestones.

---

## 10. Recommended next batch

Per this task's own instruction, the next step is **independent GitHub commit review** of the four pushed commits before any further implementation - not another immediate implementation batch from this agent. Once reviewed, plausible next slices (in rough priority order, each its own small batch, none started here):

1. **App-specific verification for `invoke`** on at least one real target class (e.g. a checkbox-adjacent button, a menu item with observable side effects) to narrow the "generic invoke is always unverified" gap without inventing a new authority.
2. **Toggle/Select physical acceptance** on a real control that actually exposes those patterns (a real checkbox/list app), since this batch could not find one on disposable Calculator/Notepad.
3. **GAP-0503 resolution** (file-root confinement/sensitive-path policy) - explicitly called out as a prerequisite before any semantic file-dialog work.
4. **Bounded native mouse/keyboard** (GAP-0102) as its own carefully-scoped, separately-approved batch - not folded into semantic work.
5. **Computer-use evaluation suite** (GAP-0105) to make future acceptance repeatable rather than ad hoc probe scripts.

No merge to `main` was performed or is recommended without the owner's explicit instruction.
