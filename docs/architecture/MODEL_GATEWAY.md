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
calls an already-running loopback `/api/chat` or `/api/tags` endpoint. It does
not pull, copy, install, or delete models and it never treats a local model
file path as configuration. GGUF and llama.cpp are explicit unavailable
adapter slots until a product-owned provider is added.

No model provider is contacted during import or runtime composition. Tests
inject mock providers and can verify routing without GPU or model state.

`JARVIS_OLLAMA_BASE_URL` remains a compatibility input, while
`model_loopback_endpoint` is the profile-neutral health/configuration name.
Live model validation is documented in `LIVE_MODEL_RUNTIME.md` and remains
opt-in; this workstation inventory found no usable Ollama listener.
