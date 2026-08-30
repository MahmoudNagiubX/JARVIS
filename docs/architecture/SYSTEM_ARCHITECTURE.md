# System architecture

## Target shape

```text
Clients / UI / Voice / Device transports
                 |
        boundary adapters and auth context
                 |
       product-owned contracts + event envelope
                 |
  Authority plane: identity -> permission -> approval -> audit
                 |
  Runtime plane: conversation -> goals -> missions -> workers -> tools
                 |
  Capability plane: models | memory | world state | computer | browser | home
                  | devices | communications | notifications | voice routing
                  | engineering | research | perception | developer workers
                  | intelligence: skills | workspace | findings | briefings | automation | evaluation
                  | personal operations | presence | attention | delivery | follow-ups | home context
                 |
      Infrastructure adapters and durable stores
```

Experience projections, the HUD, client sessions, and observability sit at
the edge. They consume events and query authorities; they do not own business
state.

The arrows represent dependency direction. A client or adapter may call a
product contract; it must not reach around the authority plane to execute a
capability directly.

## Ownership boundaries

| Boundary | Product owner | Allowed responsibilities | Explicit non-responsibilities |
|---|---|---|---|
| Identity/device | Core authority | Authenticate actors/devices, scopes, capabilities, lifecycle | UI policy, model prompts, tool implementation |
| Permission | Core authority | Evaluate action/resource against identity and device context | Executing an action |
| Approval | Core authority | Create, decide, expire, and consume human approvals | Assuming approval from voice or model text |
| Audit | Core authority | Append/query security and execution records with correlation | Storing arbitrary secrets or raw unredacted arguments |
| Event bus | Core runtime | Dispatch normalized events in-process and persist event rows | Durable queue and retry guarantees |
| Conversation/agent | Runtime | Plan turns, manage goals, coordinate workers and tool proposals | Owning credentials or bypassing approval |
| Model gateway | Capability adapter | Route provider-neutral requests, report model identity/health, and delegate one bounded local runtime | Authorizing tool calls, downloading/copying weights, or silently falling back |
| Tools | Capability adapter | Validate and execute one capability under a `ToolContext` | Deciding its own authority |
| Memory/world state | Capability adapter | Store/retrieve records and observations | Becoming hidden conversational state |
| Voice | Capability adapter | STT/TTS/realtime session and interruption state | Executing tools outside the common authority path |
| Computer/browser | Capability adapter | Translate typed actions to a selected device/session | Making direct autonomous network/device policy |
| UI/transport | Edge adapter | Present state and collect user decisions | Becoming the source of truth for approval or audit |
| Experience projection | Read model | Project real events into owner-scoped HUD/client state | Mutating authorities or faking lifecycle state |
| Engineering/research/perception | Product service + injected provider | Bound specialist work, evidence, and on-demand observation | Shell bypass, hidden memory, continuous capture |
| Mission/skill/intelligence | Product-owned bounded services | Inspectable plans, declarative procedures, findings, briefings, rules, evaluation | New authority, second scheduler/tool registry, autonomous source mutation |
| Personal operations | Orchestration services | Modes, focus, routines, presence, attention, delivery and follow-up coordination | Owning tasks, messages, notifications, home actions, or approvals |

## Event model

Every cross-boundary event uses `jarvis.events.Event` with:

- stable event id and event type;
- UTC timestamp;
- category from the product taxonomy;
- correlation id and optional causation id;
- optional session and actor ids;
- structured payload, severity, and lifecycle state.

The runtime uses `InMemoryEventBus` plus durable event persistence through the
repository. Later durable delivery, outbox, or distributed transports are
adapters and must preserve this envelope.

Phase 09's distributed node transport is such an adapter: it wraps the
existing Windows satellite registry and preserves the same event, identity,
permission, device, and audit ownership. It does not add a scheduler, EventBus,
VoiceCore, or tool registry. See `DISTRIBUTED_RUNTIME.md` and
`NODE_TRANSPORT.md`.

## Lifecycle

`created -> starting -> ready -> stopping -> stopped` is explicit. Startup
emits `system.bootstrap.started` and `system.bootstrap.ready`. Shutdown emits
`system.shutdown.started` and `system.shutdown.completed`. Startup composes
local authority, SQLite, model, tool, satellite,
computer/browser/device/home/communication/notification, voice routing,
experience, engineering, research, perception, and developer-worker
boundaries, but performs no model load, audio-hardware open, capture loop, or
non-loopback network bind unless the explicitly configured local-model
autostart lifecycle is enabled. The local model remains behind the existing
gateway/supervisor boundary and uses loopback only.

## Security ordering

For a consequential capability request, the sequence is:

```text
authenticate -> authorize -> validate -> request approval -> audit decision
-> bind device/capability -> execute -> verify -> audit outcome -> emit events
```

The model may propose; it cannot approve. Voice may collect a user decision;
it cannot turn speech into implicit authorization. A tool may return a result;
it cannot claim verification unless the controller supplies evidence.

Phase 10 adds native desktop perception as a read-only extension of the
existing runtime. Active metadata may be projected safely; visual text and
pixels remain current-turn/ephemeral data. The implementation keeps one
PerceptionService, one scheduler, one EventBus, and the existing computer and
satellite authorities.

Phase 13 adds a Windows-local physical voice lifecycle adapter. It binds local
wake, VAD, STT, TTS, and speaker implementations to the already-composed
VoiceCore only at explicit live-runner startup. The adapter cannot execute an
AgentRuntime, model, tool, permission, approval, scheduler, or EventBus path
of its own; final transcripts use the ordinary AgentRuntime authority path.
