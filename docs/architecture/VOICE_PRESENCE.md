# Voice Presence

The existing `VoiceCore` remains the sole voice pipeline. A completed TTS
turn enters an explicit, configurable follow-up window (30 seconds by
default), then returns to listening and emits `voice.follow_up_expired`.
Starting or stopping a session cancels the timer; there is no indefinite open
microphone.

`VoiceSessionContext` carries session, owner, device, endpoint, room, and
conversation references when supplied. `VoiceRoutingService` keeps output on
the originating room unless deterministic handoff is selected. Speech is
never implicit approval: durable approval context and an explicit bound
decision remain required.

Phase 09 profile fields expose the selected input/output adapter names in
health, while `VoiceCore` remains the one runtime authority. Physical adapter
selection and acceptance are documented in `LIVE_VOICE.md`; the inventory
found no installed audio runtime beyond Windows endpoint enumeration.
