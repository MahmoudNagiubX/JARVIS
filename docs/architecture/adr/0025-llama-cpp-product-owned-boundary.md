# ADR 0025: Use a product-owned llama.cpp boundary

- Status: accepted
- Date: 2026-08-30

## Decision

The existing `ModelGateway` remains the only model entry point. A
product-owned `LlamaCppProvider` speaks the bounded OpenAI-compatible
loopback protocol, while `LlamaCppRuntimeSupervisor` owns only a process it
started and can attach to an already-running compatible local listener.

The canonical provider label is `llama_cpp`; `gguf` remains a compatibility
input alias. The provider normalizes response shape, tool arguments, health,
timeouts, body limits, and offline errors at the boundary.

## Consequences

The agent, authority, tool registry, EventBus, scheduler, and VoiceCore remain
unchanged owners. A local model cannot authorize tools or silently fall back
to mock mode. Public health exposes safe alias/provider state only.
