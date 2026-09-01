# Phase 14 V2 donor extraction manifest

All donor repositories were inspected in `C:\Jarivs\14_ui_candidates` during
implementation. Donor code is not imported at runtime and donor worktrees are
unchanged. The adapted modules below keep presentation responsibility only;
JARVIS projection/API state remains authoritative.

| Donor | Source file | Component | Final decision | Destination | Reason |
|---|---|---|---|---|---|
| 01 foundation matrix | `src/components/DashboardLayout.tsx` | `DashboardLayout` | ADAPTED | `ui/src/components/foundation/MatrixFoundation.tsx` | Responsive shell and density were extracted without donor routes, mock data, or branding. |
| 01 foundation matrix | `src/components/ui/MatrixShell.tsx` | `MatrixShell` | ADAPTED | `ui/src/components/foundation/MatrixFoundation.tsx` | Layered technical surface became a product-owned shell wrapper. |
| 01 foundation matrix | `src/components/ui/MatrixExtras.tsx` | `SignalBox`, status primitives | ADAPTED | `ui/src/components/foundation/MatrixFoundation.tsx` | Signal and status language was retained with JARVIS tokens and no simulated readiness. |
| 01 foundation matrix | `src/components/ui/DataVizComponents.tsx` | trend/activity primitives | ADAPTED | `ui/src/components/foundation/MatrixFoundation.tsx` | Bounded event strip and signal treatment use real projection values only. |
| 03 jarvis UI | `packages/jarvis-ui/src/components/layout/JHudFrameCard.tsx` | `JHudFrameCard` | ADAPTED | `ui/src/components/hud/DonorFusion.tsx` | Corner-frame geometry was retained as a selective high-value surface. |
| 03 jarvis UI | `packages/jarvis-ui/src/components/layout/JHudBar.tsx` | `JHudBar` | ADAPTED | `ui/src/components/hud/DonorFusion.tsx` | Top command/status trace is bound to runtime state. |
| 03 jarvis UI | `packages/jarvis-ui/src/components/ui/JArcReactor.tsx` | `JArcReactor` | ADAPTED | `ui/src/components/hud/JArcReactor.tsx` | Existing attributed reactor remains projection-driven. |
| 03 jarvis UI | `packages/jarvis-ui/src/components/ui/JWaveform.tsx` | `JWaveform` | ADAPTED | `ui/src/components/hud/JWaveform.tsx` | Existing attributed waveform remains voice-state-only. |
| 03 jarvis UI | `packages/jarvis-ui/src/components/ui/JOrb.tsx` | `JOrb` | ADAPTED | `ui/src/components/hud/DonorFusion.tsx` | Orb rings and state label became a lightweight CSS adapter. |
| 03 jarvis UI | `packages/jarvis-ui/src/components/ui/JActivityFeed.tsx` | `JActivityFeed` | ADAPTED | `ui/src/components/hud/DonorFusion.tsx` | Activity rows consume the existing event projection. |
| 03 jarvis UI | `packages/jarvis-ui/src/components/ui/JKPITicker.tsx` | `JKPITicker` | ADAPTED | `ui/src/components/hud/DonorFusion.tsx` | KPI strip displays actual model, device, mission, approval, and mode values. |
| 03 jarvis UI | `packages/jarvis-ui/src/components/ui/JCommandPalette.tsx` | `JCommandPalette` | ADAPTED | `ui/src/components/hud/DonorFusion.tsx` | Ctrl+K remains route/navigation-only and cannot execute tools. |
| 04 mission control | `src/components/chat/chat-input.tsx` | `ChatInput` | ADAPTED | `ui/src/screens/Screens.tsx` | Composer behavior remains on `/messages/start` and existing run cancellation. |
| 04 mission control | `src/components/chat/message-bubble.tsx` | `MessageBubble` | ADAPTED | `ui/src/components/operations/OperationsPrimitives.tsx` | Rich message grouping is inert display over canonical messages. |
| 04 mission control | `src/components/chat/conversation-list.tsx` | `ConversationList` | ADAPTED | `ui/src/components/operations/OperationsPrimitives.tsx` | Conversation rail uses existing owner-scoped conversation records. |
| 04 mission control | `src/components/dashboard/widgets/task-pipeline-widget.tsx` | `TaskPipelineWidget` | ADAPTED | `ui/src/components/operations/OperationsPrimitives.tsx` | Pipeline stages map only to real mission statuses. |
| 05 assistant-ui | `packages/ui/src/components/react/assistant-ui/elements/chat-panel.tsx` | `ChatPanel` | ADAPTED | `ui/src/screens/Screens.tsx` | Conversation surface was adopted without Assistant Cloud or donor transport. |
| 05 assistant-ui | `packages/ui/src/components/react/assistant-ui/elements/composer.tsx` | `Composer` | ADAPTED | `ui/src/screens/Screens.tsx` | Accessibility and active-run presentation remain JARVIS-owned. |
| 05 assistant-ui | `packages/ui/src/components/react/assistant-ui/elements/canvas-split.tsx` | `CanvasSplit` | ADAPTED | `ui/src/components/operations/OperationsPrimitives.tsx` | Split-layout language informs chat/context and evidence composition. |
| 05 assistant-ui | `packages/ui/src/components/react/assistant-ui/elements/background-inbox.tsx` | `BackgroundInbox` | ADAPTED | `ui/src/components/operations/OperationsPrimitives.tsx` | Inbox lists only canonical active runs. |
| 06 tool UI | `apps/www/components/tool-ui/approval-card/approval-card.tsx` | `ApprovalCard` | ADAPTED | `ui/src/components/tool-ui/ToolSurfacePrimitives.tsx` | Exact target, risk, preview, and owner controls remain canonical. |
| 06 tool UI | `apps/www/components/tool-ui/plan/plan.tsx` | `Plan` | ADAPTED | `ui/src/components/operations/OperationsPrimitives.tsx` | Mission plan rows render server-reported steps. |
| 06 tool UI | `apps/www/components/tool-ui/progress-tracker/progress-tracker.tsx` | `ProgressTracker` | ADAPTED | `ui/src/components/operations/OperationsPrimitives.tsx` | Progress renders a reported value only; no invented percentage. |
| 06 tool UI | `apps/www/components/tool-ui/data-table/data-table.tsx` | `DataTable` | ADAPTED | `ui/src/components/tool-ui/ToolSurfacePrimitives.tsx` | Skills/capability rows are safe text in a bounded table. |
| 06 tool UI | `apps/www/components/tool-ui/citation/citation.tsx`, `citation-list.tsx` | `Citation`, `CitationList` | ADAPTED | `ui/src/components/tool-ui/ToolSurfacePrimitives.tsx` | Research evidence is rendered from persisted canonical evidence. |
| 06 tool UI | `apps/www/components/tool-ui/code-block/code-block.tsx` | `CodeBlock` | ADAPTED | `ui/src/components/tool-ui/ToolSurfacePrimitives.tsx` | Engineering output is read-only text. |
| 06 tool UI | `apps/www/components/tool-ui/stats-display/stats-display.tsx` | `StatsDisplay` | ADAPTED | `ui/src/components/tool-ui/ToolSurfacePrimitives.tsx` | Engineering counts are derived from reported worker records. |
| 06 tool UI | `apps/www/components/assistant-ui/tool-fallback.tsx` | `ToolFallback` | ADAPTED | `ui/src/components/tool-ui/ToolSurfacePrimitives.tsx` | Unknown results remain inert, safe display data. |

