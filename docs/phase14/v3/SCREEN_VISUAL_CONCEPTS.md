# Phase 14 V3 Screen Visual Concepts & Motion Specifications

This document defines the screen visual metaphors, motion choreography, reactor concept comparisons, and text reduction audit for the delegated Packages A-E of the Phase 14 V3 correction.

---

## 1. Route Visual Metaphors

| Route | Dominant Visual Metaphor | Primary Color Energy | Cinematic Movement | Canonical Data Anchor |
|---|---|---|---|---|
| `/` (Home) | **Cinematic Command Center** — Layered Iron Man hero scene with unobtrusive holographic chest halo, pulse network, and floating readouts | JARVIS Cyan (`#55D9FF`) + Hot Crimson (`#C40B2E`) | Parallax wallpaper drift, sweeping scanline, breathing core halo | Real projection `system`, `presence`, `missions`, `approvals`, `timeline` |
| `/chat` | **Holographic Neural Exchange** — Conversational stream with reactive waveform core, readable message bubbles, formatted code blocks, and expandable tool activity telemetry | Cyan (`#55D9FF`) + Ice Blue (`#96D8EE`) | Dynamic waveform frequency response (18 height bars), message entrance slide-up, tool expand/collapse transition | Real `/conversations`, `/conversations/:id/messages`, and `/runs/:id/activity` |
| `/missions` | **Tactical Operations Grid** — 4-stage execution pipeline (`planning`, `active`, `review`, `closed`), step-by-step plan connector list, and tick progress tracks | Cyan (`#55D9FF`) + Dark Cherry (`#7D0D20`) | Pipeline dot glow pulse (1.8s), active step highlight, tick progress transition | Real `missions` array from runtime projection and `/missions/:id/:action` |
| `/memory` | **Personal Knowledge Lattice** — Calm inspect/edit/delete durable knowledge cards, segmented confidence meter, and sensitivity categorization | Ice Blue (`#96D8EE`) + JARVIS Cyan (`#55D9FF`) | Card hover elevation, segmented confidence fill, modal fade-in | Real `/memory`, `/memory/:id` PATCH/DELETE, and canonical projection |
| `/context` | **Situational Environment Matrix** — Directional focus-window vector compass, active application presence, bounded facts ledger, and home controller connection | Steel Blue (`#3C6497`) + JARVIS Cyan (`#55D9FF`) | Compass degree indicator, bounded facts row hover, status dot pulse | Real `presence`, `devices`, `home`, and `/context` endpoint |
| `/operations` | **Personal Command Surface** — Real-time operational mode cockpit, focus session tracker, automation rules grid, and follow-up attention matrix | Armor Navy (`#15254E`) + JARVIS Cyan (`#55D9FF`) | Status badge glow, mode transition fade, compact row hover state | Real `operations.mode`, `focus`, `automations`, and `follow_ups` projection data |
| `/research` | **Evidence Ledger** — Persisted research run lifecycle, query search bar, grounded citations viewer, and cancel control | Steel Blue (`#3C6497`) + Ice Blue (`#96D8EE`) | Evidence panel slide-down, search button state transition | Real `/research/runs`, `/research/runs/:id/evidence`, and cancellation endpoint |
| `/engineering` | **Read-Only Developer Terminal** — Worker delegation grid, aggregated artifact telemetry, read-only code surface, and fallback card | Armor Navy (`#15254E`) + JARVIS Cyan (`#55D9FF`) | Monospace code block scroll, status badge pulse | Real `worker_delegations` and `engineering` projection items |
| `/browser` | **Safe Capability Boundary** — Polished deferred capability surface, explicit permission notice, and direct approval route link | Spark (`#F29361`) + Plum (`#1E0C1D`) | Deferred icon glow, smooth route transition | Real browser service availability state and `/approvals` |
| `/skills` | **Capability Registry** — Policy-controlled capability registry, risk-classified skills, source metadata, and instant enablement toggles | Cyan (`#55D9FF`) + Hot Crimson (`#C40B2E`) | Card hover elevation, enable/disable toggle transition | Real `skills` projection array and `/skills/:id/:action` |
| `/devices` | **Tactical Device Fabric** — Multi-ring device radar, registered field compass summary, and backend-verified device capability cards | JARVIS Cyan (`#55D9FF`) + Spark (`#F29361`) | Tactical radar 5.0s sweep rotation, device point glowing pips | Real `devices` array and `home` status from canonical projection |
| `/notifications` | **Attention Stream** — Filtered notice stream (`all`, `unread`, `important`, `proactive`, `system`), severity markers, and dismiss actions | Signal Crimson (`#EA2F42`) + Spark (`#F29361`) | Filter tab transition, notification dismiss fade-out | Real `notifications` projection array and `/notifications/:id/dismiss` |
| `/approvals` | **Consequential Action Checkpoint** — High-contrast decision cockpit with impact boundaries | Signal Crimson (`#EA2F42`) + Spark (`#F29361`) | Attention beacon pulse (1.2s), alert border glow | Real `approvals` array with pending status filters |
| `/activity` | **Runtime Audit Timeline** — Chronological audit ledger with severity markers, timestamp metadata, and redacted payloads | Armor Blue (`#18386A`) + JARVIS Cyan (`#55D9FF`) | Timeline stream scroll, event marker status glow | Real `timeline` projection array |
| `/settings` | **Operational Truth & Diagnostics** — Calm system health, local model availability, discovered MCP servers, privacy center boundary, and voice waveform | Armor Blue (`#18386A`) + Reactor White (`#E4EDEF`) | JWaveform frequency bars, MCP status pulse | Real `system`, `voice`, `/health`, and `/personalization/profile` |

