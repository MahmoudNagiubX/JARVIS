# PHASE 18 — WORKSTREAM A — BATCH 02
## Semantic Safety Hardening → Grounded Native Input → Repeatable Computer-Use Evaluation

**Task:** `tasks/CLOUD_CODE_MASTER_PHASE_18_WORKSTREAM_A_BATCH_02.md`
**Branch:** `feature/phase-18-computer-use-v2`
**Status:** IN PROGRESS — Milestone 0 complete, Milestones 1/2 not yet started.

This is the single report for the whole batch (per Section 11 of the task file);
it is appended to, not duplicated, as later milestones complete.

---

## 1. Starting branch/HEAD

- Branch: `feature/phase-18-computer-use-v2`
- Starting HEAD: `2390ddc7aaa7be3596826027e4cd351d919643c8` (`feat: add bounded semantic UI actions`, Batch 01 Milestone 3)
- Branch was in sync with `origin/feature/phase-18-computer-use-v2` (no unexplained divergence) at the start of this batch.

---

## 2. Independent review findings (Batch 01)

Five findings against the code pushed in Batch 01, all closed in Milestone 0 below:

| ID | Summary | Disposition |
| --- | --- | --- |
| R18B01-001 | A missing/erroring `GetRuntimeId()` was hashed into a fake "strong" digest via `repr(())`, collapsing all weak-identity elements onto the same identity. | Fixed — explicit `identity_strength: strong\|weak` model; weak refs never actionable. |
| R18B01-002 | `list_windows()` returned raw `WindowsDesktopProvider.desktop_context()` output with no privacy filtering, leaking sensitive window titles/processes. | Fixed — denies the whole call when privacy mode is OFF; filters every window failing `PerceptionPrivacyPolicy.check_window()`. |
| R18B01-003 | Post-action verification (toggle/select/invoke) re-read the *same* pre-action pattern/control object, which can be stale/destroyed by the action itself. | Fixed — a full fresh re-resolution (`_reresolve`) plus a fresh `GetPattern()` call happens after every action; never the pre-action object. |
| R18B01-004 | Semantic approval preview showed only `semantic_invoke` + an opaque `element-<uuid>`; generic ~10 min approval expiry could outlive the ~45s element-ref TTL. | Fixed — target-aware bounded preview built from a fresh trusted read, approval refused up front for stale/weak/non-actionable targets, target-identity digest re-checked on `decide()`, expiry bounded by the element-ref TTL. |
| R18B01-005 | No explicit fail-closed check for disabled/offscreen/weak-identity targets immediately before actuation. | Fixed — `_reresolve_actuation_target()` denies weak identity, sensitive/password, disabled, and offscreen targets with typed codes before any pattern call. |

---

## 3. Milestone 0 — Semantic safety hardening

**Commit:** `MILESTONE_0_COMMIT` (recorded in Section 6.5 below after push)

### 3.1 Strong/weak identity (R18B01-001)

- `_runtime_id_identity()` (`semantic_uia.py`) returns `(digest, is_strong)`; a missing, empty, or exception-raising `GetRuntimeId()` now yields `(None, False)` — never a fabricated digest.
- `_ElementRefEntry.identity_strength: "strong" | "weak"` is stored per reference at observation time.
- `_reresolve()` branches: strong references match by RuntimeId digest equality; weak references match by a bounded composite (AutomationId + control_type + name + bounded ancestry), and a weak match must be **unique** in the bounded tree or resolution fails `uia_element_ambiguous`.
- `SemanticElementSnapshot.actionable: bool` is a new, minimal model-visible field (`actionable = is_strong and enabled and not offscreen and not is_password`). It never exposes RuntimeId, digest, or *why* — only whether the target is currently a legitimate actuation candidate.
- `_reresolve_actuation_target()` refuses weak identity with `uia_element_identity_weak` before any pattern is touched.

### 3.2 Privacy (R18B01-002)

- `list_windows()` now denies the entire call (`privacy_policy_denied`) when `PerceptionPrivacyPolicy.allows_metadata()` is false, instead of silently returning nothing/partial data.
- Every window is checked with `privacy_policy.check_window(process_name, title)`; a match is dropped from the result entirely (never returned, not even in redacted form) and only counted in a new `filtered_count`.
- `computer/service.py`'s `_semantic_list_windows` surfaces `filtered_count` to the model-facing `ComputerResult` payload alongside the (already filtered) window list.

### 3.3 Fresh verification (R18B01-003)

