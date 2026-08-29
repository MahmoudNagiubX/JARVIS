# Voice acceptance

Run on the target Windows machine only after a real microphone and speaker are
selected. Verify wake/VAD, English, Arabic, mixed-language transcription,
TTS, follow-up turns, barge-in, cancellation, session cleanup, timeout, and
recovery after device removal/reconnect. Capture the evidence described in
`docs/production/PHYSICAL_ACCEPTANCE.md`.

The default Phase 06 runtime uses `NoOpSpeechToText` and
`NoOpTextToSpeech`; automated voice tests use injected deterministic fakes.
Those results prove lifecycle and cancellation boundaries only.
