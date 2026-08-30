# Live voice

`VoiceCore` remains the single logical voice authority in every runtime
profile. It owns session state, follow-up expiry, cancellation, playback, and
the common AgentRuntime text path. Phase 13 adds an explicit local Windows
runner, not an autostart service: `python -m jarvis.voice.live` must be run
from the isolated voice environment after authentication and asset setup.

The runner resolves each endpoint freshly by exact `(host API, endpoint name,
direction)`. PortAudio numeric ids are process-local and are never saved. A
missing configured endpoint fails closed as `voice_device_missing`; multiple
matches fail as `voice_device_ambiguous`; recovery retries only the same
selector. This workstation's inspected WASAPI Realtek endpoints expose 48 kHz,
so capture is explicitly normalized in memory to the 16 kHz STT/wake/VAD
pipeline and synthesized PCM is explicitly resampled to the selected speaker.

The audio callback only copies 80 ms mono frames into a 2-second bounded
queue. Wake, VAD, endpointing, STT, AgentRuntime, TTS, database, event, and
async work occur off the callback. The active path is:

```text
microphone -> local wake/VAD -> local STT -> same VoiceCore -> same AgentRuntime
-> existing local ModelGateway/tool authority -> local TTS -> explicit speaker playback
```

No normal voice runtime code downloads assets or calls cloud speech APIs.
`JARVIS_VOICE_ENABLED` defaults to false; missing local assets fail startup.
`JARVIS_VOICE_WAKE_COMMAND_TIMEOUT_SECONDS` defaults to 5 seconds and is
validated from 1 through 15 seconds. The runner owns exactly one such timer:
it replaces the timer on a new wake and cancels it on VAD speech start, stop,
configured-device recovery, or transition back to sleep. Expiry discards only
the in-memory endpoint buffer, emits safe `voice.wake_timeout`, and creates no
agent turn. Resampled playback is capped at 60 seconds before the selected
speaker is called.
Use `docs/development/LOCAL_VOICE_SETUP.md` for the environment-only identity
and device configuration.

The local adapter and silent model/device smoke checks are implemented, but
full physical acceptance remains partial until an operator completes the
documented 10 wake, English, Arabic, mixed-language, speaker, follow-up,
barge-in/thinking-cancel, and device-loss recovery observations. Device
enumeration, silence probes, and deterministic tests do not constitute a
physical voice PASS.
