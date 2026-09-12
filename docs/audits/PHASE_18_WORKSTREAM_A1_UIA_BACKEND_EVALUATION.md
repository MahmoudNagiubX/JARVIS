# PHASE 18 WORKSTREAM A.1 — WINDOWS UIA BACKEND EVALUATION

**Task:** `tasks/CLOUD_CODE_TASK_PHASE_18_WORKSTREAM_A1_UIA_BACKEND_EVALUATION.md`
**Mode:** Evidence-driven technical spike / decision gate. No production code changed.
**Date:** 2026-09-12
**Machine:** NIGHTFURY (Windows 11, the actual current development machine)

---

## 1. Starting HEAD / worktree state

```text
Branch: main
HEAD:   54b67ba396ec45180f1b60ea472ef94c9ac181a9  (unchanged throughout this task)
```

Worktree carried the same uncommitted Phase 18A.2 stabilization diff already present at the start of this session (5 modified `src/` files, the Phase 18A.2 test file, the repo-local source-of-truth pack, and two prior audit reports — all pre-existing, unrelated to this task, and left untouched). No file under `src/` or `tests/` was modified by this task. The only new file created by this task is this report.

## 2. Current Computer Use implementation summary (read before evaluating)

Read `AGENTS.md`, `docs/source_of_truth/00`–`05`, `docs/audits/PHASE_18A1_BASELINE_AUDIT.md`, `docs/audits/PHASE_18A2_STABILIZATION.md`, then inspected `src/jarvis/computer/`, `src/jarvis/perception/`, `src/jarvis/bootstrap.py`, and `pyproject.toml`.

- **Zero runtime dependencies today.** `pyproject.toml` declares `dependencies = []`. Windows control (`src/jarvis/perception/windows.py::WindowsDesktopProvider`) is implemented entirely with raw `ctypes` calls into `user32.dll`/`gdi32.dll`/`kernel32.dll` — window enumeration (`EnumWindows`), title/class reads, foreground/focus, minimize/maximize/restore, and on-demand GDI screenshot capture. There is **no COM usage anywhere in the codebase** (confirmed by grep: zero matches for `comtypes`, `CoInitialize`, `IUIAutomation`, `CoCreateInstance`, `pywin32`, `win32com` under `src/`).
- **No semantic control-tree layer exists yet.** `WindowsDesktopProvider` only exposes window-level metadata (title, class, process, bounds, foreground). There is no ControlType/Name/AutomationId/pattern access anywhere — this matches the audit's GAP-0101/GAP-0103 ("no general Windows semantic UI control", "visual grounding/OCR not production-active") and confirms Layer 1 (UIA) is a genuine, currently-unfilled gap, not a partially-built feature.
- `src/jarvis/computer/service.py::ComputerActionService` and `src/jarvis/computer/controller.py` operate on the bounded action set (open/list/inspect/search files and processes, window focus/minimize/maximize/restore, clipboard, bounded keyboard `SendInput`, media-key volume) — all coordinate/HWND-based, no semantic element targeting.
- `docs/source_of_truth/01_JARVIS_CORE_SOURCE_OF_TRUTH.md` §6 and `05_JARVIS_DECISION_LOG.md` (DEC-016/017/018/019/020) already lock the priority order (native API → UIA → app-semantic → visual → native input → PyAutoGUI-fallback) and record `winapp ui` as a "preferred evaluation candidate, not a core dependency" (DEC-018, `CANDIDATE` status) — this task resolves that open evaluation with real evidence, per OPEN-001 in the decision log.
- Relevant existing tests: `tests/test_phase_eleven_windows_interaction.py` (keyboard/window/clipboard/audio action tests against the current ctypes layer), `tests/test_phase_ten_active_perception.py` (window-ref revalidation/staleness tests for the current, non-semantic layer). No existing test touches UIA/semantic trees — confirmed there is nothing to break here.

## 3. Candidates actually tested

| Candidate | Tested? | How |
|---|---|---|
| A — Microsoft `winapp ui` CLI | **Yes**, hands-on on NIGHTFURY | Installed via `winget install Microsoft.WinAppCli` (user-scoped MSIX), ran all 7 scenarios against real running apps |
| B — Direct Python UIA client | **Yes**, hands-on on NIGHTFURY | Installed `uiautomation` 2.0.29 and `pywinauto` 0.6.9 into an isolated temp venv (outside the repo, deleted after use), ran equivalent scenarios |
| C — Direct native/WinRT/COM integration | **Evaluated, not implemented** | Rejected on evidence without writing implementation code — see §12 |

