# Phase 13 latency and bounded-work budget

The physical runner uses 80 ms capture frames and a maximum 2-second pending
queue. Its memory-only endpointing budget is 480 ms pre-roll, 240 ms minimum
speech, 800 ms end silence, 20 seconds maximum utterance, and a 30-second hard
safety cap. Final transcripts are limited to 4,000 characters and spoken TTS
input to 1,200 characters.

No end-to-end human latency is claimed yet. The inspected offline smoke checks
loaded the local wake, VAD, STT, English Piper, and Arabic Piper adapters; the
full combined cold load is resource-heavy, so CPU/int8 STT is the default and
the local Qwen service remains independently budgeted. Physical acceptance
must record aggregate latency metrics only, never audio or transcript content.
