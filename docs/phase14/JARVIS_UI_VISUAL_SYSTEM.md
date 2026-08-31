# JARVIS Phase 14 visual system

This is the product-owned visual target informed by the donor scan. It is not
a copy of any donor stylesheet or asset.

## Direction

JARVIS should read as a calm local operations console: dark, technical, and
instrument-like, with cinematic accents reserved for state transitions and
important attention. The UI must remain legible and useful when animation is
disabled.

## Tokens

| Token | Value | Use |
|---|---|---|
| `--jarvis-bg` | `#071019` | Application background |
| `--jarvis-surface` | `#0d1b27` | Cards and panels |
| `--jarvis-surface-raised` | `#132738` | Hover, focused, or selected surfaces |
| `--jarvis-line` | `#24445a` | Dividers and panel frames |
| `--jarvis-text` | `#e6f4fb` | Primary text |
| `--jarvis-muted` | `#8eacbd` | Supporting text |
| `--jarvis-cyan` | `#55d9ff` | Primary active accent |
| `--jarvis-green` | `#56e39f` | Healthy/complete |
| `--jarvis-amber` | `#f5bd63` | Attention/pending |
| `--jarvis-red` | `#ff6f7d` | Failed/blocked/danger |
| `--jarvis-purple` | `#b49cff` | Research/intelligence accent |
| `--jarvis-mono` | `ui-monospace, SFMono-Regular, Consolas, monospace` | Telemetry, IDs, timestamps |
| `--jarvis-sans` | `Inter, ui-sans-serif, system-ui, sans-serif` | Normal UI copy |

No remote font is required. If a branded font is later added, it must be
bundled locally with cleared licensing.

## Geometry and density

- 8px base spacing grid, with 12px/16px panel padding.
- 8px panel radius for normal surfaces; 2px technical frame accents.
- Minimum interactive target 40px on desktop and 44px on touch layouts.
- Desktop layout: navigation rail, command/status bar, primary work area,
  optional evidence/attention rail.
- Small screens: navigation becomes a drawer; cards stack; dense tables become
  horizontally scrollable or switch to rows.

## Component states

Every data component must define loading, ready, stale, empty, unavailable,
permission-denied, and error states. Use color plus text/icon labels; color is
not the sole status signal.

The central orb/reactor is a state indicator, not a claim of microphone,
model, or runtime readiness. Its state comes from the experience projection or
health response and has a text equivalent.

## Motion

- Boot transition: short, skippable, and never blocks application use after
  the shell is ready.
- Event transition: 120-220ms opacity/transform changes.
- Active voice visualization: derived from actual local audio/voice state only.
- No infinite animation is required to communicate health.
- `prefers-reduced-motion: reduce` disables particle fields, scan loops,
  typewriter effects, and nonessential canvas animation.

## Accessibility and trust

- Visible keyboard focus and landmark structure.
- Screen-reader labels for status, activity, approval, and live updates.
- `aria-live` limited to meaningful state changes, not every telemetry tick.
- Confirmation and approval controls state the exact action and target.
- URLs, model output, tool arguments, and error text are displayed as safe
  text; no arbitrary HTML.

## Donor influence map

- Donor 01 informs shell density, responsive navigation, and technical palette.
- Donor 03 informs reusable HUD frame, reactor, waveform, activity, and chart
  primitives after file-level MIT attribution.
- Donor 02 informs restrained canvas reactor and live activity composition.
- Donor 06 informs structured approval, plan, progress, citation, and tool
  result surfaces.
- Donor 07 informs cinematic composition only; no source or asset is reused.

## 9-repository visual delta

- Donor 08 informs tactical framing, compass/radar composition, segmented
  gauges, and corner-bracket language. It is a reference only; no Marvel or
  official Iron Man asset is used.
- Donor 09 informs a possible holographic network composition, reactor core,
  node pulse, and restrained depth cues. It is reference only; the Phase 14
  base surface remains CSS/SVG.

Real-time 3D in Phase 14: **NO**. A full WebGL/WebXR core, hand-tracking
pipeline, or biometric login adds resource cost and a competing interaction or
identity authority without a required backend projection. Any future 3D work
must be an optional isolated enhancement with a CSS/SVG fallback.
