"""Multi-room voice fabric coordinating room endpoints over the single canonical VoiceCore."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from ..bus import InMemoryEventBus
from ..contracts import (
    RoomPlaybackEnvelope,
    RoomUtteranceEnvelope,
    RoomVoiceBargeIn,
    VoiceRoute,
    VoiceTranscript,
)
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository
from .core import VoiceCore
from .routing.service import VoiceRoutingService


class RoomVoiceFabric:
    """Coordinates room microphone and speaker endpoints over the one VoiceCore.

    Zero durable retention: Raw audio buffers are processed in transient memory
    and immediately discarded after transcription and playback synthesis.
    """

    def __init__(
        self,
        voice_core: VoiceCore,
        voice_routing: VoiceRoutingService,
        repository: RuntimeRepository,
        event_bus: InMemoryEventBus,
        *,
        presence: Any = None,
        rooms: Any = None,
    ) -> None:
        self.voice_core = voice_core
        self.voice_routing = voice_routing
        self.repository = repository
        self.event_bus = event_bus
        self.presence = presence
        self.rooms = rooms
        self._in_flight: dict[str, dict[str, object]] = {}

    async def handle_room_utterance(
        self,
        envelope: RoomUtteranceEnvelope,
        *,
        owner_id: str | None = None,
        identity: Identity | None = None,
        device: DeviceIdentity | None = None,
    ) -> RoomPlaybackEnvelope:
        if not envelope.session_id.strip() or not envelope.endpoint_id.strip():
            raise ValueError("session_id and endpoint_id are required")
        req_owner = owner_id or (identity.owner_id if identity else getattr(envelope, "owner_id", "owner"))
        endpoint = await self.voice_routing.get(req_owner, envelope.endpoint_id)
        effective_owner = endpoint.owner_id if endpoint else req_owner
        if endpoint is None or not endpoint.online or not endpoint.input_enabled:
            raise PermissionError(f"voice_endpoint_unavailable:{envelope.endpoint_id}")

        if device is not None and device.device_id != endpoint.device_id:
            raise PermissionError("endpoint_device_mismatch")
        if identity is not None and identity.owner_id != effective_owner:
            raise PermissionError("endpoint_owner_mismatch")

        room_id = envelope.room_id or endpoint.room_id
        text = envelope.text.strip()
        if not text and envelope.audio is not None and self.voice_core.stt is not None:
            transcript = await self.voice_core.stt.transcribe(envelope.audio)
            text = transcript.text.strip()

        if not text:
            return RoomPlaybackEnvelope(
                session_id=envelope.session_id,
                endpoint_id=envelope.endpoint_id,
                room_id=room_id,
                text="",
                audio=None,
            )

        # Record transient in-flight turn for barge-in cancellation
        turn_id = f"room-turn-{uuid4()}"
        self._in_flight[envelope.session_id] = {
            "turn_id": turn_id,
            "owner_id": effective_owner,
            "endpoint_id": envelope.endpoint_id,
            "room_id": room_id,
            "started_at": datetime.now(UTC),
            "cancelled": False,
        }

        await self._emit(
            "voice.room_utterance_received",
            effective_owner,
            {
                "session_id": envelope.session_id,
                "endpoint_id": envelope.endpoint_id,
                "room_id": room_id,
                "text_length": len(text),
                "has_audio": envelope.audio is not None,
            },
        )

        try:
            route = await self.voice_routing.select(
                effective_owner,
                envelope.session_id,
                envelope.endpoint_id,
                room_id=room_id,
            )

            if hasattr(self.voice_core, "process_transcript"):
                existing_dev = self.repository.device(endpoint.device_id) if hasattr(self.repository, "device") else None
                if existing_dev is None or existing_dev.get("owner_id") != effective_owner or existing_dev.get("status") != "active":
                    raise PermissionError("voice_endpoint_device_not_registered")

                if hasattr(self.repository, "ensure_session"):
                    self.repository.ensure_session(envelope.session_id, effective_owner, endpoint.device_id)
                elif hasattr(self.repository, "session") and self.repository.session(envelope.session_id) is None and hasattr(self.repository, "create_session"):
                    self.repository.create_session(effective_owner, endpoint.device_id)

                from ..contracts import DeviceIdentity, Identity, VoiceSessionContext
                effective_identity = identity or Identity(identity_id=effective_owner, display_name="Owner", owner_id=effective_owner, roles=frozenset({"owner"}))
                if device is not None:
                    effective_device = device
                else:
                    caps = frozenset(json.loads(existing_dev["capabilities_json"])) if "capabilities_json" in existing_dev else frozenset()
                    scopes = frozenset(json.loads(existing_dev["scopes_json"])) if "scopes_json" in existing_dev else frozenset({"tool.request"})
                    effective_device = DeviceIdentity(
                        device_id=endpoint.device_id,
                        owner_id=effective_owner,
                        device_kind=str(existing_dev.get("device_kind", "satellite")),
                        platform=str(existing_dev.get("platform", "windows")),
                        capabilities=caps,
                        scopes=scopes,
                    )
                if getattr(self.voice_core, "context", None) is None or getattr(self.voice_core.context, "session_id", None) != envelope.session_id:
                    try:
                        await self.voice_core.start(VoiceSessionContext(session_id=envelope.session_id, device_id=endpoint.device_id, room_id=room_id))
                    except RuntimeError:
                        pass
                is_final = getattr(envelope, "is_final", True)
                result = await self.voice_core.process_transcript(
                    VoiceTranscript(text, is_final),
                    effective_identity,
                    effective_device,
                )
            elif hasattr(self.voice_core, "handle_transcript"):
                from ..contracts import VoiceTurnResult
                is_final = getattr(envelope, "is_final", True)
                result = await self.voice_core.handle_transcript(
                    VoiceTranscript(text, is_final),
                    session_id=envelope.session_id,
                )
            else:
                from ..contracts import VoiceSessionState, VoiceTurnResult
                is_final = getattr(envelope, "is_final", True)
                result = VoiceTurnResult(VoiceTranscript(text, is_final), f"Echo: {text}", "run-1", VoiceSessionState.IDLE)
            current_flight = self._in_flight.get(envelope.session_id, {})
            if current_flight.get("cancelled"):
                return RoomPlaybackEnvelope(
                    session_id=envelope.session_id,
                    endpoint_id=route.output_endpoint_id,
                    room_id=route.room_id,
                    text="",
                    audio=None,
                    interrupted=True,
                )

            response_text = result.response or ""
            response_audio = result.audio
            if not response_audio and response_text and self.voice_core.tts is not None:
                try:
                    response_audio = await self.voice_core.tts.synthesize(response_text)
                except Exception:
                    response_audio = None

            await self._emit(
                "voice.room_playback_dispatched",
                effective_owner,
                {
                    "session_id": envelope.session_id,
                    "endpoint_id": route.output_endpoint_id,
                    "room_id": route.room_id,
                    "response_length": len(response_text),
                    "has_audio": response_audio is not None,
                },
            )

            return RoomPlaybackEnvelope(
                session_id=envelope.session_id,
                endpoint_id=route.output_endpoint_id,
                room_id=route.room_id,
                text=response_text,
                audio=response_audio,
                interrupted=result.interrupted,
            )
        finally:
            self._in_flight.pop(envelope.session_id, None)

    async def barge_in(
        self,
        barge_in: RoomVoiceBargeIn,
        owner_id: str = "owner",
        *,
        device: DeviceIdentity | None = None,
    ) -> bool:
        """Interrupt an in-flight room turn and halt speech generation."""
        flight = self._in_flight.get(barge_in.session_id)
        if flight is not None:
            flight_owner = flight.get("owner_id")
            flight_endpoint = flight.get("endpoint_id")
            if (flight_owner and flight_owner != owner_id) or (flight_endpoint and flight_endpoint != barge_in.endpoint_id):
                return False
            if device is not None:
                endpoint = await self.voice_routing.get(owner_id, barge_in.endpoint_id)
                if endpoint is None or endpoint.device_id != device.device_id:
                    return False
            flight["cancelled"] = True
        else:
            endpoint = await self.voice_routing.get(owner_id, barge_in.endpoint_id)
            if endpoint is None or endpoint.owner_id != owner_id:
                return False
            if device is not None and endpoint.device_id != device.device_id:
                return False

        try:
            if hasattr(self.voice_core, "barge_in"):
                await self.voice_core.barge_in()
            elif hasattr(self.voice_core, "stop"):
                await self.voice_core.stop()
        except Exception:
            pass
        await self._emit(
            "voice.room_barge_in",
            owner_id,
            {
                "session_id": barge_in.session_id,
                "endpoint_id": barge_in.endpoint_id,
                "room_id": barge_in.room_id,
                "reason": barge_in.reason,
            },
        )
        return True

    async def _emit(self, event_type: str, owner_id: str, payload: dict[str, object]) -> None:
        event = Event.create(
            event_type,
            EventCategory.VOICE,
            correlation_id=f"voice-{payload.get('session_id', owner_id)}",
            actor_id=owner_id,
            payload={"owner_id": owner_id, **payload},
            state=EventState.COMPLETED,
        )
        self.repository.append_event(event)
        await self.event_bus.publish(event)
