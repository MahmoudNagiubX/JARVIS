# JARVIS Full-Stack Product Integration Review

## Review basis

- Baseline: `f3e6575a8032ae73b88b8bbdbede9791e75636b0`
- Branch: `feature/jarvis-final-completion`
- Baseline push: local `HEAD` equals `origin/feature/jarvis-final-completion`.
- Canonical boundary: authenticated owner/device session → `AgentRuntime` → typed capability → permission/autonomy/risk → approval when required → canonical service → adapter → verification → audit/event/result.
- Design reference: supplied `JARVIS Design System.zip`; its mock data and alternate runtime are not production dependencies.

## Product target

JARVIS will present one calm, dark-first operating surface with five primary areas:

1. Command
2. Converse
3. Work
4. Memory
5. Automations

Approvals and System remain global utilities. Existing capabilities are remapped into those areas; compatibility routes remain until the new homes are proven.

The Command/Home hero keeps the owner-selected Iron Man wallpaper as a deliberate exception to the design system's no-photography guidance. It is used only in Command, with a readable crop and restrained graphite/blue/burgundy treatment.

## Current integration findings

| ID | Finding | Severity | Status | Evidence / boundary |
|---|---|---:|---|---|
| INT-001 | Existing frontend has many top-level destinations instead of the five-area IA. | P2 | Planned for refactor | `ui/src/app/routes.ts`, `ui/src/app/App.tsx` |
| INT-002 | Existing screen data is real and authenticated, but capability homes are fragmented across routes. | P1 | Planned for remap | `ui/src/screens/Screens.tsx`, `src/jarvis/api/http.py` |
| INT-003 | High-confidence native app opens currently reach the normal model/tool loop from chat. | P1 | Planned for fast path | `src/jarvis/agents/runtime/runtime.py`, `src/jarvis/tools/registry.py` |
| INT-004 | Installed-app resolution, permissions, native launch, window readback, audit, and event boundaries already exist. | P0 | KEEP | `src/jarvis/computer/applications.py`, `src/jarvis/computer/service.py`, `src/jarvis/tools/service.py` |
| INT-005 | Home retains real projection data and the approved wallpaper, but copy and hierarchy are debug-dashboard oriented. | P2 | Planned for refactor | `ui/src/screens/Screens.tsx`, `ui/src/components/cinematic/CinematicHero.tsx` |
| INT-006 | Browser session/bootstrap and HTTP/1.1 WebSocket fixes must remain unchanged. | P0 | KEEP / regression covered | commits `4ce6291`, `f3e6575` |
| INT-007 | Frontend API client already centralizes CSRF and same-origin credentials. | P0 | KEEP | `ui/src/lib/api.ts` |
| INT-008 | Projection/EventBus is the live state source; UI must not introduce a second runtime/store authority. | P0 | KEEP | `ui/src/app/App.tsx`, `ui/src/lib/events.ts` |
| INT-009 | Existing route screens provide useful capability coverage but need truthful loading/empty/partial/unverified language. | P1 | Planned for refactor | `ui/src/screens/Screens.tsx` |
| INT-010 | No broad UI asset or remote-font dependency is required; the supplied icon/token assets can be copied selectively. | P2 | Planned | design-system ZIP, `ui/package.json` |

## Approved implementation plan

### Task 1 — Audit artifacts and contract inventory

Files: the five documents in `docs/audits/` named by the master task.

Steps:

1. Map each current route, component, read/mutation endpoint, projection/event source, auth/CSRF requirement, and canonical service.
2. Classify each surface as KEEP, MOVE, MERGE, COLLAPSE INTO INSPECTOR, SYSTEM-ONLY, or REMOVE AS DEAD/DUPLICATE.
3. Record the design-system adoption decision for every reused primitive.
4. Record known UI gaps and their test/acceptance owner.
5. Record native-action timing fields and measurement boundaries.

Exit evidence: no screen or existing capability is deleted without a row explaining the reason and compatibility path.

### Task 2 — Server-side native app fast path

Files:

- Create `src/jarvis/agents/routing/native_app_fast_path.py`.
- Modify `src/jarvis/agents/runtime/runtime.py`.
- Modify `src/jarvis/bootstrap.py` only to inject the existing registry into the classifier seam.
- Add focused tests under `tests/`.

The classifier accepts only these grammar families:

- `Open <known app>`
- `Launch <known app>`
- `Start <known app>`
- `افتح <known app>`
- `شغل <known app>`

