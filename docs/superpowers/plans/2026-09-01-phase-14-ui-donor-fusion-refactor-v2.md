# Phase 14 UI Donor-Fusion Refactor V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the generic Phase 14 dashboard presentation with a premium, wallpaper-led JARVIS Command Center while preserving every existing backend, session, event, approval, and capability authority.

**Architecture:** Keep the existing React 19 + TypeScript + Vite + React Router client and its `useJarvis` API/event boundary. Add product-owned presentation adapters that incorporate file-level donor-derived visual primitives from Matrix, JARVIS UI, Mission Control, Assistant UI, Tool UI, Cinematic, Tactical, and Holographic sources; adapters receive only canonical projection or screen data and never own transport, persistence, identity, execution, or approval truth.

**Tech Stack:** React 19, TypeScript, Vite, React Router, local CSS/SVG, supplied local Iron Man JPG, Vitest, Testing Library. No CDN, cloud UI runtime, donor backend, WebGL/WebXR scene, AntiGravity runtime, or second AgentRuntime.

**Spec:** `C:\Users\mahmo\Downloads\JARVIS_PHASE_14_UI_DONOR_FUSION_REFACTOR_V2_WALLPAPER_PALETTE.md`

## Global Constraints

- Preserve the existing `CoreApplication`, `AgentRuntime`, `ModelGateway`, local Qwen/llama.cpp, ToolRegistry, permissions, approvals, audit, memory, mission, research, browser, skills, projection, EventBus, desktop lifecycle, session, CSRF, and bootstrap authorities.
- Treat all donor source as presentation input only; do not import donor stores, routes, mock data, backend calls, cloud services, identity, WebSocket, voice, or execution code.
- Use the local owner wallpaper exactly as supplied, copy it into the frontend asset tree, and do not fetch another image.
- Use the mandated wallpaper tokens: `#0C060E`, `#1E0C1D`, `#2F0A16`, `#C40B2E`, `#EA2F42`, `#55D9FF`, and `#96D8EE`.
- Green is limited to tiny semantic success indicators; recoverable errors use neutral/amber presentation and human-readable copy.
- Meaningful visual state must come from JARVIS projection/API data; animations may visualize state but may not invent it.
- Keep frontend assets local and support keyboard focus, semantic controls, readable contrast, bounded motion, reduced motion, and responsive widths.
- Do not modify `C:\Jarivs\14_ui_candidates` or the protected Phase 10 evidence file.

---

### Task 1: Establish the donor extraction and visual-system evidence

**Files:**
- Create: `docs/phase14/ui-refactor/DONOR_EXTRACTION_MANIFEST.md`
- Create: `docs/phase14/ui-refactor/VISUAL_SYSTEM_V2.md`
- Create: `docs/phase14/ui-refactor/ANTIGRAVITY_BASELINE_REVIEW.md`
- Create: `docs/phase14/ui-refactor/BEFORE_AFTER_REVIEW.md`
- Modify: `docs/THIRD_PARTY_INVENTORY.md`
- Test: `ui/src/screens/ui-closure.test.tsx`

**Interfaces:**
- Consumes: the existing `docs/phase14/UI_DONOR_SALVAGE_MAP.md`, all nine donor directories, the supplied wallpaper, and current UI baseline.
- Produces: a 28-candidate disposition table, exact donor file attribution, token contract, baseline/after evidence, and explicit AntiGravity-unavailable note without any delegated implementation.

- [ ] **Step 1: Write the failing acceptance assertions**

Add assertions for the wallpaper asset path, mandatory token names, and donor manifest destination so later UI integration cannot silently omit the visual-system contract.

- [ ] **Step 2: Run the focused frontend test**

Run: `npm.cmd test -- --run ui/src/screens/ui-closure.test.tsx`

Expected: FAIL because the asset, token contract, and manifest evidence do not yet exist.

- [ ] **Step 3: Create the evidence and documentation**

