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
  Runtime plane: conversation -> goals -> workers -> tools
                 |
 Capability plane: models | memory | world state | computer | browser | voice
                 |
      Infrastructure adapters and durable stores
```

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
| Event bus | Core runtime | Dispatch normalized events in-process initially | Durable queue guarantees in Phase 01 |
| Conversation/agent | Runtime | Plan turns, manage goals, coordinate workers and tool proposals | Owning credentials or bypassing approval |
| Model gateway | Capability adapter | Route provider-neutral requests and report model identity/health | Authorizing tool calls |
| Tools | Capability adapter | Validate and execute one capability under a `ToolContext` | Deciding its own authority |
| Memory/world state | Capability adapter | Store/retrieve records and observations | Becoming hidden conversational state |
| Voice | Capability adapter | STT/TTS/realtime session and interruption state | Executing tools outside the common authority path |
| Computer/browser | Capability adapter | Translate typed actions to a selected device/session | Making direct autonomous network/device policy |
| UI/transport | Edge adapter | Present state and collect user decisions | Becoming the source of truth for approval or audit |

## Event model

Every cross-boundary event uses `jarvis.events.Event` with:

- stable event id and event type;
- UTC timestamp;
- category from the product taxonomy;
- correlation id and optional causation id;
- optional session and actor ids;
- structured payload, severity, and lifecycle state.

Phase 01 uses `InMemoryEventBus`. Later durable or distributed transports are
adapters and must preserve this envelope.

## Lifecycle

`created -> starting -> ready -> stopping -> stopped` is explicit. Startup
emits `system.bootstrap.started` and `system.bootstrap.ready`. Shutdown emits
`system.shutdown.started` and `system.shutdown.completed`. Phase 01 startup
only composes no-op/in-memory services and performs no model, network, audio,
database, or device initialization.

## Security ordering

For a consequential capability request, the intended future sequence is:

```text
authenticate -> authorize -> validate -> request approval -> audit decision
-> bind device/capability -> execute -> verify -> audit outcome -> emit events
```

The model may propose; it cannot approve. Voice may collect a user decision;
it cannot turn speech into implicit authorization. A tool may return a result;
it cannot claim verification unless the controller supplies evidence.
