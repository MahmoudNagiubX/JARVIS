# Tool execution policy

The only tool path is:

`Agent -> Registry -> Argument validation -> Permission -> Approval ->
Executor -> Audit -> Event Bus -> Result`

The registry is static and versioned. Each tool declares risk, scope,
capabilities, timeout, idempotency, and approval policy. Unknown tools,
disabled tools, malformed arguments, and sensitive argument keys are rejected
and audited. Raw credential-like values are not accepted by the Phase 02 tool
fixture boundary.

The default catalog contains safe status, reversible echo, and consequential
echo fixtures. The latter creates a durable approval record and pauses the
run; it is never auto-approved. Required lifecycle events include
`tool.requested`, `tool.permission_checked`, `tool.approval_required`,
`tool.started`, `tool.completed`, and `tool.failed`.
