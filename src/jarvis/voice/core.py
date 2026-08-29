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

    def __init__(
        self,
        agent: AgentRuntime,
        event_bus: InMemoryEventBus,
        stt: SpeechToText,
        tts: TextToSpeech,
        *,
        follow_up_seconds: float = 30.0,
    ) -> None:
        self.agent = agent
        self.event_bus = event_bus
        self.stt = stt
        self.tts = tts
        self._state = VoiceSessionState.IDLE
        self._context: VoiceSessionContext | None = None
        self._tts_task: asyncio.Task[bytes] | None = None
        self._active_run_id: str | None = None
        self.follow_up_seconds = max(0.0, follow_up_seconds)
        self._follow_up_task: asyncio.Task[None] | None = None

    @property
    def state(self) -> VoiceSessionState:
        return self._state

    @property
    def context(self) -> VoiceSessionContext | None:
        return self._context

    async def start(self, context: VoiceSessionContext | None = None) -> None:
        if self._follow_up_task and not self._follow_up_task.done():
            self._follow_up_task.cancel()
            await asyncio.gather(self._follow_up_task, return_exceptions=True)
        self._follow_up_task = None
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
        self._state = VoiceSessionState.LISTENING
        await self._emit("voice.listening", EventState.ACCEPTED)

    async def stop(self) -> None:
        if self._follow_up_task and not self._follow_up_task.done():
            self._follow_up_task.cancel()
            await asyncio.gather(self._follow_up_task, return_exceptions=True)
        self._follow_up_task = None
        if self._tts_task and not self._tts_task.done():
            self._tts_task.cancel()
            await asyncio.gather(self._tts_task, return_exceptions=True)
        self._tts_task = None
        self._active_run_id = None
        if self._context is not None:
            await self._emit("voice.stopped", EventState.COMPLETED)
        self._state = VoiceSessionState.STOPPED

    async def process_audio(
        self,
        audio: bytes,
        identity: Identity,
        device: DeviceIdentity,
    ) -> VoiceTurnResult | None:
        self._check_context(device)
        if self._state not in {VoiceSessionState.LISTENING, VoiceSessionState.FOLLOW_UP}:
            raise RuntimeError(f"voice session is not listening: {self._state.value}")
        if not audio:
            return None
        self._state = VoiceSessionState.TRANSCRIBING
        await self._emit("voice.audio_received")
        transcript = await self.stt.transcribe(audio)
        if not transcript.is_final or not transcript.text.strip():
            self._state = VoiceSessionState.LISTENING
            return VoiceTurnResult(transcript, None, None, self._state)
        return await self.process_transcript(transcript, identity, device)

    async def process_transcript(
        self,
        transcript: VoiceTranscript,
        identity: Identity,
        device: DeviceIdentity,
    ) -> VoiceTurnResult:
        self._check_context(device)
        if not transcript.text.strip():
            raise ValueError("voice transcript cannot be blank")
        self._state = VoiceSessionState.THINKING
        await self._emit("voice.transcript_final", EventState.ACCEPTED, {"language": transcript.language})
        outcome = await self.agent.process_text(
            transcript.text,
            identity,
            device,
            session_id=self._context.session_id if self._context else None,
            conversation_id=self._context.conversation_id if self._context else None,
        )
        self._active_run_id = outcome.run_id
        if outcome.state is not AgentRunState.SUCCEEDED or not outcome.response:
            self._state = VoiceSessionState.LISTENING if outcome.state is not AgentRunState.CANCELLED else VoiceSessionState.INTERRUPTED
            await self._emit("voice.agent_unavailable", EventState.FAILED, {"run_id": outcome.run_id, "state": outcome.state.value})
            return VoiceTurnResult(transcript, outcome.response, outcome.run_id, self._state)
        self._state = VoiceSessionState.SPEAKING
        await self._emit("voice.speaking", EventState.ACCEPTED, {"run_id": outcome.run_id})
        self._tts_task = asyncio.create_task(self.tts.synthesize(outcome.response))
        try:
            audio = await self._tts_task
        except asyncio.CancelledError:
            self._state = VoiceSessionState.INTERRUPTED
            await self._emit("voice.cancelled", EventState.COMPLETED, {"run_id": outcome.run_id})
            return VoiceTurnResult(transcript, outcome.response, outcome.run_id, self._state, interrupted=True)
        finally:
            self._tts_task = None
        self._state = VoiceSessionState.FOLLOW_UP
        await self._emit("voice.turn_completed", EventState.COMPLETED, {"run_id": outcome.run_id})
        if self.follow_up_seconds:
            self._follow_up_task = asyncio.create_task(self._expire_follow_up(self.follow_up_seconds, outcome.run_id))
        return VoiceTurnResult(transcript, outcome.response, outcome.run_id, self._state, audio=audio)

    async def barge_in(self) -> bool:
        task = self._tts_task
        if task is None or task.done():
            return False
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        self._tts_task = None
        self._state = VoiceSessionState.INTERRUPTED
        await self._emit("voice.barge_in", EventState.ACCEPTED, {"run_id": self._active_run_id})
        self._state = VoiceSessionState.LISTENING
        await self._emit("voice.listening", EventState.ACCEPTED)
        return True

    async def _expire_follow_up(self, seconds: float, run_id: str) -> None:
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            return
        if self._state is VoiceSessionState.FOLLOW_UP:
            self._state = VoiceSessionState.LISTENING
            await self._emit("voice.follow_up_expired", EventState.COMPLETED, {"run_id": run_id})

    def _check_context(self, device: DeviceIdentity) -> None:
        if self._context is None:
            raise RuntimeError("voice session has not started")
        if self._context.device_id != device.device_id:
            raise ValueError("voice device does not match session context")
        if self._context.owner_id is not None and self._context.owner_id != device.owner_id:
            raise ValueError("voice owner does not match session context")

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
