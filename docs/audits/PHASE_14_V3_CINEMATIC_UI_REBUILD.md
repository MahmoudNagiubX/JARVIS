# Phase 14 V3 cinematic UI rebuild audit

Date: 2026-09-01
Repository: `C:\Jarivs\00_final\jarvis`
Starting commit: `9e70357a62d33b4709d901fac359e49e0f16f4d9`
Owner wallpaper: `ui/src/assets/hero/ironman-owner-wallpaper.jpg`

## Scope and authority

V3 is a bounded presentation rebuild over the existing React router, API
client, session context, event stream, backend projections, and desktop
lifecycle. It adds product-owned cinematic, holographic, and tactical visual
components and a pure `deriveVisualState()` adapter. It does not add a
scheduler, EventBus, VoiceCore, browser runtime, persistence store, WebGL loop,
cloud dependency, SQL cleanup, or second API/state authority.

The supplied wallpaper is local and tracked. No remote assets, fonts, icons,
donor runtimes, mock telemetry, or credentials were added. Exact donor source
paths and exclusions are recorded in
`docs/phase14/v3/DONOR_SOURCE_EXTRACTION.md`; the visual decision, system, and
before/after records are in `docs/phase14/v3/`.

## Baseline and final test evidence

Recorded V2 baseline before V3 work:

- frontend: 32 passed;
- Phase 14 Python regression: 17 passed;
- full repository Python suite: 370 passed, 25 subtests passed, 0 failures.

Final execution evidence:

- focused V3 UI closure: 5 files, 26 tests passed;
- V3 desktop handoff: 2 tests passed;
- full frontend suite: 12 files, 44 tests passed;
- Phase 14 regression including V3 coverage: 18 tests passed;
- existing Phase 13 desktop regression: 30 tests passed;
- full repository Python suite: 372 passed, 25 subtests passed, 0 failures;
- frontend production build: passed (`tsc -b && vite build`);
- embedded frontend build: passed (`python ui/build_frontend.py`);
- Python compile gate: passed (`python -m compileall src tests`);
- whitespace gate: passed (`git diff --check`);
- npm audit: passed, 0 vulnerabilities.

## Focused acceptance matrix

- visual state derivation: offline, approval priority, voice/tool/research/
  thinking, degraded, and error states;
- Home hero: local wallpaper, subtle reactor, removed V2 hero-reactor marker,
  runtime state, pulse network, owner context, mission and attention labels;
- shell: accessible navigation/context collapse controls;
- tactical field: idle empty state and exact real device point count, including
  counts above the starter coordinate set;
- reduced motion: explicit supported fallback marker and CSS media rule;
- existing route, chat, mission, approval, activity, research, settings,
  notification, session-renewal, and error-humanization tests remain green;
- desktop second launch: local app URL handoff, no second runtime, and
  non-loopback URL rejection.

## Asset and architecture checks

SHA-256 parity between `ui/dist` and `src/jarvis/ui_static` was true for
`index.html`, `styles.css`, `app.js`, and the owner wallpaper. A source scan
found no remote runtime asset references. The only UI WebSocket is the existing
canonical connection in `ui/src/app/App.tsx`; no new WebSocket, scheduler,
EventBus, VoiceCore, polling authority, or animation canvas was introduced.
The diff contains no SQL or cleanup migration.

## Desktop reopen repair

The acceptance test exposed a real existing bug: a duplicate launch returned
`already_running` and exited without reopening the current UI. The minimal fix
publishes only the local `/app` URL alongside the existing PID in the current
single-instance lock. A duplicate reads and validates that loopback URL, then
opens it without starting a runtime. No credential or bootstrap token is
written to the lock.

## Review limitations

The execution environment had no local Chrome, Edge, Firefox, Playwright, or
other browser executable available, so real rendered screenshot QA was not
claimed. The required screenshot set remains owner-review pending. Likewise,
Antigravity was not invoked because the active workspace policy permits
delegated coding only after an explicit user request to delegate; the exact
non-invocation record is `docs/phase14/v3/ANTIGRAVITY_DELEGATION_LOG.md`.

The code/build/test gates are complete; visual screenshot acceptance and owner
review remain explicitly pending rather than being represented as completed.
