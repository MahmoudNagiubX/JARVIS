# Codex delegation boundary

JARVIS has one optional developer-child seam: Codex may request one bounded
child review through the explicit `CodexSubdelegationBoundary`. JARVIS does
not discover, authenticate to, or launch AntiGravity directly.

The boundary is fail-closed unless an approved Codex integration supplies an
executor. A supplied child request must have:

- a Codex parent provider;
- an existing Git workspace already approved for the parent task;
- a bounded task with no credential or secret instructions;
- a timeout no longer than the configured child limit;
- relative changed paths inside that workspace; and
- at most one child request per boundary instance.

Child output is untrusted and returns `verification_status=unverified`. The
Codex parent remains responsible for reviewing the result and independently
verifying any proposed change. Timeout, cancellation, invalid scope, invalid
paths, second-child attempts, and missing executors return explicit degraded
states.

This is a code-controlled boundary and deterministic fixture evidence only. It
does not claim that an owner has installed, authenticated, or accepted a live
AntiGravity integration.
