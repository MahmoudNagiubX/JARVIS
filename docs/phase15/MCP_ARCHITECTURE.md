# Phase 15 MCP Architecture

Phase 15 adds a product-owned MCP adapter boundary. It does not add a second
agent runtime, permission engine, scheduler, EventBus, or VoiceCore.

## Runtime flow

```text
configured local MCP server or bounded local provider
        -> MCPRegistry / MCPStdioClient
        -> discovered, namespaced ToolSpec
        -> existing ToolSchemaSelector
        -> existing PermissionEngine
        -> existing ApprovalEngine
        -> existing ToolExecutionService
        -> existing AuditService and EventBus
```

`MCPRegistry` owns discovery, health, lifecycle, and normalization. The native
`ToolRegistry` remains the single catalog used by `AgentRuntime` and the tool
executor. MCP results are marked untrusted data and cannot change policy or
approval state.

## Transport and lifecycle

The first transport is local stdio. A configured server is started lazily with
`shell=False`, one owned child process, explicit UTF-8 JSON-RPC lines, bounded
request/response sizes, bounded concurrency, startup/execution timeouts, and
stderr draining. A timeout, cancellation, malformed response, or process exit
fails that server and leaves the rest of the runtime available.

Local providers use the same registry and ToolSpec boundary without requiring a
child process. This is how the built-in workspace and repository capabilities
remain useful offline.

## Configuration and normalization

`MCPServerConfig` holds an ID, display name, command/args, environment allowlist,
working directory, enablement, trust level, capability allowlist, timeouts,
payload bounds, and concurrency. Runtime environment values are memory-only and
are never included in health projections.

Every discovered tool becomes `mcp.<server>.<tool>` after conservative slug
normalization. Duplicate server IDs, duplicate normalized names, and collisions
with a native tool fail closed. The host policy classifies risk; server metadata
is only descriptive.

## Product paths

The current runtime composes:

- `workspace`: bounded read/list plus approval-gated text writes inside an
  explicitly registered project;
- `repository`: bounded inspection through existing workspace intelligence;
- existing browser, research, skills, engineering, and developer seams.

The repository provider does not expose shell execution. New providers must
reuse the same identity, scope, policy, approval, audit, and retention rules.