## Distinguishing visual contributions

| Donor | Source inspected | Final decision | Product contribution |
|---|---|---|---|
| 02 JARVIS HUD | `server/hud/index.html`, `docs/ARCHITECTURE.md` | REFERENCE ONLY — technical/runtime boundary | Reactor prominence, layered HUD trace, and activity density; donor WebSocket/weather/voice runtime excluded. |
| 07 cinematic JARVIS | `components/animations/*`, `components/panels/*` | REFERENCE ONLY — no license evidence | Timing, depth, waveform and compositional restraint informed `HolographicCore` and hero treatment; fictional semantics and assets excluded. |
| 08 tactical HUD | `ironman-hud.html` | REFERENCE ONLY — monolithic CDN/WebXR runtime | Gauge, compass, radar, and corner language informed `TacticalHud`; simulated threats, WebXR, and continuous redraw excluded. |
| 09 holographic 3D | `dashboard.html`, `index.html` | REFERENCE ONLY — synthetic graph/identity runtime | Depth rings and pulse language informed `HolographicCore`; synthetic nodes, camera identity, localStorage profiles, and WebGL loop excluded. |

Primary reuse count: 28 exact candidate units re-evaluated; 28 donor-derived
presentation units adapted or wrapped. The remaining 07/08/09 items are
documented visual references because their runtime or licensing boundaries do
not fit the product.
