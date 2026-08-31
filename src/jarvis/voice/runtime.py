"""Lifecycle runner for one physical, local workstation voice endpoint."""

from __future__ import annotations

import asyncio
import math
import queue
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from ..contracts import DeviceIdentity, Identity, VoiceSessionContext, VoiceSessionState
from ..events import EventState
from .adapters import (
    FasterWhisperSpeechToText,
    OpenWakeWordDetector,
    PiperTextToSpeech,
    SileroVad,
    SoundDeviceInput,
    SoundDevicePlayback,
    SpeechEndpointDetector,
    SignalMetrics,
    VoiceDeviceError,
    pcm16_metrics,
    resample_pcm_16le,
)
from .config import VoiceRuntimeConfig
from .core import VoiceCore


class VoiceRunnerState(StrEnum):
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class WakeAcceptanceSnapshot:
    """Metrics-only state for one bounded physical wake acceptance run."""

    active: bool
    attempt_target: int
    attempt_index: int
    detections: int
    misses: int
    last_score: float | None
    best_score: float | None
    attempt_deadline: float | None
    started_at: float | None
    result: str | None


class AudioInput(Protocol):
    sample_rate: int

    def start(self, callback: callable) -> None: ...

    def stop(self) -> None: ...

    def take_fault(self) -> bool: ...


class AudioOutput(Protocol):
    def start(self) -> None: ...

    async def stop(self) -> None: ...

    def close(self) -> None: ...

    def take_fault(self) -> bool: ...


