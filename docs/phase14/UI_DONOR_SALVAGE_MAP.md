# Phase 14 UI donor salvage map

The table preserves the approved planning dispositions. The final accepted
adaptations are listed after the table. All donor paths are relative to the
named donor repository.

| Final JARVIS feature | Donor | Exact file/component | Action | Notes |
|---|---|---|---|---|
| Responsive application shell | `01_foundation_matrix` | `src/components/DashboardLayout.tsx` — `DashboardLayout` | ADAPT | Keep responsive sidebar and navigation behavior; replace all donor routes, labels, mock pages, and external links. |
| Technical surface frame | `01_foundation_matrix` | `src/components/ui/MatrixShell.tsx` — `MatrixShell` | ADAPT | Keep framing and density; bind only to product-owned screen data. |
| Status, typewriter, signal primitives | `01_foundation_matrix` | `src/components/ui/MatrixExtras.tsx` — `ConnectionStatus`, `SignalBox`, `TypewriterText`, `ScrambleText`, `MatrixRain`, `BootScreen` | ADAPT | Keep bounded visual behavior; remove timers that simulate backend state. |
| Trends and activity visualization | `01_foundation_matrix` | `src/components/ui/DataVizComponents.tsx` — `TrendMonitor`, `ActivityHeatmap`, `ArchiveHeatmap`, `TrendChart` | ADAPT | Reuse only with validated projection values; no `src/data/mock.ts`. |
| Runner history presentation | `01_foundation_matrix` | `src/components/ui/RunnerComponents.tsx` — `RunHistory`, `RunDetailModal`, `RunHeatmap` | REFERENCE ONLY | Runner data model and mock output do not match canonical mission/automation records. |
| HUD visual language | `02_jarvis_hud` | `server/hud/index.html` — reactor, activity feed, approval, and state CSS/JS sections | REFERENCE ONLY | Do not copy the WebSocket, `/api/hermes`, weather, proxy, or voice runtime. |
| HUD protocol context | `02_jarvis_hud` | `docs/ARCHITECTURE.md` | REFERENCE ONLY | Useful comparison for state/event presentation; JARVIS keeps `/v1/experience/events` and `/v1/experience/events/ws`. |
| HUD frame | `03_jarvis_ui_components` | `packages/jarvis-ui/src/components/layout/JHudFrame.tsx` — `JHudFrame` | ADAPT | MIT file-level component; preserve attribution and adapt CSS tokens. |
| Framed HUD card | `03_jarvis_ui_components` | `packages/jarvis-ui/src/components/layout/JHudFrameCard.tsx` — `JHudFrameCard` | COPY | Good reusable panel surface; strip donor-specific theme assumptions. |
| HUD header/bar | `03_jarvis_ui_components` | `packages/jarvis-ui/src/components/layout/JHudBar.tsx` — `JHudBar` | COPY | Use for screen headers and live status labels. |
| Arc-reactor state visualization | `03_jarvis_ui_components` | `packages/jarvis-ui/src/components/ui/JArcReactor.tsx` — `JArcReactor` | ADAPT | Visual only; state must come from experience projection/health. |
| Voice/activity waveform | `03_jarvis_ui_components` | `packages/jarvis-ui/src/components/ui/JWaveform.tsx` — `JWaveform` | ADAPT | Render local UI voice state, never infer microphone acceptance from animation. |
| Core orb | `03_jarvis_ui_components` | `packages/jarvis-ui/src/components/ui/JOrb.tsx` — `JOrb` | ADAPT | Use as a visual state indicator with reduced-motion fallback. |
| Activity feed | `03_jarvis_ui_components` | `packages/jarvis-ui/src/components/ui/JActivityFeed.tsx` — `JActivityFeed` | ADAPT | Feed is projection data; no second event bus. |
| KPI strip | `03_jarvis_ui_components` | `packages/jarvis-ui/src/components/ui/JKPITicker.tsx` — `JKPITicker` | ADAPT | Only display actual health, focus, mission, or attention values. |
| Read-only graph | `03_jarvis_ui_components` | `packages/jarvis-ui/src/components/ui/JNodeGraph.tsx` — `JNodeGraph` | OPTIONAL | Use only if an actual graph projection is selected; no synthetic nodes. |
| Command palette | `03_jarvis_ui_components` | `packages/jarvis-ui/src/components/ui/JCommandPalette.tsx` — `JCommandPalette` | COPY | Commands call existing routes and approval flows; no local task executor. |
| Boot presentation | `03_jarvis_ui_components` | `packages/jarvis-ui/src/components/ui/JBootScreen.tsx` — `JBootScreen` | ADAPT | Startup presentation only; do not claim runtime readiness before `/health`. |
| Chat composer | `04_mission_control` | `src/components/chat/chat-input.tsx` — `ChatInput` | ADAPT | Bind to canonical `POST /v1/messages`; retain abort as `/v1/runs/{id}/cancel`. |
| Chat message rendering | `04_mission_control` | `src/components/chat/message-bubble.tsx` — `MessageBubble` | ADAPT | Use canonical conversation message payloads and safe text/markdown policy. |
| Conversation navigation | `04_mission_control` | `src/components/chat/conversation-list.tsx` — `ConversationList` | ADAPT | Bind to `/v1/conversations`; owner scope is server-enforced. |
| Approval presentation | `04_mission_control` | `src/components/panels/exec-approval-panel.tsx` — `ExecApprovalPanel` | ADAPT | Presentation only; decisions go through existing approval endpoints. |
| Mission/task pipeline | `04_mission_control` | `src/components/dashboard/widgets/task-pipeline-widget.tsx` — `TaskPipelineWidget` | ADAPT | Map to `/v1/missions`, `/v1/goals`, or `/v1/automations`; never import donor stores. |
| Rich chat panel | `05_assistant_ui` | `packages/ui/src/components/react/assistant-ui/elements/chat-panel.tsx` — `ChatPanel`, `ChatPanelMessages`, `ChatPanelComposer` | ADAPT | Use only after a thin JARVIS transport adapter is tested. |
| Composer behavior | `05_assistant_ui` | `packages/ui/src/components/react/assistant-ui/elements/composer.tsx` — `Composer` | ADAPT | Preserve draft/accessibility behavior; no Assistant Cloud or remote runtime. |
| Split conversation/context view | `05_assistant_ui` | `packages/ui/src/components/react/assistant-ui/elements/canvas-split.tsx` — `CanvasSplit` | OPTIONAL | Consider for conversation plus evidence/context layout. |
| Background run inbox | `05_assistant_ui` | `packages/ui/src/components/react/assistant-ui/elements/background-inbox.tsx` — `BackgroundInbox` | ADAPT | Use only for canonical run/mission status; no local background runner. |
| Transport type boundary | `05_assistant_ui` | `packages/react/src/assistant-transport.ts` — `AssistantTransport*` types | REFERENCE ONLY | Do not install or adopt a second transport authority. |
| Approval card | `06_tool_ui` | `apps/www/components/tool-ui/approval-card/approval-card.tsx` — `ApprovalCard` | ADAPT | Bind decisions to existing owner-scoped approval endpoints and CSRF/session rules. |
| Approval schema | `06_tool_ui` | `apps/www/components/tool-ui/approval-card/schema.ts` — `SerializableApprovalCardSchema` | ADAPT | Narrow to JARVIS approval contract; validate display data only. |
| Plan display | `06_tool_ui` | `apps/www/components/tool-ui/plan/plan.tsx` — `Plan` | ADAPT | Render mission/goal steps from canonical records. |
| Progress tracker | `06_tool_ui` | `apps/www/components/tool-ui/progress-tracker/progress-tracker.tsx` — `ProgressTracker` | ADAPT | Display server-reported progress/status; never invent percentages. |
| Message draft | `06_tool_ui` | `apps/www/components/tool-ui/message-draft/message-draft.tsx` — `MessageDraft` | ADAPT | Map to communication draft/send/decide routes; preserve preview-before-send. |
| Tool result table | `06_tool_ui` | `apps/www/components/tool-ui/data-table/data-table.tsx` — `DataTable` | ADAPT | Useful for devices, skills, events, research evidence, and communications. |
| Research citations | `06_tool_ui` | `apps/www/components/tool-ui/citation/citation.tsx` and `citation-list.tsx` — `Citation`, `CitationList` | ADAPT | Use only persisted research evidence URLs/text from JARVIS. |
| Code/engineering output | `06_tool_ui` | `apps/www/components/tool-ui/code-block/code-block.tsx` — `CodeBlock` | ADAPT | Safe display only; execution stays in engineering authority. |
| Structured diff | `06_tool_ui` | `apps/www/components/tool-ui/code-diff/code-diff.tsx` — `CodeDiff` | OPTIONAL | Add only for a canonical engineering diff payload. |
| Statistics display | `06_tool_ui` | `apps/www/components/tool-ui/stats-display/stats-display.tsx` — `StatsDisplay` | ADAPT | Useful for health and evaluation summaries. |
| Tool fallback | `06_tool_ui` | `apps/www/components/assistant-ui/tool-fallback.tsx` — `ToolFallback` | ADAPT | Render unknown tool results as inert data, never executable markup. |
| Terminal | `06_tool_ui` | `apps/www/components/tool-ui/terminal/terminal.tsx` — `Terminal` | REFERENCE ONLY | `@xterm/xterm` and PTY require a separately approved canonical stream. |
| Cinematic reactor | `07_cinematic_jarvis` | `components/animations/ArcReactor.tsx` — `ArcReactor` | REFERENCE ONLY | No license evidence; no source/assets copy. |
| Cinematic particles | `07_cinematic_jarvis` | `components/animations/ParticleField.tsx` — `ParticleField` | REFERENCE ONLY | Reimplement independently only if later approved. |
| Cinematic boot | `07_cinematic_jarvis` | `components/BootSequence.tsx` — `BootSequence` | REFERENCE ONLY | Do not copy; no license and speech assumptions. |
| Cinematic panels | `07_cinematic_jarvis` | `components/panels/WaveformCore.tsx`, `ThreatRadar.tsx`, `SuitStatus.tsx`, `StarkAnalytics.tsx`, `CommsLog.tsx` | REFERENCE ONLY | Visual composition reference only; no direct Anthropic route, store, or Web Speech controller. |