Record all 28 original candidates, plus donor 07/08/09 visual contributions, with one of the allowed dispositions and a concrete technical reason. Record that the nine repositories were inspected, AntiGravity was not invoked under the workspace no-delegation rule, and no raw tool/auth logs are stored.

- [ ] **Step 4: Run the focused frontend test**

Run: `npm.cmd test -- --run ui/src/screens/ui-closure.test.tsx`

Expected: PASS for the documentation/asset contract assertions.

- [ ] **Step 5: Review the evidence**

Run: `rg -n -i "TODO|TBD|easier to write custom|reference only" docs/phase14/ui-refactor`

Expected: only technically justified reference-only entries remain; no placeholder or convenience-only disposition exists.

### Task 2: Add the local wallpaper asset and unified visual tokens

**Files:**
- Create: `ui/src/assets/hero/ironman-owner-wallpaper.jpg`
- Modify: `ui/src/styles.css`
- Modify: `ui/src/index.html`
- Test: `ui/src/screens/ui-closure.test.tsx`

**Interfaces:**
- Consumes: the existing `ui/src/styles.css` and supplied `C:\Users\mahmo\Pictures\ironman-owner-wallpaper.jpg`.
- Produces: `--bg-0`, `--bg-1`, `--bg-2`, `--surface-0`, `--surface-1`, `--surface-cool`, `--energy-primary`, `--energy-soft`, `--energy-red`, `--energy-red-hot`, `--energy-ember`, `--text-primary`, `--text-secondary`, `--text-muted`, `--line-neutral`, `--line-active`, and `--line-red-energy`; local typography declarations and reduced-motion rules.

- [ ] **Step 1: Write the failing token and asset assertions**

Assert that the rendered shell references the local wallpaper asset and that the CSS contains the mandatory token values and `prefers-reduced-motion` rule.

- [ ] **Step 2: Run the focused frontend test**

Run: `npm.cmd test -- --run ui/src/screens/ui-closure.test.tsx`

Expected: FAIL because the local asset and token values are absent.

- [ ] **Step 3: Add the exact local asset and tokens**

Copy only the supplied JPG to `ui/src/assets/hero/ironman-owner-wallpaper.jpg`. Refactor the token block and dependent selectors to the wallpaper system while retaining `#55D9FF` as the primary interaction color. Use sans-serif body typography and mono only for bounded telemetry/code.

- [ ] **Step 4: Run the focused frontend test and production build**

Run: `npm.cmd test -- --run ui/src/screens/ui-closure.test.tsx; npm.cmd run build`

Expected: PASS and a successful Vite build with the local JPG included.

- [ ] **Step 5: Check external asset safety**

Run: `rg -n -i "fonts\.googleapis|cdnjs|unpkg|jsdelivr|https?://" ui/src ui/index.html`

Expected: no new remote runtime assets or CDN imports.

### Task 3: Adapt Matrix and JARVIS HUD foundation primitives

**Files:**
- Create: `ui/src/components/foundation/MatrixFoundation.tsx`
- Create: `ui/src/components/hud/DonorFusion.tsx`
- Modify: `ui/src/components/hud/JArcReactor.tsx`
- Modify: `ui/src/components/hud/JHudFrame.tsx`
- Modify: `ui/src/components/layout/AppShell.tsx`
- Modify: `ui/src/components/common/Primitives.tsx`
- Test: `ui/src/screens/ui-closure.test.tsx`

**Interfaces:**
- Consumes: adapted donor 01 `MatrixShell`, `MatrixExtras`, `DataVizComponents`; donor 02 HUD language; donor 03 `JHudFrameCard`, `JHudBar`, `JOrb`, `JActivityFeed`, `JKPITicker`, `JCommandPalette`, `JBootScreen`, `JArcReactor`, `JWaveform`.
- Produces: `MatrixFoundation`, `HudBar`, `HudFrameCard`, `HudOrb`, `HudActivityFeed`, `HudKpiTicker`, `HudCommandPalette`, `HudBootScreen`, and bounded `TrendSparkline`/`StatusSignal` adapters with product-owned data props.

