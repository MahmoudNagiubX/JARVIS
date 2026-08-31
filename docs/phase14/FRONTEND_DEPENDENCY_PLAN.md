# Phase 14 frontend dependency plan

The approved frontend dependency surface is installed and locked in
`ui/package-lock.json`. Every dependency remains bounded to the local browser
bundle; no Node/npm process is required at product startup.

## Keep/allow list

| Dependency or capability | Decision | Reason |
|---|---|---|
| React and React DOM | KEEP | Required by selected future foundation. |
| TypeScript and Vite | KEEP | Typed deterministic browser build boundary. |
| React Router | KEEP | Screen routing used by donor 01; no server authority change. |
| Lucide icons | KEEP | Local icon component library with small surface. |
| CSS/SVG visualization | KEEP | Lowest-dependency path for JARVIS projections and charts. |
| Donor 03 self-contained `J*` files | ADAPTED (3 units) | MIT file-level source, with attribution and dependency audit. |
| Donor 06 isolated tool surfaces | ADAPT AFTER APPROVAL | MIT source; bind to JARVIS-owned contracts and remove app integrations. |
| Donor 05 chat elements | OPTIONAL | Use only if the JARVIS adapter and bundle cost are proven. |
| Zustand | OPTIONAL | Only for browser cache/UI state; no runtime truth. |
| `react-markdown` | OPTIONAL | Only if safe markdown rendering is required and configured without raw HTML. |

## Explicit decisions requested by the donor scan

### xterm.js

Decision: defer/reject for the base UI. Donor 04 and donor 06 contain
`@xterm/xterm` terminal surfaces, but interactive PTY streaming would require a
canonical JARVIS endpoint and a separate security review. The first UI should
display safe engineering output with `CodeBlock`-style presentation. Add
xterm only after a real backend stream and focused terminal tests exist.

### XYFlow/React Flow

Decision: reject for the base UI. Donor 03's `JNodeGraph` is sufficient as an
optional read-only visual if JARVIS exposes a real graph projection. Do not
add XYFlow merely to animate synthetic agent relationships.

### react-mosaic

Decision: reject. A multi-window workspace would add layout state and a second
desktop-like interaction model without a currently required JARVIS use case.
Use responsive panels and the single application shell.

## Rejected dependency/runtime families

- Next.js server and donor route handlers from donors 04, 06, and 07.
- Anthropic/OpenAI/AI SDK clients, Assistant Cloud, MCP, and provider SDKs.
- Hermes, ElevenLabs, faster-whisper, RealtimeSTT, and donor STT servers.
- Donor SQLite, database migrations, scheduler, EventBus, gateway, PTY, and
  agent runtime modules.
- Three.js, React Three Fiber, postprocessing, Leaflet, Google Maps, and
  weather/cloud integrations unless a separately approved product requirement
  proves them necessary.
- Donor-wide docs/demo packages and mock data.

## Donor 08/09 delta decisions

| Dependency/capability | Donor | Decision | Reason |
|---|---|---|---|
| Three.js r160, WebXR, canvas-scene loop | `08_tactical_hud` | REJECT | Monolithic tactical demo, no license file, simulated telemetry, and unnecessary runtime cost. |
| Three.js r128/WebGL scene | `09_holographic_3d` | DEFER | MIT-licensed reference, but 58 rings, 260 decor points, 42 synthetic nodes, and continuous animation are not justified for the base UI. |
| face-api.js/TensorFlow model loader | `09_holographic_3d` | REJECT | Browser biometric identity and guest bypass cannot replace JARVIS identity/session authority. |
| MediaPipe Hands/CDN gesture loader | `08_tactical_hud`, `09_holographic_3d` | REJECT | Introduces camera/gesture authority and per-frame compute without an approved product contract. |
| WebXR/immersive VR | `08_tactical_hud` | REJECT | No Phase 14 requirement; device/runtime scope is outside the local command center. |
| Orbitron/Share Tech Mono remote fonts | `09_holographic_3d` | REJECT | Remote assets violate the local deterministic/no-CDN serving boundary. |

### Final resolved dependency record

- Runtime bundle: React 19.2.8, React DOM 19.2.8, and React Router DOM 7.18.3.
- Build/test toolchain: Vite 7.3.6, TypeScript 5.9.3, and Vitest 3.2.7.
- `npm audit --json`: 0 vulnerabilities.
- Adapted donor presentation: three MIT-cleared donor 03 components; no
  donor package, mock data, remote font, CDN, or cloud runtime.

### Performance answer

Should JARVIS use a real-time 3D core in Phase 14? **NO**.

The base product uses CSS/SVG and bounded event-driven transitions. Donor 09
remains a visual reference for a possible later enhancement, but no Three.js,
WebGL, WebXR, MediaPipe, or face-recognition package is installed or planned
for this phase. This keeps GPU/CPU/RAM available for the local Qwen runtime.

## License handling

- Preserve MIT attribution for any donor 01/02/03/04/05/06 source actually
  copied or substantially adapted.
- Donor 07 source/assets remain excluded because no license evidence was found.
- Exact adapted paths are `ui/src/components/hud/JHudFrame.tsx`,
  `JArcReactor.tsx`, and `JWaveform.tsx`; versions are recorded above and in
  the lockfile.
