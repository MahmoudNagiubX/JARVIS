# Phase 15 MCP Security Model

MCP is an untrusted capability boundary. Trust is granted by the host policy,
not by a remote server's name, description, risk hint, or returned content.

## Controls

| Boundary | Control |
| --- | --- |
| Process launch | explicit command and args, `shell=False`, validated NUL/newline-free values |
| Environment | only explicitly allowlisted names and supplied values are passed; no parent environment inheritance |
| Working directory | explicit existing directory, resolved before launch |
| Protocol | JSON-RPC request IDs, UTF-8 line framing, malformed/error responses fail closed |
| Payloads | bounded request, response, tool count, schema size, content, and concurrency |
| Lifecycle | lazy start, owned process shutdown, timeout/cancel termination, stderr drain |
| Tool identity | server/tool validation, namespaced IDs, duplicate/collision rejection |
| Risk | host-owned `MCPPolicy`; unknown tools default to dangerous and require approval |
| Authorization | existing identity/device, permission, approval, executor, audit path |
| Workspace | registered approved roots, relative paths only, traversal/symlink checks, suffix and size bounds |
| Browser | existing BrowserActionService and approval authority; local DOM path first |
| Evidence | remote/browser/document output is data, bounded, attributed, and never a system instruction |
| Retention | MCP arguments/results use ephemeral retention by default |

## Risk mapping

`READ_ONLY` maps to the existing read path. `REVERSIBLE` maps to reversible
execution. `CONSEQUENTIAL` requires approval. `DANGEROUS` retains dangerous
metadata and autonomy while entering the existing consequential approval path;
the current permission engine intentionally fails closed for critical risk.

No MCP payload can approve itself, alter the policy engine, inject a system
prompt, or expose an environment secret. A dangerous capability is not bound
unless it has an explicit host-side policy decision.

## Review checklist

Before adding a provider, verify prompt-injection isolation, traversal and
symlink safety, command injection, environment/secret leakage, approval bypass,
browser credential exposure, schema explosion, unbounded responses, orphan
processes, and duplicate execution. Keep provider-specific logic below the
registry and above the existing executor.
