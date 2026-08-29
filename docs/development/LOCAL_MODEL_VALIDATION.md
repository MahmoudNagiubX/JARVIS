# Local model validation

The gateway defaults to `mock`. The opt-in probe checks the configured health
endpoint and, only with `--model-exercise`, sends one bounded chat request. It
never pulls, installs, copies, or deletes a model.

```powershell
$env:PYTHONPATH = "src"
$env:JARVIS_MODEL_PROVIDER = "ollama"
$env:JARVIS_PRIMARY_MODEL = "qwen3.5:4b"
$env:JARVIS_FALLBACK_MODEL = "qwen3.5-heretic:9b-q4km"
$env:JARVIS_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
python -m jarvis --model-probe
python -m jarvis --model-probe --model-exercise
```

Record `ollama list`, endpoint health, exact aliases, generation result,
latency, timeout behavior, and offline fallback. Phase 06 preflight found no
Ollama executable or listener on the workstation, so Qwen/Ollama live
acceptance is not claimed.
