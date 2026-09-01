# Phase 14 V3 visual foundation decision

Status: implemented locally on 2026-09-01.

## Decision

V3 keeps the existing React application, router, API client, session context,
event stream, and screen authorities. The presentation layer is rebuilt around
one local owner wallpaper, a restrained crimson/plum palette, CSS/SVG
holographic primitives, and a state adapter that projects canonical runtime
data into visual states.

The supplied wallpaper is the only hero artwork:

`ui/src/assets/hero/ironman-owner-wallpaper.jpg`

It is imported by the Home screen and emitted as a local Vite asset. No remote
image, font, icon CDN, WebSocket, cloud UI, or donor runtime is introduced.

## Why this foundation

- The current shell remains the product-owned navigation and transport boundary.
- The wallpaper provides the cinematic identity without a second canvas or a
  competing scene engine.
- SVG rings, arcs, scan planes, radar geometry, and node links reproduce the
  useful donor language with deterministic, inspectable DOM.
- `deriveVisualState()` is pure and presentation-only; it does not persist,
  mutate, or become a second runtime authority.
- Reduced motion, local asset loading, semantic labels, and responsive layout
  are part of the foundation rather than post-processing.

## Boundary decision

The execution document describes delegation through Antigravity. The workspace
policy for this run permits delegated coding only when explicitly requested by
the user, so no coding agent was invoked. The implementation and review were
performed in this workspace, and the delegation records state that limitation
explicitly rather than inventing worker evidence.

## Component map

| Product surface | V3 component | Responsibility |
|---|---|---|
| Home hero | `CinematicHero` | Wallpaper-led scene, runtime state, owner context, attention, mission, device readouts. |
| Hero boot/energy | `CinematicBoot`, `AmbientEnergy` | Decorative scene label and bounded ambient energy only. |
| Core | `HolographicCore`, `HoloRing` | Subtle state-colored SVG reactor treatment; no runtime state ownership. |
| Capability depth | `PulseNetwork`, `Primitives` | Deterministic node/link, scan, arc, label, panel, and depth-grid language. |
| Tactical field | `RadarSweep`, `CompassStrip` | Real-count radar and focused-window orientation readouts. |
| State projection | `deriveVisualState` | Pure mapping from the existing `ExperienceState` projection. |
| Shell | `AppShell` | Existing router/session shell with accessible nav/context collapse controls. |

## Animation map

- wallpaper drift: slow CSS transform on the hero artwork;
- core rings and orbit: slow SVG/CSS rotation;
- core pulse and capability dots: bounded opacity/scale pulse;
- radar sweep and scan plane: CSS-only line motion;
- node link: one bounded CSS pulse across the deterministic link;
- reduced motion: all V3 animation rules are disabled and the scene remains
  fully readable.

## Home composition

Home layers the owner wallpaper and shade first, then a thin depth grid and
scan plane. The lower-left copy carries model/runtime state and data arcs. The
center carries the subtle core, capability network, and waveform. The right
readouts carry focused window, application, owner attention, and device field.
A bottom ribbon summarizes local operations, mission field, device field, and
owner control without inventing telemetry.