The target must be one bounded app-name phrase with no compound conjunction, URL, path, shell metacharacter, or extra instruction. It resolves through `InstalledApplicationRegistry` to an opaque `app_ref` before calling `ToolExecutionService.execute("computer.open_application", {"app_ref": app_ref}, ...)`.

The fast path runs only after `prepare_text` has created the authenticated owner/device-bound run. It records monotonic timings in the run's structured result/event payload, then either:

- completes with a truthful verified/unverified message;
- pauses for the existing approval boundary; or
- declines the fast path and lets the normal model/tool loop handle the request.

It never invokes a general LLM for a high-confidence match, never accepts a model-supplied executable path, and never bypasses permission, approval, audit, or verification.

Required timing fields: `request_received`, `intent_classified`, `app_ref_resolved`, `authority_decided`, `launch_dispatched`, `verification_completed`.

### Task 3 — Design tokens and reusable production primitives

Files:

- Modify `ui/src/styles.css`.
- Modify `ui/src/components/common/Primitives.tsx` and existing shell primitives where reuse is appropriate.
- Create only focused production components under `ui/src/components/jarvis/` when an existing component cannot carry the contract.
- Copy only required approved Lucide SVGs to `ui/src/assets/icons/`.

Use CSS variables for graphite canvas/surfaces, electric blue intelligence, restrained burgundy consequence, rare gold approval, teal verification, and muted red failure. Use local/system font fallbacks; do not add remote font loading. Motion uses transform/opacity, explicit transitions, one stateful Core animation, and a reduced-motion variant.

### Task 4 — Five-area shell and compatibility routing

Files:

- Modify `ui/src/app/routes.ts`.
- Modify `ui/src/app/App.tsx`.
- Modify `ui/src/components/layout/AppShell.tsx`.
- Add/update route and shell tests.

The primary rail becomes Command, Converse, Work, Memory, Automations. Approvals and System remain utility actions. Existing `/chat`, `/missions`, `/operations`, `/research`, `/engineering`, `/browser`, `/skills`, `/devices`, `/notifications`, `/activity`, and `/settings` paths remain addressable through redirects or nested Work/System views.

The shell has one top command bar, one contextual inspector pattern, and one projection/event source. The UI remains a projection/control surface, not a second agent.

### Task 5 — Screen integration and product copy

Files:

- Modify `ui/src/screens/Screens.tsx` or split only where file size requires a direct responsibility boundary.
- Modify `ui/src/app/context.tsx` only for shared server-backed screen data.
- Modify relevant tests in `ui/src/screens/`.

Command keeps the wallpaper hero and adds NOW, NEEDS YOU, CONTINUE, and SYSTEM sections using real projection data. Converse keeps authenticated conversations, messages, run polling, cancellation, structured results, and refresh persistence. Work becomes a shared segmented workspace for Computer, Web, Files & Code, Communications, Devices, and Runs. Memory and Automations become their approved primary areas. Approvals and System expose existing endpoints without leaking secrets or raw debug codes as primary copy.

### Task 6 — Verification, security, performance, and live acceptance

Steps:

1. Add backend tests for narrow English/Arabic classification, ambiguity, compound fallback, app-ref resolution, owner/device binding, timing fields, and no-model-call behavior.
2. Add frontend tests for five-area navigation, compatibility routes, Arabic/mixed direction, loading/empty/offline/unverified/approval states, focus, keyboard navigation, and reduced motion.
3. Run the full Python suite and frontend suite/build.
4. Render and inspect 1920×1080, 1440×900, laptop, and narrow/tablet-like viewports.
5. Run live Chat, native fixture, Arabic native command, approval, and cloud-disabled/local fallback flows.
6. Run two review passes: integration contract review, then security/performance/product-truth review.

## Commit grouping

1. `docs: record full-stack integration audit and plan`
2. `feat: add server-side native app fast path`
3. `refactor: adopt five-area JARVIS command shell`
4. `test: close full-stack acceptance gaps`

Each commit is staged explicitly and tested before creation. No history rewrite, merge, force push, or broad generated-file staging is allowed.

## Completion gate

The final verdict is `JARVIS_FULLSTACK_PRODUCT_READY` only when all P0/P1 gaps are closed, the five-area UI is rendered and reviewed, the native fast path has real timing evidence and live verification, all required tests/builds pass, and the worktree is clean. Otherwise the result is `JARVIS_FULLSTACK_BLOCKED` or `JARVIS_OWNER_VISUAL_REVIEW_REQUIRED` with the exact remaining evidence.