class LocalVoiceRuntime:
    """Capture/endpoint lifecycle only; VoiceCore remains the authority owner."""

    queue_capacity = 25  # 25 x 80 ms frames: at most two seconds of pending PCM.

    def __init__(
        self,
        voice: VoiceCore,
        audio_input: AudioInput,
        audio_output: AudioOutput,
        wake: OpenWakeWordDetector,
        endpointing: SpeechEndpointDetector,
        *,
        wake_command_timeout_seconds: float = 5.0,
    ) -> None:
        self.voice = voice
        self.audio_input = audio_input
        self.audio_output = audio_output
        self.wake = wake
        self.endpointing = endpointing
        self.wake_command_timeout_seconds = wake_command_timeout_seconds
        self._state = VoiceRunnerState.CREATED
        self._identity: Identity | None = None
        self._device: DeviceIdentity | None = None
        self._pcm: queue.Queue[bytes] = queue.Queue(maxsize=self.queue_capacity)
        self._queue_overruns = 0
        self._total_queue_overruns = 0
        self._consumer_task: asyncio.Task[None] | None = None
        self._turn_task: asyncio.Task[None] | None = None
        self._wake_command_task: asyncio.Task[None] | None = None
        self._wake_detections = 0
        self._input_frames_received = 0
        self._input_bytes_received = 0
        self._last_input_frame_monotonic: float | None = None
        self._wake_frames_received = 0
        self._last_wake_score: float | None = None
        self._last_input_metrics: SignalMetrics | None = None
        self._last_resampled_metrics: SignalMetrics | None = None
        self._wake_acceptance_active = False
        self._wake_acceptance_attempt_target = 10
        self._wake_acceptance_attempt_index = 0
        self._wake_acceptance_detections = 0
        self._wake_acceptance_misses = 0
        self._wake_acceptance_last_score: float | None = None
        self._wake_acceptance_best_score: float | None = None
        self._wake_acceptance_attempt_deadline: float | None = None
        self._wake_acceptance_started_at: float | None = None
        self._wake_acceptance_result: str | None = None
        self._wake_acceptance_attempt_open = False
        self._wake_acceptance_attempt_seconds = 3.5
        self._wake_acceptance_cooldown_seconds = 0.1
        self._wake_acceptance_signal: asyncio.Event | None = None
        self._wake_acceptance_task: asyncio.Task[None] | None = None

    @property
    def state(self) -> VoiceRunnerState:
        return self._state

    @property
    def queue_overruns(self) -> int:
        return self._total_queue_overruns

    @property
    def wake_command_timer_active(self) -> bool:
        task = self._wake_command_task
        return task is not None and not task.done()

    @property
    def wake_detections(self) -> int:
        """Count safe wake detections for the in-app physical acceptance flow."""

        return self._wake_detections

    @property
    def input_frames_received(self) -> int:
        return self._input_frames_received

    @property
    def input_bytes_received(self) -> int:
        return self._input_bytes_received

    @property
    def last_input_frame_monotonic(self) -> float | None:
        return self._last_input_frame_monotonic

    @property
    def audio_callback_fault_count(self) -> int:
        return int(getattr(self.audio_input, "callback_fault_count", 0))

    @property
    def wake_frames_received(self) -> int:
        return self._wake_frames_received

    @property
    def last_wake_score(self) -> float | None:
        return self._last_wake_score

    @property
    def wake_acceptance_active(self) -> bool:
        return self._wake_acceptance_active

    @property
    def wake_acceptance_snapshot(self) -> WakeAcceptanceSnapshot:
        return WakeAcceptanceSnapshot(
            active=self._wake_acceptance_active,
            attempt_target=self._wake_acceptance_attempt_target,
            attempt_index=self._wake_acceptance_attempt_index,
            detections=self._wake_acceptance_detections,
            misses=self._wake_acceptance_misses,
            last_score=self._wake_acceptance_last_score,
            best_score=self._wake_acceptance_best_score,
            attempt_deadline=self._wake_acceptance_attempt_deadline,
            started_at=self._wake_acceptance_started_at,
            result=self._wake_acceptance_result,
        )

    @property
    def diagnostics(self) -> dict[str, int | float | None | bool | dict[str, float] | str]:
        """Return safe counters and levels; never include PCM or transcripts."""

        def metrics(value: SignalMetrics | None) -> dict[str, float] | None:
            if value is None:
                return None
            return {
                "peak": value.peak,
                "rms": value.rms,
                "peak_dbfs": value.peak_dbfs,
                "rms_dbfs": value.rms_dbfs,
            }

        vad = getattr(self.endpointing, "vad_diagnostics", {})
        return {
            "input_frames_received": self.input_frames_received,
            "input_bytes_received": self.input_bytes_received,
            "last_input_frame_monotonic": self.last_input_frame_monotonic,
            "audio_callback_fault_count": self.audio_callback_fault_count,
            "wake_frames_received": self.wake_frames_received,
            "wake_detections": self.wake_detections,
            "last_wake_score": self.last_wake_score,
            "wake_threshold": getattr(self.wake, "threshold", None),
            "wake_acceptance": {
                "active": self.wake_acceptance_active,
                "attempt_target": self._wake_acceptance_attempt_target,
                "attempt_index": self._wake_acceptance_attempt_index,
                "detections": self._wake_acceptance_detections,
                "misses": self._wake_acceptance_misses,
                "last_score": self._wake_acceptance_last_score,
                "best_score": self._wake_acceptance_best_score,
                "result": self._wake_acceptance_result,
            },
            "input_signal": metrics(self._last_input_metrics),
            "resampled_signal": metrics(self._last_resampled_metrics),
            **vad,
        }

    async def start(
        self,
        context: VoiceSessionContext,
        identity: Identity,
        device: DeviceIdentity,
    ) -> None:
        if self._state is not VoiceRunnerState.CREATED:
            raise RuntimeError("local voice runner can only start once")
        if identity.owner_id != device.owner_id:
            raise ValueError("voice identity/device owner binding mismatch")
        self._state = VoiceRunnerState.STARTING
        self._identity = identity
        self._device = device
        await self.voice.start(context, wake_enabled=True)
        try:
            self.audio_output.start()
            self.audio_input.start(self._capture_callback)
        except Exception as exc:
            self._state = VoiceRunnerState.DEGRADED
            await self.voice.report_runtime_event(
                "voice.runner_degraded",
                state=EventState.FAILED,
                payload={"reason": _safe_reason(exc)},
            )
            raise
        self._state = VoiceRunnerState.RUNNING
        await self.voice.report_runtime_event("voice.runner_started", state=EventState.ACCEPTED)
        self._consumer_task = asyncio.create_task(self._consume())

    async def stop(self) -> None:
        if self._state in {VoiceRunnerState.STOPPED, VoiceRunnerState.STOPPING}:
            return
        await self.stop_wake_acceptance()
        self._state = VoiceRunnerState.STOPPING
        await self._cancel_wake_command_timer()
        if self._consumer_task is not None:
            self._consumer_task.cancel()
            await asyncio.gather(self._consumer_task, return_exceptions=True)
        if self._turn_task is not None and not self._turn_task.done():
            await self.voice.barge_in()
            self._turn_task.cancel()
            await asyncio.gather(self._turn_task, return_exceptions=True)
        self.endpointing.discard()
        self._drain_queue()
        self.audio_input.stop()
        await self.audio_output.stop()
        self.audio_output.close()
        await self.voice.stop()
        self._state = VoiceRunnerState.STOPPED

    async def pause(self) -> None:
        """Disarm capture while keeping the existing runner reusable."""

        if self._state is VoiceRunnerState.PAUSED:
            return
        if self._state is not VoiceRunnerState.RUNNING:
            raise RuntimeError("local voice runner is not running")
        await self.stop_wake_acceptance()
        await self._cancel_wake_command_timer()
        self.endpointing.discard()
        self.audio_input.stop()
        await self.voice.barge_in()
        await self.voice.return_to_sleeping()
        await self.voice.report_runtime_event("voice.paused", state=EventState.ACCEPTED)
        self._state = VoiceRunnerState.PAUSED

    async def resume(self) -> None:
        """Re-arm the same configured microphone and wake boundary."""

        if self._state is VoiceRunnerState.RUNNING:
            return
        if self._state is not VoiceRunnerState.PAUSED:
            raise RuntimeError("local voice runner is not paused")
        self.audio_input.start(self._capture_callback)
        self._state = VoiceRunnerState.RUNNING
        await self.voice.report_runtime_event("voice.resumed", state=EventState.ACCEPTED)
        if self._consumer_task is None or self._consumer_task.done():
            self._consumer_task = asyncio.create_task(self._consume())

    async def rebind_audio(self, audio_input: AudioInput, audio_output: AudioOutput) -> None:
        """Replace only physical audio handles while preserving VoiceCore state."""

        if self._state not in {VoiceRunnerState.RUNNING, VoiceRunnerState.PAUSED}:
            raise RuntimeError("local voice audio can only be rebound while running or paused")
        prior_state = self._state
        await self._cancel_wake_command_timer()
        self.endpointing.discard()
        self.audio_input.stop()
        await self.audio_output.stop()
        self.audio_output.close()
        self.audio_input = audio_input
        self.audio_output = audio_output
        self.voice.playback = audio_output
        if prior_state is VoiceRunnerState.PAUSED:
            return
        try:
            self.audio_output.start()
            self.audio_input.start(self._capture_callback)
        except Exception as exc:
            self._state = VoiceRunnerState.DEGRADED
            try:
                self.audio_input.stop()
            except Exception:
                pass
            try:
                await self.audio_output.stop()
                self.audio_output.close()
            except Exception:
                pass
            await self.voice.report_runtime_event(
                "voice.audio_rebind_failed",
                state=EventState.FAILED,
                payload={"reason": _safe_reason(exc)},
            )
            raise
        self._state = VoiceRunnerState.RUNNING
        await self.voice.report_runtime_event("voice.audio_rebound", state=EventState.COMPLETED)
        if self._consumer_task is None or self._consumer_task.done():
            self._consumer_task = asyncio.create_task(self._consume())

    async def recover_device(self, attempts: int = 3) -> bool:
        """Re-open only the configured selector after an input endpoint loss."""

        if self._state is VoiceRunnerState.STOPPED:
            return False
        self._state = VoiceRunnerState.DEGRADED
        await self._cancel_wake_command_timer()
        self.endpointing.discard()
        self.audio_input.stop()
        await self.voice.barge_in()
        await self.voice.return_to_sleeping()
        await self.voice.report_runtime_event(
            "voice.device_lost",
            state=EventState.FAILED,
            payload={"reason": "configured_input_unavailable"},
        )
        for _ in range(max(1, min(attempts, 3))):
            await asyncio.sleep(0.25)
            try:
                self.audio_input.start(self._capture_callback)
            except VoiceDeviceError:
                continue
            except Exception:
                continue
            self._state = VoiceRunnerState.RUNNING
            await self.voice.report_runtime_event("voice.device_recovered", state=EventState.COMPLETED)
            return True
        await self.voice.report_runtime_event(
            "voice.device_recovery_failed",
            state=EventState.FAILED,
            payload={"reason": "configured_input_unavailable"},
        )
        return False

    def _capture_callback(self, audio: bytes) -> None:
        """Audio-thread work: copy into a bounded queue and return immediately."""

        copied = bytes(audio)
        self._input_bytes_received += len(copied)
        self._input_frames_received += len(copied) // 2
        self._last_input_frame_monotonic = time.monotonic()
        try:
            self._pcm.put_nowait(copied)
        except queue.Full:
            self._queue_overruns += 1
            self._total_queue_overruns += 1

    async def _consume(self) -> None:
        while self._state is VoiceRunnerState.RUNNING:
            if self.audio_input.take_fault():
                await self.recover_device()
                continue
            if self.audio_output.take_fault():
                await self.recover_output()
                continue
            if self._queue_overruns:
                overruns, self._queue_overruns = self._queue_overruns, 0
                await self.voice.report_runtime_event(
                    "voice.queue_overrun",
                    state=EventState.FAILED,
                    payload={"dropped_frames": overruns},
                )
            try:
                captured = self._pcm.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.01)
                continue
            try:
                self._last_input_metrics = pcm16_metrics(captured)
                pcm = resample_pcm_16le(captured, self.audio_input.sample_rate, 16_000)
                self._last_resampled_metrics = pcm16_metrics(pcm)
                await self._process_pcm(pcm)
            finally:
                del captured

    async def _process_pcm(self, pcm: bytes) -> None:
        if self.wake_acceptance_active:
            try:
                detected = self._detect_wake(pcm)
            except Exception:
                await self.stop_wake_acceptance()
                raise
            self._record_wake_acceptance_frame(detected)
            return
        state_before = self.voice.state
        if state_before in {VoiceSessionState.SLEEPING, VoiceSessionState.THINKING, VoiceSessionState.SPEAKING}:
            if self._detect_wake(pcm):
                self._wake_detections += 1
                self.endpointing.discard()
                await self._cancel_wake_command_timer()
                if await self.voice.wake_detected():
                    await self._arm_wake_command_timer()
            return
        if state_before not in {VoiceSessionState.LISTENING, VoiceSessionState.FOLLOW_UP}:
            return
        if state_before is VoiceSessionState.LISTENING and self.wake_command_timer_active and self._detect_wake(pcm):
            self._wake_detections += 1
            self.endpointing.discard()
            await self._arm_wake_command_timer()
            return
        speech_was_active = self.endpointing.speech_active
        utterance = self.endpointing.feed(pcm)
        speech_is_active = self.endpointing.speech_active
        if not speech_was_active and speech_is_active:
            if state_before is VoiceSessionState.LISTENING:
                await self._cancel_wake_command_timer()
            else:
                await self.voice.hold_follow_up_for_speech()
        if speech_was_active and not speech_is_active and utterance is None:
            if state_before is VoiceSessionState.LISTENING:
                await self._cancel_wake_command_timer()
                await self.voice.return_to_sleeping()
                await self.voice.report_runtime_event(
                    "voice.utterance_rejected",
                    state=EventState.COMPLETED,
                )
            else:
                await self.voice.restore_follow_up_after_rejected_speech()
            return
        if utterance is None or self._turn_task is not None and not self._turn_task.done():
            return
        self._turn_task = asyncio.create_task(self._dispatch(utterance))

    def _detect_wake(self, pcm: bytes) -> bool:
        self._wake_frames_received += 1
        detected = self.wake.detect_pcm(pcm)
        score = getattr(self.wake, "last_score", None)
        if isinstance(score, (int, float)):
            self._last_wake_score = float(score)
        return detected

    async def start_wake_acceptance(self, attempts: int = 10) -> WakeAcceptanceSnapshot:
        """Start a bounded wake-only benchmark on the existing runner."""

        if self._state is not VoiceRunnerState.RUNNING:
            raise RuntimeError("wake acceptance requires a running voice runner")
        if not 1 <= attempts <= 20:
            raise ValueError("wake acceptance attempts are outside bounds")
        if self._wake_acceptance_active:
            raise RuntimeError("wake acceptance is already active")
        await self._cancel_wake_command_timer()
        self.endpointing.discard()
        await self.voice.return_to_sleeping()
        self._wake_acceptance_active = True
        self._wake_acceptance_attempt_target = attempts
        self._wake_acceptance_attempt_index = 1
        self._wake_acceptance_detections = 0
        self._wake_acceptance_misses = 0
        self._wake_acceptance_last_score = None
        self._wake_acceptance_best_score = None
        self._wake_acceptance_attempt_deadline = time.monotonic() + self._wake_acceptance_attempt_seconds
        self._wake_acceptance_started_at = time.monotonic()
        self._wake_acceptance_result = None
        self._wake_acceptance_attempt_open = True
        self._wake_acceptance_signal = asyncio.Event()
        self._wake_acceptance_task = asyncio.create_task(self._run_wake_acceptance())
        return self.wake_acceptance_snapshot

    async def stop_wake_acceptance(self) -> WakeAcceptanceSnapshot:
        """Cancel an active benchmark and restore the normal sleeping boundary."""

        if not self._wake_acceptance_active:
            return self.wake_acceptance_snapshot
        self._wake_acceptance_active = False
        self._wake_acceptance_attempt_open = False
        self._wake_acceptance_result = self._wake_acceptance_result or "CANCELLED"
        if self._wake_acceptance_signal is not None:
            self._wake_acceptance_signal.set()
        task = self._wake_acceptance_task
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await self._restore_normal_wake()
        return self.wake_acceptance_snapshot

    def _record_wake_acceptance_frame(self, detected: bool) -> None:
        score = self._last_wake_score
        if isinstance(score, (int, float)):
            self._wake_acceptance_last_score = float(score)
            if self._wake_acceptance_best_score is None:
                self._wake_acceptance_best_score = float(score)
            else:
                self._wake_acceptance_best_score = max(self._wake_acceptance_best_score, float(score))
        if not detected or not self._wake_acceptance_attempt_open:
            return
        deadline = self._wake_acceptance_attempt_deadline
        if deadline is not None and time.monotonic() > deadline:
            return
        self._wake_acceptance_attempt_open = False
        self._wake_acceptance_detections += 1
        if self._wake_acceptance_signal is not None:
            self._wake_acceptance_signal.set()

    async def _run_wake_acceptance(self) -> None:
        current = asyncio.current_task()
        try:
            while self._wake_acceptance_active:
                signal = self._wake_acceptance_signal
                deadline = self._wake_acceptance_attempt_deadline
                if signal is None or deadline is None:
                    raise RuntimeError("wake acceptance session is not initialized")
                try:
                    await asyncio.wait_for(signal.wait(), max(0.0, deadline - time.monotonic()))
                except asyncio.TimeoutError:
                    if self._wake_acceptance_active and self._wake_acceptance_attempt_open:
                        self._wake_acceptance_attempt_open = False
                        self._wake_acceptance_misses += 1
                signal.clear()
                if not self._wake_acceptance_active:
                    break
                if self._wake_acceptance_attempt_open:
                    continue
                if self._wake_acceptance_attempt_index >= self._wake_acceptance_attempt_target:
                    self._wake_acceptance_result = self._wake_acceptance_result_for(
                        self._wake_acceptance_detections,
                        self._wake_acceptance_attempt_target,
                    )
                    self._wake_acceptance_active = False
                    break
                await asyncio.sleep(self._wake_acceptance_cooldown_seconds)
                if not self._wake_acceptance_active:
                    break
                self._wake_acceptance_attempt_index += 1
                self._wake_acceptance_attempt_open = True
                self._wake_acceptance_attempt_deadline = time.monotonic() + self._wake_acceptance_attempt_seconds
        except asyncio.CancelledError:
            raise
        except Exception:
            self._wake_acceptance_result = "FAIL"
            self._wake_acceptance_active = False
        finally:
            if self._wake_acceptance_task is current:
                self._wake_acceptance_task = None
            self._wake_acceptance_active = False
            self._wake_acceptance_attempt_open = False
            self._wake_acceptance_attempt_deadline = None
            await self._restore_normal_wake()

    @staticmethod
    def _wake_acceptance_result_for(detections: int, attempts: int) -> str:
        pass_threshold = max(1, math.ceil(attempts * 0.8))
        partial_threshold = max(1, math.ceil(attempts * 0.5))
        if detections >= pass_threshold:
            return "PASS"
        if detections >= partial_threshold:
            return "PARTIAL"
        return "FAIL"

    async def _restore_normal_wake(self) -> None:
        self.endpointing.discard()
        await self._cancel_wake_command_timer()
        if self.voice.state not in {VoiceSessionState.SLEEPING, VoiceSessionState.STOPPED}:
            await self.voice.return_to_sleeping()

    async def _dispatch(self, utterance: bytes) -> None:
        try:
            if self._identity is None or self._device is None:
                return
            await self.voice.process_audio(utterance, self._identity, self._device)
        except Exception as exc:
            await self.voice.report_runtime_event(
                "voice.turn_failed",
                state=EventState.FAILED,
                payload={"reason": _safe_reason(exc)},
            )
            await self.voice.return_to_sleeping()
        finally:
            # ``utterance`` must not outlive this in-memory dispatch.
            del utterance

    async def recover_output(self, attempts: int = 3) -> bool:
        """Re-open only the configured output selector after a playback fault."""

        if self._state is VoiceRunnerState.STOPPED:
            return False
        self._state = VoiceRunnerState.DEGRADED
        await self._cancel_wake_command_timer()
        await self.audio_output.stop()
        self.audio_output.close()
        await self.voice.barge_in()
        await self.voice.return_to_sleeping()
        await self.voice.report_runtime_event(
            "voice.output_lost",
            state=EventState.FAILED,
            payload={"reason": "configured_output_unavailable"},
        )
        for _ in range(max(1, min(attempts, 3))):
            await asyncio.sleep(0.25)
            try:
                self.audio_output.start()
            except VoiceDeviceError:
                continue
            except Exception:
                continue
            self._state = VoiceRunnerState.RUNNING
            await self.voice.report_runtime_event("voice.output_recovered", state=EventState.COMPLETED)
            return True
        await self.voice.report_runtime_event(
            "voice.output_recovery_failed",
            state=EventState.FAILED,
            payload={"reason": "configured_output_unavailable"},
        )
        return False

    async def _arm_wake_command_timer(self) -> None:
        await self._cancel_wake_command_timer()
        self._wake_command_task = asyncio.create_task(self._expire_wake_command())

    async def _cancel_wake_command_timer(self) -> None:
        task = self._wake_command_task
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._wake_command_task = None

    async def _expire_wake_command(self) -> None:
        current = asyncio.current_task()
        try:
            await asyncio.sleep(self.wake_command_timeout_seconds)
            if (
                self._state is VoiceRunnerState.RUNNING
                and self.voice.state is VoiceSessionState.LISTENING
                and not self.endpointing.speech_active
            ):
                self.endpointing.discard()
                await self.voice.return_to_sleeping()
                await self.voice.report_runtime_event("voice.wake_timeout", state=EventState.COMPLETED)
        except asyncio.CancelledError:
            return
        finally:
            if self._wake_command_task is current:
                self._wake_command_task = None

    def _drain_queue(self) -> None:
        while True:
            try:
                self._pcm.get_nowait()
            except queue.Empty:
                return


