# Model gateway

`ModelGateway` is the only runtime model entry point. Routes are explicit:

- `fast_conversation`
- `general_reasoning`
- `tool_orchestration`
- `vision`
- `coding_worker`

Configuration is environment-driven:

```text
JARVIS_MODEL_PROVIDER=mock|ollama|gguf|llama_cpp
JARVIS_PRIMARY_MODEL=qwen3.5:4b
JARVIS_FALLBACK_MODEL=qwen3.5-heretic:9b-q4km
JARVIS_MODEL_LOOPBACK_ENDPOINT=http://127.0.0.1:11434
```

The default provider is deterministic mock mode. The Ollama adapter only
calls an already-running loopback `/api/chat` or `/api/tags` endpoint. The
`llama_cpp` adapter calls the product-owned bounded OpenAI-compatible
`/v1/chat/completions` boundary. It normalizes response and tool-call shapes,
caps response bodies and generation timeouts, and reports offline/readiness
errors without a cloud or mock fallback. `gguf` is accepted as a compatibility
alias for `llama_cpp`.

An explicitly configured local llama.cpp runtime may be started by the single
`LlamaCppRuntimeSupervisor`; the default bootstrap remains no-autostart. The
supervisor validates an external `.gguf`, uses a fixed loopback-only argv with
`shell=False`, and stops only a process it owns. It can attach to a compatible
listener but never kills an incompatible listener or copies/downloads model
weights.

No model provider is contacted during import or runtime composition. Tests
inject mock providers and can verify routing without GPU or model state.

`JARVIS_OLLAMA_BASE_URL` remains a compatibility input, while
`model_loopback_endpoint` is the profile-neutral health/configuration name.
Live model validation is documented in `LIVE_MODEL_RUNTIME.md` and remains
opt-in. Phase 12 validated one existing external Qwen GGUF through llama.cpp;
the real text path, provider tool normalization, and three fresh real
AgentRuntime desktop-tool turns passed. The local text model truthfully
reports `model_route_unsupported` for vision, requires its configured alias in
`/v1/models`, and serializes generation with one active request plus eight
bounded waiters.
