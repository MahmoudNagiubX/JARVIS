# JARVIS local-model readiness report

**Status: `LOCAL_HERETIC_LIVE_READY`**

**Review date:** 2026-09-20
**Repository:** `C:\Jarivs\00_final\jarvis`
**Branch:** `feature/jarvis-final-completion`

## Exact model and runtime

The active local identity is exactly `Qwen3.5-4B-Heretic`. Standard Qwen 4B,
the legacy 9B Heretic file, projector/speculative files, and partial-download
artifacts are not substitutes and remain rejected by the production validators.

| Item | Live value |
|---|---|
| Final GGUF | `C:\Users\mahmo\AppData\Local\JARVIS\models\Qwen3.5-4B-heretic-Q4_K_M.gguf` |
| GGUF size | `2,708,804,384` bytes |
| GGUF SHA-256 | `E09C792EFC37446E3D31DFC7C9B91B8A6CEB7768DCD3EFE0A8F9D287C1A74579` |
| Source re-hash | Download source was independently re-hashed before use; exact SHA and size matched |
| Required alias | `Qwen3.5-4B-Heretic` |
| llama-server | `C:\Users\mahmo\AppData\Local\JARVIS\runtimes\llama.cpp\b10690\cuda12.4\package\llama-server.exe` |
| Runtime version | `0.3.0-dev`, build `10690`, commit `bdf395515`, Windows x86_64, Clang 20.1.8 |
| Runtime SHA-256 | `13C6F274CA84B6BABBDB6EABF51AC109D76C8EA3D1125F8A5C773C9733512E61` |
| Runtime signature | Authenticode `NotSigned`; no signer certificate |

The repository provenance record identifies this as the official
`ggml-org/llama.cpp` Windows CUDA 12.4 `b10690` release and records checksum
verification. The installed executable itself is unsigned; no publisher or
signature is inferred. The bounded runtime directory contains the CUDA package
archives, binaries, and `LICENSE-LLVM-OpenMP`, but no separate signed
provenance manifest.

The owner-provisioned GGUF was the exact `Qwen3.5-4B-heretic-Q4_K_M.gguf` file
from the approved `FadedRedStar/Qwen3.5-4B-heretic-GGUF` repository; its source
download was re-hashed locally before the JARVIS-owned copy was used.

## Final configuration and launch

The JARVIS-owned settings file was updated only in its model/runtime fields;
21 other owner settings were preserved unchanged. The effective desktop
configuration now validates as:

```text
provider_mode=hybrid
local_model=Qwen3.5-4B-Heretic
primary_model=Qwen3.5-4B-Heretic
fallback_model=Qwen3.5-4B-Heretic
endpoint=http://127.0.0.1:18765
autostart=true
context_size=4096
threads=8
gpu_layers=99
```

The canonical supervisor launched this exact bounded command:

```text
llama-server.exe --model C:\Users\mahmo\AppData\Local\JARVIS\models\Qwen3.5-4B-heretic-Q4_K_M.gguf --host 127.0.0.1 --port 18765 --ctx-size 4096 --threads 8 --no-webui --alias Qwen3.5-4B-Heretic --n-gpu-layers 99
```

Networking remained loopback-only. No Ollama was installed, added, started,
or used. No second browser/model authority was introduced.

The local provider also sends
`chat_template_kwargs={"enable_thinking": false}`. This is required for this
Qwen3.5 checkpoint: the default thinking channel can exhaust a small bounded
response budget while returning empty assistant `content`. JARVIS now rejects
empty non-tool content instead of reporting it as a successful response.

## Live evidence

All live checks used the real owner GGUF and the existing JARVIS supervisor,
not a mock server. The final settings-driven run reported the exact selected
model from both health and generation responses.

| Check | Result |
|---|---|
| Startup | PASS; observed `5,697 ms` from supervisor start through ready |
| Readiness | PASS; `llama_cpp_ready`, provider `llama_cpp`, model `Qwen3.5-4B-Heretic` |
| English | PASS; non-empty, `stop`, exact model, observed `283 ms` |
| Egyptian Arabic | PASS; non-empty Arabic-script response, exact model, observed `1,677 ms` |
| Mixed Arabic-English | PASS; non-empty mixed response, exact model, observed `501 ms` |
| Simple conversation | PASS; non-empty, exact model, observed `288 ms` |
| Simple command/intent | PASS; local `tool_orchestration`, non-empty intent response, observed `265 ms` |
| Cloud-disabled complex fallback | PASS; Groq/Gemini disabled, reasoning request fell back to local, non-empty, `stop` at a 256-token bound, observed `3,536 ms` |
| CLI model probe | PASS; generation checked and local model reported, observed probe generation `655 ms` |
| Fresh-process CLI recheck (2026-09-20) | PASS; `python -m jarvis --model-probe --model-exercise` reported `llama_cpp`, exact Heretic alias, `available=true`, and `generation_checked=true`; no owned runtime remained after shutdown |