def build_local_voice_runtime(voice: VoiceCore, config: VoiceRuntimeConfig) -> LocalVoiceRuntime:
    """Bind the existing VoiceCore to explicit local adapters before startup."""

    config.validated()
    if not config.enabled:
        raise ValueError("JARVIS_VOICE_ENABLED must be true for the local voice runner")
    assert config.input_device and config.output_device
    assert config.wake_model_path and config.vad_model_path and config.stt_model_path
    assert config.tts_en_model_path and config.tts_ar_model_path
    playback = SoundDevicePlayback(config.output_device)
    voice.configure_adapters(
        FasterWhisperSpeechToText(
            config.stt_model_path,
            device=config.stt_device,
            compute_type=config.stt_compute_type,
        ),
        PiperTextToSpeech(config.tts_en_model_path, config.tts_ar_model_path),
        playback,
    )
    voice.follow_up_seconds = config.follow_up_seconds
    vad = SileroVad(config.vad_model_path, config.vad_threshold)
    return LocalVoiceRuntime(
        voice,
        SoundDeviceInput(config.input_device),
        playback,
        OpenWakeWordDetector(config.wake_model_path, config.wake_threshold),
        SpeechEndpointDetector(vad, end_silence_ms=config.vad_end_silence_ms),
        wake_command_timeout_seconds=config.wake_command_timeout_seconds,
    )


def _safe_reason(exc: Exception) -> str:
    if isinstance(exc, VoiceDeviceError):
        return str(exc)
    return exc.__class__.__name__
