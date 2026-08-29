"""Realtime voice boundaries without binding the core to an audio framework."""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class VoiceSessionState(StrEnum):
    IDLE = "idle"
    SLEEPING = "sleeping"
    WAKE_DETECTED = "wake_detected"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    FOLLOW_UP = "follow_up"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class VoiceTranscript:
    text: str
    is_final: bool
    language: str | None = None


@dataclass(frozen=True, slots=True)
class VoiceSessionContext:
    """Routing metadata carried through a voice turn.

    Audio devices and rooms are intentionally identifiers only. Hardware and
    room discovery belong to adapters outside the core runtime.
    """

    session_id: str
    device_id: str
    input_device: str | None = None
    output_device: str | None = None
    room_id: str | None = None
    owner_id: str | None = None
    endpoint_id: str | None = None
    conversation_id: str | None = None


@dataclass(frozen=True, slots=True)
class VoiceEndpoint:
    endpoint_id: str
    device_id: str
    room_id: str | None = None
    input_enabled: bool = True
    output_enabled: bool = True
    online: bool = False
    last_seen: datetime | None = None
    owner_id: str | None = None


@dataclass(frozen=True, slots=True)
class VoiceRoute:
    session_id: str
    source_endpoint_id: str
    output_endpoint_id: str
    room_id: str | None = None
    handoff: bool = False
    conversation_id: str | None = None
    priority: int = 0
    active_speaker: str | None = None


@dataclass(frozen=True, slots=True)
class VoiceTurnResult:
    transcript: VoiceTranscript
    response: str | None
    run_id: str | None
    state: VoiceSessionState
    audio: bytes | None = None
    interrupted: bool = False


class VoiceActivityDetector(Protocol):
    def is_speech(self, audio: bytes) -> bool: ...


class WakeDetector(Protocol):
    def detect(self, transcript: VoiceTranscript) -> bool: ...


class RealtimeVoiceSession(Protocol):
    @property
    def state(self) -> VoiceSessionState: ...

    def start(self) -> Awaitable[None]: ...

    def stop(self) -> Awaitable[None]: ...


class SpeechToText(Protocol):
    def transcribe(self, audio: bytes) -> Awaitable[VoiceTranscript]: ...


class TextToSpeech(Protocol):
    def synthesize(self, text: str) -> Awaitable[bytes]: ...
