# Voice Presence

The existing `VoiceCore` remains the sole voice pipeline. A completed TTS
turn enters an explicit, configurable follow-up window (30 seconds by
default), then returns to `sleeping` for wake-enabled physical sessions (or
`listening` for historical text/fake sessions) and emits
`voice.follow_up_expired`. Starting or stopping a session cancels the timer.

`VoiceSessionContext` carries session, owner, device, endpoint, room, and
conversation references when supplied. `VoiceRoutingService` keeps output on
the originating room unless deterministic handoff is selected. Speech is
never implicit approval: durable approval context and an explicit bound
decision remain required.

Phase 13's local runner is a lifecycle adapter only. It carries the existing
enrolled `Identity`, authenticated `DeviceIdentity`, and
`VoiceSessionContext`; it never infers an owner or turns voice into a durable
approval decision. Its safe lifecycle events contain only ids/counts/reasons,
never PCM, transcript text, generated audio, credentials, or device paths.
