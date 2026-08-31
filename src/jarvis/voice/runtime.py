"""Lifecycle runner for one physical, local workstation voice endpoint."""

from __future__ import annotations

import asyncio
import queue
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
    VoiceDeviceError,
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

        try:
            self._pcm.put_nowait(bytes(audio))
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
                pcm = resample_pcm_16le(captured, self.audio_input.sample_rate, 16_000)
                await self._process_pcm(pcm)
            finally:
                del captured

    async def _process_pcm(self, pcm: bytes) -> None:
        state_before = self.voice.state
        if state_before in {VoiceSessionState.SLEEPING, VoiceSessionState.THINKING, VoiceSessionState.SPEAKING}:
            if self.wake.detect_pcm(pcm):
                self.endpointing.discard()
                await self._cancel_wake_command_timer()
                if await self.voice.wake_detected():
                    await self._arm_wake_command_timer()
            return
        if state_before not in {VoiceSessionState.LISTENING, VoiceSessionState.FOLLOW_UP}:
            return
        if state_before is VoiceSessionState.LISTENING and self.wake_command_timer_active and self.wake.detect_pcm(pcm):
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
