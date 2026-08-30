# Live model runtime

Model access remains behind the existing `ModelGateway`. Phase 12 adds an
explicit `llama_cpp` provider and a bounded `LlamaCppRuntimeSupervisor` for an
already available external GGUF. The gateway never downloads, pulls, copies,
or starts a model runtime as a side effect of import or ordinary composition;
autostart requires explicit `JARVIS_LOCAL_MODEL_AUTOSTART=true` and validated
paths.

The default provider is deterministic mock mode. A live probe is opt-in and
reports provider, alias, health, generation check, latency, and failure. The
llama.cpp path is loopback-only and has no cloud/paid fallback. Phase 12
physical evidence is in `docs/phase12/evidence/PHYSICAL_LOCAL_BRAIN.json`.
AgentRuntime supplies deterministic, intent-scoped tool schemas (maximum
eight), omits the full context snapshot on tool-result follow-ups, and bounds
structured tool evidence before sending it to a local context window. Empty
no-tool responses fail as `model_empty_response`; a blank response with a
valid tool call remains executable.

The selector's bilingual closure is deliberately small and does not translate
or reinterpret user text. It case-folds Latin text, removes Arabic tatweel and
diacritics, normalizes common Arabic letter variants, and matches only the
registered production tool groups. Arabic and mixed active-window metadata
requests select `desktop.context.read`; English visual requests retain the
existing visual schema group. Tool output is never used to expand a later
turn's selection.

```powershell
$env:JARVIS_MODEL_PROVIDER = "ollama"
$env:JARVIS_MODEL_LOOPBACK_ENDPOINT = "http://127.0.0.1:11434"
python -m jarvis --model-smoke
```

For an explicitly configured llama.cpp runtime:

```powershell
$env:JARVIS_MODEL_PROVIDER = "llama_cpp"
$env:JARVIS_LLAMA_CPP_SERVER_PATH = "<user-local-runtime>\llama-server.exe"
$env:JARVIS_LLAMA_CPP_MODEL_PATH = "<external-model-directory>\model.gguf"
$env:JARVIS_MODEL_LOOPBACK_ENDPOINT = "http://127.0.0.1:18765"
$env:JARVIS_LOCAL_MODEL_AUTOSTART = "true"
python -m jarvis --model-smoke
```

The endpoint must remain a loopback HTTP origin with an explicit port. Heavy
inference and model storage are deployment-owned and must not create duplicate
stores on the constrained workstation. Model weights remain operator-owned;
Phase 12 does not download or copy them.
