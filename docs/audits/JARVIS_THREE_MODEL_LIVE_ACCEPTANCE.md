# JARVIS three-model live acceptance

**Final verdict: `THREE_MODEL_LIVE_READY`**

**Review date:** 2026-09-20
**Repository:** `C:\Jarivs\00_final\jarvis`
**Branch:** `feature/jarvis-final-completion`
**Code status:** secure-store integration and persisted non-secret enablement
are implemented, tested, and proven from fresh processes.

This report separates provider live evidence from credential-persistence
evidence. The three providers have real live acceptance evidence, and the
cloud probes were rerun from fresh PowerShell child processes with
`GROQ_API_KEY` and `GEMINI_API_KEY` removed from the process environment.
Those probes loaded credentials from the protected current-user store and
loaded model enablement from persisted desktop settings.

## LOCAL

| Item | Verified value |
|---|---|
| Model identity | `Qwen3.5-4B-Heretic` |
| GGUF | `C:\Users\mahmo\AppData\Local\JARVIS\models\Qwen3.5-4B-heretic-Q4_K_M.gguf` |
| GGUF size | `2,708,804,384` bytes |
| GGUF SHA-256 | `E09C792EFC37446E3D31DFC7C9B91B8A6CEB7768DCD3EFE0A8F9D287C1A74579` |
| Runtime | `C:\Users\mahmo\AppData\Local\JARVIS\runtimes\llama.cpp\b10690\cuda12.4\package\llama-server.exe` |
| Runtime version | `0.3.0-dev`, build `10690`, commit `bdf395515` |
| Runtime SHA-256 | `13C6F274CA84B6BABBDB6EABF51AC109D76C8EA3D1125F8A5C773C9733512E61` |
| Runtime signature | Authenticode `NotSigned`; signer certificate `NONE` |
| Endpoint | `http://127.0.0.1:18765` |
| Fresh-process model exercise | PASS; `llama_cpp_ready`; generation checked |

Live local evidence is `Qwen3.5-4B-Heretic` through llama.cpp with health and
generation passing. The supervisor owns startup and cleanup; previous runs
reported no owned `llama-server.exe` after shutdown. No Ollama or LM Studio was
added. The Q4_K_M run observed approximately 3.41 GiB working set and
4,106/6,141 MiB RTX 4050 VRAM used/total. These are workstation observations,
not service-level guarantees.

## CLOUD PROVIDERS

### Groq

| Field | Truth |
|---|---|
| Provider/model | `groq` / `openai/gpt-oss-120b` |
| Live model access | PASS |
| Live text generation | PASS |
| Fallback used | `false` |
| Health reason | `groq_ready` |
| Persistent desktop key | Configured in the protected current-user store; fresh-process probe PASS |

The fresh-process result came from the protected current-user store with the
process-only Groq environment variable removed. No key value is retained in
this report.

### Gemini

| Field | Truth |
|---|---|
| Provider/model | `gemini` / `gemini-3.5-flash` |
| Live model access | PASS |
| Live text generation | PASS |
| Live vision generation | PASS |
| Fallback used | `false` |
| Persistent desktop key | Configured in the protected current-user store; fresh-process probe PASS |

The fresh-process vision acceptance used the bounded generated PNG fixture and
direct provider isolation with the process-only Gemini environment variable
removed. No owner media or key value is retained in this report.

## SECURE-STORE IMPLEMENTATION

The normal desktop path now uses the existing `platform_secret_store()`
authority: Windows Credential Manager first, DPAPI CurrentUser fallback, and
no plaintext fallback. The bounded identifiers are:

```text
jarvis-groq-api-key
jarvis-gemini-api-key
```

`python -m jarvis --set-cloud-key groq` and `--set-cloud-key gemini` read a
hidden prompt and replace the protected value without accepting a command-line
secret. `--delete-cloud-key` and `--cloud-key-status` are also available.

Desktop startup reads the two values once, passes them directly to the cloud
provider objects, and does not copy them to `os.environ`. Missing store values
are explicit empty provider credentials, so a stale process environment cannot
silently override the secure-store decision. The existing process-environment
compatibility path remains available for acceptance tooling and direct tests,
but it is not the normal desktop source.

The non-secret authority is `%LOCALAPPDATA%\JARVIS\config\settings.json`.
`resolve_runtime_config()` is shared by the desktop lifecycle and the normal
CLI runtime, so provider probes do not have a special enablement path. The
persisted values are `hybrid`, local `Qwen3.5-4B-Heretic`, Groq enabled with
`openai/gpt-oss-120b`, and Gemini enabled with `gemini-3.5-flash`. A fresh
`python -m jarvis` process therefore uses the same settings and secure-store
resolution as desktop startup without requiring cloud environment variables.

Only non-secret desktop settings are persisted: `hybrid` mode, provider
enablement, the exact required cloud model IDs, and the existing Heretic local
configuration. Settings, `JarvisConfig`, SQLite, events, audits, and normal
diagnostics contain no cloud key values. Desktop diagnostics expose only
`configured`, `missing_key`, `ready`, or `unavailable` cloud states.

## ROUTING MATRIX

The capability router is deterministic and does not call an LLM to choose the
next model:

| Capability | Provider/model | Evidence |
|---|---|---|
| Simple, fast, command/intent, offline | local / `Qwen3.5-4B-Heretic` | live local smoke plus routing tests |
| Complex reasoning, planning, coding, tools | Groq / `openai/gpt-oss-120b` | live provider acceptance plus routing tests |
| Vision, screenshots, media, large context | Gemini / `gemini-3.5-flash` | live text/vision acceptance plus routing tests |

Only the selected provider is called on success. Cloud prompts remain bounded;
local requests do not require cloud access.

## FALLBACK MATRIX

| Condition | Expected/covered result |
|---|---|
| Groq healthy | Groq |
| Groq unavailable and Gemini healthy | Gemini |
| Groq and Gemini unavailable | local Heretic |
| No internet | local Heretic |
| Gemini media route unavailable | truthful Gemini failure; no unsafe text-only acceptance |

The fallback matrix is covered by deterministic hybrid tests. The fresh
process provider probes above close the restart-persistence gate.

## SECURITY AND PROVENANCE

- API keys are not in repository files, `.env`, settings JSON, SQLite,
  JARVIS Memory, logs, events, audits, or command-line arguments.
- Diagnostics expose only bounded status/metadata and never raw keys or
  authorization headers.
- No direct OpenAI runtime provider exists; `openai/` is only the required
  Groq model identifier.
- The llama.cpp binary is checksum-recorded and identified as the official
  `ggml-org/llama.cpp` Windows CUDA 12.4 `b10690` package, but it is unsigned;
  no publisher/signature is inferred.

## TESTS

The current change adds secure-store round-trip, replacement/deletion, hidden
entry, no-environment-fallback, settings-scrubbing, provider-injection, and
fresh-process settings-resolution regressions. Verification evidence:

- Focused model/config/desktop suite: `134 passed, 919 deselected, 9
  subtests passed`.
- Full suite: `1050 passed, 3 skipped, 54 subtests passed`.
- `python -m compileall src tests scripts -q`: PASS.
- `python scripts/verify_clean_tree_import.py`: PASS.
- `git diff --check`: PASS.

The required release commands are:

```text
python -m pytest tests -q
python -m compileall src tests scripts -q
python scripts/verify_clean_tree_import.py
git diff --check
```

## OWNER ACTIONS REMAINING

No additional key entry is required for this acceptance. The existing
protected current-user entries were read successfully from fresh processes;
the raw values remain outside the repository and this report.
