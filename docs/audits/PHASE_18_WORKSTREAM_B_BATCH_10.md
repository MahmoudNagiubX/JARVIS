# Phase 18 Workstream B - Batch 10 Audit

**Status:** T0 PASS; T1 PASS; T2 PARTIAL; T3-T6 not started
**Verdict:** `PHASE18_BROWSER_V2_BATCH10_PARTIAL` pending implementation and
live owner-session evidence.

**Repository:** `MahmoudNagiubX/JARVIS`
**Starting source branch:** `feature/phase-18-computer-use-v2`
**Starting source HEAD:** `31b0185b9d5793cbbe8a306a459a861cbfc102b7`
**Workstream branch:** `feature/phase-18-browser-v2`
**Workstream branch HEAD after creation:** `31b0185b9d5793cbbe8a306a459a861cbfc102b7`
**Origin main:** `54b67ba396ec45180f1b60ea472ef94c9ac181a9`

## 1. Scope and locked boundaries

Batch 10 implements Browser V2 behind the existing `BrowserActionService`.
The browser controller/provider is subordinate execution and observation code;
it is not a second browser authority. Existing identity/device, permission,
approval, audit, event, tool, and research authorities remain canonical.

The following locked decisions are in scope and preserved:

- DEC-003: one logical authority per domain;
- DEC-009/010: browser content is untrusted data and cannot become authority or
  durable owner Memory automatically;
- DEC-012: all browser side effects use permission/approval/audit;
- DEC-021/022: Playwright is the primary live backend and Selenium is not;
- DEC-023/024: browser and research remain separate, with static-first layered
  extraction;
- DEC-030/034: secrets, cookies, tokens, credentials, and raw screenshots are
  not model-visible or durable by default.

No `BrowserActionServiceV2`, browser-owned approval/permission authority,
arbitrary model JavaScript/CDP, normal Brave profile attachment, credential
automation, broad process kill, or hidden browser download is permitted.

## 2. T0 bootstrap and current-browser review

### Preflight

The supplied source preflight matched exactly:

| Check | Result |
|---|---|
| source branch | `feature/phase-18-computer-use-v2` |
| source HEAD | `31b0185b9d5793cbbe8a306a459a861cbfc102b7` |
| origin source branch | `31b0185b9d5793cbbe8a306a459a861cbfc102b7` |
| origin/main | `54b67ba396ec45180f1b60ea472ef94c9ac181a9` |
| source worktree | clean |

The new `feature/phase-18-browser-v2` branch was created without switching or
altering the Workstream A branch.

### Existing implementation truth

Inspected current HEAD files and tests:

- `src/jarvis/browser/service.py`
- `src/jarvis/browser/policy.py`
- `src/jarvis/contracts/browser.py`
- `src/jarvis/tools/registry.py`
- `src/jarvis/authority/permissions/engine.py`
- `src/jarvis/authority/approvals/service.py`
- `src/jarvis/authority/audit/service.py`
- `src/jarvis/tools/service.py`
- `src/jarvis/bootstrap.py`
- `src/jarvis/config.py`
- `src/jarvis/computer/file_access.py`
- `docs/architecture/BROWSER_AUTOMATION.md`
- Phase 15 browser/security and integration tests
- `docs/audits/PHASE_18_WORKSTREAM_A_BATCH_09.md`

Current browser truth:

| Component | T0 finding |
|---|---|
| `LocalBrowserController` | bounded urllib/HTML parser sessions with existing URL/redirect policy; static reads and deterministic interaction simulation |
| `PlaywrightBrowserController` | thin injected-executor seam only; no live Playwright runtime |
| `BrowserActionService` | existing permission, approval, audit, event, and pending-approval authority |
| bootstrap | wires only `LocalBrowserController` into `BrowserActionService` |
| model-facing tools | bounded browser open/navigate/read/find/accessibility/tabs/click/type/select schemas; no model-facing JS/CDP |
| uploads/downloads/screenshots | current local controller returns `browser_action_requires_configured_adapter` |
| URL policy | existing single `BrowserURLPolicy`, including scheme/userinfo/private/loopback/DNS/redirect checks |

### Batch 09 carry-forward

Batch 09 `RW-BRAVE-001` correctly stopped at the host-only boundary after
fail-closed `brave_window_ambiguous` results. Browser navigation and
authenticated web control are the `GAP-0201` cross-workstream blocker. Batch
10 owns a dedicated browser process/context/page identity and must not solve
that blocker by selecting or attaching to an existing Brave window.

## 3. T0 baseline evidence

Environment:

