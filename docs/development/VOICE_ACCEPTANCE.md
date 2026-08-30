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

The normal runtime still defaults to `NoOpSpeechToText` and
`NoOpTextToSpeech`. The local runner is opt-in and retains no raw input or
generated audio. Arabic `ar_JO-kareem-low` only establishes Arabic routing;
Egyptian-Arabic intelligibility remains partial/deferred until an Egyptian
speaker verifies it.
