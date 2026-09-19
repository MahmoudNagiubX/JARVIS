# Local model validation

The normal CLI gateway defaults to `hybrid` through `JarvisConfig.from_env`.
Isolated tests may construct explicit `mock` mode. The opt-in probe checks the
configured health endpoint and, only with `--model-exercise`, sends one bounded
chat request. It never pulls, installs, copies, or deletes a model. `llama_cpp`
is the canonical local GGUF adapter; `gguf` is a compatibility alias. Hybrid
mode uses llama.cpp for the local route and does not probe or assume Ollama.

```powershell
$env:PYTHONPATH = "src"
$env:JARVIS_MODEL_PROVIDER = "ollama" # explicit compatibility profile only
$env:JARVIS_PRIMARY_MODEL = "Qwen3.5-4B-Heretic"
$env:JARVIS_FALLBACK_MODEL = "Qwen3.5-4B-Heretic"
$env:JARVIS_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
python -m jarvis --model-probe
python -m jarvis --model-probe --model-exercise
```

For the product-owned hybrid/llama.cpp boundary, configure the exact Heretic
GGUF and user-local runtime:

```powershell
$env:JARVIS_MODEL_PROVIDER = "hybrid"
$env:JARVIS_LLAMA_CPP_SERVER_PATH = "<user-local-runtime>\llama-server.exe"
$env:JARVIS_LOCAL_MODEL = "Qwen3.5-4B-Heretic"
$env:JARVIS_PRIMARY_MODEL = "Qwen3.5-4B-Heretic"
$env:JARVIS_FALLBACK_MODEL = "Qwen3.5-4B-Heretic"
$env:JARVIS_LLAMA_CPP_MODEL_PATH = "<JARVIS-owned-models>\Qwen3.5-4B-Heretic-Q4_K_M.gguf"
$env:JARVIS_MODEL_LOOPBACK_ENDPOINT = "http://127.0.0.1:18765"
$env:JARVIS_LOCAL_MODEL_AUTOSTART = "true"
python -m jarvis --model-probe --model-exercise
```

Record endpoint health, exact Heretic identity, generation result, latency, timeout
behavior, offline failure, and restart recovery. The current live evidence is
`LOCAL_HERETIC_LIVE_READY`; use the separate three-model acceptance report for
cloud-key-gated status and the explicit provider probe. Do not record absolute
personal paths, private prompts, or raw model output. Phase 12 evidence is
bounded in `docs/phase12/evidence/PHYSICAL_LOCAL_BRAIN.json`; its live text
brain and three real AgentRuntime desktop-tool turns are historical evidence,
not current proof of the required 4B weights. Current status is recorded in
`docs/audits/JARVIS_LOCAL_MODEL_READINESS.md`.
