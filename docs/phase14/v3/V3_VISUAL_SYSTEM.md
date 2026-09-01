# Phase 14 V3 visual system

## Palette and composition

The V3 palette is a dark plum/void base with burgundy and crimson energy, dark
armor panels, restrained white text, and cyan used only for local operational
readouts. The owner wallpaper is shaded in place so the hero remains legible.
The large V2 reactor is replaced by a subtle chest-core treatment and thin
orbit/ring geometry.

The shell has a top bar, collapsible navigation rail, collapsible live-context
dock, and responsive workspace. Home is the cinematic hero; other screens keep
their functional product surfaces and receive the shared tactical/holographic
language.

## Visual state contract

`deriveVisualState(projection)` maps canonical projection evidence to:

`idle`, `ready`, `thinking`, `tool`, `researching`, `waiting_approval`,
`speaking`, `degraded`, `offline`, or `error`.

Approval and error evidence takes precedence over activity. Missing projection
is offline. The adapter is pure and does not create a second state authority.

## Data binding

- Hero model and offline copy come from `projection.system`.
- Active application and focused window come from `projection.presence`.
- Mission, attention, device, and voice readouts come from their canonical
  projection collections.
- Device radar point count is exactly the registered-device count; zero devices
  renders an explicit idle state.
- No random values, fabricated telemetry, remote assets, or fake target labels
  are emitted by V3 components.

## Motion and accessibility

Motion is CSS-only and bounded to slow drift, ring rotation, pulse links, and a
scan plane. `prefers-reduced-motion: reduce` disables the animation rules while
retaining the visual structure. Interactive shell toggles expose labels and
`aria-expanded`; wallpaper and decorative geometry are non-semantic or
support readable labels.
