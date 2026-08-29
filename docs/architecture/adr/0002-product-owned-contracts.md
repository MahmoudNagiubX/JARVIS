# ADR 0002: Product-owned contracts are the dependency center

- Status: accepted
- Date: 2026-08-29

## Decision

`src/jarvis/contracts` owns identity, authorization, approval, audit, model,
tool, memory, world-state, goal, computer, browser, voice, and communication
interfaces. Adapters depend on these contracts; contracts do not depend on
donor repositories, SDKs, frameworks, or operating-system clients.

## Consequences

Historical types may be mapped at adapter boundaries. This prevents donor
coupling and lets offline tests validate product behavior without installing
the full integration stack.
