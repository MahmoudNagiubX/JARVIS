# Phase 14 UI backend integration map

All screens use the existing JARVIS API under `/v1`. The table names the
canonical read and action authorities used by the final UI adapter. It
does not authorize new endpoints.

| Screen | Read projections | Mutations/actions | Live updates and guardrails |
|---|---|---|---|
| Home | `/health`, `/experience/state`, `/experience/system`, `/presence`, `/attention`, `/focus`, `/notifications?active_only=true` | None by default; navigation to canonical actions | Experience stream; server-derived empty/stale states. |
| Chat | `/conversations`, `/conversations/{id}/messages`, `/context` | `POST /messages`, `POST /runs/{id}/cancel` | Conversation owner check, session/CSRF, event stream for run state. |
| Missions | `/missions`, `/goals`, `/experience/timeline` | `POST /missions`, mission action routes, goal create/update/control | No synthetic progress; approvals remain server-owned. |
| Memory | `/memory`, `/memory/search`, `/world-state`, `/world-state/conflicts` | `POST/PATCH/DELETE /memory`, forget, pin, archive | Owner scope and memory policy remain backend-enforced. |
| Current context | `/context`, `/presence`, `/attention`, `/home/context`, `/experience/state` | No direct write unless a canonical operation exists | Do not infer presence, quiet hours, or attention from visual state. |
| Operations | `/personal-operations/modes`, `/focus`, `/automations`, `/briefings`, `/routines` | Personal mode, focus start/end, automation create/update, briefing generate, routine run | Sensitive actions use existing permission/approval policy. |
| Research | `/research/runs`, `/research/runs/{id}`, `/research/runs/{id}/evidence` | Start/cancel research | Evidence comes from persisted research service; no donor provider calls. |
| Engineering | `/engineering/providers`, `/engineering/sessions/{id}` | Engineering session/action/approval | Existing worker and approval authority; terminal remains deferred. |
| Browser | `/browser/*` capability/approval responses | Browser action and approval decisions | Existing browser permission, audit, and session controls. |
| Skills | `/skills`, `/skills/{id}`, `/skills/{id}/versions` | Enable, execute, resume | Existing skill registry, policy, and execution authority. |
| Devices | `/devices`, `/devices/{id}/capabilities`, `/capabilities` | Device actions only through canonical capabilities | Identity/device ownership is server-verified. |
| Notifications | `/notifications`, `/attention` | Create, dismiss, deliver notification | Delivery remains protected by attention/owner policy. |
| Approvals | `/approvals/{id}`, action-specific approval responses | Existing approval decision endpoints | Never accept a donor approval ID without server validation. |
| Activity | `/experience/timeline`, `/experience/events`, `/events/stream` | None | Existing event envelope and event bus only; no donor EventBus. |
| Settings | `/auth/session`, `/personalization/profile`, `/perception/capabilities`, `/engineering/providers` | Personalization, configuration actions already exposed by JARVIS | Session, CSRF, identity, and audit rules remain unchanged. |

## Transport rules

1. Prefix all application calls with `/v1` through one adapter.
2. Use `/v1/auth/session` for safe session metadata and the existing desktop
   bootstrap flow; do not implement donor auth or local credentials.
3. Use `/v1/experience/events` or `/v1/experience/events/ws` for live state;
   the UI must consume the existing event envelope.
4. Treat all UI state as a cache of server projections.
5. Re-fetch after mutations when the response is not a complete projection.
6. Do not call donor `/api`, `/api/hermes`, Anthropic, OpenAI, MCP, cloud,
   weather, or gateway routes.

## Authority preservation checklist

- One `JarvisRuntime` and one `CoreApplication` remain authoritative.
- One persistence repository and existing migrations remain authoritative.
- One backend event bus remains authoritative.
- One identity/session/permission/approval boundary remains authoritative.
- One VoiceCore/voice runtime remains authoritative.
- Existing owner scoping and audit records are preserved.

## 9-repository visual-donor boundary

Donors 08 and 09 add no backend integration. Their simulated telemetry,
fictional targeting state, localStorage face profiles, guest bypass, gesture
classifier, CDN model loaders, and WebXR/Three.js loops are explicitly outside
the JARVIS API boundary. Tactical, compass, radar, holographic core, and node
visuals may only render values already returned by the existing projections in
this document.

## Final implementation boundary

`ui/src/lib/api.ts` is the single browser transport boundary and
`ui/src/lib/events.ts` is the single experience-event normalization boundary.
Mutations refresh the canonical projection; no browser-side authority was
added for runtime, memory, missions, approvals, scheduling, or VoiceCore.
