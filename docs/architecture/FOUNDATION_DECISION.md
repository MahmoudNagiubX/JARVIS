# Foundation decision

## Decision

Select **BMO/JARVIS** as the single architectural spine for the JARVIS
Personal AI OS.

This is not a vague hybrid selection. The final product core owns the BMO
boundary model and lifecycle. PersonalJarvis and aceFelix/jarvis may be
integrated later only as isolated adapters or migrated implementations that
conform to the product-owned contracts.

## Why this spine

The core problem is not obtaining the most assistant features immediately. It
is establishing one trustworthy authority for who may act, on which device,
with which capability, under which approval, and with which audit record. BMO
already has the strongest local evidence for that shape:

- strict identity/device contracts and scoped credentials;
- provider-neutral model identity, health, and request/response contracts;
- risk, permission, approval, idempotency, deadline, sandbox, verification,
  reconciliation, and audit fields at the tool boundary;
- explicit API factory and shutdown/reconciliation lifecycle;
- typed Windows satellite and voice boundaries.

The missing agent runtime, worker broker, memory, and context features are
important, but they can be added behind these boundaries. Starting from the
large PersonalJarvis brain would make the authority plane a later extraction
from a 13,679-line cross-cutting manager. Starting from Ace would leave
durable identity/device authority to be invented later.

## Ownership rule

`src/jarvis` owns the contracts, event envelope, lifecycle, and authority
ordering. No donor package is imported by the foundation. Future adapters may
depend on the contracts; contracts may not depend on donors, providers,
frameworks, operating-system clients, or model runtimes.

## Consequences

Positive:

- Every future capability has a place to enter without bypassing identity,
  permission, approval, audit, and event correlation.
- Phase 01 can be tested offline with the standard library.
- Existing BMO evidence and deployment state remain untouched.

Tradeoffs:

- The first foundation does not perform real AI, voice, browser, or computer
  actions.
- Agent and memory functionality must be migrated deliberately in later
  phases rather than copied wholesale.
- Some BMO implementation details will be re-expressed behind the new
  product-owned contracts to prevent historical coupling from becoming a new
  dependency.
