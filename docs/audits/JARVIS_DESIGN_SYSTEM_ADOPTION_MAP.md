# JARVIS Design System Adoption Map

The supplied ZIP is a visual/component reference. Production state, authority, API contracts, and event handling remain in the repository.

| Design-system component/foundation | Current JARVIS equivalent | Decision | Production source / note |
|---|---|---|---|
| graphite canvas/surfaces | `ui/src/styles.css`, `MatrixFoundation` | ADOPT | CSS tokens; no remote runtime dependency |
| electric blue / burgundy / gold / teal semantic palette | existing cyan/crimson variables and state classes | ADAPT | consolidate into CSS variables; gold only approval/attention |
| Lexend / Rubik / JetBrains Mono hierarchy | existing font stacks | ADAPT | local/system fallbacks; no font download |
| Lucide icon masks | Unicode glyphs in `routes.ts` and shell | ADOPT | copy only required approved SVGs to `ui/src/assets/icons` |
| `JarvisCore` | `CinematicHero`, `HolographicCore`, `JArcReactor` | ADAPT | one semantic Core state, no second runtime |
| `StatusBadge` | `StatusBadge` in `common/Primitives` | ADAPT | unified state vocabulary |
| `Button` / `IconButton` | existing `Button` and shell buttons | ADAPT | semantic elements, focus, aria labels |
| `Panel` / `SectionHeader` | `FramePanel`, `Panel`, `SectionHeading` | MERGE | one surface vocabulary, fewer nested cards |
| `NavRail` | `ContextRail` + `sidebar` in `AppShell` | ADAPT | five primary areas + Approvals/System utilities |
| `TopCommandBar` | `topbar`, `HudBar`, palette trigger | ADAPT | remove raw provider/debug details from global bar |
| `SegmentedControl` | current tab/action controls | ADOPT | Work modes and Memory views |
| `CommandPalette` | `HudCommandPalette` | ADAPT | real route/conversation/memory data |
| `Composer` | Chat `textarea` composer | ADAPT | truthful accepted/working/approval/verified states |
| `InlineAlert` / `Toast` | `global-error`, inline notices | ADAPT | human copy with raw reason in inspector |
| `Skeleton` / `EmptyState` / `Progress` | existing loading/empty components | ADOPT | each major view gets loading/empty/partial states |
| `TaskCard` / `ApprovalCard` | mission/approval surfaces | ADAPT | real projection and approval data |
| `MemoryCard` / `SourceCard` / `ArtifactCard` | `RichMessage`, memory rows, tool surfaces | ADAPT | details collapsed; no fake content |
| `TaskBlock` / `ToolBlock` / `ApprovalBlock` | `RichMessage`, `ToolFallbackSurface`, `ApprovalSurface` | ADAPT | structured results from actual messages/tool activity |
| `Inspector` | no single shared inspector; per-screen details | ADOPT | contextual Work/Memory/System side panel |
| `TimelineItem` / `AuditRow` / `LogRow` | activity and diagnostics rows | ADAPT | System-only technical detail |
| `Sheet` / `VoiceOverlay` | existing settings/action overlays and VoiceCore integration | ADAPT | contextual overlay; no second voice app |
| glass material | existing broad translucent/hud surfaces | REDUCE | only composer, palette, sheets, voice, hero Core frame |
| continuous ambient loops | `AmbientEnergy`, cinematic effects | REDUCE | one Core animation; disable under reduced motion |
| mock UI-kit `data.jsx` and fake runtime | none in production | REJECT | never import demo state or alternate architecture |
| supplied photography | existing owner wallpaper only | REFERENCE + OWNER OVERRIDE | retain wallpaper on Command/Home; do not spread photography |

## Token contract

- Base: `#07090D` / `#0A0D12` graphite.
- Intelligence: electric blue around `#3AA8FF`.
- Identity/consequence: restrained burgundy around `#861F43`.
- Approval/owner attention: dark gold around `#C99B46`.
- Independently verified: teal around `#37C8A3`.
- Failure: muted red around `#DB536A`.
- Motion: 150ms micro, 260ms standard, 340ms panel, 380ms sheet; transform/opacity first; reduced motion freezes continuous motion.

## Component adoption rule

Every adapted component must consume current typed API/projection data, preserve keyboard/focus behavior, and leave technical detail in an inspector or expandable region. A design-system component that requires mock data or a second event/store authority is rejected.