---

## 2. State Motion & Choreography

The visual system translates canonical runtime states (`deriveVisualState`) into distinct CSS animation tempos, glow intensities, and color energies without fabricating artificial telemetry:

| Visual State | Core Spin Speed | Core Pulse Period | Waveform Activity | Dominant Hue | Accent Hue | Tactical Behavior |
|---|---|---|---|---|---|---|
| `ready` | 8.0s | 2.4s | Inactive (flat) | JARVIS Cyan (`#55D9FF`) | Crimson Shadow (`#610817`) | Calm breathing, smooth ambient energy spark drift |
| `thinking` | 2.0s | 1.2s | Dynamic active bars | Ice Blue (`#96D8EE`) | Hot Crimson (`#C40B2E`) | Accelerated inner-ring rotation, energetic core glow |
| `tool` | 3.0s | 1.5s | Active directional bars | Signal Crimson (`#EA2F42`) | JARVIS Cyan (`#55D9FF`) | Directional pulse links, active radar ping highlights |
| `researching` | 3.0s | 1.8s | Steady wave pulse | JARVIS Cyan (`#55D9FF`) | Steel Blue (`#3C6497`) | Radar sweep accelerated, node pulse link traversal |
| `waiting_approval` | 4.0s | 1.0s (alert) | Checkpoint pause | Spark (`#F29361`) | Signal Crimson (`#EA2F42`) | Attention badge glowing beacon, high-contrast border |
| `speaking` | 4.0s | 1.6s | Audio-frequency reactive | JARVIS Cyan (`#55D9FF`) | Ice Blue (`#96D8EE`) | Waveform oscillation across 18 height steps |
| `degraded` | 12.0s | 3.6s | Muted minimum bars | Ember (`#DA4F2E`) | Wine Black (`#2F0A16`) | Subdued motion, reduced glow opacity |
| `offline` | Static (0s) | Inactive (0s) | Disabled (0px) | Steel Blue (`#3C6497`) | Void (`#0C060E`) | Static freeze, clear "LOCAL ONLY" indicators |
| `error` | 1.5s | 0.8s | Static warning | Signal Crimson (`#EA2F42`) | Deep Burgundy (`#4E0715`) | Fast warning pulse, high-priority notification banner |

---

## 3. Small Reactor Treatment Evaluation & Selection

Three distinct non-obtrusive reactor treatments were evaluated to solve the owner rejection of the previous oversized, opaque chest circle:

### Concept A: Chest Halo
- **Structure**: Concentric transparent SVG energy rings tightly aligned with the chest reactor in the wallpaper artwork.
- **Visual Footprint**: 132px diameter, 100% transparent center with zero opaque backgrounds.
- **Strengths**: Keeps Iron Man's armor artwork fully visible; delicate 12-tick geometry and rotating dashed tracks create a living technological aura.
- **Donor Adaptation**: Donor 03 `JOrb` (12 ticks at 30° angles) + Donor 07 `ArcReactor` (3 energy arms at 120°).

### Concept B: Offset JARVIS Orb
- **Structure**: Standalone holographic orb floating beside Iron Man's shoulder with an offset light trace leading to the suit.
- **Visual Footprint**: 110px floating orb in the upper-right or center-right quadrant.
- **Strengths**: Completely separates the HUD overlay from the wallpaper artwork.
- **Weakness**: Creates visual competition with the natural chest focal point of the artwork.

### Concept C: Reactor-Origin HUD Traces
- **Structure**: No central circular geometry; instead, data arcs, pulse links, and holographic scanlines radiate directly outward from the natural chest reactor in the wallpaper.
- **Visual Footprint**: Line and node network spanning across the hero scene.
- **Strengths**: Highly cinematic and integrated with the wider HUD.

### Selection Rationale: The Winner (Hybrid Concept A+C)
The implemented solution is **Concept A (Chest Halo) integrated with Concept C (Origin HUD Traces)**:
1. **Zero suit obstruction**: The center core is completely transparent (`fill="none"` on outer tracks, soft radial gradient on the 6px center node), ensuring the painted chest reactor on Iron Man remains the visual hero.
2. **True state reactivity**: Rotation speed dynamically changes from 8s (ready) to 2s (thinking) to 1.5s (error); core glow shifts between cyan, ice blue, spark amber, and signal crimson based on canonical state.
3. **Integrated telemetry traces**: Radial traces (`.reactor-trace.trace-left`, `.reactor-trace.trace-right`) emit energy directly into the `PulseNetwork` and contextual data arcs.