| Check | Result |
|---|---|
| Python | `3.14.6` |
| Playwright in current interpreter | absent; no import or package metadata |
| `python -m pytest tests -q` | `903 passed, 3 skipped, 41 subtests passed` in `489.82s` |
| skipped tests | EasyOCR, torch, torchvision optional interpreter dependencies |
| `python -m compileall src tests scripts -q` | PASS |
| `git diff --check` | PASS |

The baseline ran on the clean Workstream-B branch before Batch 10 production
changes. No browser binary was downloaded by the baseline.

## 4. Rechecked Brave environment evidence

Safe inspection was limited to the three standard installation locations from
the Batch 10 specification. An existing binary was found at:

`C:\Users\mahmo\AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe`

This is local environment evidence, not a universal allowlist. Current
provenance:

| Property | Observed value |
|---|---|
| version | `153.1.95.101` |
| company/publisher | `Brave Software, Inc.` |
| Authenticode | `Valid` |
| signer | `CN="Brave Software, Inc.", O="Brave Software, Inc.", L=San Francisco, S=California, C=US` |
| issuer | `CN=DigiCert Trusted G4 Code Signing RSA4096 SHA384 2021 CA1, O="DigiCert, Inc.", C=US` |
| SHA-256 | `BDA9ED87B3A04D9C474768B66660681BF1D9E9D6CE03D53D98909FAB9B5CC624` |

No installer, recursive search, machine-wide scan, normal profile inspection,
or Brave process/window mutation was performed by T0.

## 5. Ordered task table

| Gate | Scope | T0 disposition |
|---|---|---|
| T0 | Workstream-B bootstrap, current browser review, baseline | PASS |
| T1 | optional Playwright dependency evaluation and real controller foundation | PASS |
| T2 | ephemeral/dedicated persistent profile policy | PARTIAL - policy seam and tests pass; physical persistent restart pending |
| T3 | DOM/accessibility grounding and approval-bound actions | NOT STARTED |
| T4 | layered extraction and provenance | NOT STARTED |
| T5 | bounded upload/download/screenshot workflows | NOT STARTED |
| T6 | security red team and owner-authenticated foundation | NOT STARTED |

## 6. Open gaps at T0

- GAP-0201: live Playwright action adapter is not active in the default runtime.
- GAP-0202: bounded browser upload/download workflows are missing.
- GAP-0203: production dynamic extraction and the approved layered parser path
  are incomplete.
- GAP-0204: live browser hostile-page and prompt-injection matrix is incomplete.
- GAP-0205: ephemeral versus dedicated owner-persistent browser session policy
  has an implementation seam and tests, but its physical restart evidence is
  still pending.

## 7. T1/T2 implementation evidence

### T1 - optional real Playwright controller

T1 is PASS for the implementation and dependency foundation:

- `pyproject.toml` declares only the optional `browser-playwright` extra with
  `playwright==1.62.0`; base dependencies remain empty.
- `PlaywrightBrowserController` lazily imports `playwright.async_api`, launches
  only through the existing `BrowserActionService` seam, and normalizes missing
  adapters/provider failures to bounded error codes.
- Launch uses the exact configured Brave executable and no model-controlled
  flags, CDP attachment, or browser download/install step.
- `close()` owns and closes only contexts/browsers created by the controller,
  then stops the Playwright runtime; no broad process termination is used.
- Focused foundation evidence: `12 passed, 2 subtests passed` in
  `tests/test_phase_eighteen_browser_v2.py`; existing browser integration and
  security suites: `30 passed, 11 subtests passed`.
- Disposable dependency evaluation recorded Playwright `1.62.0`, Apache-2.0,
  PyPI install, no `playwright install`, and a clean headless launch of the
  verified Brave executable (`launch=PASS`, `contexts=1`, `pages=1`,
  `url=about:blank`), with no remaining Brave process.

### T2 - session/profile policy foundation

T2 currently has a PARTIAL implementation status pending the physical profile
restart gate. `BrowserSessionMode` contains only product-owned `EPHEMERAL` and
`OWNER_PERSISTENT` modes. The default is ephemeral; owner-persistent mode
requires explicit local opt-in and resolves a dedicated JARVIS profile path.
Known Brave, Chrome, and Edge `User Data` profile paths are rejected, and no
profile path or mode is present in model-facing browser schemas. The remaining
evidence is an actual dedicated-profile launch, clean close, and controlled
reopen without touching the normal Brave profile.

## 8. T0/T1 checkpoint

T0 audit-only checkpoint is intended to be committed as:

`docs: start phase 18 browser v2 workstream`

T2-T6 evidence, commit chain, dependency audit, security counters, physical
receipts, source-of-truth updates, limitations, and final remote verification
will be appended here as each gate completes. No Batch 11 work is in scope.
