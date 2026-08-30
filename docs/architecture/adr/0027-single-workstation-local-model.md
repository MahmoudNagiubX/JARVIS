# ADR 0027: Select one workstation-local model

- Status: accepted
- Date: 2026-08-30

## Decision

Phase 12 validates one existing external Qwen GGUF in place through one
official llama.cpp runtime package. The constrained workstation does not get
a second model store, background model manager, cloud fallback, or paid
provider path.

## Consequences

The selected alias and physical result are auditable without publishing a
personal absolute path or model prompts. The real text path is PASS, while
the current GGUF/runtime combination remains explicitly PARTIAL for the
real AgentRuntime tool turn until it emits and completes a JARVIS tool call.
