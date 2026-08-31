"""Text-first voice session orchestration.

The core owns session state and cancellation. Audio capture, wake-word
recognition, speech recognition, and synthesis are injected adapters; no
device, model, or network is opened while importing this module.
"""

from __future__ import annotations

import asyncio

from ..agents.runtime.runtime import AgentRunState, AgentRuntime
from ..bus import InMemoryEventBus
from ..contracts import (
    DeviceIdentity,
    Identity,
    AudioPlayback,
    SpeechToText,
    TextToSpeech,
    VoiceSessionContext,
    VoiceSessionState,
    VoiceTranscript,
    VoiceTurnResult,
)
from ..events import Event, EventCategory, EventState


class VoiceCore:
    """Owns one logical realtime voice session at a time."""

    APPROVAL_REQUIRED_MESSAGE = "This action needs your approval in the authenticated interface."

    def __init__(
        self,
        agent: AgentRuntime,
        event_bus: InMemoryEventBus,
        stt: SpeechToText,
        tts: TextToSpeech,
        *,
        playback: AudioPlayback | None = None,
        follow_up_seconds: float = 30.0,
    ) -> None:
        self.agent = agent
        self.event_bus = event_bus
        self.stt = stt
        self.tts = tts
        self.playback = playback
        self._state = VoiceSessionState.IDLE
        self._context: VoiceSessionContext | None = None
        self._tts_task: asyncio.Task[bytes] | None = None
        self._agent_task: asyncio.Task | None = None
        self._playback_task: asyncio.Task[None] | None = None
        self._active_run_id: str | None = None
        self._wake_enabled = False
        self._turn_generation = 0
        self._barge_generation = -1
        self.follow_up_seconds = max(0.0, follow_up_seconds)
        self._follow_up_task: asyncio.Task[None] | None = None
        self._follow_up_deadline: float | None = None
        self._follow_up_run_id: str | None = None

    @property
    def state(self) -> VoiceSessionState:
        return self._state

    @property
    def context(self) -> VoiceSessionContext | None:
        return self._context

    async def start(
        self,
        context: VoiceSessionContext | None = None,
        *,
        wake_enabled: bool = False,
    ) -> None:
        await self._cancel_follow_up_timer()
        if context is not None:
            if not context.session_id or not context.device_id:
                raise ValueError("voice session requires session and device identifiers")
            self._context = context
        if self._context is None:
            # Preserve the Phase 01 lifecycle contract. A routable audio turn
            # still requires explicit context and will fail closed in
            # _check_context().
            self._state = VoiceSessionState.LISTENING
            return
        if self._state is VoiceSessionState.STOPPED:
            raise RuntimeError("voice session cannot restart after stop")
        self._wake_enabled = wake_enabled
        self._state = VoiceSessionState.SLEEPING if wake_enabled else VoiceSessionState.LISTENING
        await self._emit(
            "voice.sleeping" if wake_enabled else "voice.listening",
            EventState.ACCEPTED,
        )

    async def stop(self) -> None:
        await self._cancel_follow_up_timer()
        await self._cancel_active_turn()
        self._active_run_id = None
        if self._context is not None:
            await self._emit("voice.stopped", EventState.COMPLETED)
        self._state = VoiceSessionState.STOPPED

    def configure_adapters(
        self,
        stt: SpeechToText,
        tts: TextToSpeech,
        playback: AudioPlayback | None = None,
    ) -> None:
        """Bind optional physical adapters to this existing authority instance.

        The bootstrap keeps one ``VoiceCore`` for notifications and live voice;
        the explicit physical runner calls this only before a session starts.
        """

        if self._state is not VoiceSessionState.IDLE:
            raise RuntimeError("voice adapters can only be configured before start")
        self.stt = stt
        self.tts = tts
        self.playback = playback

    async def speak_safe_test(self, text: str = "JARVIS speaker test.") -> bool:
        """Play a bounded fixed test phrase without invoking AgentRuntime."""

        if self.playback is None or self._state in {VoiceSessionState.THINKING, VoiceSessionState.SPEAKING}:
            return False
        if not text or len(text) > 120:
            raise ValueError("speaker test text is outside bounds")
        self._state = VoiceSessionState.SPEAKING
        await self._emit("voice.speaker_test_started", EventState.ACCEPTED)
        audio: bytes | None = None
        try:
            self._tts_task = asyncio.create_task(self.tts.synthesize(text))
            try:
                audio = await self._tts_task
            finally:
                self._tts_task = None
            if audio:
                self._playback_task = asyncio.create_task(
                    self.playback.play(audio, int(getattr(self.tts, "sample_rate", 16_000)))
                )
                try:
                    await self._playback_task
                finally:
                    self._playback_task = None
            if self._state is VoiceSessionState.SPEAKING:
                self._state = VoiceSessionState.SLEEPING if self._wake_enabled else VoiceSessionState.LISTENING
                await self._emit(
                    "voice.speaker_test_completed",
                    EventState.COMPLETED,
                )
            return True
        except asyncio.CancelledError:
            return False
        finally:
            if audio is not None:
                del audio

    async def wake_detected(self) -> bool:
        """Transition a wake-enabled session to listening, interrupting safely."""

        if not self._wake_enabled:
            return False
        if self._state in {VoiceSessionState.THINKING, VoiceSessionState.SPEAKING}:
            interrupted = await self.barge_in()
            if interrupted:
                self._state = VoiceSessionState.WAKE_DETECTED
                await self._emit("voice.wake_detected", EventState.ACCEPTED)
                self._state = VoiceSessionState.LISTENING
                await self._emit("voice.listening", EventState.ACCEPTED)
                return True
        if self._state is not VoiceSessionState.SLEEPING:
            return False
        self._state = VoiceSessionState.WAKE_DETECTED
        await self._emit("voice.wake_detected", EventState.ACCEPTED)
        self._state = VoiceSessionState.LISTENING
        await self._emit("voice.listening", EventState.ACCEPTED)
        return True

    async def return_to_sleeping(self) -> None:
        """Discard an incomplete physical turn and re-arm its wake boundary."""

        if not self._wake_enabled or self._state is VoiceSessionState.STOPPED:
            return
        await self._cancel_follow_up_timer()
        self._state = VoiceSessionState.SLEEPING
        await self._emit("voice.sleeping", EventState.ACCEPTED)

    async def report_runtime_event(
        self,
        event_type: str,
        *,
        state: EventState = EventState.EMITTED,
        payload: dict[str, object] | None = None,
    ) -> None:
        """Publish a runner lifecycle observation through the same voice context."""

        await self._emit(event_type, state, payload)

    async def hold_follow_up_for_speech(self) -> bool:
        """Reserve an active follow-up while physical endpointing is in progress."""

        if self._state is not VoiceSessionState.FOLLOW_UP:
            return False
        task = self._follow_up_task
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if self._follow_up_task is task:
            self._follow_up_task = None
        return True

    async def restore_follow_up_after_rejected_speech(self) -> bool:
        """Resume only the original remaining follow-up window after rejected noise."""

        if self._state is not VoiceSessionState.FOLLOW_UP:
            return False
        await self._restore_follow_up()
        return self._state is VoiceSessionState.FOLLOW_UP

    async def process_audio(
        self,
        audio: bytes,
        identity: Identity,
        device: DeviceIdentity,
    ) -> VoiceTurnResult | None:
        self._check_context(device, identity)
        if self._state not in {VoiceSessionState.LISTENING, VoiceSessionState.FOLLOW_UP}:
            raise RuntimeError(f"voice session is not listening: {self._state.value}")
        if not audio:
            return None
        prior_state = self._state
        self._state = VoiceSessionState.TRANSCRIBING
        await self._emit("voice.audio_received")
        transcript = await self.stt.transcribe(audio)
        if not transcript.is_final or not transcript.text.strip():
            if prior_state is VoiceSessionState.FOLLOW_UP:
                await self._restore_follow_up()
            elif self._wake_enabled:
                await self.return_to_sleeping()
            else:
                self._state = VoiceSessionState.LISTENING
            return VoiceTurnResult(transcript, None, None, self._state)
        return await self.process_transcript(transcript, identity, device)

    async def process_transcript(
        self,
        transcript: VoiceTranscript,
        identity: Identity,
        device: DeviceIdentity,
    ) -> VoiceTurnResult:
        self._check_context(device, identity)
        if not transcript.text.strip():
            raise ValueError("voice transcript cannot be blank")
        await self._cancel_follow_up_timer()
        self._turn_generation += 1
        turn_generation = self._turn_generation
        self._active_run_id = None
        self._state = VoiceSessionState.THINKING
        await self._emit("voice.transcript_final", EventState.ACCEPTED, {"language": transcript.language})
        self._agent_task = asyncio.create_task(
            self.agent.process_text(
                transcript.text,
                identity,
                device,
                session_id=self._context.session_id if self._context else None,
                conversation_id=self._context.conversation_id if self._context else None,
            )
        )
        try:
            outcome = await self._agent_task
        except asyncio.CancelledError:
            return await self._interrupted_result(transcript, None, None)
        finally:
            self._agent_task = None
        if self._barge_generation == turn_generation:
            return VoiceTurnResult(transcript, None, None, self._state, interrupted=True)
        self._active_run_id = outcome.run_id
        if outcome.state is AgentRunState.PAUSED:
            await self._emit(
                "voice.approval_required",
                EventState.ACCEPTED,
                {"run_id": outcome.run_id, "approval_id": outcome.pending_approval_id},
            )
            audio, interrupted = await self._speak_product_message(
                self.APPROVAL_REQUIRED_MESSAGE,
                outcome.run_id,
                turn_generation,
            )
            if interrupted:
                return VoiceTurnResult(transcript, None, outcome.run_id, self._state, interrupted=True)
            if self._wake_enabled:
                await self.return_to_sleeping()
            else:
                self._state = VoiceSessionState.LISTENING
                await self._emit("voice.listening", EventState.ACCEPTED)
            return VoiceTurnResult(transcript, None, outcome.run_id, self._state, audio=audio)
        if outcome.state is not AgentRunState.SUCCEEDED or not outcome.response:
            await self._emit("voice.agent_unavailable", EventState.FAILED, {"run_id": outcome.run_id, "state": outcome.state.value})
            if self._wake_enabled and outcome.state is not AgentRunState.CANCELLED:
                await self.return_to_sleeping()
            else:
                self._state = VoiceSessionState.LISTENING if outcome.state is not AgentRunState.CANCELLED else VoiceSessionState.INTERRUPTED
            return VoiceTurnResult(transcript, outcome.response, outcome.run_id, self._state)
        self._state = VoiceSessionState.SPEAKING
        await self._emit("voice.speaking", EventState.ACCEPTED, {"run_id": outcome.run_id})
        self._tts_task = asyncio.create_task(self.tts.synthesize(self._spoken_text(outcome.response)))
        try:
            audio = await self._tts_task
        except asyncio.CancelledError:
            return await self._interrupted_result(transcript, outcome.response, outcome.run_id)
        finally:
            self._tts_task = None
        if self._barge_generation == turn_generation:
            return VoiceTurnResult(transcript, outcome.response, outcome.run_id, self._state, interrupted=True)
        if self.playback is not None and audio:
            self._playback_task = asyncio.create_task(
                self.playback.play(audio, int(getattr(self.tts, "sample_rate", 16_000)))
            )
            try:
                await self._playback_task
            except asyncio.CancelledError:
                return await self._interrupted_result(transcript, outcome.response, outcome.run_id)
            finally:
                self._playback_task = None
            if self._barge_generation == turn_generation:
                return VoiceTurnResult(transcript, outcome.response, outcome.run_id, self._state, interrupted=True)
        self._state = VoiceSessionState.FOLLOW_UP
        await self._emit("voice.turn_completed", EventState.COMPLETED, {"run_id": outcome.run_id})
        if self.follow_up_seconds:
            self._arm_follow_up(self.follow_up_seconds, outcome.run_id)
        return VoiceTurnResult(transcript, outcome.response, outcome.run_id, self._state, audio=audio)

    async def barge_in(self) -> bool:
        tasks = tuple(
            task
            for task in (self._agent_task, self._tts_task, self._playback_task)
            if task is not None and not task.done()
        )
        if not tasks:
            return False
        self._barge_generation = self._turn_generation
        for task in tasks:
            task.cancel()
        if self.playback is not None:
            await self.playback.stop()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._agent_task = None
        self._tts_task = None
        self._playback_task = None
        self._state = VoiceSessionState.INTERRUPTED
        await self._emit("voice.barge_in", EventState.ACCEPTED, {"run_id": self._active_run_id})
        self._state = VoiceSessionState.LISTENING
        await self._emit("voice.listening", EventState.ACCEPTED)
        return True

    async def _expire_follow_up(self, seconds: float, run_id: str) -> None:
        current = asyncio.current_task()
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            return
        finally:
            if self._follow_up_task is current:
                self._follow_up_task = None
        if self._state is not VoiceSessionState.FOLLOW_UP:
            return
        self._follow_up_deadline = None
        self._follow_up_run_id = None
        self._state = VoiceSessionState.SLEEPING if self._wake_enabled else VoiceSessionState.LISTENING
        await self._emit("voice.follow_up_expired", EventState.COMPLETED, {"run_id": run_id})

    def _arm_follow_up(self, seconds: float, run_id: str) -> None:
        loop = asyncio.get_running_loop()
        self._follow_up_deadline = loop.time() + seconds
        self._follow_up_run_id = run_id
        self._follow_up_task = asyncio.create_task(self._expire_follow_up(seconds, run_id))

    async def _cancel_follow_up_timer(self) -> None:
        task = self._follow_up_task
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._follow_up_task = None
        self._follow_up_deadline = None
        self._follow_up_run_id = None

    async def _restore_follow_up(self) -> None:
        self._state = VoiceSessionState.FOLLOW_UP
        task = self._follow_up_task
        if task is not None and not task.done():
            return
        loop = asyncio.get_running_loop()
        deadline = self._follow_up_deadline
        run_id = self._follow_up_run_id or self._active_run_id or "unknown"
        remaining = (deadline - loop.time()) if deadline is not None else self.follow_up_seconds
        if remaining <= 0:
            self._follow_up_deadline = None
            self._follow_up_run_id = None
            self._state = VoiceSessionState.SLEEPING if self._wake_enabled else VoiceSessionState.LISTENING
            await self._emit("voice.follow_up_expired", EventState.COMPLETED, {"run_id": run_id})
            return
        self._follow_up_task = asyncio.create_task(self._expire_follow_up(remaining, run_id))

    async def _speak_product_message(
        self,
        message: str,
        run_id: str,
        turn_generation: int,
    ) -> tuple[bytes | None, bool]:
        self._state = VoiceSessionState.SPEAKING
        await self._emit("voice.speaking", EventState.ACCEPTED, {"run_id": run_id})
        self._tts_task = asyncio.create_task(self.tts.synthesize(message))
        try:
            audio = await self._tts_task
        except asyncio.CancelledError:
            await self._interrupted_result(VoiceTranscript("", True), None, run_id)
            return None, True
        finally:
            self._tts_task = None
        if self._barge_generation == turn_generation:
            return None, True
        if self.playback is not None and audio:
            self._playback_task = asyncio.create_task(
                self.playback.play(audio, int(getattr(self.tts, "sample_rate", 16_000)))
            )
            try:
                await self._playback_task
            except asyncio.CancelledError:
                await self._interrupted_result(VoiceTranscript("", True), None, run_id)
                return None, True
            finally:
                self._playback_task = None
        return audio, self._barge_generation == turn_generation

    async def _cancel_active_turn(self) -> None:
        tasks = tuple(
            task
            for task in (self._agent_task, self._tts_task, self._playback_task)
            if task is not None and not task.done()
        )
        for task in tasks:
            task.cancel()
        if self.playback is not None:
            await self.playback.stop()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._agent_task = None
        self._tts_task = None
        self._playback_task = None

    async def _interrupted_result(
        self,
        transcript: VoiceTranscript,
        response: str | None,
        run_id: str | None,
    ) -> VoiceTurnResult:
        if self._barge_generation != self._turn_generation:
            self._state = VoiceSessionState.INTERRUPTED
            await self._emit("voice.cancelled", EventState.COMPLETED, {"run_id": run_id})
        return VoiceTurnResult(transcript, response, run_id, self._state, interrupted=True)

    @staticmethod
    def _spoken_text(response: str) -> str:
        """Keep only the spoken presentation bounded; typed output is unchanged."""

        return response[:1200]

    def _check_context(self, device: DeviceIdentity, identity: Identity | None = None) -> None:
        if self._context is None:
            raise RuntimeError("voice session has not started")
        if self._context.device_id != device.device_id:
            raise ValueError("voice device does not match session context")
        if self._context.owner_id is not None and self._context.owner_id != device.owner_id:
            raise ValueError("voice owner does not match session context")
        if identity is not None and identity.owner_id != device.owner_id:
            raise ValueError("voice identity/device owner binding mismatch")

    async def _emit(
        self,
        event_type: str,
        state: EventState = EventState.EMITTED,
        payload: dict[str, object] | None = None,
    ) -> None:
        if self._context is None:
            return
        event = Event.create(
            event_type,
            EventCategory.VOICE,
            correlation_id=self._context.session_id,
            session_id=self._context.session_id,
            actor_id=self._context.device_id,
            payload=payload or {},
            state=state,
        )
        self.agent.repository.append_event(event)
        await self.event_bus.publish(event)
