# Phase 13 physical acceptance backlog

Phase 14 intentionally does not claim physical voice acceptance. The current
status remains deferred/partial for human end-to-end acceptance.

Deferred items:

- human wake-word reliability acceptance;
- English, Egyptian Arabic, and mixed STT acceptance;
- audible TTS quality and Egyptian-accent quality;
- follow-up and barge-in physical acceptance;
- Bluetooth duplex/output acceptance;
- device-loss physical recovery;
- the offline physical voice loop;
- acceptance-wizard gating and polish.

Known wizard debt:

1. The backend wake benchmark maps 8/10 or better to PASS, while a current UI
   or controller path may still effectively require 10/10 for operator PASS.
2. Current acceptance UI button-state logic can disable evidence buttons on
   non-Wake steps.

These are acceptance/test debts, not evidence of a physical PASS. Phase 14
keeps normal voice state visible when the backend reports it, but the primary
daily surface is text-capable and remains usable with `voice_enabled=false`.
The backlog belongs to the Phase 19 acceptance sweep.
