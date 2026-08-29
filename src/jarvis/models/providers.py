"""Mock and loopback Ollama providers.

The Ollama adapter only sends requests to an already-running local endpoint. It
never pulls, installs, copies, or deletes a model.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from ..contracts import LLMRequest, LLMResponse


class ModelProviderError(RuntimeError):
    """Normalized provider failure."""


class ModelOfflineError(ModelProviderError):
    pass


class MockModelProvider:
    name = "mock"

    def __init__(self, handler: Callable[[LLMRequest], LLMResponse | Awaitable[LLMResponse]] | None = None) -> None:
        self._handler = handler
        self.requests: list[LLMRequest] = []

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if self._handler is not None:
            result = self._handler(request)
            if inspect.isawaitable(result):
                return await result
            return result
        last_user = next((message.content for message in reversed(request.messages) if message.role.value == "user"), "")
        return LLMResponse(
            request_id=request.request_id,
            text=f"Mock JARVIS response: {last_user}",
            model=request.model or "mock",
            finish_reason="stop",
            provider=self.name,
        )

    async def health(self, model: str) -> object:
        from .health import ModelHealth

        return ModelHealth(self.name, True, datetime.now(UTC), "mock_ready", model)


class UnavailableModelProvider:
    name = "unavailable"

    def __init__(self, reason: str) -> None:
        self.reason = reason

    async def generate(self, request: LLMRequest) -> LLMResponse:
        del request
        raise ModelProviderError(self.reason)


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def generate(self, request: LLMRequest) -> LLMResponse:
        return await asyncio.to_thread(self._generate_sync, request)

    def _generate_sync(self, request: LLMRequest) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
            "stream": False,
            "options": {"num_predict": request.max_output_tokens},
        }
        if request.tools:
            payload["tools"] = [dict(tool) for tool in request.tools]
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_obj = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request_obj, timeout=request.timeout_seconds or 60.0) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ModelOfflineError(f"ollama_unavailable:{exc.__class__.__name__}") from exc
        if not isinstance(decoded, dict) or not isinstance(decoded.get("message"), dict):
            raise ModelProviderError("ollama_invalid_response")
        message = decoded["message"]
        content = message.get("content", "")
        if not isinstance(content, str):
            raise ModelProviderError("ollama_invalid_content")
        tool_calls = tuple(call for call in message.get("tool_calls", ()) if isinstance(call, dict))
        usage = {
            "prompt_tokens": int(decoded.get("prompt_eval_count", 0) or 0),
            "output_tokens": int(decoded.get("eval_count", 0) or 0),
        }
        return LLMResponse(
            request_id=request.request_id,
            text=content,
            model=request.model,
            finish_reason=str(decoded.get("done_reason", "stop")),
            tool_calls=tool_calls,
            usage=usage,
            provider=self.name,
        )

    async def health(self, model: str) -> object:
        return await asyncio.to_thread(self._health_sync, model)

    def _health_sync(self, model: str) -> object:
        from .health import ModelHealth
        from datetime import UTC, datetime

        request_obj = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
        try:
            with urllib.request.urlopen(request_obj, timeout=2.0) as response:
                if response.status != 200:
                    return ModelHealth(self.name, False, datetime.now(UTC), "http_not_ready", model)
        except (urllib.error.URLError, TimeoutError, OSError):
            return ModelHealth(self.name, False, datetime.now(UTC), "provider_offline", model)
        return ModelHealth(self.name, True, datetime.now(UTC), "provider_ready", model)
