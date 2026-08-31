# Phase 14 API and UI inventory

## Existing projection and application surface

The loopback `CoreHttpServer` already exposes authenticated projections and
application use cases for the existing authorities. The main families are:

- experience: `/experience/state`, `/experience/system`,
  `/experience/timeline`, `/experience/events`, `/experience/events/ws`, and
  `/experience/clients`;
- runtime and context: `/health`, `/presence`, `/attention`, `/focus`,
  `/context`, `/home/context`, and `/home/entities`;
- work: `/goals`, `/missions`, `/routines`, `/automations`, `/briefings`,
  `/workspace/projects`, `/intelligence/findings`, and `/evaluations`;
- memory and personal operation: `/memory`, `/memory/search`, `/world-state`,
  `/notifications`, `/personal-operations/*`, and `/communications/*`;
- capabilities: `/devices`, `/skills`, `/research/runs`, `/engineering/*`,
  `/perception/*`, `/computer/*`, `/browser/*`, `/home/actions`, and
  `/capabilities`;
- conversations and agent runs: `/messages`, `/approvals/*`, and
  `/runs/*/cancel`.

The legacy public routes remain `/health`, `/hud`, and `/experience/hud`.
They are intentionally preserved for compatibility and diagnostics.

## Missing UI use cases found

Before Phase 14, the rich daily product surface was missing a static local
application shell, browser session handoff, canonical conversation listing,
canonical conversation message history, and a normal-launch target separate
from the large legacy HUD string.

## Phase 14 additions

| Route | Purpose | Authentication |
|---|---|---|
| `/app`, `/app/index.html`, `/app/*.css`, `/app/*.js` | Local compiled Command Center assets | Public shell only; no runtime state |
| `POST /auth/desktop-session` | Consume one-use desktop bootstrap and issue session cookie | Bootstrap is server-held and one-use |
| `GET /auth/session` | Return safe owner/device/session metadata | HttpOnly session cookie |
| `GET /conversations` | List canonical persisted conversations | Owner-bound session or existing credential |
| `GET /conversations/{id}/messages` | Read canonical message history after owner check | Owner-bound session or existing credential |

Cookie-backed mutations use the existing application methods and require the
session CSRF token. Existing credential/device/identity API clients remain
compatible; no mutation route is public.

## UI route map

The local static application provides Home, Chat, Missions, Memory, Current
Context, Automation, Research, Engineering, Browser, Skills, Devices,
Notifications, Approvals, Activity, and Settings. Empty and unavailable
states are derived from backend projections rather than production fixtures.