- [ ] **Step 1: Add failing donor-adapter and shell assertions**

Assert that the shell renders a `JHudBar`-derived status surface, a command palette with routes/capabilities, and a compact calm recovery notice instead of the current prominent red runtime strip.

- [ ] **Step 2: Run the focused frontend tests**

Run: `npm.cmd test -- --run ui/src/screens/ui-closure.test.tsx ui/src/screens/final-closure.test.ts ui/src/screens/residual-closure.test.tsx`

Expected: FAIL on the new donor-fusion selectors/copy.

- [ ] **Step 3: Implement the adapters**

Copy/adapt only self-contained presentation markup and styles. Remove donor imports for i18n, mock data, stores, backend, and timers that simulate state. Feed activity, KPI, connection, boot, and command rows from `useJarvis` values. Map `principal_not_found`, reconnecting, and offline notices to human-readable neutral/amber copy while keeping raw details in an accessible diagnostic attribute or advanced section.

- [ ] **Step 4: Run the focused frontend tests**

Run: `npm.cmd test -- --run ui/src/screens/ui-closure.test.tsx ui/src/screens/final-closure.test.ts ui/src/screens/residual-closure.test.tsx`

Expected: PASS with the existing route and session semantics preserved.

- [ ] **Step 5: Review donor provenance**

Run: `rg -n "Source:|Adapted from|DONOR|Matrix|JHudBar|JOrb|JKPITicker|JActivityFeed" ui/src/components`

Expected: exact donor source attribution exists in each adapted module and no donor repository path is imported at runtime.

### Task 4: Build donor-derived rich chat, operations, tool, and evidence primitives

**Files:**
- Create: `ui/src/components/chat/RichChatPrimitives.tsx`
- Create: `ui/src/components/operations/OperationsPrimitives.tsx`
- Create: `ui/src/components/tool-ui/ToolSurfacePrimitives.tsx`
- Modify: `ui/src/screens/Screens.tsx`
- Test: `ui/src/screens/ui-closure.test.tsx`
- Test: `ui/src/screens/residual-closure.test.tsx`

**Interfaces:**
- Consumes: canonical `screenData`, `projection`, `api`, and existing `useJarvis`; donor 04 chat/composer/message/conversation/approval/pipeline files; donor 05 ChatPanel/Composer/CanvasSplit/BackgroundInbox; donor 06 ApprovalCard/Plan/ProgressTracker/MessageDraft/DataTable/Citation/CitationList/CodeBlock/CodeDiff/StatsDisplay/ToolFallback.
- Produces: presentation-only components `ConversationRail`, `RichMessage`, `RichComposer`, `RunInbox`, `MissionPipeline`, `ApprovalSurface`, `PlanSurface`, `ProgressSurface`, `CitationSurface`, `CodeSurface`, `StatsSurface`, `ToolFallbackSurface`, and `EvidenceTable`.

- [ ] **Step 1: Add failing component-contract assertions**

Assert that Chat exposes conversation navigation, readable messages, run state, cancel, inline tool activity, and empty state; Missions exposes pipeline/plan/progress framing; Research exposes evidence/citations; Engineering exposes code-safe output; Approvals exposes exact target/risk/actions.

- [ ] **Step 2: Run the focused frontend tests**

Run: `npm.cmd test -- --run ui/src/screens/ui-closure.test.tsx ui/src/screens/residual-closure.test.tsx`

Expected: FAIL for the new rich presentation contracts.

- [ ] **Step 3: Implement the primitives and screen mappings**

Preserve existing API calls and run cancellation. Render all model/tool/research content as safe text or bounded markdown/code text; never use donor cloud transports or raw JSON as the primary presentation. Use server-reported statuses only, and keep approval buttons disabled while deciding.

