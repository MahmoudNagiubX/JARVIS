# Physical acceptance

Automated tests prove contracts and deterministic adapters, not physical
acceptance. A physical result is recorded only after the named dependency is
present and the operator observes the result on the target machine.

Required evidence for a live run includes timestamp, host/device identity,
software/model aliases, configuration fingerprint without secrets, command,
observed result, latency/error notes, and recovery result. Do not mark a
missing microphone, speaker, model, satellite, browser, Venom, HA/MQTT, or
messaging account as PASS.

The Phase 06 workstation audit detected Windows audio devices but found no
Ollama, PostgreSQL listener/client, Node/Playwright, FFmpeg, Venom, HA/MQTT, or
other live listener. Voice, satellite, browser/Playwright, and external-node
physical acceptance therefore remain deferred or partial in the checklist.

Phase 09 adds a runnable typed Windows satellite and loopback transport. On
2026-08-30, a bounded same-host physical acceptance ran a real Core server and
real satellite-agent process with an environment-only owner credential. A
non-dry-run `list_processes` observation reached the target through the
product `ComputerActionService`, returned a verified native result, and
produced matching audit metadata. The bounded evidence is stored at
`docs/phase09/evidence/PHYSICAL_COMPUTER_AUTHORITY_ACCEPTANCE.json`.

This proves the Windows authority path on the inspected host; it does not
claim an authorized second physical node. Phase 12 also loaded the existing
external Qwen GGUF through one loopback llama.cpp server and passed real
English, Arabic-script, mixed-language, provider-tool, AgentRuntime-text,
offline, and restart checks. The real AgentRuntime `desktop.context.read`
turn did not emit a tool event and remains `PARTIAL`; see
`docs/phase12/evidence/PHYSICAL_LOCAL_BRAIN.json`. Physical voice, Venom,
browser, and external services remain deferred.

Phase 10 desktop perception passed native active-window metadata, bounded
visible-window enumeration, and a real on-demand GDI capture on the inspected
Windows workstation. The transient frame was released and no screenshot file
was created. OCR, accessibility packages, local image-model inference, and
camera remain deferred; see `docs/phase10/evidence/PHYSICAL_DESKTOP_PERCEPTION.json`.

Phase 13 installed an explicit local physical-voice runner outside the normal
bootstrap. On 2026-08-31, local wake/VAD silence rejection, local STT silence
finalization, in-memory English/Arabic Piper synthesis, configured microphone
open with a drop-only callback, and configured speaker-format resolution
passed. This is **PARTIAL**, not a human physical voice PASS: no human wake,
English/Arabic/mixed transcription, audible speaker, Egyptian-Arabic quality,
barge-in observation, or device-loss recovery result is claimed. Sanitized
metrics-only evidence is in `docs/phase13/evidence/PHYSICAL_LOCAL_VOICE.json`.

The zero-touch desktop productization adds an in-app acceptance wizard and
sanitized evidence boundary. Its automated closure is recorded in
`docs/phase13/evidence/PHYSICAL_REALTIME_VOICE.json`; it remains
**PENDING / PARTIAL** until a human completes the microphone, wake, audible
speaker, bilingual, follow-up, and barge-in steps in the app. No automated
product test is a physical voice claim.
