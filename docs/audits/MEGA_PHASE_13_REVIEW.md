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

## Zero-Touch Productization Independent GitHub Review Remediation

The independent review found that the local `src/jarvis/desktop/secrets.py`
implementation was hidden by the generic `secrets.*` ignore rule and was not
present in the committed GitHub tree. It is now `secret_store.py`, explicitly
tracked, and retains Windows Credential Manager with DPAPI CurrentUser fallback
only; there is no plaintext fallback and the raw credential is absent from
settings, SQLite, logs, CLI arguments, VBS, UI, evidence, and Git.

The clean-tree gate is `scripts/verify_clean_tree_import.py`. It archives the
staged/committed tree and imports `jarvis.desktop`,
`JarvisDesktopLifecycle`, and `platform_secret_store` using only archived
sources. The product installer targets only the existing local voice venv,
uses offline `--no-deps --no-build-isolation` editable installation, and
verifies importability with `PYTHONPATH` and `JARVIS_VOICE_*` removed.

Setup now reconciles the secure device credential, safe settings, the
current-user Startup VBS, and the idempotent current-user Start Menu
`JARVIS.lnk`. The launcher targets `pythonw.exe`, carries only `-m
jarvis.desktop`, and the actual registered VBS launch reached
`desktop_start_ready` on NIGHTFURY. A second registered launch did not add a
second product runtime; the two observed Windows processes are the normal
venv launcher/interpreter process chain. Secure credential restore, same
product device reuse, local Qwen readiness, all local voice assets, and
mic/speaker selector resolution passed safe diagnostics.

The native UI now contains the requested setup/status matrix, microphone and
speaker selectors, transient mic and fixed safe speaker tests, bounded
follow-up setting, voice and Start-with-Windows toggles, device repair,
diagnostics, and a real guided physical acceptance wizard. Selector changes
persist stable names and rebind only the existing audio boundary. The wizard
requires Speaker, Microphone, Wake, English, Egyptian Arabic, Mixed
Arabic-English, Follow-Up, Barge-In, and Privacy Timeout in order. It cannot
write physical PASS before all human steps pass, and evidence remains
`PENDING` until then.

### Final automated closure

- Productization focused remediation matrix: **43 passed, 0 failed**.
- Phase 13 regression plus productization/remediation: **73 passed, 0 failed**.
- Phase 12 regression: **45 passed, 25 subtests passed, 0 failed**.
- Phase 11 regression: **26 passed, 0 failed**.
- Phase 10 regression: **31 passed, 0 failed**.
- Phase 09 regression: **39 passed, 0 failed**.
- Phase 08 regression: **13 passed, 0 failed**.
- Full repository suite: **291 passed, 25 subtests passed, 0 failed**.
- `python -m compileall src tests`: **PASS**.
- `git diff --check`: **PASS**.

Physical voice remains **PENDING / PARTIAL**. No human wake performance,
English/Arabic/mixed transcription quality, audibility, Egyptian-Arabic
quality, physical barge-in, or device-loss recovery PASS is inferred from
automated or subprocess checks.

## Physical Microphone Capture Reliability Closure

The old 250 ms `sounddevice.rec()` one-shot has been replaced by an explicit
2--5 second, approximately 3 second `InputStream` probe. The probe presents
“Speak now...” before capture, keeps Tk responsive, reports only peak/RMS/dBFS,
500 ms ambient baseline, speech delta, duration, frame count, clipping, and
usable-signal status, and never returns or persists PCM. A live meter is
updated from a worker-safe UI queue.

The existing runner is paused and restored in `finally` for explicit probes.
Candidate calibration tests stable host API/name selectors, ranks measured
speech signal before API preference, and offers one-click persistence/rebind.
Input/output duplex is opened together for an explicit PASS/PARTIAL result.
Recoverable PortAudio status flags are counted while healthy frames continue;
runner diagnostics expose input frames/bytes, callback time/faults, wake
frames/detections/score, and pre/post-resample safe signal metrics. Silero VAD
and wake scores are exposed as status only. Acceptance microphone PASS now
requires a usable probe, and wake PASS requires backend detections.

The authority boundary is unchanged: no second VoiceCore, scheduler, EventBus,
ModelGateway, model server, SQL cleanup, cloud audio path, raw-audio file, or
transcript retention was added.

### Final closure validation

- New physical microphone capture focused file: **15 passed, 0 failed**.
- Phase 13 regression plus productization/remediation: **88 passed, 0 failed**.
- Phase 08--12 regression: **154 passed, 25 subtests passed, 0 failed**.
- Full repository suite: **306 passed, 25 subtests passed, 0 failed**.
- `python -m compileall src tests`: **PASS**.
- `git diff --check`: **PASS**.

### Bounded local host probe

- Configured input opened through the isolated voice interpreter at native
  **44,100 Hz**, receiving **84,672 frames** with **0 callback faults**.
- No human speech was supplied during the probe: peak **-90.31 dBFS**, RMS
  **-96.70 dBFS**, ambient RMS **-96.71 dBFS**, speech delta **0.02 dB**,
  `usable_signal=false`. This is the expected non-acceptance result for a
  silent automated run and is not a human voice PASS.
- Configured output `MME / Headphones (soundcore R60i NC)` was absent from the
  current PortAudio enumeration, so simultaneous duplex was **PARTIAL** and
  failed closed without opening an unselected endpoint.

Physical human acceptance remains **PENDING / PARTIAL**. The only required
operator action is to speak when the in-app probe says “Speak now...” and then
complete the guided wake/voice steps; no terminal or manual numeric device
index is required.

## Wake Acceptance Wizard Final Closure

The Wake step is now a guided, bounded diagnostic on the existing
`LocalVoiceRuntime`. `Start Wake Test` and `Stop Test` control a ten-attempt
session with isolated 3.5-second attempts, automatic miss/reset progression,
100 ms UI polling, live confidence metrics, and PASS/PARTIAL/FAIL mapping at
8/10, 5--7/10, and below 5/10. Diagnostic detections remain in the sleeping
boundary and do not invoke STT, AgentRuntime, Qwen, TTS, follow-up, or the
normal wake command timeout. The session counter is independent from the
process-lifetime wake counter, and close, stop, completion, and failure restore
normal voice wake behavior. Only sanitized counters and scores are exposed;
raw audio is not retained.

### Final closure validation

- Wake acceptance focused matrix: **19 passed, 0 failed**.
- Phase 13 regression including the wake wizard fix: **107 passed, 0 failed**.
- Phase 08--12 regression: **154 passed, 25 subtests passed, 0 failed**.
- Full repository suite: **325 passed, 25 subtests passed, 0 failed**.
- `python -m compileall src tests`: **PASS**.
- `git diff --check`: **PASS**.

Physical human voice acceptance remains **PENDING / PARTIAL**. Automated tests
prove the guided backend flow and its safety boundaries; they do not infer
human wake performance, audibility, transcription quality, or the remaining
physical acceptance steps.
