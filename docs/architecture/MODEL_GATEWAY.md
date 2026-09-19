# Model gateway

`ModelGateway` is the only runtime model entry point. Routes are explicit:

- `fast_conversation`
- `general_reasoning`
- `tool_orchestration`
- `vision`
- `coding_worker`

Configuration is environment-driven. Production bootstrap defaults to the
hybrid route; direct `JarvisConfig()` construction remains mock-compatible for
deterministic tests.

```text
JARVIS_MODEL_PROVIDER=hybrid|mock|ollama|gguf|llama_cpp
JARVIS_PRIMARY_MODEL=Qwen3.5-4B-Heretic
JARVIS_FALLBACK_MODEL=Qwen3.5-4B-Heretic
JARVIS_LOCAL_MODEL=Qwen3.5-4B-Heretic
JARVIS_MODEL_LOOPBACK_ENDPOINT=http://127.0.0.1:18765
JARVIS_GROQ_ENABLED=false
JARVIS_GROQ_MODEL=openai/gpt-oss-120b
JARVIS_GROQ_REASONING_EFFORT=low
JARVIS_GEMINI_ENABLED=false
JARVIS_GEMINI_MODEL=gemini-3.5-flash
```

The default provider is deterministic mock mode. In production environment
bootstrap, hybrid mode uses the explicit loopback llama.cpp endpoint and does
not assume Ollama is installed or running. The Ollama adapter is an explicit
compatibility profile only: it calls an already-running loopback `/api/chat`
or `/api/tags` endpoint when `JARVIS_MODEL_PROVIDER=ollama`. The `llama_cpp`
adapter calls the product-owned bounded OpenAI-compatible
`/v1/chat/completions` boundary. It normalizes response and tool-call shapes,
caps response bodies and generation timeouts, and reports offline/readiness
errors without a cloud or mock fallback. `gguf` is accepted as a compatibility
alias for `llama_cpp`.

An explicitly configured local llama.cpp runtime may be started by the single
`LlamaCppRuntimeSupervisor`; the default bootstrap remains no-autostart. The
supervisor validates an external `Qwen3.5-4B-Heretic` `.gguf`, uses a fixed
loopback-only argv with `shell=False`, and stops only a process it owns. It can
attach to a compatible listener but never kills an incompatible listener or
copies/downloads model weights. The exact model filename and server alias are
required; standard Qwen, 9B Heretic, partial-download, and projector GGUFs are
rejected.

No model provider is contacted during import or runtime composition. Tests
inject mock providers and can verify routing without GPU or model state.

## Hybrid capability routing

The hybrid gateway keeps one common `LLMProvider` boundary and chooses a
provider from request capability facts, never by asking another model to make
the choice:

| Capability | Primary | Bounded fallback order |
|---|---|---|
| simple/fast/basic command | local `Qwen3.5-4B-Heretic` | Groq, then Gemini |
| complex reasoning, planning, coding, tools | Groq `openai/gpt-oss-120b` | Gemini, then local |
| screenshot/image/document/multimodal | Gemini `gemini-3.5-flash` | local only when no media bytes are present |

Only the first provider is called when it succeeds. Cloud requests retain the
system instruction and recent bounded evidence rather than sending the entire
conversation history. Groq and Gemini keys are read only from `GROQ_API_KEY`
and `GEMINI_API_KEY`; their enablement flags default to false so a local-only
machine remains offline-capable. Groq use is limited by configuration to the
owner's Groq account/model choice; the owner must keep that account on the
Groq Free Tier.

The gateway emits `model.route.selected` and `model.route.fallback` events and
writes bounded provider/model/route/reason fields to the operational logger.
It never records prompts, media bytes, or API keys.

`JARVIS_OLLAMA_BASE_URL` remains a compatibility input, while
`model_loopback_endpoint` is the profile-neutral health/configuration name.
Live model validation is documented in `LIVE_MODEL_RUNTIME.md` and remains
opt-in. The current bounded audit has now verified the owner-provisioned exact
4B Heretic GGUF, its checksum, the existing llama.cpp runtime, fresh startup,
live generation, and supervisor cleanup; current evidence is recorded in
`docs/audits/JARVIS_LOCAL_MODEL_READINESS.md` with verdict
`LOCAL_HERETIC_LIVE_READY`. The local text model truthfully
reports `model_route_unsupported` for vision, requires its configured alias in
`/v1/models`, and serializes generation with one active request plus eight
bounded waiters. Tool-schema selection is deterministic and selector-only:
conservative Unicode normalization preserves reachability for English,
Egyptian-Arabic Arabic-script, and mixed intents. Arabic or mixed requests
for active application/window metadata expose the bounded
`desktop.context.read` schema; English visual requests retain the existing
visual group. Explicit pixel, region, or cached-observation requests remain
the only reason to expose `screen.observe` or `screen.latest`.
