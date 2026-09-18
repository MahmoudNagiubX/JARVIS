"""Provider-neutral language-model contracts."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class LLMRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True, slots=True)
class LLMInputMedia:
    """Transient multimodal input; never persisted by the model contract."""

    mime_type: str
    data: bytes


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: LLMRole
    content: str
    media: tuple[LLMInputMedia, ...] = ()


@dataclass(frozen=True, slots=True)
class LLMRequest:
    request_id: str
    messages: tuple[LLMMessage, ...]
    model: str | None = None
    tools: tuple[Mapping[str, Any], ...] = ()
    max_output_tokens: int = 512
    timeout_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class LLMResponse:
    request_id: str
    text: str
    model: str | None
    finish_reason: str
    tool_calls: tuple[Mapping[str, Any], ...] = ()
    usage: Mapping[str, int] = field(default_factory=dict)
    provider: str | None = None
    model_digest: str | None = None


class LLMProvider(Protocol):
    name: str

    def generate(self, request: LLMRequest) -> Awaitable[LLMResponse]: ...


class LLMRouter(Protocol):
    def generate(self, request: LLMRequest) -> Awaitable[LLMResponse]: ...
