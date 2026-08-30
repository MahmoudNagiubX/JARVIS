# Phase 13 voice workstation inventory

Inspected 2026-08-31 on the Windows-primary workstation. This document records
safe device/runtime facts only; it contains no captured audio, transcript,
credential, or absolute user path.

| Item | Observation | Phase 13 treatment |
|---|---|---|
| OS | Windows 11 Home Single Language, build 26200 | Windows-first local runner |
| CPU/RAM | 15.6 GiB RAM | CPU/int8 STT default preserves local-model headroom |
| GPUs | NVIDIA RTX 4050 Laptop GPU and Intel UHD | No GPU STT claim; CUDA remains opt-in |
| Input | Windows WASAPI `Microphone Array (Realtek(R) Audio)` | exact host/name selector; 48 kHz endpoint |
| Output | Windows WASAPI `Speakers (Realtek(R) Audio)` | exact host/name selector; 48 kHz endpoint |
| Device probe | input opened briefly with a drop-only callback; output format resolved | no input byte was retained and no sound was played |
| Python | isolated `%LOCALAPPDATA%\JARVIS\voice\venv` | optional voice stack stays outside repository interpreter |
| Wake/VAD | openWakeWord ONNX `hey_jarvis_v0.1`, Silero VAD ONNX | local, explicit asset paths only |
| STT | faster-whisper `small`, local directory, CPU/int8 | silence probe returned final empty text; no hub/model-name runtime load |
| TTS | Piper English `en_US-hfc_female-medium`; Arabic `ar_JO-kareem-low` | in-memory PCM only; English 22.05 kHz and Arabic 16 kHz resampled for output |

The original Realtek endpoints reject direct 16/22.05 kHz PortAudio format
checks but accept 48 kHz. The runner intentionally converts in memory rather
than selecting another endpoint or relying on a persisted numeric device id.

Installed optional versions in the isolated environment: `sounddevice 0.5.6`,
`onnxruntime 1.29.0`, `openwakeword 0.6.0`, `faster-whisper 1.2.1`, and
`piper-tts 1.7.0`. No asset, binary, venv, or audio file is tracked by Git.
