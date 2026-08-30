# Phase 09 Workstation Inventory

Inventory timestamp: `2026-08-30T02:53:17.9221284+03:00`
Host: `NIGHTFURY`
Scope: non-destructive Windows workstation discovery; no audio capture, model download, or BMO modification.

## Operating system

Observed with `[System.Environment]::OSVersion` and bounded `Get-ComputerInfo`:

| Field | Value |
|---|---|
| Product | Windows 10 Home Single Language |
| Version | 2009 |
| Build | 26200 |
| Architecture | 64-bit |
| Computer name | NIGHTFURY |
| Processor | 12th Gen Intel(R) Core(TM) i7-12700H |

The product/version label and build are recorded as reported by Windows; no deployment assumption is made from the label alone.

## Python and Git

| Probe | Result |
|---|---|
| Python | 3.14.6 |
| Python launcher | 3.14 default; 3.12.13 also installed via uv |
| Git | 2.55.0.windows.3 |
| Repository | `C:\Jarivs\00_final\jarvis` |
| Phase 09 starting HEAD | `cc62a44c07d5fec763ba4252ec86f07bd13b3273` |

The repository was clean after the separately pushed Phase 08 closure commit.

## Disk, RAM, and CPU

| Resource | Observed |
|---|---:|
| C: used | 426.43 GB |
| C: free | 22.92 GB |
| Physical RAM | 15.64 GB |
| Free RAM at probe | 2.26 GB |
| CPU cores / logical processors | 14 / 20 |
| CPU max clock reported | 2300 MHz |

C: space and free RAM are constrained. Phase 09 must not create large model caches, duplicate model stores, or heavy local inference artifacts. A Windows workstation profile is the practical first target; heavy inference should remain external to this machine only if an already configured runtime exists.

## Audio devices

`Get-PnpDevice -Class AudioEndpoint` found these available endpoints:

- `Microphone Array (Realtek(R) Audio)` — OK
- `Speakers (Realtek(R) Audio)` — OK

Default endpoint selection was not changed, and no continuous recording was performed. No Phase 10 audio runtime was found installed in this Python environment: `sounddevice`, `pyaudio`, `faster_whisper`, `torch`, and `onnxruntime` were not importable. `numpy` was importable. Physical voice acceptance is therefore `DEFERRED` pending an explicitly selected local adapter and existing speech assets.

## Local AI runtime

| Probe | Result |
|---|---|
| Ollama executable | NOT_FOUND |
| Ollama process | NOT_FOUND |
| `127.0.0.1:11434` | NOT_LISTENING |
| `/api/tags` | NOT_PROBED because loopback port was closed |
| llama.cpp / llama-server | NOT_FOUND |
| Existing Ollama directory | `C:\Users\mahmo\.ollama` exists with `models` directory |
| Ollama manifests | No manifest files returned by bounded probe |

The existing external Ollama directory was not modified and model blobs were not opened, copied, hashed, or downloaded. Local model physical acceptance is `PARTIAL`/`DEFERRED`: an external model-store shape exists, but no usable runtime or alias was detected.

## SSH and Venom configuration

| Probe | Result |
|---|---|
| `ssh.exe` | `C:\Windows\System32\OpenSSH\ssh.exe` |
| `scp.exe` | `C:\Windows\System32\OpenSSH\scp.exe` |
| `ssh-agent` | Stopped, Disabled |
| `%USERPROFILE%\.ssh\config` | NOT_FOUND |
| SSH alias `venom` | NOT_FOUND |
| `JARVIS_VENOM_HOST` | NOT_SET |

No Venom hostname/IP/SSH user was guessed. Venom physical probing and tunnel acceptance are `DEFERRED` until an authorized host configuration exists.

## BMO historical reference inspection

The legacy BMO repository was inspected read-only at:

`C:\Users\mahmo\Desktop\BMO\BMO-Personal-AI-OS`

Relevant reusable reference areas found:

- `src/personal_ai_os/voice/state.py` — 112 lines; explicit wake/follow-up/barge-in state machine.
- `src/personal_ai_os/voice/pipeline.py` — 298 lines; bounded wake/VAD/STT/Core/TTS/follow-up flow.
- `src/personal_ai_os/voice/adapters.py` — 492 lines; lazy optional adapters and dependency checks.
- `src/personal_ai_os/satellites/windows/agent.py` — 258 lines; authenticated typed satellite agent reference.
- `src/personal_ai_os/satellites/windows/config.py` — 50 lines; bounded satellite configuration reference.
- `scripts/phase_09` and `scripts/phase_10` — deployment and acceptance references.

The reference uses optional components including `faster-whisper`, `onnxruntime`, `sherpa-onnx`, `sounddevice`, and `torch`. These are not installed into JARVIS by this inventory and no BMO source or evidence was changed.

Protected evidence verification:

`docs/phase_reports/evidence/PHASE_10_JARVIS_VOICE_CORE.json` SHA-256 remained `9A04DD2BD7717B70817DFFB62707512376CF378EB82B1028135A0D978ECB85D1`.

## Deployment decision

- **Profile A — live workstation:** selected as the only immediately plausible deployment profile, but model and physical voice remain deferred by the inventory results.
- **Profile B — always-on distributed:** deferred; no authorized Venom host, SSH alias, or tunnel configuration is present.
- **Physical computer control:** existing local bounded controller is available for later harmless acceptance; no new UI automation was run during inventory.
- **Physical evidence:** no PASS is claimed from mocks or from device enumeration alone.
