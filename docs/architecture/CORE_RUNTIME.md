# Core runtime

The runtime keeps the BMO/JARVIS spine and provides a working text-first
execution path:

`Client/API -> Session -> Conversation -> Agent -> Model Gateway -> Tool
Registry -> Permission -> Approval -> Executor -> Audit/Event Bus ->
Persistence -> Response`

`create_runtime()` composes one repository boundary, one event bus, the
authority services, model gateway, bounded agent runtime, tool pipeline,
Windows satellite registry, and voice core. Importing or composing the
runtime does not load a model, start a server, open an audio device, or bind a
non-loopback socket.

The local adapter is deliberately small and dependency-free. SQLite provides
durable records for owners, identities, devices, credentials, enrollments,
sessions, conversations, messages, runs, events, approvals, audit records,
and tool calls. The repository is the product boundary; a PostgreSQL adapter
and pgvector integration can replace SQLite without creating a second domain
store.

Cancellation is represented in durable run state. Approval pauses are durable
and must be explicitly resumed. Every capability path carries owner/device,
session, and correlation identifiers. HTTP mutations authenticate the device
credential before resolving the owner identity.

The runtime composes product-owned computer, browser, device-fabric, home,
communications, notifications, room-voice, and capability-registry services.
External transports are injected and optional. The loopback API exposes their
bounded read/action contracts without adding paid providers, model operations,
public bindings, or unrestricted shell/UI automation.
