# Foundation audit

## Scope and method

Phase 01 audited three local candidates using the completed Phase 00 reports,
read-only repository inspection, package metadata, tracked-file counts, and
code-level review of their lifecycle, contracts, eventing, agent, tool,
security, voice, device, and memory surfaces.

The actual workspace is `C:\Jarivs`; the phase document's `C:\Jarvis` path is
not present. The final repository is therefore
`C:\Jarivs\00_final\jarvis`. The Phase 00 reports remain at
`C:\Jarivs\docs\research\phase-00`.

Audited sources:

| Candidate | Local source | Observed size |
|---|---|---:|
| PersonalJarvis | `C:\Jarivs\01_foundation_candidates\personal-jarvis` | 7,495 tracked files; 3,588 Python files |
| aceFelix/jarvis | `C:\Jarivs\01_foundation_candidates\acefelix-jarvis` | 369 tracked files; 272 Python files |
| BMO/JARVIS | `C:\Users\mahmo\Desktop\BMO\BMO-Personal-AI-OS` | 404 tracked files; 236 Python files |

All three were inspected without modifying them. No fetch, install, model
download, model copy, or provider invocation was performed.

## PersonalJarvis

Strengths:

- The broadest mature runtime surface: brain routing, tool-use loops, missions,
  workers, voice, Windows/computer control, memory, UI, telemetry, and local
  model discovery.
- `jarvis/core/bus.py` provides a useful in-process async pub/sub pattern, and
  `jarvis/core/events.py` has an extensive event vocabulary.
- `jarvis/core/protocols.py` already expresses tool, memory, observation, and
  brain interfaces.
- `jarvis/safety/tool_executor.py` provides a valuable evaluate/approve/
  execute/log sequence. Mission worker modules provide a donor pattern for
  isolated external workers.

Risks and boundary gaps:

- `jarvis/brain/manager.py` is 13,679 lines and imports routing, memory,
  safety, tools, voice, cost, provider, and computer-use concerns. It is a
  strong feature reference but a high-risk product spine.
- The event system is rich but not the Phase 01 normalized envelope: concrete
  event dataclasses center on `trace_id`/`source_layer` and do not establish a
  single product-owned correlation/causation/session/actor schema.
- The project metadata has a large dependency and optional-feature surface
  (audio, realtime media, computer vision, browser, provider SDKs, MCP,
  telemetry, and UI). A direct foundation copy would make a no-I/O bootstrap
  difficult to guarantee.
- Identity and device concepts exist in feature modules, but not as one
  durable, authority-owning identity/device service comparable to BMO.

Assessment: best donor for agent runtime, worker isolation, mission/task
orchestration, rich voice behavior, computer use, and memory patterns; not the
selected core spine.

## aceFelix/jarvis

Strengths:

- `agent/core/orchestrator.py` is a compact, understandable tool orchestration
  pipeline with permission resolution, concurrent safe calls, sequential unsafe
  calls, cancellation, hooks, audit, and recovery.
- `agent/core/tool.py`, `agent/permissions/checker.py`, and the sandbox modules
  provide useful tool, path-guard, shell-classification, and fail-closed
  patterns.
- `agent/voice/realtime_talk.py` demonstrates realtime duplex audio, VAD,
  interruption, echo-control hooks, and function-call integration.
- The repository is relatively small and has a focused test suite.

Risks and boundary gaps:

- Realtime voice directly builds and executes the default tool registry; the
  voice path is not an authority-neutral adapter. The module is 805 lines and
  couples audio, WebSocket protocol, tool schemas, prompts, and execution.
- The package has strong session-local permissions but lacks BMO-level durable
  owner/device credential authority, scoped device enrollment, and a central
  persisted approval/audit authority.
- It has no comparable world-state contract or product-wide normalized event
  model. Memory is primarily file/session based.
- Optional “all” dependencies span GUI, browser, camera, vision, voice,
  daemon, realtime UI, and chat-channel extras, so the complete product surface
  remains integration-heavy.

Assessment: best donor for orchestrator mechanics, sandbox/permission
techniques, recovery, and realtime voice UX; not the selected core spine.

## BMO/JARVIS

Strengths:

- `src/personal_ai_os/app.py` is a concise application factory with explicit
  lifespan, bounded resources, database health, reconciliation gates, executor
  routing, model gateway composition, and sanitized boundary errors.
- `identity/contracts.py` and `identity/service.py` define strict device
  principals, enrollment, credential rotation, scopes, capabilities, and
  heartbeats. Extra fields are forbidden at the security boundary.
- `model_gateway/contracts.py` separates provider-neutral requests, responses,
  model identity/digest, capability, health, and provider adapters.
- `tools/contracts.py` and `tools/service.py` model risk levels, approval
  policy, permission decisions, idempotency, execution targets, sandbox policy,
  deadline, audit metadata, verification, and reconciliation.
- Voice has a product-owned state machine and pipeline boundary; Windows
  satellites have typed commands and capability checks.
- The repository uses strict typing/lint/test configuration and a small
  dependency surface for the core platform.

Gaps to fill through later adapters:

- There is not yet a complete goal/mission runtime, isolated worker broker,
  durable memory/context subsystem, or broad computer/browser controller model.
- The current voice and model implementations are platform-specific and must
  remain behind the product contracts during migration.
- The existing BMO repositories are historical, checkout-specific sources and
  must remain read-only during this foundation phase.

Assessment: strongest architectural spine for authority, persistence, device
control, model/tool boundaries, and safe lifecycle. Its missing agent and
memory features are intentionally scheduled as adapters in Mega Phase 02+.

## Audit conclusion

BMO/JARVIS is selected as the one architectural spine. PersonalJarvis and
aceFelix/jarvis are donor/reference systems, not a blended runtime. Phase 01
implements only new product-owned contracts and no-op lifecycle code in the
final repository.
