# Live model runtime

Model access remains behind the existing `ModelGateway`. Phase 09 adds only
profile naming and an explicit `model_loopback_endpoint` alias for the
existing Ollama configuration. The gateway may inspect or call an already
running local provider; it never downloads, pulls, copies, or starts a model
runtime as a side effect of bootstrap.

The default provider is deterministic mock mode. A live probe is opt-in and
reports provider, alias, health, generation check, latency, and failure. On
this workstation no Ollama executable or listener was found, so no live model
PASS is claimed. The existing Ollama directory was not opened or modified.

```powershell
$env:JARVIS_MODEL_PROVIDER = "ollama"
$env:JARVIS_MODEL_LOOPBACK_ENDPOINT = "http://127.0.0.1:11434"
python -m jarvis --model-smoke
```

The endpoint must remain a loopback HTTP origin with an explicit port. Heavy
inference and model storage are deployment-owned and must not create duplicate
stores on the constrained workstation.
