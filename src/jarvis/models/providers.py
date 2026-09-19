"""Mock and loopback Ollama providers.

The Ollama adapter only sends requests to an already-running local endpoint. It
never pulls, installs, copies, or deletes a model.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from ..config import validate_loopback_http_origin
from ..contracts import LLMRequest, LLMResponse
from ..local_model_identity import REQUIRED_LOCAL_MODEL
from .health import ModelHealth


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

    async def health(self, model: str | None = None) -> ModelHealth:
        return ModelHealth(self.name, False, datetime.now(UTC), self.reason, model)


class LlamaCppProvider:
    """OpenAI-compatible llama-server adapter restricted to loopback HTTP."""

    name = "llama_cpp"
    MAX_RESPONSE_BYTES = 4 * 1024 * 1024
    MIN_TIMEOUT_SECONDS = 1.0
    MAX_TIMEOUT_SECONDS = 180.0
    MAX_WAITERS = 8
    MODEL_ALIAS_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@+\-]{0,99}\Z")

    def __init__(
        self,
        base_url: str,
        *,
        model_alias: str = REQUIRED_LOCAL_MODEL,
        urlopen: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        validate_loopback_http_origin(base_url)
        if not self.MODEL_ALIAS_PATTERN.fullmatch(model_alias):
            raise ValueError("llama_cpp_model_alias_invalid")
        self.base_url = base_url.rstrip("/")
        self.model_alias = model_alias
        self._urlopen = urlopen
        self.requests = 0
        self.failures = 0
        self.last_latency_ms: float | None = None
        self._generation_slot = asyncio.Semaphore(1)
        self._waiting_generations = 0

    @staticmethod
    def supports_route(route: object) -> bool:
        return getattr(route, "value", route) != "vision"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        started = time.perf_counter()
        self.requests += 1
        try:
            await self._acquire_generation_slot(self._timeout(request.timeout_seconds))
            try:
                response = await asyncio.to_thread(self._generate_sync, request)
            finally:
                self._generation_slot.release()
        except ModelProviderError:
            self.failures += 1
            raise
        finally:
            self.last_latency_ms = (time.perf_counter() - started) * 1000
        return response

    async def _acquire_generation_slot(self, timeout: float) -> None:
        if not self._generation_slot.locked():
            await self._generation_slot.acquire()
            return
        if self._waiting_generations >= self.MAX_WAITERS:
            raise ModelProviderError("local_model_busy")
        self._waiting_generations += 1
        try:
            await asyncio.wait_for(self._generation_slot.acquire(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise ModelProviderError("local_model_busy") from exc
        finally:
            self._waiting_generations -= 1

    def _generate_sync(self, request: LLMRequest) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": request.model or self.model_alias,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
            "max_tokens": max(1, min(int(request.max_output_tokens), 4096)),
            "stream": False,
            # Qwen3.5 emits its chain of thought in ``reasoning_content`` by
            # default.  The local JARVIS contract consumes the final
            # assistant ``content`` and has a bounded response budget, so
            # request the usable answer channel explicitly.
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if request.tools:
            payload["tools"] = [dict(tool) for tool in request.tools]
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_obj = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        decoded = self._request_json(request_obj, self._timeout(request.timeout_seconds))
        choices = decoded.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ModelProviderError("llama_cpp_invalid_response")
        choice = choices[0]
        message = choice.get("message")
        if not isinstance(message, dict):
            raise ModelProviderError("llama_cpp_invalid_response")
        content = message.get("content", "")
        if content is None:
            content = ""
        if not isinstance(content, str):
            raise ModelProviderError("llama_cpp_invalid_response")
        tool_calls = self._normalize_tool_calls(message.get("tool_calls", ()))
        if not content.strip() and not tool_calls:
            raise ModelProviderError("llama_cpp_empty_content")
        finish_reason = choice.get("finish_reason", "stop")
        if finish_reason is None:
            finish_reason = "stop"
        if not isinstance(finish_reason, str):
            raise ModelProviderError("llama_cpp_invalid_response")
        model = decoded.get("model", request.model or self.model_alias)
        if not isinstance(model, str) or not self.MODEL_ALIAS_PATTERN.fullmatch(model):
            raise ModelProviderError("llama_cpp_invalid_response")
        return LLMResponse(
            request_id=request.request_id,
            text=content,
            model=model,
            finish_reason=finish_reason,
            tool_calls=tool_calls,
            usage=self._normalize_usage(decoded.get("usage", {})),
            provider=self.name,
            model_digest=None,
        )

    async def health(self, model: str | None = None) -> ModelHealth:
        return await asyncio.to_thread(self._health_sync, model or self.model_alias)

    def _health_sync(self, model: str) -> ModelHealth:
        checked = datetime.now(UTC)
        request = urllib.request.Request(f"{self.base_url}/health", headers={"Accept": "application/json"}, method="GET")
        try:
            status, body = self._request_bytes(request, 2.0, allow_http_error=True)
        except ModelOfflineError:
            return ModelHealth(self.name, False, checked, "llama_cpp_unavailable", model, self.last_latency_ms)
        except ModelProviderError:
            return ModelHealth(self.name, False, checked, "llama_cpp_invalid_response", model, self.last_latency_ms)
        if status == 503:
            return ModelHealth(self.name, False, checked, "llama_cpp_model_not_ready", model, self.last_latency_ms)
        if status != 200:
            return ModelHealth(self.name, False, checked, "llama_cpp_unavailable", model, self.last_latency_ms)
        reported = self._reported_models()
        if self.model_alias not in reported:
            return ModelHealth(self.name, False, checked, "llama_cpp_model_mismatch", model, self.last_latency_ms)
        return ModelHealth(self.name, True, checked, "llama_cpp_ready", self.model_alias, self.last_latency_ms)

    def _reported_models(self) -> tuple[str, ...]:
        request = urllib.request.Request(f"{self.base_url}/v1/models", headers={"Accept": "application/json"}, method="GET")
        try:
            status, body = self._request_bytes(request, 2.0, allow_http_error=True)
            if status != 200:
                return ()
            decoded = json.loads(body.decode("utf-8"))
            data = decoded.get("data") if isinstance(decoded, dict) else None
            if not isinstance(data, list):
                return ()
            return tuple(
                item["id"]
                for item in data
                if isinstance(item, dict)
                and isinstance(item.get("id"), str)
                and self.MODEL_ALIAS_PATTERN.fullmatch(item["id"])
            )
        except (ModelProviderError, UnicodeDecodeError, json.JSONDecodeError):
            return ()

    @classmethod
    def _timeout(cls, value: float | None) -> float:
        requested = cls.MAX_TIMEOUT_SECONDS if value is None else float(value)
        return max(cls.MIN_TIMEOUT_SECONDS, min(requested, cls.MAX_TIMEOUT_SECONDS))

    def _request_json(self, request: urllib.request.Request, timeout: float) -> dict[str, Any]:
        status, body = self._request_bytes(request, timeout)
        if status != 200:
            raise ModelProviderError("llama_cpp_http_error")
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelProviderError("llama_cpp_invalid_response") from exc
        if not isinstance(decoded, dict):
            raise ModelProviderError("llama_cpp_invalid_response")
        return decoded

    def _request_bytes(self, request: urllib.request.Request, timeout: float, *, allow_http_error: bool = False) -> tuple[int, bytes]:
        try:
            with self._urlopen(request, timeout=timeout) as response:
                content_length = self._content_length(response)
                if content_length is not None and content_length > self.MAX_RESPONSE_BYTES:
                    raise ModelProviderError("llama_cpp_response_too_large")
                body = response.read(self.MAX_RESPONSE_BYTES + 1)
                if len(body) > self.MAX_RESPONSE_BYTES:
                    raise ModelProviderError("llama_cpp_response_too_large")
                return int(getattr(response, "status", 200)), body
        except urllib.error.HTTPError as exc:
            if allow_http_error:
                try:
                    return int(exc.code), exc.read(self.MAX_RESPONSE_BYTES + 1)[: self.MAX_RESPONSE_BYTES]
                except OSError:
                    return int(exc.code), b""
            if exc.code == 503:
                raise ModelOfflineError("llama_cpp_unavailable") from exc
            raise ModelProviderError("llama_cpp_http_error") from exc
        except ModelProviderError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ModelOfflineError("llama_cpp_unavailable") from exc

    @staticmethod
    def _content_length(response: Any) -> int | None:
        headers = getattr(response, "headers", None)
        value = headers.get("Content-Length") if headers is not None and hasattr(headers, "get") else None
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError) as exc:
            raise ModelProviderError("llama_cpp_invalid_response") from exc

    @staticmethod
    def _normalize_usage(value: object) -> dict[str, int]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ModelProviderError("llama_cpp_invalid_response")
        prompt = value.get("prompt_tokens", value.get("prompt_eval_count", 0))
        output = value.get("completion_tokens", value.get("eval_count", 0))
        try:
            return {"prompt_tokens": max(0, int(prompt or 0)), "output_tokens": max(0, int(output or 0))}
        except (TypeError, ValueError) as exc:
            raise ModelProviderError("llama_cpp_invalid_response") from exc

    @staticmethod
    def _normalize_tool_calls(value: object) -> tuple[dict[str, object], ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ModelProviderError("llama_cpp_tool_call_invalid")
        normalized: list[dict[str, object]] = []
        for call in value:
            if not isinstance(call, dict) or not isinstance(call.get("function"), dict):
                raise ModelProviderError("llama_cpp_tool_call_invalid")
            function = call["function"]
            name = function.get("name")
            arguments = function.get("arguments", {})
            if not isinstance(name, str) or not name.strip():
                raise ModelProviderError("llama_cpp_tool_call_invalid")
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError as exc:
                    raise ModelProviderError("llama_cpp_tool_call_invalid") from exc
            if not isinstance(arguments, dict):
                raise ModelProviderError("llama_cpp_tool_call_invalid")
            normalized.append({"function": {"name": name, "arguments": arguments}})
        return tuple(normalized)


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
