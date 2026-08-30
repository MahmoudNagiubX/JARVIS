# ADR 0023: Keep VoiceCore above optional audio adapters

- Status: accepted
- Date: 2026-08-30

## Decision

`VoiceCore` remains the sole logical voice authority. Audio capture, STT, TTS,
and wake/VAD implementations are injected optional adapters selected by
profile configuration and cannot bypass identity or approval.

## Consequence

NoOp defaults and fake tests remain honest until physical audio dependencies
and acceptance evidence exist.
