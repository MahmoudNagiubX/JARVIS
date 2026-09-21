# JARVIS Frontend ↔ Backend Integration Matrix

This matrix records the current production surface and the approved five-area destination. Endpoints are listed only when traced in the current frontend or when needed to preserve an existing capability home.

| Current surface | Current route/component | Read endpoints | Mutations | Stream/state | Owner/session | Canonical authority | Decision | Status |
|---|---|---|---|---|---|---|---|---|
| Command | `/`, `HomeScreen`, `AppShell` | `/experience/state`, projection sections | refresh projection | `/experience/events/ws?topic=system_health` | desktop session + cookie | `ExperienceProjection` / EventBus | KEEP as Command | PASS; hierarchy refactor |
| Converse | `/chat`, `ChatScreen` | `/conversations`, `/conversations/{id}/messages`, `/runs/{id}`, `/runs/{id}/activity` | `/messages/start`, `/runs/{id}/cancel` | projection/WebSocket plus bounded run polling | desktop session + CSRF for mutations | `AgentRuntime` / conversation service | MOVE to Converse | PASS; copy/structured states refactor |
| Missions | `/missions`, `MissionsScreen` | `/missions`, mission detail/evidence | `/missions`, `/missions/{id}/{action}` | projection mission state | authenticated owner | Goal/Mission authority | MOVE under Work → Runs | KEEP compatibility route |
| Memory | `/memory`, `MemoryScreen` | `/memory` | `/memory/{id}`, `/memory/{id}/pin`, delete/forget routes | snapshot; projection where available | authenticated owner + CSRF | Memory authority | KEEP as Memory | PASS; visual refactor |
| Current context | `/context`, `ContextScreen` | `/context` | none | projection presence/world state | authenticated owner/device | Context/World State authority | COLLAPSE INTO Memory inspector | KEEP compatibility route |
| Operations/focus | `/operations`, `OperationsScreen` | `/personal-operations/modes`, `/focus`, projection | `/personal-operations/mode`, `/personal-operations/run`, `/focus/start`, `/focus/end` | projection/event stream | authenticated owner/device + CSRF | Operations/Focus services | MOVE under Work | KEEP compatibility route |
| Research | `/research`, `ResearchScreen` | `/research/runs`, `/research/runs/{id}/evidence` | `/research/runs`, cancel | projection/run polling | authenticated owner/device + CSRF | Research service / Browser authority | MOVE under Work → Web | PASS; source inspector |
| Engineering | `/engineering`, `EngineeringScreen` | `/engineering/providers`, `/engineering/sessions/{id}` | `/engineering/sessions`, `/engineering/actions`, approvals | run/projection | authenticated owner/device + CSRF | Engineering worker coordinator | MOVE under Work → Files & Code | KEEP compatibility route |
| Browser | `/browser`, `BrowserScreen` | capability/provider state | `/browser/actions`, browser approvals | projection/events | authenticated owner/device + CSRF | `BrowserActionService` | MOVE under Work → Web | PASS; no new browser authority |
| Skills | `/skills`, `SkillsScreen` | `/skills`, versions/executions | enable/disable/run/resume | projection/audit | authenticated owner/device + CSRF | Skill registry/execution service | MOVE under Work → Files & Code or System | KEEP compatibility route |
| Devices | `/devices`, `DevicesScreen` | `/devices`, capabilities, fabric diagnostics | enroll/revoke/degraded | projection/device events | authenticated owner/device + CSRF | DeviceFabric/identity authority | MOVE under Work → Devices | PASS; device inspector |
| Notifications | `/notifications`, `NotificationsScreen` | `/notifications` | dismiss/deliver | projection/event stream | authenticated owner + CSRF | Notification service | COLLAPSE INTO contextual attention/System | KEEP compatibility route |
| Approvals | `/approvals`, `ApprovalsScreen` | projection approvals, `/approvals/{id}` | approval decision endpoints | approval events | authenticated owner/device + CSRF | ApprovalEngine | KEEP as utility | PASS; gold attention state |
| Activity | `/activity`, `ActivityScreen` | `/experience/timeline`, `/events` | none | EventBus snapshot/events | authenticated owner | audit/event authority | SYSTEM-ONLY inspector | KEEP compatibility route |
| System | `/settings`, `SettingsScreen` | `/health`, `/experience/system`, `/computer/apps`, profile, `/capabilities` | app refresh/settings/computer actions | projection/runtime state | authenticated owner/device + CSRF | runtime/model/desktop authorities | MOVE to System | PASS; technical detail secondary |

## Compatibility and contract rules

- `ui/src/lib/api.ts` remains the only browser API client and continues to add `/v1`, same-origin credentials, and CSRF headers for mutations.
- Owner IDs in query strings are never treated as authority; backend authenticated principal scoping remains authoritative.
- The session/bootstrap and per-server cookie behavior from commits `4ce6291` and `f3e6575` remains unchanged.
- No UI state becomes authoritative for run, approval, permission, model, voice, device, or memory state.
- WebSocket snapshot reconciliation remains the live projection path; reconnecting must degrade to snapshot without poisoning an authenticated session.

## Endpoint disposition

Endpoints without a dedicated current screen remain useful through Work/System/Inspector: `/experience/system`, `/experience/clients`, `/presence`, `/attention`, `/home/context`, `/world-state`, `/goals`, `/proactive/findings`, `/communications/*`, `/workspace/projects`, `/intelligence/*`, `/briefings`, `/evaluations`, `/nodes/venom/*`, `/rooms`, `/fabric/diagnostics`, `/perception/*`, and `/workers/developer/*`. They are not deleted during this refactor.
