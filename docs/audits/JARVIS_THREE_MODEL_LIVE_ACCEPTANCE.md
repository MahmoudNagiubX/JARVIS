# JARVIS three-model live acceptance

**Final verdict: `THREE_MODEL_OWNER_KEYS_REQUIRED`**

**Review date:** 2026-09-20
**Repository:** `C:\Jarivs\00_final\jarvis`
**Branch:** `feature/jarvis-final-completion`
**Starting HEAD:** `8df09797bcb0152a5bd9a048e52ed36c4a868b50`
**Final HEAD:** `8df09797bcb0152a5bd9a048e52ed36c4a868b50` (working tree changes are not committed)

The local Heretic route is live and verified. The final verdict is not
`THREE_MODEL_LIVE_READY` because `GROQ_API_KEY` and `GEMINI_API_KEY` were
absent from the acceptance process, so no real cloud request is claimed.
All code-controlled acceptance work was completed; only owner secret entry and
the resulting live cloud calls remain.

## LOCAL

Exact active identity and runtime:

| Item | Verified value |
|---|---|
| Model identity | `Qwen3.5-4B-Heretic` |
| GGUF | `C:\Users\mahmo\AppData\Local\JARVIS\models\Qwen3.5-4B-heretic-Q4_K_M.gguf` |
| GGUF size | `2,708,804,384` bytes |
| GGUF SHA-256 | `E09C792EFC37446E3D31DFC7C9B91B8A6CEB7768DCD3EFE0A8F9D287C1A74579` |
| Runtime | `C:\Users\mahmo\AppData\Local\JARVIS\runtimes\llama.cpp\b10690\cuda12.4\package\llama-server.exe` |
| Runtime version | `0.3.0-dev`, build `10690`, commit `bdf395515`, Windows x86_64, Clang 20.1.8 |
| Runtime SHA-256 | `13C6F274CA84B6BABBDB6EABF51AC109D76C8EA3D1125F8A5C773C9733512E61` |
| Runtime signature | Authenticode `NotSigned`; signer certificate `NONE` |
| Endpoint | `http://127.0.0.1:18765` |

The runtime provenance record identifies the binary as the checksum-verified
official `ggml-org/llama.cpp` Windows CUDA 12.4 `b10690` package. The binary
is unsigned; no publisher or signature is inferred.

Effective user-scoped non-secret configuration was verified in a fresh child
process:

```text
provider=hybrid
primary=Qwen3.5-4B-Heretic
fallback=Qwen3.5-4B-Heretic
local=Qwen3.5-4B-Heretic
endpoint=http://127.0.0.1:18765
context=4096
threads=8
gpu_layers=99
autostart=true
```

The exact supervisor launch configuration is:

```text
llama-server.exe --model C:\Users\mahmo\AppData\Local\JARVIS\models\Qwen3.5-4B-heretic-Q4_K_M.gguf --host 127.0.0.1 --port 18765 --ctx-size 4096 --threads 8 --no-webui --alias Qwen3.5-4B-Heretic --n-gpu-layers 99
```

Fresh-process live evidence:

```text
python -m jarvis --model-probe --model-exercise
provider=llama_cpp
model=Qwen3.5-4B-Heretic
available=true
health_reason=llama_cpp_ready
generation_checked=true
```

The current recheck observed `237.89 ms` probe generation. Earlier settings-
driven live runs also passed English, Egyptian Arabic, mixed Arabic-English,
simple conversation, simple command/intent, and cloud-disabled complex
fallback. Their observed startup/generation ranges are approximately
`5.7–8.1 s` startup and `0.27–3.54 s` generation, with approximately 3.41 GiB
working set and 4,106/6,141 MiB RTX 4050 VRAM used/total during the selected
Q4_K_M run. These are workstation observations, not SLAs.

Every live run ended with a bounded process check reporting no owned
`llama-server.exe`; the supervisor remains the only process owner/cleanup
authority. No Ollama or LM Studio was installed, added, or used. Legacy BMO
9B files were preserved and are not active configuration.

## GROQ

| Field | Truth |
|---|---|
| Adapter | Actual modular `GroqProvider` behind `ModelGateway` |
| Required model | `openai/gpt-oss-120b` |
| Key state | `GROQ_API_KEY` absent in the acceptance process |
| Enabled state for normal process | false by default; owner opt-in only |
| Live request | Not run; no key was available |
| Safe CLI probe | `--model-provider-probe groq` returned `OWNER_ACTION_REQUIRED` with `generation_checked=false` before making a provider call |

The adapter’s HTTP, payload, tool-call, rate-limit, timeout, and redaction
paths are covered by deterministic tests. A real Groq success, real model
response, and real Free Tier account acceptance remain owner-key-gated.

## GEMINI

| Field | Truth |
|---|---|
| Adapter | Actual modular `GeminiProvider` behind `ModelGateway` |
| Required model | `gemini-3.5-flash` |
| Key state | `GEMINI_API_KEY` absent in the acceptance process |
| Enabled state for normal process | false by default; owner opt-in only |
| Live request | Not run; no key was available |
| Safe CLI probe | `--model-provider-probe gemini` returned `OWNER_ACTION_REQUIRED` with `generation_checked=false` before making a provider call |
| Media fixture | Provider probe uses a transient in-memory 1×1 PNG; no owner media is read or persisted |

The adapter’s GenerateContent, transient inline media, function-call,
large-context, timeout/error, and redaction paths are covered by deterministic
tests. Real Gemini vision acceptance remains owner-key-gated.

## ROUTING MATRIX

