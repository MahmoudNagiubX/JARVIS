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
JARVIS_OLLAMA_BASE_URL=http://127.0.0.1:11434
```

The default provider is deterministic mock mode. The Ollama adapter only
calls an already-running loopback `/api/chat` or `/api/tags` endpoint. It does
not pull, copy, install, or delete models and it never treats a local model
file path as configuration. GGUF and llama.cpp are explicit unavailable
adapter slots until a product-owned provider is added.

No model provider is contacted during import or runtime composition. Tests
inject mock providers and can verify routing without GPU or model state.
