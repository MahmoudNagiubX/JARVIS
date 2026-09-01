# Phase 14 UI donor fusion refactor V2

## Scope and authority boundary

This execution applies the V2 donor-fusion brief to the existing React/Vite
Command Center. It is presentation work only. The existing CoreApplication,
AgentRuntime, local brain, ToolRegistry, PermissionEngine, ApprovalEngine,
Audit, MemoryService, World State, Goals/Missions, Automation, Research,
Browser, SkillRegistry, ExperienceProjection, EventBus, desktop lifecycle,
session, CSRF, and owner-scoping boundaries remain authoritative.

No second AgentRuntime, model gateway, scheduler, EventBus, VoiceCore,
database cleanup path, cloud transport, OpenFlow bridge, Google auth/cookies,
or browser identity surface was added.

## Starting state and donor review

- Verified starting `HEAD` and `origin/main`: `1116a5e1f843aa7d0677b01c920f98dfab046e3a`.
- Phase 15 clean baseline: YES.
- Nine donor repositories under `C:\Jarivs\14_ui_candidates` were inspected.
- The supplied owner wallpaper was inspected at
  `C:\Users\mahmo\Pictures\ironman-owner-wallpaper.jpg` and copied exactly
  to `ui/src/assets/hero/ironman-owner-wallpaper.jpg`.
- The exact extraction record is
  `docs/phase14/ui-refactor/DONOR_EXTRACTION_MANIFEST.md`.
- 28 exact donor candidate units were re-evaluated; 28 presentation units
  were adapted or wrapped. Donor 02, 07, 08, and 09 remain reference-only
  where runtime, licensing, identity, or synthetic-world boundaries did not
  fit the product.
- Approximate presentation split: 60% donor-derived visual language and
  40% JARVIS integration/state wiring.

AntiGravity status: NOT AVAILABLE / NOT INVOKED. The workspace policy requires
an explicit user request before delegating to another coding agent. No CLI,
authentication, proxy, OpenFlow, browser-cookie, token, or credential action
was attempted.

## Implemented surface

| Surface | Result |
|---|---|
| Home | Wallpaper-led hero, central reactor/orb, capability spine, KPI trace, owner queue, mission preview, activity, tactical signal |
| Chat | Conversation rail, rich messages, active-run inbox, existing composer and cancellation flow |
| Missions | Pipeline stages, plan surface, progress surface, existing mission actions |
| Research | Evidence-first citation surface over canonical research records |
| Skills | Safe capability data table |
| Devices | Lightweight radar and compass over reported device data |
| Approvals | Donor-derived approval card with existing decision endpoint and same owner/run boundary |
| Engineering | Reported stats, read-only code surface, safe fallback |
| Shell | Selective HUD bar/frame treatment, local command palette navigation, calm human-readable recoverable error |

## Visual system V2

The required tokens are present in `ui/src/styles.css` and documented in
`docs/phase14/ui-refactor/VISUAL_SYSTEM_V2.md`:

- plum/near-black: `#0C060E`, `#1E0C1D`, `#2F0A16`;
- crimson/ember: `#C40B2E`, `#EA2F42`, `#DA4F2E`;
- navy/steel: `#15254E`, `#18386A`, `#3C6497`;
- ice/cyan: `#96D8EE`, existing `#55D9FF`;
- text: `#E6F4FB`, `#A8B6C4`, `#718294`.

The wallpaper appears on Home only with plum overlays and a vignette. No
remote font, image, icon, CSS, or JavaScript dependency was introduced. Green
is not an identity color. Reduced-motion and responsive rules are included.

## Verification record

Counts below are the actual local results for this execution:

| Gate | Result |
|---|---|
| Focused V2 UI closure | 14 passed, 0 failed |
| Full frontend suite | 32 passed, 0 failed across 8 files |
| Frontend production build | PASS |
| Deterministic embedded asset build | PASS - `built 3 local JARVIS assets` |
| Phase 14 Python regression | PASS - 17 passed, 0 failed |
| Python full repository suite | PASS - 369 passed, 1 existing Windows-window skip, 25 subtests, 0 failed |
| `python -m compileall src tests` | PASS |
| `git diff --check` | PASS |
| Remote asset scan | PASS - no remote asset or transport references in UI source/static assets |
| Screenshot/browser smoke | NOT CLAIMED until an available local browser/backend is verified |

## Review constraints

- Donor worktrees were not modified and are not imported at runtime.
- No broad SQL cleanup or unrelated backend repair was performed.
- The only runtime code change is the bug-driven cancellation durability fix:
  cancellation is terminal immediately and a late model result cannot revive
  a cancelled run.
- The protected Phase 10 voice evidence file was not touched.
- Physical voice acceptance is outside this UI refactor and is not claimed.
- Final commit/push and clean-worktree status are release handoff gates after
  the pending verification rows are complete.
