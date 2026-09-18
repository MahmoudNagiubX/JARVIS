# Local models

The gateway defaults to mock mode. To probe an already-running local Ollama
service, set aliases and run the optional smoke test:

```powershell
$env:JARVIS_MODEL_PROVIDER = "ollama"
$env:JARVIS_PRIMARY_MODEL = "qwen3.5:4b"
$env:JARVIS_FALLBACK_MODEL = "qwen3.5-heretic:9b-q4km"
$env:JARVIS_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
python -m jarvis --model-smoke
```

The smoke test only checks `/api/tags` and sends one bounded chat request. It
does not run `ollama pull`, change the model store, copy GGUF files, or start
Ollama. Existing local Qwen assets are referenced by alias only.

## llama.cpp / GGUF

The explicit local path uses the existing `ModelGateway` and one bounded
`LlamaCppRuntimeSupervisor`; it does not create a second model manager:

```powershell
$env:JARVIS_MODEL_PROVIDER = "llama_cpp"
$env:JARVIS_LLAMA_CPP_SERVER_PATH = "<user-local-runtime>\llama-server.exe"
$env:JARVIS_LLAMA_CPP_MODEL_PATH = "<external-model-directory>\model.gguf"
$env:JARVIS_MODEL_LOOPBACK_ENDPOINT = "http://127.0.0.1:18765"
$env:JARVIS_LLAMA_CPP_CONTEXT_SIZE = "4096"
$env:JARVIS_LLAMA_CPP_THREADS = "8"
$env:JARVIS_LLAMA_CPP_GPU_LAYERS = "99"
$env:JARVIS_LOCAL_MODEL_AUTOSTART = "true"
python -m jarvis --model-smoke
```

The executable must already exist and the model must be an existing external
`.gguf`. Paths are validated; model weights are never downloaded, copied,
imported, or deleted. `JARVIS_LOCAL_MODEL_AUTOSTART` defaults to false, so
test/development composition does not launch a heavy model.

## Explicit OpenAI route

The cloud route is optional and never a hidden fallback. Select it explicitly
only when the owner has chosen a current model and intentionally provided the
key through the process environment:

```powershell
$env:JARVIS_MODEL_PROVIDER = "openai"
$env:JARVIS_OPENAI_ENABLED = "true"
$env:JARVIS_OPENAI_MODEL = "<owner-selected-current-model>"
$env:OPENAI_API_KEY = "<process-only-secret>"
python -m jarvis --model-smoke
```

JARVIS uses the official Responses API endpoint with bounded timeouts and
`store=false`; the key is not part of `JarvisConfig`, logs, events, or audit
payloads. Without both explicit enablement and `OPENAI_API_KEY`, health is
reported as unavailable and no network request is made. The default provider
remains local/mock.