- [ ] **Step 4: Run the focused frontend tests**

Run: `npm.cmd test -- --run ui/src/screens/ui-closure.test.tsx ui/src/screens/residual-closure.test.tsx`

Expected: PASS with current API mock contracts unchanged.

- [ ] **Step 5: Check authority boundaries**

Run: `rg -n -i "AgentRuntime|WebSocket|localStorage|Anthropic|OpenAI|Gemini|Assistant Cloud|fetch\(|axios|zustand|store" ui/src/components/chat ui/src/components/operations ui/src/components/tool-ui`

Expected: only existing JARVIS adapters and safe display code remain; no donor runtime or second authority is introduced.

### Task 5: Add cinematic, tactical, and holographic lightweight visual contributions

**Files:**
- Create: `ui/src/components/visuals/CinematicDepth.tsx`
- Create: `ui/src/components/visuals/TacticalHud.tsx`
- Create: `ui/src/components/visuals/HolographicCore.tsx`
- Modify: `ui/src/screens/Screens.tsx`
- Modify: `ui/src/styles.css`
- Test: `ui/src/screens/ui-closure.test.tsx`

**Interfaces:**
- Consumes: real `presence`, `devices`, `missions`, `system`, `operations`, `voice`, and `mcp` projection data; donor 07 timing/depth references; donor 08 gauge/compass/radar functions; donor 09 depth rings/node pulse concepts.
- Produces: bounded SVG/CSS `CinematicDepth`, `TacticalRadar`, `ContextCompass`, `SystemGauge`, and `HolographicCore` components with no fictional threat/weapon/biometric semantics.

- [ ] **Step 1: Add failing visual state assertions**

Assert that Home has a visible hero image/core composition, Context and Devices have tactical visual elements, and reduced-motion mode disables nonessential animated classes.

- [ ] **Step 2: Run the focused frontend tests**

Run: `npm.cmd test -- --run ui/src/screens/ui-closure.test.tsx`

Expected: FAIL because the new visual roles are absent.

- [ ] **Step 3: Implement bounded visuals**

Use CSS/SVG and a bounded number of DOM nodes. Bind labels and values to real projection data. Keep the hero image to Home (and optional boot/reconnect), blend it with dark plum overlays/vignette, and never repeat it as a literal background on every route.

- [ ] **Step 4: Run tests and build**

Run: `npm.cmd test -- --run ui/src/screens/ui-closure.test.tsx; npm.cmd run build`

Expected: PASS and successful build without WebGL/WebXR or continuous high-cost loops.

- [ ] **Step 5: Check responsive and motion rules**

Run: `rg -n "prefers-reduced-motion|@media|overflow-x|hero-art|tactical|radar|compass" ui/src/styles.css ui/src/components ui/src/screens`

Expected: laptop stacking/collapse and reduced-motion rules are present.

### Task 6: Refactor all routes and launch/error UX without changing authorities

**Files:**
- Modify: `ui/src/screens/Screens.tsx`
- Modify: `ui/src/components/layout/AppShell.tsx`
- Modify: `ui/src/app/App.tsx`
- Modify: `ui/src/app/routes.ts`
- Modify: `ui/src/screens/ui-closure.test.tsx`
- Modify: `ui/src/screens/final-closure.test.ts`
- Modify: `ui/src/screens/residual-closure.test.tsx`

**Interfaces:**
- Consumes: Tasks 2–5 presentation primitives and existing route/API contracts.
- Produces: immersive Home; rich Chat; mission pipeline; memory inspector; tactical Context/Devices; evidence-first Research; safe Engineering/Browser/Skills; grouped Notifications/Approvals/Activity; calmer Settings; second-launch focus behavior where the existing lifecycle supports it.

- [ ] **Step 1: Add failing route-level assertions**