---

## 4. Text & Microcopy Reduction Audit

To resolve the owner rejection regarding "too much developer copy and micro-labels," a comprehensive copy reduction was implemented across all routes:

| Surface | Rejected Prior Copy | Corrected V3 Copy | Reduction Impact |
|---|---|---|---|
| **Home Hero Title** | `jarvis-local-qwen` (model alias displayed as main identity) | `JARVIS` (Primary headline; model details strictly in Diagnostics/Settings) | Clear assistant identity without technical model labels |
| **Home Hero Subtitle** | "The local operating picture: runtime state, current work, and owner attention in one calm surface." | "Live command center and operational picture." | 65% reduction in word count |
| **Home Subtitle Lede** | "Runtime connected to the local application boundary." | "All systems nominal." (or offline notice when disconnected) | Concise, owner-facing status |
| **Chat Header Subtitle** | "The text path reaches the same local AgentRuntime, context, tools, permissions, and approvals." | "Direct communication with local intelligence." | 60% reduction in technical jargon |
| **Chat Composer Footer** | "Enter a message · no cloud provider" | "Local runtime · Private boundary" | Concise boundary confirmation |
| **Missions Header Subtitle** | "Bounded work already owned by the canonical mission and goal services." | "Tactical operations grid and execution tracking." | Replaced service documentation with owner-ready status |
| **Operations Header Subtitle** | "Modes, focus, briefings, automations, and follow-ups from the existing authorities." | "Real-time mode, focus state, automations, and follow-ups." | Clean operational cockpit focus |
| **Memory Header Subtitle** | "Inspect durable accepted knowledge." | "Durable accepted knowledge separate from observations." | Direct owner focus |
| **Context Header Subtitle** | "Fresh, bounded observations from perception, presence, workspace, and world-state services." | "Fresh bounded observations from perception and presence." | Removed developer-focused caveats |
| **Devices Header Subtitle** | "Actual registered device and home-controller state. A device is never marked live without backend evidence." | "Actual registered device and home-controller state." | Clean operational picture |
| **Research Header Subtitle** | "Persisted research runs and evidence. Web access remains explicit when the provider is unavailable." | "Persisted research runs and grounded evidence." | Focused evidence ledger copy |
| **Engineering Header Subtitle** | "Read-only worker and engineering-session state. Terminal streaming remains intentionally deferred." | "Read-only worker and session telemetry." | Truthful developer surface copy |
| **Browser Header Subtitle** | "Browser work remains behind the existing browser authority, session, permission, and approval policy." | "Safe capability boundary and approvals." | Direct capability boundary copy |
| **Skills Header Subtitle** | "Installed skill metadata from the product-owned registry. Enablement and execution remain policy-controlled." | "Policy-controlled capabilities and registry." | Clear capability registry copy |
| **Notifications Header Subtitle** | "Unread, proactive, and system notices from the existing notification service." | "Unread, proactive, and system notices." | Streamlined notification focus |
| **Approvals Header Subtitle** | "Consequential actions remain backend-authoritative. Each decision is owner-scoped, CSRF-protected, and audited." | "Consequential actions and decision checkpoint." | Focused owner checkpoint copy |
| **Activity Header Subtitle** | "A readable owner-facing timeline. Sensitive payloads are redacted before reaching this projection." | "Readable owner-facing runtime audit timeline." | Clean audit copy |
| **Settings Header Subtitle** | "Operational truth, privacy controls, and safe product surfaces for the local runtime." | "Operational truth, health, and privacy controls." | Truthful diagnostics copy |
| **Approval Card Header** | `OWNER QUEUE` / "Consequential actions will appear here with a sanitized preview." | `ATTENTION` / "You're all clear." | Removed developer jargon ("sanitized preview") |
| **Spine Card Header** | `REAL-TIME PROJECTION` / `SOURCE-OWNED` / `BOUNDED FACTS` | `SYSTEM` / "Local capability spine" | Eliminated redundant architecture labels |
| **Missions Card Header** | `MISSION SERVICE` / "Create bounded work through the canonical mission service." | `MISSIONS` / "Ready for new instructions." | Replaced service documentation with owner-ready status |
| **Activity Card Header** | `EVENT PROJECTION` | `ACTIVITY` / "Recent activity" | Natural presentation copy |
| **Health Card Header** | `LOCAL-FIRST` | `DIAGNOSTICS` / "Diagnostics" | Standardized nomenclature |
| **Context Dock Default** | "Not observed" (repeated 6 times across columns) | "Waiting for context" | Graceful sparse state wording |