The Arabic case was tested with an explicit Arabic/Egyptian-language system
instruction and produced Arabic-script output. The language observations are
smoke evidence, not a quality benchmark.

## Hybrid routing evidence

The three-model architecture remains unchanged:

| Capability | Provider/model | Evidence |
|---|---|---|
| Simple, fast, offline, intent | local / `Qwen3.5-4B-Heretic` | Real local generation; simple route made zero Groq/Gemini calls |
| Complex reasoning, coding, tools | Groq / `openai/gpt-oss-120b` | Deterministic recording-provider proof selected Groq when configured |
| Vision, media, large context | Gemini / `gemini-3.5-flash` | Deterministic recording-provider proof selected Gemini for media and large context |
| Cloud failure/rate-limit fallback | local / `Qwen3.5-4B-Heretic` | Recording Groq/Gemini failures fell through to local; real cloud-disabled complex run also passed |

No Groq or Gemini key is configured in this workstation, so no external cloud
request is claimed. The route proofs use provider-boundary recording adapters
only to verify selection and fallback order without spending cloud calls.

## Resource and latency observations

These are observations from NIGHTFURY, not product SLAs. During the final
settings-driven run, the owned `llama-server` process reported approximately
`3,659,952,128` bytes working set (about 3.41 GiB); `nvidia-smi` reported the
RTX 4050 Laptop GPU at `4,106 / 6,141 MiB` VRAM used/free `1,815 MiB`, and the
host had about `2,380 MiB` free RAM at the sample. The Q4_K_M model loaded and
generated reliably under this configuration; memory headroom remains a local
workstation observation rather than a guarantee under unrelated workloads.

Additional startup observations across the live runs were approximately
`5.7–8.1 seconds`; bounded generation observations were approximately
`0.27–2.30 seconds`, depending on language and response length.

## Process ownership and stale-path checks

- Start and shutdown were performed through `LlamaCppRuntimeSupervisor`.
- The observed command line contained only the exact Heretic GGUF and loopback
  flags; no legacy 9B path or old `jarvis-local-qwen` alias was active.
- After each owned run, a bounded process check found no JARVIS
  `llama-server.exe`, Ollama, or LM Studio process.
- Bounded source/config checks found no active standard-Qwen, 9B, BMO model,
  or old alias path. The legacy BMO 9B GGUF and `.invalid-resume` file were
  preserved and were not deleted or modified.
- The compatibility-only `11434` Ollama default remains in legacy API fields,
  but the active hybrid/desktop endpoint is `127.0.0.1:18765` and no Ollama
  process is present.

## Code fixes and verification

Root causes found and fixed during this continuation:

1. The owner-provided GGUF was not yet in the canonical JARVIS model root.
   It was independently hashed and copied without touching the Downloads
   source or unrelated owner files.
2. Qwen3.5 thinking output could consume the bounded response budget and
   leave empty assistant content. The local provider now disables thinking for
   this local contract and rejects empty non-tool responses.
3. System-prompt words such as `explain` could incorrectly promote a simple
   user turn to cloud routing. Capability marker inspection now ignores system
   contract text.
4. Desktop settings could force direct llama.cpp mode and bypass the hybrid
   router. Desktop startup now uses environment-driven hybrid defaults, and
   configured local autostart remains inside hybrid mode.

Regression coverage was added for all four code-controlled fixes. Final
verification results are:

```text
focused_model_hybrid_desktop=90 passed in 22.71s
full_python_regression=1013 passed, 3 skipped, 45 subtests passed in 441.71s
compileall=PASS
git_diff_check=PASS
```

## Verdict

`LOCAL_HERETIC_LIVE_READY`

No owner action remains for the local model setup. Optional cloud keys remain
unconfigured by design. The unsigned runtime signature is an informational
provenance limitation, not a fabricated trust claim; replacing it with a
publisher-signed/trusted build would be a separate operator policy decision.