The deterministic capability router does not call an LLM to choose a model.
The following matrix is proven by the gateway tests and the prior real local
smoke evidence:

| Category | First provider/model | Reason | Fallback count on success | Result |
|---|---|---|---:|---|
| Short simple chat | local / `Qwen3.5-4B-Heretic` | `fast_local_capability` | 0 | PASS |
| Simple command/intent | local / `Qwen3.5-4B-Heretic` | `simple_command_capability` | 0 | PASS; zero cloud calls |
| Offline | local / `Qwen3.5-4B-Heretic` | local/offline capability | 0 | PASS; real local generation |
| Complex reasoning | Groq / `openai/gpt-oss-120b` | `reasoning_or_tool_capability` | 0 | PASS by recording-provider route proof; real call pending key |
| Planning/coding/tools | Groq / `openai/gpt-oss-120b` | `reasoning_or_tool_capability` | 0 | PASS by deterministic route proof |
| Screenshot/image/document | Gemini / `gemini-3.5-flash` | `multimodal_or_visual_capability` | 0 | PASS by media route proof; real call pending key |
| Large context | Gemini / `gemini-3.5-flash` | `large_context` | 0 | PASS by deterministic route proof |

Only the selected first provider is called when it succeeds. Cloud history is
compacted to the system contract plus bounded recent evidence, and media is
never sent to local or Groq text-only providers.

## FALLBACK MATRIX

| Condition | Observed truth |
|---|---|
| Groq healthy → complex request | Groq selected; no fallback |
| Groq unavailable/rate-limited + Gemini healthy | Gemini selected after one normalized Groq failure |
| Groq and Gemini unavailable | Local Heretic selected after two normalized cloud failures |
| Local unavailable + Groq healthy on complex request | Groq succeeds first; local is not called |
| Gemini unavailable with real media | Truthful normalized Gemini failure; no unsafe text-only fallback |
| All providers unavailable | Truthful final normalized provider error; no false success |
| No internet/no cloud keys | Local Heretic remains the offline path |

The last three fallback/error cases have explicit regression coverage in
`tests/test_hybrid_models.py`.

## HEALTH / STATUS TRUTH

The safe architecture snapshot and UI health projection distinguish:

```text
Local Heretic: configured/live when loopback health is checked
Groq: disabled or missing_key until owner opt-in and key are present
Gemini: disabled or missing_key until owner opt-in and key are present
```

The new CLI surfaces are:

```powershell
python -m jarvis --model-architecture
python -m jarvis --model-provider-probe groq
python -m jarvis --model-provider-probe gemini
```

The provider probe performs one bounded real call only after the configured
provider has a process key; it reports the actual provider/model and marks a
fallback instead of treating a fallback response as provider acceptance.

## SECRETS REVIEW

- `GROQ_API_KEY` and `GEMINI_API_KEY` were absent; no secret discovery or
  credential-manager/browser-cookie scraping was attempted.
- No `.env` file exists in the repository; only `.env.example` is present.
- No secret-shaped `gsk_...` or `AIza...` values were found in bounded source,
  docs, audit, or repository text checks.
- Three repository SQLite files were checked for the same secret-shaped
  patterns; zero matches were found.
- Architecture snapshots, health/UI projections, events, and provider errors
  expose only provider/model/state/error-code metadata; tests assert that
  injected fake keys do not appear.
- No direct OpenAI API runtime provider or `OPENAI_API_KEY` path exists. The
  `openai/` text is only the required Groq model identifier and compatibility
  wording.

## ISSUES FOUND / FIXED

1. Cloud model IDs could be overridden by arbitrary environment values. Hybrid
   configuration now rejects anything except the required Groq and Gemini IDs.
2. There was no explicit cloud-provider/architecture CLI acceptance surface.
   Added safe architecture and one-call provider probes with missing-key
   short-circuiting and no secret output.
3. There was no safe owner key-entry helper. Added
   `scripts/invoke_cloud_provider_probe.ps1`; it prompts via `SecureString`,
   passes the key only to a child process, and removes it on exit without
   writing `.env` or command-line secrets.
4. The active model-gateway and local-policy documents still described the
   exact local GGUF as owner-download-pending. Updated them to the verified
   live state.
5. Added regression coverage for both-cloud fallback, local-unavailable with
   Groq healthy, all-provider unavailable truth, exact cloud IDs, provider
   probe call count, and missing-key short-circuiting.

## TESTS

```text
model/provider subset: 96 passed, 927 deselected, 2 subtests passed
hybrid routing final file: 26 passed, 2 subtests passed
full regression: 1020 passed, 3 skipped, 47 subtests passed
compileall src tests scripts: PASS
verify_clean_tree_import.py: OK
git diff --check: PASS
```

The three skips are pre-existing optional OCR dependency skips for EasyOCR,
torch, and torchvision.

## OWNER ACTIONS REMAINING

Only the two cloud secrets and the resulting live provider acceptance remain:

```powershell
.\scripts\invoke_cloud_provider_probe.ps1 -Provider groq
.\scripts\invoke_cloud_provider_probe.ps1 -Provider gemini
```

Each command prompts for its key with hidden input and keeps it process-only.
The owner must use Groq Free Tier credentials and a Gemini API key through the
approved owner environment/secret mechanism. After keys are present in the
inherited JARVIS process environment with the two enablement flags set to
`true`, rerun the two probes and the routing/fallback live matrix. Until then,
the truthful status is `THREE_MODEL_OWNER_KEYS_REQUIRED`, not live cloud
acceptance.