- `invoke()`, `toggle()`, `select()` each call `self._reresolve(element_ref)` again *after* the pattern call, never trusting the pre-action `Control`/pattern object.
- A target that disappears post-action (closed dialog, navigation, stale, ambiguous, window gone) is reported as `succeeded, verified=False` with a bounded `verification_reason` (`target_disappeared_after_invoke`, `post_observation_unavailable`) — never an uncaught exception, never a fabricated `verified=True`.
- `toggle()`/`select()` additionally fetch a **fresh** pattern object (`_get_pattern(fresh_control, pattern_id)`) for the post-action state read; the pre-action pattern object/variable is never reused for that read. `pre_state`/`post_state` (renamed from Batch 01's `toggle_state_before`/`toggle_state_after`) are bounded receipt fields; no auto-retry is performed anywhere.

### 3.4 Approval target binding/TTL (R18B01-004)

- New `ComputerActionService._semantic_target_preview()` fetches a fresh, trusted snapshot through the **existing canonical read path** (`self.controller.execute(ComputerAction("semantic_get_element", ...))` — the same `semantic_get_element` capability the model already uses, not a new adapter method or a second authority).
- Before creating an approval for `semantic_invoke`/`semantic_toggle`/`semantic_select`, this preview is fetched; if the fetch fails or the target's `actionable` is `False`, approval creation is refused outright (typed `denied` result, no approval record minted, no execution).
- The preview shown to the approver is bounded and safe: `action`, `control_type`, `automation_id`, a name truncated to 80 chars, `window_ref`, `element_ref` — never text/value contents, never a raw parameter dump, never model-supplied text.
- A bounded identity digest (hash of `element_ref` + fresh `window_ref`/`control_type`/`automation_id`/`name`) is stored in `ComputerActionService._pending` alongside the existing pending-action tuple.
- On `decide()`, the same preview fetch runs again and the digest is recomputed; if it no longer matches (target renamed/replaced) the action is refused with `approval_target_changed` and never executes; if the re-fetch itself fails, a typed stale failure is returned instead.
- `approval_expires_at = min(now + 10 minutes, now + ELEMENT_REF_TTL_SECONDS)` for these three actions specifically (imported from `semantic_uia.ELEMENT_REF_TTL_SECONDS = 45`), so the approval can never legitimately outlive the element reference it targets.

### 3.5 Interactability (R18B01-005)

- `_reresolve_actuation_target()` fails closed, after a fresh re-resolution, on: weak identity (`uia_element_identity_weak`), password/sensitive (`uia_sensitive_value_denied`), disabled (`uia_target_not_interactable`), and offscreen (`uia_target_not_interactable`) — all before any pattern object is even fetched.
- Combined with 3.4, a non-actionable target is refused **twice**, independently: once at approval-creation time (preview refusal) and again at actuation time (defense in depth; no single code path is trusted).

### 3.6 Physical semantic acceptance

**Approach:** a disposable Microsoft Edge **Guest** window over a temporary local HTML fixture (`file://` URI under the OS temp directory; inert button/checkbox/two-option `<select>`/status label; no owner profile, no login, no internet), driven strictly through `computer.semantic.read` / `computer.semantic.act` with normal approval — `uiautomation` was never called directly for acceptance. The fixture and the Guest browser instance were both deleted/closed after the probe.

**Finding — Chromium content is unreachable at the adapter's current bounded depth.** `inspect_window`/`find_elements` walk at most `MAX_INSPECT_DEPTH = 5` levels from the top-level window. Live inspection showed that in a real Edge (Guest) window, all 5 levels are consumed by the browser's own UI-automation wrapper chrome (`WindowControl` → nested `PaneControl`s → tab bar / minimize-maximize-close buttons) before the actual rendered page (DOM) is ever reached — `find_elements` for `ButtonControl`/`CheckBoxControl`/`ComboBoxControl` on the fixture page returned zero matches, not because Chromium fails to expose `Invoke`/`Toggle`/`SelectionItem` patterns on its own controls, but because the fixture's controls are structurally deeper than the bound allows. This is a genuine, reproducible limitation of the existing (Batch 01) bounded-depth design when applied to Chromium-based browser content specifically, not a defect introduced by this milestone's hardening, and not in scope to change here (`MAX_INSPECT_DEPTH` is an existing architectural bound, not part of R18B01-001..005). Per the task's own explicit fallback instruction ("If Chromium does not expose the required pattern... try another safe local surface... if none works, keep code/test acceptance and mark physical acceptance pending rather than fabricate success"), this path was not force-fixed and no toggle/select success is claimed from it.

**Incident during the search for an alternative surface:** a second attempt used `notepad.exe` as a candidate disposable surface. Windows 11's in-box Notepad turned out to be a single-instance app that reuses an already-open window rather than spawning an independent disposable instance; the probe's launch attached to the owner's real, already-open Notepad window (which had an unsaved/"Modified" tab), and the read-only inspection call plus the probe's own cleanup left that window with a single blank tab, with the prior unsaved content very likely lost (Notepad's on-disk session-state file was observed rewritten to a 20-byte blank-tab-only state with no recoverable history). No actuation (`invoke`/`toggle`/`select`) was ever called against this window, and this was disclosed to the owner immediately and in full before any further work continued; the owner confirmed no material harm and directed that all further physical acceptance in this batch use only disposable, non-owner surfaces (Edge Guest, Calculator) and never touch Notepad or other in-box apps that might reuse a live owner session again. This is recorded as a real, if minor, incident for the record — see `SendFeedback` draft queued this session — and as a concrete argument for treating *any* Windows in-box app as a potentially non-disposable surface unless independently confirmed multi-instance beforehand.

**What was physically proven:**

- **`invoke`** — re-confirmed end-to-end through the *fully hardened* pipeline (this milestone's R18B01-001/003/004/005 code, not just Batch 01's) on a freshly launched, confirmed-not-already-running, disposable Calculator instance: `computer.semantic.read find_elements` located the "Seven" button (`automation_id="num7Button"`, `actionable=true`, strong identity); `computer.semantic.act invoke` correctly required approval, the target-aware preview was created and matched on decide, the action executed, and reported `succeeded, verified=false, verification_reason="generic_invoke_no_postcondition"` (honest, non-fabricated); an **independent** second `find_elements` call (not the action's own report) against `automation_id="CalculatorResults"` read back `"Display is 7"`, physically confirming the real effect. The disposable Calculator instance was then closed.
- **`toggle` / `select`** — **not physically re-demonstrated live this batch.** No safe, disposable, semantically-reachable `TogglePattern`/`SelectionItemPattern` control was found within this batch's time-boxed scope (Edge Guest fixture blocked by the depth limitation above; Calculator has no toggle-capable control per Batch 01's own finding; Notepad ruled unsafe by the incident above; no further owner-app exploration was attempted per the owner's directive). This remains **code/test acceptance only**: 9 deterministic `semantic_uia` unit tests plus 13 approval/architecture tests exercise toggle/select — including new tests added this milestone for fresh-post-action re-observation (a fake control whose `GetPattern()` mints a new, "freezes at fetch" pattern instance every call, proving the adapter fetches a genuinely fresh post-action pattern rather than reusing the pre-action reference or object identity) — but this is disclosed honestly as test evidence, not physical evidence (AGENTS.md §6).
- **Weak identity, disabled/offscreen/password denial, approval-target-changed, and approval-TTL binding** are all proven by deterministic unit/integration tests (fakes) only in this batch; no live weak-identity/disabled/offscreen Windows control was independently sourced for physical demonstration within scope.

### 3.7 Tests

New/updated test modules:

- `tests/test_phase_eighteen_semantic_uia.py` — 38 tests (was 22): added `list_windows` privacy-filtering tests (denied-process/denied-title filtering, `filtered_count`, privacy-mode-OFF denial), weak-identity tests (missing RuntimeId, raising RuntimeId, weak-ref actuation denial, weak-composite ambiguity), `actionable` field coverage (strong ref stays actionable), disabled/offscreen pre-actuation denial, and three fresh-post-action-observation tests (destroyed target → unverified not an exception; a "freezes at fetch" fake pattern proving a genuinely fresh `GetPattern()` call is used post-action, not the cached pre-action reference; provider raising after the action → `post_observation_unavailable`). Renamed `toggle_state_before`/`toggle_state_after` references to `pre_state`/`post_state`.
- `tests/test_phase_eighteen_semantic_actions.py` — 17 tests (was 13): added approval-preview-content test (bounded fields, no secrets/text/value/raw-parameter-dump), pre-approval refusal when the target read fails, target-changed-after-request-before-decide refusal (`approval_target_changed`), and approval-expiry-bounded-by-element-ref-TTL. Updated the password-control test: it now asserts refusal *before* approval creation (`uia_target_not_actionable`, no approval minted) rather than denial after approval, matching R18B01-004/005's fail-closed-earlier behavior.
- `tests/test_phase_eighteen_semantic_tool_path.py` — unchanged, still green (12 tests).

Results:

```text
python -m pytest tests -k "phase_eighteen" -q
85 passed, 515 deselected

python -m pytest tests -q
600 passed, 36 subtests passed

python -m compileall src tests -q
(clean)

git diff --check
(clean)
```

Frontend suite was not run for Milestone 0 (no frontend files touched; deferred to the final batch gate per Section 6.3 of the task file).

### 3.8 Commit

- **Files staged (explicit paths, no `git add .`):** `tasks/CLOUD_CODE_MASTER_PHASE_18_WORKSTREAM_A_BATCH_02.md`, `src/jarvis/computer/semantic_uia.py`, `src/jarvis/computer/service.py`, `src/jarvis/contracts/semantic_ui.py`, `tests/test_phase_eighteen_semantic_uia.py`, `tests/test_phase_eighteen_semantic_actions.py`, `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_02.md`.
- **Commit message:** `fix: harden semantic computer-use targets`
- **MILESTONE_0_COMMIT:** recorded after push, see final response.

---

<!-- Sections 4 (Milestone 1), 5 (Milestone 2), 6 (final regression), 7 (security review),
     8 (gap status), 9 (manual dependencies), 10 (restrictions remaining), and
     11 (recommended Batch 03) are appended here once those milestones run. -->
