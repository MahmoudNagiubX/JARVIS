"""Realtime voice boundaries without binding the core to an audio framework."""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class VoiceSessionState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class VoiceTranscript:
    text: str
    is_final: bool
    language: str | None = None


class RealtimeVoiceSession(Protocol):
    @property
    def state(self) -> VoiceSessionState: ...

    def start(self) -> Awaitable[None]: ...

    def stop(self) -> Awaitable[None]: ...


class SpeechToText(Protocol):
    def transcribe(self, audio: bytes) -> Awaitable[VoiceTranscript]: ...


class TextToSpeech(Protocol):
    def synthesize(self, text: str) -> Awaitable[bytes]: ...
