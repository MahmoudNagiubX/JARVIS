# Voice core

`VoiceCore` owns logical voice session state and delegates audio work to
injected STT/TTS/playback adapters. `VoiceSessionContext` carries session,
device, input, output, and optional room identifiers. The state model includes
sleeping, wake-detected, listening, transcribing, thinking, speaking,
interrupted, follow-up, and stopped states.

Final transcripts enter the same `AgentRuntime` text path as API messages.
`VoiceCore` owns the active AgentRuntime task, synthesis task, and explicit
playback task. `barge_in()` cancels any of those tasks, stops playback, emits
a safe event, and returns the session to listening; a cancelled response is
never played later. Spoken presentation is bounded to 1,200 characters only
at the TTS boundary and does not alter typed chat.

The explicit Phase 13 local runner starts a context in `sleeping`, detects a
local wake word, then moves through `wake_detected` to `listening`. A
follow-up window accepts a second turn without another wake; its expiry returns
a wake-enabled session to `sleeping`. Owner/device/context checks happen
before STT. Voice cannot decide an approval: spoken confirmation is ordinary
input and existing approval routes still require their explicit durable
decision context.

Normal bootstrap remains no-op and opens no hardware or model. Phase 13 adds
an opt-in `python -m jarvis.voice.live` runner that configures the *existing*
runtime VoiceCore before it starts; it does not create a VoiceAgent, a second
AgentRuntime, model gateway, tool registry, scheduler, or EventBus. Raw PCM,
pre-roll, partial transcripts, and generated audio are memory-only and never
enter events, audit, memory, world state, HUD, logs, evidence, or Git.
