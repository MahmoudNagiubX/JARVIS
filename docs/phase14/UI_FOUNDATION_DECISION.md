# Phase 14 UI foundation decision

## Decision

The conditional future frontend foundation is donor
`01_foundation_matrix`, specifically:

- `src/components/DashboardLayout.tsx` for the responsive application shell;
- `src/components/ui/MatrixShell.tsx` for technical panel framing;
- the donor's React/TypeScript/Vite conventions for the future frontend build.

The foundation is not accepted as a data, runtime, auth, persistence, or
execution authority. Its mock view models and `src/data/mock.ts` are excluded.

The final shipped JARVIS product surface is the product-owned React/TypeScript/
Vite application under `ui/src/`, compiled to `src/jarvis/ui_static` by the
existing deterministic build step. This implementation uses the foundation
decision for shell and presentation boundaries without importing its mock data,
routes, or runtime authority.

## Why this foundation

`01_foundation_matrix` is the only candidate that combines a coherent
React/TypeScript/Vite application shell, responsive navigation, typed view
models, visual tests, and a sufficiently small extraction boundary. It is more
appropriate as a future frontend foundation than donor 04's full product
runtime, donor 05's framework monorepo, or donor 06's broad documentation and
cloud application.

Donor 03 is the component source, not the application foundation. Donor 02
and donor 07 establish the cinematic direction but have incompatible or
uncleared runtime/source boundaries.

## Composition decision

| Layer | Decision |
|---|---|
| Application shell | Product-owned shell informed by donor 01's layout decisions; no donor shell source copied. |
| HUD primitives | Adapt only file-cleared, self-contained donor 03 `J*` components. |
| Chat | Product-owned screen behind the JARVIS-owned adapter; no donor transport. |
| Tools/approvals | Product-owned presentation bound to existing approval routes; no donor tool runtime. |
| Cinematic direction | Reference donors 02 and 07; independently implement any uncleared visual. |
| Data and actions | Existing JARVIS `/v1` API and `CoreApplication` only. |
| Events | Existing `experience` projection/event stream only. |
| Auth and approvals | Existing JARVIS identity, session, CSRF, permission, and approval authorities only. |

## Non-negotiable exclusions

- No donor scheduler, EventBus, database, agent runtime, memory store, or
  provider adapter.
- No donor Anthropic/OpenAI/AI SDK/MCP/cloud endpoint.
- No frontend-generated mission, goal, progress, health, device, or approval
  truth.
- No SQL cleanup or migration based on donor schemas.
- No second VoiceCore, voice session, browser microphone acceptance authority,
  or speech transport.
- No source/assets copy from donor 07 without file-level license evidence.

## Final reuse record

The original 28-unit list remains a planning candidate set. The actual Phase
14 implementation is narrower:

- 28 primary donor component/file units are candidates for adaptation;
- actual adapted donor presentation units: 3 (`JHudFrame`, `JArcReactor`,
  `JWaveform`), all from donor 03's MIT-cleared component package;
- approximate implementation mix: 5% adapted presentation / 95%
  product-owned shell, API adapters, state, security, screens, accessibility,
  and tests;
- actual backend authority changes from this scan: 0.

## 9-repository comparison delta

Donor 08 was evaluated as the tactical HUD candidate. Its single
`ironman-hud.html` file combines the visual layer with Three.js/WebXR, CDN
imports, simulated telemetry, and fictional targeting actions. It is not a
better application foundation and has no file-level license document.

Donor 09 was evaluated as the holographic/3D candidate. Its MIT-licensed
`dashboard.html` provides the strongest 3D visual reference, but it is a
vanilla monolith with synthetic nodes, continuous WebGL animation, CDN model
dependencies, and a separate localStorage face-recognition gate in
`index.html`. It is not a better full application foundation.

Foundation remains 01_foundation_matrix after 9-repo comparison.

The final implementation uses product-owned CSS/SVG presentation with the
three donor 03 adaptations above. Donor 08 is the Tactical HUD visual donor and donor 09 is the
Holographic/3D visual donor. Neither adds a primary salvage candidate, and
neither adds a runtime authority, remote asset, or heavy 3D dependency.
