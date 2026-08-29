# Voice core

`VoiceCore` owns logical voice session state and delegates audio work to
injected STT/TTS adapters. `VoiceSessionContext` carries session, device,
input, output, and optional room identifiers. The state model includes
sleeping, wake-detected, listening, transcribing, thinking, speaking,
interrupted, follow-up, and stopped states.

Final transcripts enter the same `AgentRuntime` text path as API messages.
Synthesis is cancellable; `barge_in()` cancels the active TTS task, emits
voice cancellation events, and returns the session to listening. Language
metadata is preserved on transcripts and is not used to claim perfect Arabic,
Egyptian Arabic, or multilingual recognition quality.

Phase 02 supplies no new audio models and does not open hardware at startup.
The default adapters are no-op; tests inject deterministic STT/TTS fakes.
Physical microphone, speaker, wake-word, VAD, and realtime transport
acceptance is therefore partial.