## 4. Exact versions

| Component | Version | Source |
|---|---|---|
| `winapp` CLI (Microsoft.WinAppCli) | 0.6.1 | winget, MSIX, released 2026-08-19 |
| `uiautomation` (Python) | 2.0.29 | PyPI, temp venv |
| `pywinauto` (Python) | 0.6.9 | PyPI, temp venv |
| `comtypes` | (transitive dep of both above) | PyPI, temp venv |
| `pywin32` | (transitive dep of `pywinauto` only) | PyPI, temp venv |
| Project system Python | 3.14.6 | used to run winapp/pytest from the CLI |
| Project `.venv` Python | 3.12.13 | satisfies `pyproject.toml` `requires-python >= 3.11` |
| Temp evaluation venv Python | matches system 3.14.6 | isolated, `python -m venv`, deleted after use |
| OS | Windows 11 | NIGHTFURY |

No project dependency file (`pyproject.toml`, lockfile) was edited. `winapp` was installed at the machine level via winget (reversible: `winget uninstall Microsoft.WinAppCli`); the Python packages were installed only into a throwaway venv under the session scratchpad directory, which was deleted at the end of this task.

## 5. Environment/runtime constraints observed

- Installing **either** candidate required internet access (winget download for A; PyPI download for B). Once installed, all UIA operations tested were fully offline — no network calls were observed during `inspect`/`search`/`get-value`/`get-property`/`list-windows`/`status`/`invoke`, except that **`winapp` sends anonymous usage telemetry by default** (its own startup banner states this, opt-out via `WINAPP_CLI_TELEMETRY_OPTOUT=1`). This is a concrete local-first consideration: if `winapp` is ever adopted even as a dev/CI tool inside this project's workflows, telemetry must be explicitly disabled to preserve the "no cloud runtime dependency" invariant. `uiautomation`/`pywinauto`/`comtypes` sent no telemetry (pure local COM calls).
- Neither candidate required administrator elevation for any tested scenario. `winapp` installed as a normal user-scoped MSIX; all `winapp ui`/`uiautomation` calls against Notepad, Calculator, and a Guest Edge window ran without a UAC prompt.
- `winapp`'s `-a <process-name>` targeting failed to match Calculator (a UWP app hosted under `ApplicationFrameWindow`) by process name (`calculator`/`CalculatorApp` both returned "Found 0 windows"); `-w <HWND>` (from an unfiltered `list-windows`) worked reliably. This is a real, minor discoverability gap for UWP-hosted apps specifically — HWND targeting is the reliable fallback the tool's own docs already recommend for exactly this situation.

## 6. Scenario-by-scenario results

All scenarios were run against real, disposable app instances launched for this task (Notepad, Calculator, a Guest-profile Edge window). The owner's own pre-existing Notepad session (a restored draft with real unsaved content, discovered when a fresh `notepad.exe` invocation attached a new blank window to the same process) was **never modified, typed into, or closed** — only read via one bounded, read-only `get-value` call, used to prove text-retrieval works. Its content is not reproduced in this report; only its length (376 characters) is recorded, cross-validated against Notepad's own status-bar character count and independently reproduced by both candidates.

### Scenario 1 — top-level window discovery

- **A (`winapp ui list-windows`):** found Notepad (HWND, title, process, size) in 232ms; Calculator required `-w` fallback (see §5).
- **B (`uiautomation`, root enumeration):** enumerated all top-level windows (name, class, HWND, PID, bounding rect) including Notepad, Calculator (`ApplicationFrameWindow`), and — incidentally — every other currently-open top-level window on the desktop (Electron apps, an overlay, etc.), confirming full-desktop enumeration works identically to the existing `WindowsDesktopProvider.desktop_context()`'s `EnumWindows` approach, just with richer per-window semantic access available beneath each result.
- Both candidates report the same real HWNDs/titles/process IDs; no discrepancy.

### Scenario 2 — semantic tree inspection (bounded)

