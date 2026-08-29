# ADR 0001: Select BMO/JARVIS as the architectural spine

- Status: accepted
- Date: 2026-08-29

## Context

The local candidates have complementary strengths. PersonalJarvis has the
largest agent/voice/memory surface, aceFelix/jarvis has focused orchestration
and sandbox behavior, and BMO/JARVIS has the clearest authority, persistence,
device, model, tool, and lifecycle boundaries.

## Decision

BMO/JARVIS is the single architectural spine. PersonalJarvis and
aceFelix/jarvis are donor/reference systems whose implementations may be
migrated behind product contracts later.

## Consequences

The first product runtime must grow from explicit authority boundaries. Agent,
worker, memory, and richer voice features are migration work, not reasons to
copy a second spine into the product.