## Exact candidate count

The primary post-approval salvage set contains 28 named component/file units:
4 from donor 01, 8 from donor 03, 4 from donor 04, 4 from donor 05, and 8
from donor 06. Optional units are `JNodeGraph`, `CanvasSplit`, and `CodeDiff`.
The planning count is 28 candidates. The final JARVIS implementation adapted
three donor 03 presentational units and no donor runtime, mock data, or asset:

- `JHudFrame` -> `ui/src/components/hud/JHudFrame.tsx`;
- `JArcReactor` -> `ui/src/components/hud/JArcReactor.tsx`;
- `JWaveform` -> `ui/src/components/hud/JWaveform.tsx`.

The adapted files retain the donor's MIT treatment in the source header. The
remaining candidate units are reference-only for this release.

## 9-repository delta candidates

The following exact files/functions were inspected from donors 08 and 09. None
is accepted into the primary count. Performance concern is recorded even for
reference-only items because the target is a local application that may run
alongside the local Qwen runtime.

| Repo | Exact path | Component/file | Target JARVIS feature | Action | Reason | Performance concern |
|---|---|---|---|---|---|---|
| `08_tactical_hud` | `ironman-hud.html` | `createCurvedPlane`, `createHUDTexture`, `makeCurvedPanel` | Home HUD framing / perception visualization | REFERENCE ONLY | Useful curved-panel concept, but embedded in a monolith with no license file and a CDN Three.js import. | WebGL scene and canvas textures add GPU work; no measured JARVIS need. |
| `08_tactical_hud` | `ironman-hud.html` | `drawCorners`, `drawCircularGauge`, `drawBar`, `drawMiniBar` | System monitoring / device status | REFERENCE ONLY | Recreate as product-owned CSS/SVG if needed; do not copy uncleared source. | Repainting multiple canvas panels every frame is unnecessary for ordinary projections. |
| `08_tactical_hud` | `ironman-hud.html` | `drawRightPanel`, compass strip, threat radar | Devices / current context | REFERENCE ONLY | Tactical visual language only; telemetry and threats are simulated. | Continuous sweep animation and panel redraws are avoidable idle load. |
| `08_tactical_hud` | `ironman-hud.html` | `createThreatBracket` and lock-on/missile/explosion state | Mission status | REJECT | Encodes fictional weapon actions and synthetic targeting state, not JARVIS missions or approvals. | Particle/explosion effects add cost without product value. |
| `08_tactical_hud` | `ironman-hud.html` | `initScene`, WebXR setup, 1,200-particle world | Tactical/3D mode | REJECT | Adds WebXR/Three.js runtime and no backend integration boundary. | Explicitly rejected as unnecessary GPU/CPU/RAM use in Phase 14. |
| `09_holographic_3d` | `dashboard.html` | `fibonacciSphere`, wire rings, reactor core, `spawnPing` | Home visual core | REFERENCE ONLY | MIT-licensed visual reference, but embedded in a 1,628-line vanilla monolith. | 58 rings, 260 decor points, WebGL, and continuous render loop are excessive for the base UI. |
| `09_holographic_3d` | `dashboard.html` | `NODE_DATA`, `nodeMeshes`, `nodeEdges`, data pulses | Current context / system graph | REFERENCE ONLY | 42 nodes are synthetic and do not correspond to JARVIS projections. | 16 moving pulse sprites and graph redraws add continuous idle work. |
| `09_holographic_3d` | `dashboard.html` | `selectNode`, pointer drag, `projectToNodeDragPlane` | Read-only system visualization | REFERENCE ONLY | Interaction model can inform a later enhancement; no canonical graph/action contract exists. | Raycasting and drag tracking require a dedicated performance budget. |
| `09_holographic_3d` | `dashboard.html` | `classifyHandRaw`, `debounce`, gesture loop | Perception/desktop awareness | REJECT | Camera gesture control is a separate sensor authority and must not be introduced through the UI. | Per-frame MediaPipe processing competes with local model resources. |
| `09_holographic_3d` | `index.html` | `bestMatch`, `loadProfiles`, `saveProfiles`, `grantAccess` | Identity/login | REJECT | Browser localStorage face profiles and guest bypass cannot replace JARVIS identity/session/approval authority. | Face-api.js model downloads and camera inference are unnecessary for Phase 14. |
| `09_holographic_3d` | `index.html` | boot/login scan UI and model loader | Boot presentation | REFERENCE ONLY | Visual sequence only; no biometric source or CDN loader may be imported. | Initial model download and repeated detection delay startup. |

Primary salvage candidates after the 9/9 comparison: **28**. Donors 08 and 09
add no accepted primary units; they add two visual-reference roles only.
