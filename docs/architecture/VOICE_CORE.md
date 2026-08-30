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
bounded wake-command timer then requires VAD speech to start within the
configured window; otherwise the endpoint buffer is discarded, no agent turn
is created, and the session returns to `sleeping`. A follow-up window accepts
a second turn without another wake. Its old timer is cancelled when a valid
transcript starts, every successful completion receives a fresh full interval,
and expiry returns a wake-enabled session to `sleeping`.

Empty STT has state-specific semantics without creating a user message or
agent run: initial wake listening returns to `sleeping`, follow-up restores its
existing bounded deadline, and historical non-wake voice returns to
`listening`. Owner/device/context checks still happen before STT. A paused
agent run emits a safe `voice.approval_required` event, speaks only a fixed
product message, leaves the durable approval pending, and bounds a wake session
back to `sleeping`. Spoken confirmation remains ordinary input and cannot
decide an approval. Failed wake turns likewise return to `sleeping`.

Physical speech start reserves an active follow-up immediately: VoiceCore
holds its expiry task while preserving the original deadline and run id. A
rejected endpoint candidate restores only the remaining original window, while
an accepted candidate stays reserved through STT and receives a fresh full
window only after a successful completed turn. Rejected initial wake noise
returns to `sleeping` and requires a fresh wake without invoking STT or the
agent.

Automated cancellation coverage blocks a real AgentRuntime model generation,
barges in during `thinking`, proves the run is cancelled before TTS/playback,
and proves a subsequent turn is clean. Speaker PCM is resampled first and then
rejected before the device call when it exceeds the hard 60-second playback
bound (`voice_playback_too_long`).

Normal bootstrap remains no-op and opens no hardware or model. Phase 13 adds
an opt-in `python -m jarvis.voice.live` runner that configures the *existing*
runtime VoiceCore before it starts; it does not create a VoiceAgent, a second
AgentRuntime, model gateway, tool registry, scheduler, or EventBus. Raw PCM,
pre-roll, partial transcripts, and generated audio are memory-only and never
enter events, audit, memory, world state, HUD, logs, evidence, or Git.