Cover navigation, empty states, `principal_not_found` copy, Phase 15 capability health, approval/action semantics, command palette search, route responsiveness classes, and no raw error-code primary presentation.

- [ ] **Step 2: Run all frontend tests**

Run: `npm.cmd test -- --run`

Expected: FAIL only on the new route-level contracts.

- [ ] **Step 3: Refactor screens behind adapters**

Keep the current API calls and route paths. Use the new primitives to compose screens with hierarchy rather than identical cards. Keep lists bounded, avoid fake metrics/progress, preserve all existing semantic labels, and avoid changing backend code.

- [ ] **Step 4: Run all frontend tests**

Run: `npm.cmd test -- --run`

Expected: PASS.

- [ ] **Step 5: Build and inspect route assets**

Run: `npm.cmd run build; rg -n -i "google|cdn|cloud|antigravity|openflow|refresh_token|cookie" ui/src src/jarvis/ui_static`

Expected: build passes and only intentional local safety/diagnostic text is present.

### Task 7: Execute final visual/product/security gates and document closure

**Files:**
- Create: `docs/phase14/ui-refactor/ANTIGRAVITY_FINAL_REVIEW.md`
- Create: `docs/audits/PHASE_14_UI_DONOR_FUSION_REFACTOR.md`
- Modify: `docs/phase14/ui-refactor/BEFORE_AFTER_REVIEW.md`
- Modify: `docs/phase14/ui-refactor/VISUAL_SYSTEM_V2.md`
- Modify: `docs/THIRD_PARTY_INVENTORY.md`

**Interfaces:**
- Consumes: final frontend, all test/build outputs, local screenshots where available, exact donor adaptation list, and security scans.
- Produces: auditable handoff with actual donor units/reuse mix, wallpaper evidence, route status, AntiGravity-unavailable status, test counts, and clean Git handoff.

- [ ] **Step 1: Run frontend and Python verification**

Run:

```text
npm.cmd test -- --run
npm.cmd run build
npm.cmd audit --audit-level=high
python -m pytest -q
python -m compileall src tests
git diff --check
```

Expected: every command exits 0; record actual counts rather than estimates.

- [ ] **Step 2: Run safety and authority scans**

Run:

```text
rg -n -i "antigravity|openflow|google oauth|google token|refresh_token|browser cookie auth|AgentRuntime|WebSocket" ui/src src/jarvis docs/phase14/ui-refactor
rg -n -i "https?://|fonts\.googleapis|cdnjs|unpkg|jsdelivr" ui/src ui/index.html src/jarvis/ui_static
```

Expected: no runtime AntiGravity/OpenFlow/Google auth, no credential material, no new remote UI assets, and only existing canonical authority references.

- [ ] **Step 3: Complete visual review evidence**

Review Home at 1366×768 and 1920×1080 plus Chat, Missions, Research, Devices, and Settings at laptop and narrow widths. Record hierarchy, donor components visible, green reduction, calm recoverable errors, typography, hero blending, and any unavailable live backend state honestly.

- [ ] **Step 4: Review the full diff**

Run: `git diff --stat; git diff --check; git status --short`

Expected: only intended UI/docs/assets/tests are changed; no donor repositories, protected evidence, duplicate authorities, backend architecture, or broad SQL cleanup appear.

- [ ] **Step 5: Commit once and push**

Use one coherent commit after all gates:

```text
refactor(ui): fuse donor presentation and wallpaper visual system
```

Then run:

```text
git push origin main
```

- [ ] **Step 6: Verify remote equality and clean worktree**

Run:

```powershell
$local = git rev-parse HEAD
$remote = git ls-remote origin refs/heads/main | ForEach-Object { ($_ -split '\s+')[0] }
if ($local -ne $remote) { exit 1 }
if (git status --porcelain) { exit 1 }
```

Expected: local HEAD equals remote `main` and the worktree is clean. Stop before Phase 16.
