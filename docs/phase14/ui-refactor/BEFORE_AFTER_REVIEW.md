# Phase 14 V2 before/after review

## Before

The prior Phase 14 implementation was functionally valid but visually read as
a generic dark admin dashboard: a small reactor, repeated cyan-outline cards,
small technical labels, a debug-like context rail, and a prominent red runtime
notice. The original donor map recorded 28 promising units, but only
`JHudFrame`, `JArcReactor`, and `JWaveform` had reached the frontend.

## After

- **Hierarchy:** Home now has a full-height hero command center with a central
  orb/reactor, readable owner/runtime copy, KPI trace, and a lower operational
  band. Supporting panels are secondary rather than equal tiles.
- **Donor visibility:** Matrix signal/foundation treatment, JARVIS HUD bar,
  framed surfaces, orb, activity feed, KPI ticker, command palette, mission
  pipeline, conversation rail, rich messages, run inbox, approvals, plans,
  progress, citations, tables, code, stats, and safe tool fallback are visible
  in the actual frontend. See the exact file-level record in the extraction
  manifest.
- **Wallpaper and palette:** the owner-supplied Iron Man image is used on Home
  as `ui/src/assets/hero/ironman-owner-wallpaper.jpg`; the global palette uses
  `#0C060E / #1E0C1D / #2F0A16`, restrained `#C40B2E / #EA2F42`, preserved
  `#55D9FF`, and `#96D8EE`.
- **Generic-dashboard removal:** the shell uses an atmospheric hero and
  selective HUD framing rather than identical cards everywhere. Activity,
  mission, research, device, and capability surfaces have distinct visual
  responsibilities.
- **Green reduction:** healthy states are cyan/ice/neutral; green no longer
  drives borders, badges, navigation, or reactor styling.
- **Error UX:** global recoverable errors now read “Local session needs
  attention” with calm amber/plum treatment; raw `principal_not_found` is not
  primary copy.
- **Typography:** body content uses the sans-serif system stack; mono is
  reserved for bounded metadata, identifiers, and technical traces.
- **State integrity:** all displayed mission, activity, capability, device,
  voice, health, approval, and research values still come from the existing
  JARVIS projection/API boundary.

## Evidence

- Focused V2 UI contracts: 14 passed.
- Full frontend suite after integration: 32 passed across 8 test files.
- Production build includes the local hero asset and completes successfully.
- Reduced-motion, responsive laptop, no-CDN, and no-donor-runtime rules are
  encoded in source and CSS.
- AntiGravity review was unavailable/not invoked under the workspace
  no-delegation policy; no raw authentication/tool logs were saved.
