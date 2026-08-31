# Phase 14 UI donor scorecard

This is a read-only assessment of the seven repositories in
`C:\Jarivs\14_ui_candidates`. The scores are evidence-based planning scores,
not claims that donor source has been integrated. Scores are 1-10; the
maintenance-burden column is a risk score where lower is better.

| Donor | Visual | JARVIS fit | Code quality | React | TypeScript | Modularity | Extraction ease | Performance | Responsive | Backend independence | Animation | Product usefulness | Maintenance burden |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `01_foundation_matrix` | 8 | 7 | 8 | 9 | 9 | 8 | 8 | 8 | 8 | 4 | 8 | 7 | 5 |
| `02_jarvis_hud` | 9 | 9 | 6 | 1 | 1 | 5 | 6 | 7 | 7 | 2 | 9 | 7 | 7 |
| `03_jarvis_ui_components` | 8 | 9 | 8 | 9 | 9 | 10 | 8 | 7 | 8 | 9 | 8 | 9 | 5 |
| `04_mission_control` | 8 | 9 | 8 | 9 | 9 | 8 | 5 | 7 | 8 | 2 | 6 | 9 | 8 |
| `05_assistant_ui` | 8 | 8 | 9 | 10 | 9 | 9 | 7 | 8 | 9 | 7 | 7 | 10 | 7 |
| `06_tool_ui` | 9 | 8 | 9 | 9 | 9 | 9 | 8 | 7 | 9 | 8 | 8 | 10 | 7 |
| `07_cinematic_jarvis` | 10 | 10 | 7 | 9 | 8 | 7 | 7 | 7 | 8 | 1 | 10 | 7 | 8 |
| `08_tactical_hud` | 9 | 8 | 6 | 1 | 1 | 2 | 2 | 3 | 7 | 1 | 10 | 6 | 8 |
| `09_holographic_3d` | 10 | 9 | 7 | 1 | 1 | 2 | 3 | 3 | 8 | 8 | 10 | 7 | 8 |

## Evidence and decisions

### `01_foundation_matrix`

- 119 tracked files at commit `91556a6510239e399de92770ed0bdc6bdee33a82`.
- MIT license in `LICENSE`.
- React 19, TypeScript, Vite, React Router, i18n, Lucide, and Vitest.
- Strong shell and responsive layout primitives in
  `src/components/DashboardLayout.tsx` and
  `src/components/ui/MatrixShell.tsx`.
- The view models and `src/data/mock.ts` make the application materially
  mock-driven; those data paths cannot cross into JARVIS.
- Decision: conditional frontend foundation and source of layout patterns,
  not a runtime or data-model donor.

### `02_jarvis_hud`

- 40 tracked files at commit `f9aec211cc8e17ae8b03205fbcefa2fbae88e779`.
- MIT license in `LICENSE`.
- The visual donor is a single browser HUD at
  `server/hud/index.html`, with canvas reactor animation, browser mic/audio,
  WebSocket transport, Hermes proxy calls, weather fetches, and periodic
  polling.
- The repository also contains Python worker/client/server code and
  ElevenLabs, faster-whisper, RealtimeSTT, and Hermes assumptions.
- Decision: visual and interaction reference only. Its WebSocket, voice,
  proxy, weather, and server code are rejected for JARVIS integration.

### `03_jarvis_ui_components`

- 894 tracked files at commit `1a87057012b4eee3222ca466629045ec11bab987`.
- MIT license for the package in
  `packages/jarvis-ui/LICENSE`; package version `1.1.3`.
- The package publishes 143 export lines from `packages/jarvis-ui/src/index.ts`
  and exposes narrowly typed `J*` components, including HUD frames, reactor,
  waveform, orb, activity feed, graph, charts, boot, and command palette.
- Package dependencies include Leaflet, React Leaflet, Google Maps, date
  picker, and Recharts. Only self-contained files may be considered for
  extraction.
- Decision: primary component-library source; no package installation during
  the audit.

### `04_mission_control`

- 806 tracked files at commit `5483a0e1eef15b467c167e95796791112cedbb7c`.
- MIT license in `LICENSE`.
- The UI has useful chat, dashboard widgets, approvals, task board, agent
  panels, terminal, activity, audit, memory, and navigation surfaces.
- The same repository also owns scheduler, event bus, database, auth,
  gateways, agent runtimes, PTY, memory, and many provider integrations.
- Decision: adapt isolated presentational components only. All runtime,
  persistence, authorization, scheduler, event-bus, gateway, and API code is
  rejected so JARVIS keeps one authority for each concern.

### `05_assistant_ui`

