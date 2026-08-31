# Phase 14 UI implementation plan

This plan records the completed execution of the approved Phase 14 UI
implementation. The donor deep scan and foundation decision remain the
source-of-truth boundaries for the implementation.

## Block 1 — frontend shell and build boundary

Adapt donor 01's `DashboardLayout` and `MatrixShell` into the product-owned
frontend. Establish React routing, the local build artifact, keyboard/focus
behavior, responsive breakpoints, and the `/v1/app/*` serving contract. Keep
the backend unchanged.

Exit evidence: deterministic local build, route smoke test, no remote assets,
no donor mock imports, and unchanged backend authority inventory.

## Block 2 — API/session/event adapters

Create one typed JARVIS API adapter for `/v1`, session/CSRF handling, safe
error states, and owner-scoped query helpers. Create one event normalizer for
the existing experience stream/WebSocket. Do not import donor transports,
EventBus, or gateway code.

Exit evidence: focused adapter tests for owner scoping, mutation refresh,
reconnect, stale state, and event envelope handling.

## Block 3 — home, context, activity, and visual state

Build the Home, Current Context, Activity, and Settings surfaces from existing
experience, health, presence, attention, personalization, and client
projections. Adapt donor 03 HUD frames and activity/KPI primitives only where
they remain presentational.

Exit evidence: no fabricated telemetry, reduced motion, accessibility labels,
and backend projection fixtures only in tests.

## Block 4 — chat and conversation history

Adapt the selected donor 04/05 chat components behind the JARVIS adapter.
Implement conversation list/history, typed send, streaming/live status,
cancel, retry/error, safe markdown/text, and owner-bound routes.

Exit evidence: conversation ownership tests, duplicate send protection, cancel
behavior, XSS-safe rendering, and no Assistant Cloud/provider dependency.

## Block 5 — missions, memory, operations, and approvals

Compose mission/goal/memory/personal-operation screens with donor 04/06
presentational pieces. Approval cards, mode changes, communication drafts,
automation, notification delivery, and focus actions call existing JARVIS
routes and display the server result.

Exit evidence: approval and CSRF tests, no synthetic progress, explicit stale
approval handling, and unchanged persistence/migration surface.

## Block 6 — capabilities and evidence surfaces

Add Research, Engineering, Browser, Skills, and Devices screens using the
existing capability APIs. Use DataTable, Citation, CodeBlock, Plan, and
ProgressTracker only as inert presentation adapters. Defer xterm, XYFlow, and
multi-window layout until a separate requirement and backend contract exist.

Exit evidence: permission-denied and unavailable states, action/audit
correlation, bounded rendering for large evidence, and no donor runtime import.

The 9-repository delta does not add a new implementation block. Block 1 may
use donor 08's tactical framing and donor 09's holographic composition as
independent visual references only. No Three.js/WebGL/WebXR render loop,
MediaPipe gesture pipeline, face-recognition login, synthetic node graph, or
CDN model loader is added. The base implementation remains CSS/SVG with a
product-owned fallback for all visual state.

## Block 7 — hardening and release gate

Run focused UI/security/accessibility tests, Phase 14 regression, the full
repository suite, compile checks, diff checks, final dependency/license
review, and a complete visual smoke pass. Update the audit with actual
reuse/custom percentages and exact adapted paths before commit.

## Clone-set decision

The seven repositories remain untouched audit inputs on disk.

| Donor | Clone-set status | Future use |
|---|---|---|
| `01_foundation_matrix` | KEEP | Conditional application foundation. |
| `03_jarvis_ui_components` | KEEP | Bounded component extraction source. |
| `05_assistant_ui` | KEEP | Optional chat component/package reference. |
| `06_tool_ui` | KEEP | Bounded tool-surface extraction source. |
| `02_jarvis_hud` | OPTIONAL | Visual/protocol reference only. |
| `04_mission_control` | OPTIONAL | Isolated operational component reference only; runtime rejected. |
| `07_cinematic_jarvis` | DROP FROM SOURCE IMPORT SET | Visual reference only; no license evidence. |
| `08_tactical_hud` | OPTIONAL | Tactical radar/compass/gauge reference only; no license file and no source import. |
| `09_holographic_3d` | OPTIONAL | MIT-licensed holographic reference only; Three.js, biometrics, and gesture runtime rejected. |

“Drop” means drop from source-import consideration; no donor directory is
deleted by this audit.

## 9-repository handoff state

- Repositories scanned: 9/9.
- Foundation changed: NO.
- Primary salvage candidates: 28.
- Tactical HUD role: donor 08 visual reference for radar, compass, gauges, and
  framing.
- Holographic/3D role: donor 09 visual reference for depth and network-core
  composition.
- Final observed mix: approximately 5% adapted presentation / 95%
  product-owned.
- Heavy dependencies: REJECT for Phase 14 base; 3D is NO for this phase.

## Final execution record

- One React application under `ui/src/` owns routing, presentation, API
  transport, projection normalization, and screen state.
- The existing Python server, session/bootstrap boundary, experience stream,
  and backend authorities were preserved.
- Donor 03 contributed only the three adapted HUD presentation components
  recorded in `UI_DONOR_SALVAGE_MAP.md`.
- Donor 08 and donor 09 remain visual references only; no heavy 3D, biometric,
  gesture, synthetic telemetry, or CDN runtime was introduced.
- Final test and release evidence is recorded in
  `docs/audits/MEGA_PHASE_14_REVIEW.md`.
