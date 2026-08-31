# Implementation Plan: Phase 14 Unified Product Experience

## Overview

Add a product-owned, local static Command Center over the existing JARVIS
application and experience authorities. The legacy HUD remains available as a
diagnostic fallback; daily desktop launch opens the new shell. No new model,
tool, memory, mission, scheduler, event bus, or voice authority is introduced.

## Architecture decisions

- Use dependency-free HTML, CSS, and JavaScript under `ui/src/`, built by a
  deterministic Python script into package-local static assets.
- Keep `ExperienceProjection` read-only and expose existing application use
  cases through the current HTTP adapter.
- Add a short-lived desktop bootstrap exchange to establish an HttpOnly local
  session cookie; browser mutations require the returned CSRF token.
- Preserve `/hud`, `/experience/hud`, and their public-route compatibility.
- Keep physical voice acceptance deferred and surface only normal operational
  voice state.
- Do not copy donor source; record inspected donors and license decisions.

## Task list

### Foundation and boundary

- [x] Add failing tests for local app serving, session bootstrap, cookie/CSRF
      protection, conversation history, and desktop primary URL.
- [x] Add the authenticated local browser session boundary and safe static
      asset serving while preserving legacy routes.
- [x] Add canonical conversation list/history read use cases for the UI.

### Command Center slices

- [x] Add the product-owned static shell, responsive design system, navigation,
      real-state dashboard, and offline/degraded rendering.
- [x] Add chat, approval, conversation history, and cancel flows through the
      existing AgentRuntime and approval authority.
- [x] Add projection-backed pages for missions, memory/context, research,
      skills, devices, notifications, settings, and activity.
- [x] Switch daily desktop launch/tray open behavior to the Command Center;
      retain Tk setup and diagnostics.

### Documentation and verification

- [x] Add donor salvage, API/UI inventory, capability matrix, frontend
      architecture, security/auth, UX acceptance, roadmap, and deferred
      Phase 13 backlog documents.
- [x] Add frontend build/static checks and Phase 14 backend/UI tests.
- [ ] Run focused tests, full suite, frontend build/tests, compileall,
      `git diff --check`, and a complete architecture/security diff review.
- [ ] Make the required coherent commit, push `main`, and verify remote HEAD
      equals local HEAD with a clean worktree.

## Checkpoints

- After boundary work: focused tests pass and legacy route tests remain green.
- After Command Center slices: frontend build/static checks and UI contract
  tests pass; no remote assets or fake production data.
- Before commit: all repository tests, compileall, diff check, and final review
  pass.

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Browser auth leaks a long-lived device credential | High | One-use bootstrap token, HttpOnly session cookie, CSRF header, no URL credential |
| UI becomes a second authority | High | Read through projection/application methods only; test route ownership |
| Static frontend is not packaged | Medium | Build into `src/jarvis/ui_static` and declare package data |
| Donor code carries unclear obligations | High | Inspect licenses; do not copy donor source in this phase |
| Existing Windows launch behavior regresses | Medium | Preserve setup/diagnostics/Tk paths and add lifecycle regression tests |
