# Voice acceptance

Run on the target Windows machine only after the explicit local voice setup is
complete. Verify 10 detected wakes, VAD/endpointing, English, Arabic, and
mixed-language transcription, English and Arabic TTS, speaker output,
follow-up turns, wake during thinking/playback, cancellation, session cleanup,
timeout, and recovery after the *configured* device removal/reconnect. Capture
only the safe metrics described in `docs/production/PHYSICAL_ACCEPTANCE.md`.

Run the automated Phase 13 matrix first:

```powershell
$env:PYTHONPATH = 'src'
python -m unittest tests.test_phase_thirteen_physical_voice -v
```

It proves authority, privacy, bounded queue, state, and adapter contracts; it
does not prove a human can hear or be understood by the selected hardware.

The pre-physical matrix currently contains 30 passing tests. It also proves
that wake listening times out without speech or an agent run; actual VAD speech
cancels that timeout; a new wake replaces it; and stop or configured-device
recovery cancels it. Empty STT sleeps after an initial wake, preserves the
existing bounded follow-up expiry, and restores historical non-wake listening.
Every successful follow-up turn receives a fresh full interval.

Approval-required voice turns keep the durable approval pending, emit only a
safe approval event, speak a fixed product message, and bound wake mode back to
sleep. The matrix cancels an actual blocked AgentRuntime generation during
thinking and verifies that no old TTS/playback survives into the next turn.
It also verifies the typed `voice_playback_too_long` failure occurs after
resampling and before any device call for PCM over the 60-second hard bound.

The normal runtime still defaults to `NoOpSpeechToText` and
`NoOpTextToSpeech`. The local runner is opt-in and retains no raw input or
generated audio. Arabic `ar_JO-kareem-low` only establishes Arabic routing;
Egyptian-Arabic intelligibility remains partial/deferred until an Egyptian
speaker verifies it.

## In-app physical wizard

The installed desktop UI exposes the human acceptance flow in this exact
order: Speaker, Microphone, Wake, English, Egyptian Arabic, Mixed
Arabic-English, Follow-Up, Barge-In, and Privacy Timeout. Speaker and
microphone checks are transient; the wake screen displays the safe detected-wake
counter from the existing runner. Each step must be explicitly recorded by the
operator, and the controller prevents advancing out of order. Evidence remains
`PENDING` until all nine steps are PASS; automated tests never fabricate
acoustic or language-quality PASS.

The zero-touch final remediation also validates the tracked secure store,
clean-archive imports, the exact product interpreter without `PYTHONPATH`, the
secret-free Startup VBS and Start Menu shortcut, the UI seams, and the
single-instance second-launch boundary.

## Bounded product preflight

Before opening the microphone continuously, run the silent product-owned
preflight from the provisioned local voice environment:

```powershell
$env:PYTHONPATH = 'C:\Jarivs\00_final\jarvis\src'
& "$env:LOCALAPPDATA\JARVIS\voice\venv\Scripts\python.exe" -m jarvis --voice-preflight
```

It reads the existing desktop settings and secure device credential, checks
the exact configured input/output selectors by descriptor enumeration only,
validates the wake/VAD/faster-whisper/Piper asset shape, and checks the exact
local Heretic runtime/model references. It does not start the runtime, open a
continuous audio stream, retain PCM, or call cloud speech. A nonzero result is
not physical acceptance; it is a readiness blocker to fix or hand to the
owner.

The STT setting may point at the JARVIS-owned `voice\stt` root. The resolver
now selects the actual loadable `faster-whisper-small` directory beneath it;
the preflight will not report a parent directory as ready when
`config.json`/`model.bin` are missing.
