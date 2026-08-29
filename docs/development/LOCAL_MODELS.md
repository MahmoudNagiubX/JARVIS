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
