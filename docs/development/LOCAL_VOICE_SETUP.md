# Local physical voice setup

This is a Windows-first, local-only setup. Run it from the isolated voice
environment, not the normal repository interpreter. It requires pre-existing
enrolled identity/device credentials; it does not bootstrap an owner.

Set these environment variables in the launching process, never as CLI secret
arguments:

```powershell
$env:JARVIS_VOICE_ENABLED = 'true'
$env:JARVIS_VOICE_INPUT_HOST_API = 'Windows WASAPI'
$env:JARVIS_VOICE_INPUT_DEVICE = 'Microphone Array (Realtek(R) Audio)'
$env:JARVIS_VOICE_OUTPUT_HOST_API = 'Windows WASAPI'
$env:JARVIS_VOICE_OUTPUT_DEVICE = 'Speakers (Realtek(R) Audio)'
$env:JARVIS_VOICE_WAKE_MODEL_PATH = "$env:LOCALAPPDATA\JARVIS\voice\wake\hey_jarvis_v0.1.onnx"
$env:JARVIS_VOICE_VAD_MODEL_PATH = "$env:LOCALAPPDATA\JARVIS\voice\vad\silero_vad_16k_op15.onnx"
$env:JARVIS_VOICE_STT_MODEL_PATH = "$env:LOCALAPPDATA\JARVIS\voice\stt\faster-whisper-small"
$env:JARVIS_VOICE_TTS_EN_MODEL_PATH = "$env:LOCALAPPDATA\JARVIS\voice\tts\en\en_US-hfc_female-medium.onnx"
$env:JARVIS_VOICE_TTS_AR_MODEL_PATH = "$env:LOCALAPPDATA\JARVIS\voice\tts\ar\ar_JO-kareem-low.onnx"
$env:JARVIS_VOICE_IDENTITY_ID = '<existing identity id>'
$env:JARVIS_VOICE_DEVICE_ID = '<existing enrolled device id>'
$env:JARVIS_VOICE_CREDENTIAL = '<existing credential>'
```

Optional bounded controls are `JARVIS_VOICE_WAKE_THRESHOLD` (0.05--0.99),
`JARVIS_VOICE_VAD_THRESHOLD` (0.05--0.99),
`JARVIS_VOICE_VAD_END_SILENCE_MS` (600--900),
`JARVIS_VOICE_FOLLOW_UP_SECONDS` (1--120),
`JARVIS_VOICE_STT_DEVICE` (`cpu` or `cuda`), and
`JARVIS_VOICE_STT_COMPUTE_TYPE`. CPU/int8 is the inspected workstation default
to preserve the separate local Qwen runtime.

Start only after the normal local-model environment is configured:

```powershell
$env:PYTHONPATH = 'src'
& "$env:LOCALAPPDATA\JARVIS\voice\venv\Scripts\python.exe" -m jarvis.voice.live
```

Ctrl+C stops capture, playback, the voice session, and the regular runtime.
Do not set the process to autostart yet. The runner has no cloud fallback,
model download, audio file output, or persisted PortAudio device id.
