# Local model validation

The gateway defaults to `mock`. The opt-in probe checks the configured health
endpoint and, only with `--model-exercise`, sends one bounded chat request. It
never pulls, installs, copies, or deletes a model. `llama_cpp` is the canonical
local GGUF provider; `gguf` is a compatibility alias.

```powershell
$env:PYTHONPATH = "src"
$env:JARVIS_MODEL_PROVIDER = "ollama"
$env:JARVIS_PRIMARY_MODEL = "qwen3.5:4b"
$env:JARVIS_FALLBACK_MODEL = "qwen3.5-heretic:9b-q4km"
$env:JARVIS_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
python -m jarvis --model-probe
python -m jarvis --model-probe --model-exercise
```

For the product-owned llama.cpp boundary, configure an existing external
GGUF and user-local runtime:

```powershell
$env:JARVIS_MODEL_PROVIDER = "llama_cpp"
$env:JARVIS_LLAMA_CPP_SERVER_PATH = "<user-local-runtime>\llama-server.exe"
$env:JARVIS_LLAMA_CPP_MODEL_PATH = "<external-model-directory>\model.gguf"
$env:JARVIS_MODEL_LOOPBACK_ENDPOINT = "http://127.0.0.1:18765"
$env:JARVIS_LOCAL_MODEL_AUTOSTART = "true"
python -m jarvis --model-probe --model-exercise
```

Record endpoint health, exact aliases, generation result, latency, timeout
behavior, offline failure, and restart recovery. Do not record absolute
personal paths, private prompts, or raw model output. Phase 12 evidence is
bounded in `docs/phase12/evidence/PHYSICAL_LOCAL_BRAIN.json`; its live text
brain and three real AgentRuntime desktop-tool turns are PASS.
