# Manual owner setup

This file contains only owner-controlled steps that cannot be completed safely
by unattended JARVIS code. No secret value belongs in this repository, SQLite,
Memory, logs, prompts, browser pages, or audit payloads.

| Item | Needed? | Secret? | Exact owner action | Exact place/config | Test |
|---|---:|---:|---|---|---|
| Groq API key | Optional for cloud reasoning | Yes | Create a Groq Free Tier key and supply it to the JARVIS process as `GROQ_API_KEY`; do not paste it into chat or commit it | Process environment / approved secret store; `JARVIS_GROQ_ENABLED=true` | Run a complex planning request and confirm the UI/event shows Groq `openai/gpt-oss-120b` without exposing the key |
| Gemini API key | Optional for vision/large context | Yes | Supply `GEMINI_API_KEY` to the JARVIS process and set `JARVIS_GEMINI_ENABLED=true` | Process environment / approved secret store | Submit a screenshot or document and confirm Gemini `gemini-3.5-flash` is selected |
| Local model | Configured and live-ready | No, but path is private | No remaining download action; keep the exact owner-provisioned `Qwen3.5-4B-Heretic-Q4_K_M.gguf` and never replace it with standard Qwen or the legacy 9B file | JARVIS-owned desktop settings: exact Heretic alias/path, existing llama.cpp runtime, loopback `http://127.0.0.1:18765`, autostart enabled | Read `docs/audits/JARVIS_LOCAL_MODEL_READINESS.md`; re-hash before any future relocation and rerun the live smoke matrix |
| Codex login | Only for live developer work | Session credential | Sign in to the installed Codex CLI yourself | Codex CLI; enable `JARVIS_CODEX_WORKER_ENABLED=true` only after review | Run a read-only task, then an explicitly approved fixture workspace-write task |
| AntiGravity via Codex | Optional | Session credential | If desired, configure the approved AntiGravity interface for Codex only; JARVIS must not launch or authenticate to AntiGravity directly | Developer environment used by Codex | Ask Codex for one bounded UI-review child and confirm the parent reviews it |
| Spotify | Optional | App login | Sign in inside the installed Spotify app | Native desktop app; configure an exact study playlist alias | Open/focus, resolve the exact playlist, play, pause, and verify title/playlist |
| Discord | Optional | App login | Sign in inside Discord and configure one exact test destination alias | Native desktop app / JARVIS integration settings | Compose a nonce to the exact destination; approve manually; verify one read-back |
| WhatsApp | Optional | App login/link | Link/sign in inside WhatsApp Desktop and use self-chat only by default | Native desktop app / JARVIS integration settings | Send a nonce to “myself” only after approval and verify one read-back |
| OneNote | Optional | Microsoft login | Sign in inside OneNote and configure a dedicated JARVIS study notebook/section/page | Native desktop app / study settings | Open the exact page and use only the dedicated JARVIS test area |
| Notion | Optional | App login | Sign in inside Notion and configure an exact Study Dashboard alias | Native desktop app preferred; Browser V2 fallback | Open the exact page; add only a nonce/test block after approval |
| ChatGPT | Optional | App/web login | Authenticate only in the dedicated JARVIS browser profile or verified official ChatGPT app; never use the normal Brave profile | Browser V2 owner-session settings / dedicated `OwnerPersistent` profile | Open ChatGPT, confirm the owner shell, and use a fresh nonce only after explicit send confirmation |
| Gmail | Optional | Browser login | Authenticate only in the dedicated JARVIS browser profile and configure a self/test recipient | Browser V2 setup | Create, verify, and delete a test draft; keep send disabled unless explicitly approved |
| Brave | Required for Browser V2 | No | Keep the already installed standard Brave binary selected; do not install another browser | Exact local executable path and dedicated JARVIS profile, never normal profile | Run bounded public navigation/read/close; owner-authenticated acceptance remains separate |
| Microphone | Optional until voice acceptance | No | Select the intended microphone in the desktop setup wizard | Desktop settings; no raw audio persistence | Run the physical voice checklist |
| Speaker | Optional until voice acceptance | No | Select the intended speaker in the desktop setup wizard | Desktop settings; no raw audio persistence | Run the physical voice checklist |
| Wake-word acceptance | Physical owner gate | No | Say `Hey JARVIS` in a quiet and normal environment and record pass/fail | Physical acceptance checklist | Repeat in English, Egyptian Arabic, mixed speech, and with interruption |

## Safety boundary

Owner login, API-key entry, exact private destinations, microphone choice, and
physical acceptance remain manual. JARVIS must show `Missing key`, `Login
Required`, `Service Blocked`, `Offline`, or `PHYSICAL_PENDING` truthfully rather
than inventing a ready state.

The current local-model evidence is recorded separately in
`docs/audits/JARVIS_LOCAL_MODEL_READINESS.md`. The download gate is complete;
future changes must preserve the exact identity, loopback boundary, and
supervisor cleanup behavior.

## Safe one-shot cloud probe

When a cloud key is available, use the repository helper from a PowerShell
session. It prompts with hidden input, supplies the key only to the child
process, runs exactly one bounded provider probe, and removes the process
environment value before exiting. It never writes `.env`, SQLite, Memory,
logs, or command-line arguments.

```powershell
.\scripts\invoke_cloud_provider_probe.ps1 -Provider groq
.\scripts\invoke_cloud_provider_probe.ps1 -Provider gemini
```

The owner must run these commands locally; JARVIS cannot discover or extract
the keys.
without downloading weights.
