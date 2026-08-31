# Phase 14 final frontend architecture map

This document is the final implementation record for the approved Phase 14
frontend architecture.

## Stack

- React 19 and TypeScript, following the selected donor 01 Vite-compatible
  foundation conventions without importing its application source.
- React Router for screen routing, with a single `/app` entry served by the
  existing local JARVIS server.
- A small JARVIS-owned API adapter under `ui/src/lib/api.ts`.
- A small projection store under `ui/src/state/`; Zustand is optional only if
  the final build demonstrates a need. The browser store is never truth.
- Existing `/v1` session/cookie/CSRF protocol.
- Existing `/v1/experience/events` stream and
  `/v1/experience/events/ws` WebSocket for live projection updates.
- CSS custom properties and file-cleared/adapted donor primitives. No remote
  fonts, CDN assets, or external runtime at startup.

## Data flow

```text
CoreHttpServer /v1
  -> JARVIS-owned typed API adapter
  -> projection store / screen query state
  -> screens and presentational components

experience event stream
  -> event normalizer
  -> invalidation/update of the same projection store
```

Mutations use the same API adapter, include the existing session/CSRF
requirements, and refresh or reconcile against the server response. A donor
store cannot create tasks, runs, approvals, conversations, or events.

## Routing

The shipped route map is:

`/app` home, `/app/chat`, `/app/missions`, `/app/memory`, `/app/context`,
`/app/operations`, `/app/research`, `/app/engineering`, `/app/browser`,
`/app/skills`, `/app/devices`, `/app/notifications`, `/app/approvals`,
`/app/activity`, and `/app/settings`.

Each route is a screen projection. Route changes do not change backend
ownership or establish a separate session.

## Folder layout

```text
ui/
  src/
    app/
      App.tsx
      routes.ts
    components/
      layout/
      hud/
      chat/
      tools/
      common/
    screens/
      Screens.tsx
    lib/
      api.ts
      events.ts
      format.ts
    state/
    styles.css
```

## Rendering and safety

- Render server-returned text as text or through a narrowly configured safe
  markdown renderer; never render arbitrary model HTML.
- Escape or validate URLs and external references before rendering.
- Show unavailable, stale, empty, and permission-denied states explicitly.
- Use `prefers-reduced-motion` and an application motion setting for all donor
  HUD animation.
- Keep interactive actions disabled while an approval or request is stale.

## Production serving

The frontend build output is copied into
`src/jarvis/ui_static` by an explicit deterministic build step and served by
the existing `/v1/app/*` path. The current `ui/build_frontend.py` contract is
the reference for local, offline-safe serving; any future build change must
retain the no-remote-asset and deterministic-artifact guarantees.

The existing Python server, desktop bootstrap, and loopback-only binding stay
in place. No Next.js server, donor proxy, or second process is introduced by
this implementation.

## 9-repository visual delta

The tactical composition from donor 08 and the holographic composition from
donor 09 remain reference material only. The base architecture uses CSS/SVG
panels and bounded transitions; it does not add a Three.js/WebXR/WebGL render
loop, MediaPipe gesture authority, face-recognition gate, or CDN model loader.

If a later product requirement demonstrates a need for a 3D visualization, it
must be an isolated, read-only enhancement with an explicit frame/resource
budget and a CSS/SVG fallback. It must consume an existing JARVIS projection,
not synthetic donor telemetry or local browser identity state.

The shipped implementation adapts only donor 03's `JHudFrame`, `JArcReactor`,
and `JWaveform` as product-owned HUD presentation components. No donor
application shell, mock store, transport, database, or capability runtime is
imported.
