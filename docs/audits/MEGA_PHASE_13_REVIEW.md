# Mega Phase 13 review: physical realtime voice

## Scope and authority result

Phase 13 adds an opt-in Windows-local physical voice lifecycle runner. It
extends the existing `VoiceCore`; it does not add a VoiceAgent, AgentRuntime,
ModelGateway, ToolRegistry, PermissionEngine, ApprovalEngine, scheduler, or
EventBus. Final STT text takes the existing AgentRuntime/tool authority path.
Notifications retain the same bootstrap VoiceCore instance.

## Implemented boundaries

- `VoiceRuntimeConfig` is disabled by default and validates exact input/output
  host API/name selectors plus local wake, VAD, STT, and both Piper model paths.
- `LocalVoiceRuntime` owns only device/capture lifecycle. Its 80 ms callback
  copies into a bounded 2-second queue; VAD/STT/TTS/DB/events never run on the
  audio callback.
- The configured Realtek WASAPI endpoints are resolved per run. Numeric
  PortAudio ids are not persisted; missing/ambiguous selectors fail closed and
  recovery retries only the same selector.
- Local ONNX wake/VAD, local-directory faster-whisper, and local Piper run on
  explicit paths. There is no runtime cloud speech API, hub download, raw-audio
  file, or normal-runtime optional package import.
- VoiceCore owns cancellation for thinking, synthesis, and playback. Barge-in
  cannot leave an old answer playing. Wake-enabled follow-up expiry returns to
  sleeping.
- PCM, pre-roll, partial STT, and generated TTS are memory-only. Safe events
  contain only language/ids/counts/reasons. Voice owner/device binding is
  checked before STT; spoken “yes” does not resume a durable approval.

## Review constraints and open physical work

The protected BMO Phase 10 evidence file was not read, modified, staged, or
committed. No broad SQL cleanup, schema migration, public binding, model reset,
or duplicate authority was introduced.

The delivered local smoke evidence is **PARTIAL**. It does not claim human
wake performance, English/Arabic/mixed STT quality, speaker audibility,
Egyptian-Arabic intelligibility, live barge-in perception, or real device-loss
recovery. See `docs/phase13/evidence/PHYSICAL_LOCAL_VOICE.json` and the
operator matrix in `docs/development/VOICE_ACCEPTANCE.md`.

## Closure validation

- Phase 13 focused matrix: **14 passed, 0 failed**.
- Phase 12 focused regression: **11 passed, 0 failed**.
- Phase 08--09 regression: **52 passed, 0 failed**.
- Phase 10--11 regression: **57 passed, 0 failed**.
- Full repository suite: **232 passed, 0 failed**.
- `python -m compileall src tests`: PASS.
- `git diff --check`: PASS.

## Independent GitHub Review Remediation

The pre-physical review gaps were closed without changing the Phase 13
authority shape. `LocalVoiceRuntime` now owns one bounded wake-command timer;
`VoiceCore` preserves state-specific empty-STT and renewed follow-up semantics,
handles PAUSED and FAILED wake turns safely, and retains the existing
AgentRuntime cancellation boundary. Playback rejects post-resample PCM over
60 seconds before a sound-device call. No VoiceAgent, second AgentRuntime,
second ModelGateway, second Qwen server, scheduler, EventBus, schema migration,
cloud speech path, or broad cleanup was added.

The focused tests prove false-wake timeout with zero agent runs, VAD-start and
lifecycle cancellation, timer replacement, empty-STT restoration, fresh
follow-up timing, pending approval safety and spoof resistance, real thinking
cancellation with a clean next turn, and the playback hard bound.

- Phase 13 focused/total matrix: **25 passed, 0 failed**.
- Phase 12 focused regression: **11 passed, 0 failed**.
- Phase 11 regression: **26 passed, 0 failed**.
- Phase 10 regression: **31 passed, 0 failed**.
- Phase 09 regression: **39 passed, 0 failed**.
- Phase 08 regression: **13 passed, 0 failed**.
- Full repository suite: **243 passed, 0 failed**.
- `python -m compileall src tests`: PASS.
- `git diff --check`: PASS.

Physical status remains **PARTIAL**. Automated lifecycle proof does not claim
human wake detection, transcription quality, audibility, live physical
barge-in, or physical device-loss recovery.

## Speech-start liveness closure

The physical runner now treats endpoint speech transitions explicitly without
owning follow-up timing. Rejected short speech after an initial wake cancels
any stale command-start timer, returns the session to sleeping, and performs no
STT or AgentRuntime call, so a fresh wake is required. When speech starts in
follow-up, VoiceCore holds its existing expiry task while preserving the
original deadline and run id, preventing expiry in the middle of an active
utterance.

Rejected follow-up noise restores only the remaining original deadline. An
accepted candidate remains reserved through STT: empty STT restores that same
remaining deadline, while a successful completed turn receives one fresh full
follow-up window. Repeated hold/restore cycles produce one expiry, and stop
clears a held reservation without a leaked timer.

- Phase 13 focused/total matrix: **30 passed, 0 failed**.
- Phase 12 focused regression: **11 passed, 0 failed**.
- Phase 11 regression: **26 passed, 0 failed**.
- Phase 10 regression: **31 passed, 0 failed**.
- Phase 09 regression: **39 passed, 0 failed**.
- Phase 08 regression: **13 passed, 0 failed**.
- Full repository suite: **248 passed, 0 failed, 0 errors**.
- Raw PCM, partial STT, and generated-audio retention regression: **ZERO**.
- `python -m compileall src tests`: **PASS**.
- `git diff --check`: **PASS**.
- Physical human acceptance: **PENDING / PARTIAL**.

## Zero-touch desktop productization closure

The final productization pass adds a single `JarvisDesktopLifecycle`
orchestrator around the already-composed runtime. It adds versioned safe user
settings, current-user Windows Credential Manager with DPAPI fallback, explicit
first-run enrollment/reuse through `IdentityService`, product-device repair,
stable audio selector reconciliation, local speech-asset validation, a
current-user no-console startup entry, single-instance locking, tray/status
control, diagnostics, and sanitized in-app acceptance evidence. The existing
HUD remains the primary experience surface; no second dashboard or domain
authority was introduced.

The product path does not read `JARVIS_VOICE_CREDENTIAL`,
`JARVIS_VOICE_IDENTITY_ID`, or `JARVIS_VOICE_DEVICE_ID`. It does not download
or copy Qwen, start a second model server, persist raw credentials, retain
audio/transcripts/TTS bytes, expand public GET routes, or revoke unrelated
devices. Voice pause/resume reuses the existing `LocalVoiceRuntime` and
`VoiceCore`.

### Final automated closure

- Productization focused matrix: **29 passed, 0 failed**.
- Phase 13 regression plus productization: **59 passed, 0 failed**.
- Phase 12 suite including focused closure: **45 passed, 0 failed**.
- Phase 11 regression: **26 passed, 0 failed**.
- Phase 10 regression: **31 passed, 0 failed**.
- Phase 09 regression: **39 passed, 0 failed**.
- Phase 08 regression: **13 passed, 0 failed**.
- Full repository suite: **277 passed, 25 subtests passed, 0 failed**.
- `python -m compileall src tests`: **PASS**.
- `git diff --check`: **PASS**.

Physical voice remains **PENDING / PARTIAL**. The productization tests do not
claim human wake performance, transcription quality, speaker audibility,
Egyptian-Arabic intelligibility, physical barge-in, or device-loss recovery.
The sanitized product evidence is in
`docs/phase13/evidence/PHYSICAL_REALTIME_VOICE.json`.
