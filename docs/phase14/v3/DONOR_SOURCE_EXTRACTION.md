# Phase 14 V3 donor source extraction

This is a source-level attribution and adaptation record. Donor code is not a
runtime dependency and donor backends, mock data, cloud assets, and transports
were not copied.

| Donor | Exact source | V3 treatment |
|---|---|---|
| 03 React UI library | `packages/jarvis-ui/src/components/ui/JWaveform.tsx` | Adapted waveform presentation through the existing product `JWaveform`; transport and props remain product-owned. |
| 03 React UI library | `packages/jarvis-ui/src/components/ui/JNodeGraph.tsx` | Adapted deterministic node/link geometry into product-owned `PulseNetwork`. |
| 03 React UI library | `packages/jarvis-ui/src/components/layout/JHudFrame.tsx`, `JHudBar.tsx`, `JHudFrameCard.tsx` | Used as HUD framing references; product-owned `HoloPanel`, labels, cards, and existing panels remain the implementation. |
| 03 React UI library | `packages/jarvis-ui/src/components/charts/JRadarChart.tsx` | Used as radial information-design reference; product-owned `RadarSweep` renders only reported points. |
| 04 mission control | `src/components/layout/nav-rail.tsx` | Adapted compact navigation and collapsible-rail idea into the existing `AppShell`; no router or state store copied. |
| 04 mission control | `src/components/panels/activity-feed-panel.tsx`, `src/components/chat/chat-panel.tsx` | Used for density and hierarchy references; existing JARVIS activity/chat transport remains authoritative. |
| 06 tool UI | `apps/www/components/tool-ui/progress-tracker/progress-tracker.tsx`, `plan/plan.tsx`, `approval-card/approval-card.tsx` | Used for readable progress, plan, and approval presentation; product-owned canonical action handlers remain in place. |
| 07 cinematic React | `components/BootSequence.tsx`, `components/animations/ArcReactor.tsx`, `components/panels/WaveformCore.tsx`, `components/panels/ThreatRadar.tsx` | Extracted cinematic timing, glow, ring, waveform, and radar language only. Stark/weapon/threat semantics and runtime were excluded. |
| 08 static tactical HUD | `ironman-hud.html` functions `drawReticle`, `drawCircularGauge`, `drawMiniBar`, `drawCompass` | Geometry and scanline references only; no Three.js CDN, animation loop, fabricated threat data, or weapon semantics. |
| 09 static dashboard | `dashboard.html` functions `randomGreatCircle`, `fibonacciSphere`, `spawnPing`, `makeCurvedPanel` | Depth/node/curved-panel references only; no WebGL, face recognition, hand gesture, MediaPipe, remote assets, or mock telemetry. |

Donors 02 and 05 were inspected as references but were not imported into the
runtime. Donor 02 remains a static HUD reference with external-font concerns;
donor 05 is an assistant-UI framework surface rather than a drop-in product
component. Donor license and exclusion decisions remain in the Phase 14
inventory and salvage map.

## Product-owned V3 files

- `ui/src/features/core/deriveVisualState.ts`
- `ui/src/components/cinematic/CinematicHero.tsx`
- `ui/src/components/cinematic/CinematicBoot.tsx`
- `ui/src/components/cinematic/AmbientEnergy.tsx`
- `ui/src/components/holographic/HolographicCore.tsx`
- `ui/src/components/holographic/HoloRing.tsx`
- `ui/src/components/holographic/PulseNetwork.tsx`
- `ui/src/components/holographic/Primitives.tsx`
- `ui/src/components/tactical/RadarSweep.tsx`
- `ui/src/components/tactical/CompassStrip.tsx`