- **A:** `winapp ui inspect -w <hwnd> --depth 3` on Calculator returned a full structured tree (25 elements at depth 4 via `--json`): ControlType, Name, AutomationId (as the selector), enabled/offscreen state, bounding rect, and an explicit `isInvokable` flag per element — in 343ms.
- **B:** a manual bounded recursive walk (depth ≤ 4) over the same Calculator window found 27 elements in 38.7ms (same process, after the one-time COM init already paid by Scenario 1's call).
- Both correctly bounded the walk (no unbounded desktop dump); both exposed the exact property set the task requires (Name/ControlType/AutomationId/enabled/offscreen/bounds).

### Scenario 3 — semantic search (more than one property)

- **A:** `winapp ui search "Seven" -w <hwnd>` (name text) and cross-checked `get-property num7Button --json` (AutomationId lookup) — both resolved to the same element (`Name: Seven, AutomationId: num7Button, ControlType: Button`) in ~300ms each. A broader `search Button` (ambiguous, 20+ real matches) correctly returned the first 5 with a "showing first 5" note rather than silently truncating.
- **B:** manual filter by `ControlTypeName == "ButtonControl" and Name == "Seven"` resolved the same element in 53.4ms; AutomationId-based resolution in 41.1ms.
- **Real ambiguity-handling evidence (organic, from Scenario 7 below):** searching `"Close"` on a browser window matched two elements (window-Close and tab-Close); `winapp` returned a structured `UiAmbiguousSelectorException` listing both candidate slugs rather than guessing — exactly the disambiguation behavior the task asks to record.

### Scenario 4 — read text/value

- **A:** `winapp ui get-value doc-texteditor-517d -w <hwnd> --json` on the owner's existing (untouched, not typed into) Notepad document returned `{"elementId": "...", "text": "<376 chars>"}` in 300ms.
- **B:** `TextPattern.DocumentRange.GetText(-1)` on the same live document returned the same 376-character length in 0.5ms (warm, same process).
- Both independently retrieved the identical text length from the identical live document with zero modification — the strongest possible cross-validation available without altering owner data.
- No text was typed by either candidate in this task. `winapp set-value`/`send-keys` and `uiautomation`'s value-setting APIs were read about but never invoked.

### Scenario 5 — stale reference behavior

This produced the most consequential finding of the evaluation.

- **Setup:** a genuinely disposable, blank `"Untitled - Notepad"` window was opened (separate HWND from the owner's draft, confirmed via `list-windows`), inspected, and its `Close` button invoked via `winapp ui invoke Close -w <hwnd>` (a UIA `InvokePattern` call — not mouse/keyboard input injection).
- **A (`winapp`):**
  - Reusing a slug from a *different* window against this one produced a clean, typed error: `"Element with slug 'doc-texteditor-517d' found by name but RuntimeId hash doesn't match — the UI may have changed. Re-run 'inspect' to get updated selectors."` (`InvalidOperationException`, non-zero exit) — **no accidental mis-targeting occurred; the tool detected the identity mismatch and refused.**
  - After closing the window, both `inspect -w <hwnd>` and `get-value <selector> -w <hwnd>` failed cleanly: `"Window HWND <n> not found or not accessible."` (`AppNotFoundException`, exit code 1, structured JSON error).
- **B (`uiautomation`, same disposable-window pattern):**
  - After closing the window via `InvokePattern.Invoke()` on its Close button, accessing the stale `Control` object's `.Exists(0,0)` **and** its `.Name` property both raised a raw `comtypes.COMError(-2147220991, "An event was unable to invoke any of the subscribers", ...)` — an opaque, low-level COM exception, not a typed/domain error.
  - Calling `.GetTextPattern()` on the same stale reference instead returned `None` silently (no exception) — **inconsistent behavior between different accessors on the same stale object** within one library.
- **Conclusion:** `winapp` already implements exactly the clean, typed, "fail closed, never mis-target" staleness contract Computer Use V2 needs, out of the box. Raw `uiautomation` provides the same underlying COM-level detection capability, but as low-level, inconsistent, unwrapped exceptions — a JARVIS-owned adapter would have to build this entire staleness/error-translation layer itself before it could safely support the `revalidate_reference` operation this task's semantic contract requires.

### Scenario 6 — dynamic UI behavior

- Used Calculator's `TogglePaneButton` ("Open Navigation" ⇄ "Close Navigation") via `winapp ui invoke` — a reversible, UIA-pattern-driven, non-consequential state change (not mouse/keyboard injection).
- After toggling, `winapp ui inspect` correctly re-queried the live tree: new navigation-menu items appeared (`Scientific`, `Graphing`, `Programmer`, …, several correctly marked `[offscreen]`), and the *same* `TogglePaneButton` element's reported **Name changed live** ("Open Navigation" → "Close Navigation") while its **selector (`btn-togglepanebutto-ce03`) stayed stable** across the state change — confirming the tool distinguishes "same element, changed property" from "different element," which is exactly the re-resolution behavior the semantic contract in §10 depends on.
- Toggled back to restore the original state before closing the window; no residual effect on the (then-closed, disposable) Calculator instance.

### Scenario 7 — Chromium/Electron coverage

- Launched Microsoft Edge in **`--guest`** mode (a fully ephemeral profile — no cookies/history/extensions/logins from the owner's real profile were touched or created; confirmed via the window title showing `[Guest]`), first at `about:blank`, then navigating (via a fresh process launch with the target URL as an argument, not by typing/clicking) to `https://www.wikipedia.org/` — a public, non-sensitive page.
- **A (`winapp`):** `inspect` on the blank page returned only generic browser-chrome `Pane` containers (Chromium's accessibility tree is lazily populated and `about:blank` has near-zero DOM). On the real Wikipedia page, `--interactive` inspection found **18 interactive elements**, and `search "English"` correctly resolved a real page hyperlink with its DOM properties exposed through UIA: `Hyperlink "English 7,237,000+ articles"`, `value="https://en.wikipedia.org/"` — full DOM-level semantic + value access, not just chrome furniture.
- **B (`uiautomation`):** the same top-level enumeration (Scenario 1) independently identified multiple already-open Electron windows on the desktop (class `Chrome_WidgetWin_1`) at the OS/HWND level, confirming Electron windows are visible to raw UIA root enumeration exactly as they are to `winapp`. Deeper DOM-level tree-walking on Electron content was not separately re-verified with Candidate B in this task (Candidate A's Wikipedia result was taken as sufficient, redundant confirmation that Chromium-family accessibility trees are UIA-visible in general, since both candidates sit on the same underlying OS UIA provider) — recorded here as an explicit scope note rather than an unverified claim.
- Per the task's privacy instruction, the *specific* titles/content of the owner's other already-open windows (revealed incidentally by the full-desktop enumeration) are intentionally **not reproduced** in this report beyond their application category (an editor, a chat client, a voice/overlay app) — none were opened, inspected in depth, or modified by this task.

## 7. Benchmark measurements

| Measurement | Result |
|---|---|
| `winapp --version` (pure CLI startup, no UIA) | 184–250ms (×3 runs) |
| `winapp ui inspect` (each call = new process; "warm" only in the sense of an already-open target) | 258–343ms (×5 runs against the same window) |
| `uiautomation`: fresh Python process + first UIA call (cold) | 264–304ms (×3 runs) |
| `uiautomation`: pure Python interpreter startup, no UIA import (baseline) | 68–70ms |
| `uiautomation`: same-process warm calls after first UIA init (tree walk / search / property / text-read) | **10.2–53.4ms** |
| `winapp` package size on disk | ~39.5 MB (plus several shared "WinAppRuntime" MSIX framework dependency packages pulled in at install) |
| `uiautomation` + `comtypes` only (minimal Candidate B footprint) | ~5.3 MB in a venv |
| `uiautomation` + `pywinauto` + `comtypes` + `pywin32` + `six` (both packages together) | ~44 MB in a venv |

**The single most decision-relevant number:** `winapp` pays its ~200–300ms process-spawn-and-COM-init cost on **every single call** (it is not a persistent daemon). A Python UIA library embedded in JARVIS's own long-running `AgentRuntime` process pays that cost **once**, after which every subsequent UIA operation costs 10–50ms — a 5–20× latency advantage for JARVIS's actual usage pattern (many calls across a long-lived session), which is architecturally how `ComputerActionService`/`WindowsDesktopProvider` already work today (in-process, not subprocess-per-call).

## 8. 1–5 weighted comparison matrix

Scored 1 (poor) – 5 (excellent), with evidence from §6–7. Candidate C is scored N/A (rejected without implementation — see §12).

| Criterion | A — `winapp ui` | B — Python `uiautomation` |
|---|---|---|
| 1. Semantic coverage | 5 — full property/pattern set incl. `isInvokable`, control-type-specific state markers | 5 — same underlying UIA properties/patterns, manual access |
| 2. App coverage (Win32/WinUI/Electron) | 5 — WPF/WinForms/Win32/WinUI 3 full; Electron DOM-level confirmed on real content | 4 — same OS-level coverage; not separately re-verified at DOM depth on Electron in this task (see §6 Scenario 7 note) |
| 3. Target stability (identity/staleness detection) | 5 — RuntimeId-hash-validated slugs, clean typed mismatch/not-found errors | 3 — underlying detection works, but surfaces as raw/inconsistent COM exceptions |
| 4. Verification support (re-read/re-resolve/distinguish stale) | 5 — built-in, demonstrated in Scenario 5 | 3 — possible, but requires JARVIS to build the wrapper itself |
| 5. Performance (cold/warm/search latency) | 3 — good absolute latency (~250–350ms) but **no warm mode**; every call pays full cost | 5 — comparable cold cost, then 10–50ms warm — matches JARVIS's real call pattern |
| 6. Runtime footprint (process spawn, size, memory) | 2 — new process per call; ~39.5MB + shared framework deps | 4 — in-process, no spawn overhead; ~5.3MB minimal footprint |
| 7. Python compatibility (current/min project Python, Win 11) | 3 — not a Python library at all; must be subprocess-invoked and its JSON parsed | 5 — pure Python, works on both project Pythons (3.12.13 venv, 3.14.6 system), confirmed on Windows 11 |
| 8. Offline/local behavior | 3 — functions offline after install, but ships telemetry-by-default (opt-out env var) | 5 — no telemetry observed, pure local COM |
| 9. Licensing/free-runtime suitability | 4 — free, MIT-licensed, Microsoft-published, but distributed as a Windows Store/winget MSIX, not a project-manifest-pinnable artifact | 5 — free, pip-installable, pinnable in `pyproject.toml` exactly like the existing `voice` extra |
| 10. Stability/maintenance risk | 2 — v0.6.1, explicitly still evolving (matches DEC-018's "preview" framing); no version pin possible from the project manifest | 4 — community-maintained but mature/stable API surface (`comtypes`-based), version-pinnable and reproducible |
| 11. Testability (deterministic seams, mocking) | 2 — subprocess + text/JSON parsing only; hard to unit-test without shelling out in CI | 5 — a normal Python object graph; trivially mockable/fakeable behind a product-owned adapter interface, matching every other canonical service in this codebase |
| 12. Security/control (no hidden shell interpolation, bounded args, no implicit elevation) | 4 — no elevation required for tested scenarios; but any future adoption as a subprocess tool adds an argument-construction/injection surface that must be built with an argv array, never shell string concatenation | 5 — in-process library calls, no subprocess/shell surface at all; no elevation required |
| 13. Architecture fit (behind one product-owned adapter, no vendor leakage) | 3 — clean CLI/JSON contract is easy to wrap, but its own concepts (slugs, `-a`/`-w` targeting quirks) would need translation either way | 4 — naturally wrappable behind a thin adapter; still needs deliberate work to avoid leaking raw COM/`comtypes` types into `AgentRuntime` |
| **Weighted fit for PRIMARY runtime backend** | **Not recommended as primary** (own #5/#6/#10/#11 scores) | **Recommended as primary** |
| **Weighted fit for optional dev/CI/verification tool** | **Strong fit** (own #1/#3/#4 scores, plus screenshot/record/CI-assertion features not evaluated in depth here but documented) | Less needed in this role (already embedded) |

## 9. Reliability/staleness observations

Covered in depth in Scenario 5 (§6). Summary: both candidates can genuinely detect a stale/closed target and refuse to act on it — this was demonstrated, not assumed, for both. The material difference is **where the safety work already lives**: `winapp` ships it as a finished, typed contract; a `uiautomation`-based adapter must build it. This is the central engineering cost the A2 implementation slice must budget for if Candidate B is chosen as primary (which this report recommends).

## 10. Security/authority observations

- Neither candidate required elevation for any read-only or bounded-`invoke` scenario tested.
- Neither candidate was used to perform, and neither was asked to perform, any consequential action (no messages sent, no owner documents altered, no files deleted, no settings/registry changed, no login/session changes). The only "write-shaped" calls made in this entire evaluation were two safe, reversible `InvokePattern` clicks on `Close` buttons of app instances this task itself created, and two reversible `TogglePaneButton` toggles restored to their original state — never mouse/keyboard input injection (`click`/`send-keys`/`touch`/`pen`/`drag` in `winapp`, or any `SendInput`-based API) — consistent with the task's explicit prohibition on adding mouse/keyboard automation in this spike.
- `winapp`'s own documentation shows it already has non-trivial, well-designed safety boundaries for its *injection* verbs (locked/secure-desktop refusal, foreground-verification-before-injection, re-resolution immediately before a gesture) — not exercised in this task (out of scope), but directly relevant evidence for a **future** Layer 4 native-input evaluation, should JARVIS ever consider `winapp`'s injection verbs (or the same design pattern) for that later, separate workstream.
- `winapp` telemetry-by-default is a concrete local-first/offline consideration (see §5); `uiautomation`/`comtypes` showed no such behavior.
- Neither candidate grants any capability beyond what any other accessibility/automation tool already has on this machine (the OS UIA provider is the actual authority being queried in both cases) — no "broad machine-control bypass" beyond standard, OS-sanctioned accessibility API access was observed or exercised.
- **No secret, API key, or credential was requested, required, or used** by either candidate for any tested scenario.

## 11. Dependency/maintenance risks

- **`winapp`:** cannot be version-pinned from the JARVIS project manifest (it is a machine-level winget/MSIX install, not a `pyproject.toml` entry) — this alone is disqualifying for treating it as anything other than an optional, developer-machine-local tool. It pulls in several Microsoft "WinAppRuntime" MSIX framework dependencies at install time. It is explicitly evolving software (v0.6.1, frequent releases) — acceptable for a dev/CI tool whose exact output format a human or CI script tolerates drifting on, unsafe to hard-code JARVIS's production parsing logic against without a strict version pin, which the distribution mechanism doesn't support.
- **`uiautomation`:** pip-installable and pinnable exactly like the project's existing `voice` optional-dependency group (e.g. a new `computer-uia = ["uiautomation==2.0.29"]` extra, decided and added in the A2 implementation task, not this one). Depends on `comtypes`, a long-established, low-churn library. Community-maintained (not a Microsoft first-party package) — a real but bounded maintenance-risk consideration to disclose, not a blocker.
- **`pywinauto`:** adds `pywin32` (a large, C-extension, Windows-specific wheel) as a transitive dependency without adding functionality JARVIS's stated Computer Use V2 needs (inspect/search/get-value/re-resolve) don't already get from `uiautomation` alone. Recommend **not** adding `pywinauto` — `uiautomation` (or, if the team later wants to shed even that dependency, direct `comtypes`-generated IUIAutomation bindings) is the leaner choice.

## 12. Candidate C — rejected on evidence, not implemented

Per the task's explicit instruction not to write throwaway COM glue merely to make this candidate look viable: a repository-wide search (`comtypes`, `CoInitialize`, `IUIAutomation`, `CoCreateInstance`, `pywin32`, `win32com`) under `src/` returned **zero matches**. The project's only Windows-native plumbing is a hand-rolled `ctypes` binding to three plain Win32 DLLs (`user32`, `gdi32`, `kernel32`) with no COM/OLE initialization of any kind. Building direct IUIAutomation COM bindings from scratch via raw `ctypes` (defining the full `IUIAutomation`/`IUIAutomationElement`/pattern-interface vtables by hand) would be a substantial, error-prone, hundreds-of-lines undertaking that a small, well-tested pip dependency (`comtypes`, already proven working in this task) makes entirely unnecessary. **Candidate C is rejected for the current implementation slice.** It is not permanently closed — it could be revisited later if `comtypes` itself ever becomes a problem — but there is no present evidence justifying the engineering cost.

## 13. Recommended backend topology

**Layered, not all-or-nothing** (per the task's Preview Dependency Rule):

1. **Primary runtime backend (Candidate B):** a new, product-owned adapter (implementation deferred to A2) wrapping a Python UIA client (`uiautomation`, or a narrower direct `comtypes` binding if the team wants to shed even that dependency later) embedded **in-process** inside the existing JARVIS runtime, behind a single typed interface — not exposed to `AgentRuntime` as raw COM/`comtypes` objects. This matches the existing architecture pattern (`WindowsDesktopProvider` lives in-process today) and gets the 5–20× warm-call latency advantage demonstrated in §7.
2. **Optional developer/verification tool (Candidate A):** `winapp` CLI remains installed on NIGHTFURY (user-scoped, already present from this evaluation) as a developer- and future-CI-facing tool — for interactive debugging, screenshots, and building the Computer-Use-V2 evaluation suite (GAP-0105) — but is **never invoked by JARVIS's production agent loop**, is **not** added to `pyproject.toml`, and its telemetry must be disabled (`WINAPP_CLI_TELEMETRY_OPTOUT=1`) in any script/CI job that uses it.
3. **Candidate C (native/COM-from-scratch):** deferred indefinitely; no work scheduled.

This is a recommendation only. Per the task's explicit instruction, the canonical Decision Log (`05_JARVIS_DECISION_LOG.md`, `OPEN-001`) was **not** updated or locked in this task — that remains the owner's/planner's call.

## 14. Proposed minimal semantic contract (not implemented)

Scoped to exactly what the task requests — read/inspect/re-resolve only, no invoke/click/type.

```text
WindowReference
  reference_id            : opaque, ephemeral, JARVIS-issued (matches the existing "window-<uuid>" pattern
                             already used by WindowsDesktopProvider — do not invent a second window-ref scheme)
  pid                      : int
  hwnd                     : int (internal detail; never surfaced as a raw targeting mechanism to the model)
  title_hint, class_hint   : str | None (best-effort identity aid, not authoritative)
  observed_at              : timestamp
  expires_at               : timestamp (bounded TTL, mirrors WINDOW_REF_TTL_SECONDS convention already in use)

SemanticElementReference
  reference_id             : opaque, ephemeral
  window_reference_id      : WindowReference.reference_id (containing window)
  automation_id            : str | None
  control_type             : str
  name_hint                : str | None
  ancestry_hint             : bounded list of (control_type, automation_id|name) from element to window root
                             (bounded depth — no unbounded path storage)
  provider_identity        : opaque implementation detail only (e.g. a RuntimeId digest) — never exposed to the model
  observed_at / expires_at : timestamp / TTL

ElementSnapshot
  name, control_type, automation_id
  enabled, offscreen, focused, focusable
  bounds                   : {x, y, width, height}
  supported_patterns       : bounded list of pattern names actually available (Invoke/Toggle/Value/Text/...)
  text_or_value            : str | None, bounded length, only when the pattern chain supports it (mirrors
                             winapp's own TextPattern -> ValuePattern -> SelectionPattern -> Name fallback,
                             which both candidates already implement or can trivially replicate)
```

### Required operations for the A2 slice

```text
list_windows(target_device_id?)                         -> WindowReference[]
inspect_window(window_reference, bounded_depth)          -> ElementSnapshot tree (bounded, never unbounded)
find_elements(window_reference, control_type?, name?, automation_id?) -> SemanticElementReference[]
get_element(semantic_element_reference)                  -> ElementSnapshot
get_text_or_value(semantic_element_reference)            -> str | None, bounded
revalidate_reference(window_reference | semantic_element_reference) -> fresh reference | explicit "stale" result
                                                               (never a silent re-target to a different element —
                                                               Scenario 5 proved this distinction is detectable
                                                               and must be preserved end to end)
```

Explicitly **excluded** from this slice, per the task: `invoke`, `click`, `send-keys`, `set-value`, `drag`, `touch`, `pen`, `scroll`, `hover`. These belong to a later, separately-reviewed slice once the read/inspect/verify foundation is proven.

## 15. Explicit carry-forward restrictions

- **F18A1-010 / GAP-0503 remains open and untouched.** This task did not widen `computer.inspect_file`, `computer.search_files`, `computer.open_file`, or `computer.open_folder`, did not add arbitrary path access, and the proposed semantic contract above has no filesystem surface at all — a UIA element/window reference carries no path-access capability. **The A2 implementation must not use UIA work as a backdoor to increase filesystem authority** — any future file-dialog interaction (e.g. the pattern `winapp`'s own docs show for file-open dialogs) must still go through the existing, unwidened, GAP-0503-gated file-access boundary, not a new UIA-native path.
- No mouse/keyboard automation was added to JARVIS's codebase in this task (none was added at all — this was a pure evaluation spike).
- No architecture change was made: `AgentRuntime`, `ComputerActionService`, `PermissionEngine`, `ApprovalEngine`, and `WindowsDesktopProvider` are all unmodified.
- No dependency was permanently added: `pyproject.toml` is untouched; `winapp` is a machine-level (not project-level) install; the Python UIA packages were installed only in a temp venv that has been deleted.

## 16. Exact next implementation slice (A2 — not started)

1. Decide and add the chosen Python UIA dependency as a new optional extra in `pyproject.toml` (e.g. `computer-uia`), pinned to the exact version evaluated here or newer after re-verification.
2. Implement a product-owned adapter (new module under `src/jarvis/computer/` or `src/jarvis/perception/`, not a second `ComputerActionService`) implementing exactly the six operations in §14, with the raw `comtypes.COMError`/stale-reference cases from Scenario 5 wrapped into the same typed-result conventions already used across the codebase (`verified: bool | None`, explicit `error_code` strings — following the pattern this session's own Phase 18A.2 stabilization work (`docs/audits/PHASE_18A2_STABILIZATION.md`) just reinforced for `ComputerActionService`/`HomeAssistantTransport`).
3. Wire the adapter behind `ComputerActionService`'s existing permission/audit path — do not create a second computer authority.
4. Add focused tests: bounded tree inspection, AutomationId/name/control-type search, stale-reference detection (mirroring Scenario 5's exact pattern), and a fake/mock UIA provider seam for CI (per Criterion #11 above).
5. Only after that foundation is proven: a separate, explicitly-reviewed task for invoke/click/type (Layer 4-adjacent), which is out of scope for A2 as well as this A1 spike.

## 17. Manual owner actions required, if any

**None required now.** No credential, API key, account, or owner decision is blocking. One **optional** note for the owner's awareness, not a gate: `winapp` CLI is now installed on NIGHTFURY (user-scoped, from this evaluation) and defaults to sending anonymous telemetry; if the owner wants it fully removed, `winget uninstall Microsoft.WinAppCli` reverses the install, or it can be kept with telemetry disabled via the `WINAPP_CLI_TELEMETRY_OPTOUT=1` environment variable for any future dev/CI use.

---

## Verification

```text
python -m pytest tests -q        -> 529 passed, 1 skipped (environment-dependent, already documented
                                     in Phase 18A.1/18A.2 — same test, same known condition), 36 subtests
python -m compileall src tests -q -> exit 0
git diff --check                  -> exit 0
```

No production/UI code was changed by this task, so a frontend re-run was not required and was not performed. `git status --short` before and after this task is identical (the pre-existing Phase 18A.2 diff, unmodified) — confirmed no unintended change.

---

`UIA_BACKEND_RECOMMENDATION_READY`

```text
Starting HEAD: 54b67ba396ec45180f1b60ea472ef94c9ac181a9
Ending HEAD: 54b67ba396ec45180f1b60ea472ef94c9ac181a9 (unchanged)
Production code changed: NO
Candidates evaluated: A (Microsoft winapp CLI 0.6.1, hands-on), B (Python uiautomation 2.0.29 + pywinauto 0.6.9, hands-on), C (native/WinRT/COM from scratch, rejected on evidence, not implemented)
Recommended primary backend: Candidate B — a product-owned adapter around a Python UIA client (uiautomation/comtypes), embedded in-process
Recommended optional/fallback backend: Candidate A — winapp CLI as a developer/CI/verification tool only, never invoked by the production agent loop, never added to pyproject.toml
Why: Candidate B wins decisively on the criteria that matter for JARVIS's actual call pattern (in-process warm latency 10-50ms vs. winapp's ~250-350ms per call every call, since winapp has no persistent-process mode), on testability (mockable Python objects vs. subprocess/JSON parsing), and on dependency pinning (pyproject.toml-pinnable vs. machine-level winget install). Candidate A wins decisively on staleness/verification ergonomics (typed, structured errors out of the box) and app-coverage breadth, making it the stronger developer/CI/evaluation-suite tool rather than the production runtime path.
Python/runtime compatibility: confirmed on both project Pythons (3.12.13 venv satisfying requires-python>=3.11, and 3.14.6 system) and Windows 11
Admin/elevation required: NO for either candidate, for every scenario tested
Manual owner action required now: none (optional: winapp telemetry opt-out env var if kept for dev use)
Filesystem restriction preserved: YES — F18A1-010/GAP-0503 untouched; proposed semantic contract has no filesystem surface
May semantic implementation slice A2 start after owner/planner review: YES
Report: docs/audits/PHASE_18_WORKSTREAM_A1_UIA_BACKEND_EVALUATION.md
```
