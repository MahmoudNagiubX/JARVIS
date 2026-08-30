# Live voice

`VoiceCore` remains the single logical voice authority in every runtime
profile. It owns session state, follow-up expiry, cancellation, and the common
text-agent path. Input and output adapters are selected by explicit profile
configuration; Phase 09 defaults remain `noop` because this workstation has
no installed audio runtime or speech assets.

Physical acceptance is deferred until an operator selects a microphone and
speaker and installs an explicitly approved adapter. The acceptance record
must cover wake/VAD, English and Arabic samples, TTS, follow-up, barge-in,
cancellation, device removal/reconnect, and recovery. Device enumeration or
deterministic fake tests do not constitute physical voice PASS.