- 5,143 tracked files at commit `2c920a6503180d29fec98eba2fd7f7c9210fe999`.
- MIT license in `LICENSE`.
- The package family is mature and typed: `@assistant-ui/react` 0.15.17,
  `@assistant-ui/core` 0.3.16, `@assistant-ui/store` 0.3.11, and
  `assistant-stream` 0.3.40.
- The `packages/ui` package contains rich chat, composer, attachment,
  generative UI, plans, agent cards, canvas split, background inbox, code,
  and activity elements.
- `packages/react/src/assistant-transport.ts` demonstrates a transport
  abstraction but must not replace the JARVIS `/v1` API or create a second
  conversation authority.
- Decision: optional bounded chat-component source or package reference after
  a JARVIS adapter is proven; not the overall foundation.

### `06_tool_ui`

- 796 tracked files at commit `49a870286facdbf28160cd647f0d337ebdc9b275`.
- MIT license in `LICENSE.md`.
- Exact tool surfaces include approval card, plan, progress tracker, terminal,
  message draft, data table, citations, code block, stats display, and
  assistant thread/reasoning components.
- The `apps/www` application also depends on AI SDKs, MCP, cloud providers,
  Three.js, Leaflet, Recharts, MDX/docs infrastructure, and many external
  integrations.
- Decision: high-value isolated presentational source; adapt component files
  and schemas only, never the application runtime or cloud integrations.

### `07_cinematic_jarvis`

- 33 tracked files at commit `284fc820e0821c0a2090f156cf1c6737f61efc56`.
- No `LICENSE`, `LICENSE.md`, or `NOTICE` file was found.
- It contains a compelling five-panel HUD, boot sequence, canvas particle
  field, voice controller, Web Speech API, and a direct Anthropic route in
  `app/api/jarvis/route.ts`.
- Decision: reject source and assets for copying because file-level license
  clearance is absent. It remains a visual reference only.

## Ranking

1. `01_foundation_matrix` — best React/TypeScript shell and responsive
   foundation, after replacing mock view models with JARVIS adapters.
2. `03_jarvis_ui_components` — best bounded HUD/component library.
3. `06_tool_ui` — best approval and tool-surface source.
4. `05_assistant_ui` — best chat interaction source, with a large dependency
   and transport boundary.
5. `04_mission_control` — strongest operational coverage but too much coupled
   runtime authority.
6. `02_jarvis_hud` — strong visual voice reference, incompatible runtime.
7. `07_cinematic_jarvis` — strongest cinematic reference, no source license.

### `08_tactical_hud` delta

- 3 tracked files at commit `68e81567c1f159ee15bef0eebd08b28ea4063eb4`.
- No `LICENSE`, `LICENSE.md`, or `NOTICE` file was found; the README's badge
  and prose are not sufficient file-level clearance for copying.
- `ironman-hud.html` is a 1,970-line monolith with Three.js r160 from a CDN,
  Google Fonts, WebXR, canvas textures, 1,200 ambient particles, simulated
  telemetry, and targeting/missile/explosion state.
- Its tactical composition is visually useful, but it has no React/TypeScript
  extraction boundary and no JARVIS backend contract.
- Decision: visual reference only; no new primary salvage candidate.

### `09_holographic_3d` delta

- 4 tracked files at commit `110c00209525be7df5fbd78ce57186f23ab1c368`.
- MIT license in `LICENSE`.
- `dashboard.html` is a 1,628-line vanilla/WebGL monolith using Three.js r128,
  58 wire rings, 260 decorative points, 42 synthetic system nodes, 16 pulse
  sprites, continuous render/telemetry loops, and MediaPipe Hands from a CDN.
- `index.html` adds face-api.js CDN model downloads, localStorage biometric
  profiles, guest bypass, and camera access. That is not an acceptable JARVIS
  identity or security authority.
- Decision: visual and interaction reference only. The source is licensed, but
  no component boundary or measured product need justifies adopting its 3D or
  biometric runtime in Phase 14.

## 9-repository delta conclusion

Repositories scanned: 9/9.

Neither donor 08 nor donor 09 materially improves the safe extraction set.
The primary salvage count remains 28. They are assigned tactical-HUD and
holographic/3D visual roles, respectively, with source import rejected or
deferred. Donor 09's MIT license permits review but does not override the
performance, security, monolith, and authority constraints.

## Final implementation delta

The approved implementation adapted three donor 03 presentation units:
`JHudFrame`, `JArcReactor`, and `JWaveform`. The remaining donor scorecard
entries stayed reference-only. The shipped UI is approximately 5% adapted
presentation and 95% product-owned application shell, API/state boundary,
screens, styling, security behavior, and tests. No donor runtime or asset was
copied.
