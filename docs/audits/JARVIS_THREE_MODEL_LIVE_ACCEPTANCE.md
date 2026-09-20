# JARVIS three-model live acceptance

**Final verdict: `THREE_MODEL_OWNER_KEYS_REQUIRED`**

**Review date:** 2026-09-20
**Repository:** `C:\Jarivs\00_final\jarvis`
**Branch:** `feature/jarvis-final-completion`
**Code status:** secure-store integration is implemented and tested; owner
secret entry and a fresh desktop-process cloud retest remain pending.

This report separates provider live evidence from credential-persistence
evidence. The three providers have real live acceptance evidence from the
owner's process-only helper runs, but `THREE_MODEL_LIVE_READY` is not claimed
until the same providers are proven after a normal desktop restart using keys
read from the protected current-user store.

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
| Persistent desktop key | Not yet owner-entered in the protected store |

The live result came from the owner-approved process-only acceptance flow. No
key value is retained in this report.

### Gemini

| Field | Truth |
|---|---|
| Provider/model | `gemini` / `gemini-3.5-flash` |
| Live model access | PASS |
| Live text generation | PASS |
| Live vision generation | PASS |
| Fallback used | `false` |
| Persistent desktop key | Not yet owner-entered in the protected store |

The vision acceptance used the bounded generated PNG fixture and direct
provider isolation. No owner media or key value is retained in this report.

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
but it is not the normal desktop source. A normal `python -m jarvis` runtime
also prefers stored values when present; an empty store preserves the
process-only acceptance-helper path.

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

The fallback matrix is covered by deterministic hybrid tests. The owner still
needs one fresh desktop-process check after secure key entry to close the
restart-persistence gate.

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
entry, no-environment-fallback, settings-scrubbing, and provider-injection
regressions. Required release checks remain:

```text
python -m pytest tests -q
python -m compileall src tests scripts -q
python scripts/verify_clean_tree_import.py
git diff --check
```

## OWNER ACTIONS REMAINING

Run these two commands locally and enter each key only at the hidden prompt:

```powershell
python -m jarvis --set-cloud-key groq
python -m jarvis --set-cloud-key gemini
python -m jarvis --cloud-key-status
```

Then start a fresh normal desktop process and run the bounded provider probes
or the desktop diagnostics. Once both providers are observed using the stored
credentials after restart, update this verdict to
`THREE_MODEL_LIVE_READY` with that fresh-process evidence.
