"""Optional Groq and Gemini adapters for the hybrid model gateway.

Both adapters are standard-library HTTP boundaries. They are enabled only by
explicit configuration and process environment keys; neither provider is a
second JARVIS authority or an execution path for tools.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from ..contracts import LLMMessage, LLMRequest, LLMResponse, LLMRole
from .health import ModelHealth
from .providers import ModelOfflineError, ModelProviderError


class _BoundedCloudHTTP:
    MAX_RESPONSE_BYTES = 4 * 1024 * 1024
    MAX_TIMEOUT_SECONDS = 180.0

    def __init__(self, *, urlopen: Callable[..., Any]) -> None:
        self._urlopen = urlopen

    def _request_bytes(
        self,
        request: urllib.request.Request,
        timeout: float,
        *,
        prefix: str,
        allow_http_error: bool = False,
    ) -> tuple[int, bytes]:
        try:
            with self._urlopen(request, timeout=timeout) as response:
                content_length = self._content_length(response, prefix)
                if content_length is not None and content_length > self.MAX_RESPONSE_BYTES:
                    raise ModelProviderError(f"{prefix}_response_too_large")
                body = response.read(self.MAX_RESPONSE_BYTES + 1)
                if len(body) > self.MAX_RESPONSE_BYTES:
                    raise ModelProviderError(f"{prefix}_response_too_large")
                return int(getattr(response, "status", 200)), body
        except urllib.error.HTTPError as exc:
            if allow_http_error:
                try:
                    return int(exc.code), exc.read(self.MAX_RESPONSE_BYTES + 1)[: self.MAX_RESPONSE_BYTES]
                except OSError:
                    return int(exc.code), b""
            if exc.code == 429:
                raise ModelProviderError(f"{prefix}_rate_limited") from exc
            if exc.code in {408, 500, 502, 503, 504}:
                raise ModelOfflineError(f"{prefix}_unavailable") from exc
            if exc.code in {401, 403}:
                raise ModelProviderError(f"{prefix}_auth_failed") from exc
            raise ModelProviderError(f"{prefix}_http_error") from exc
        except ModelProviderError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ModelOfflineError(f"{prefix}_unavailable") from exc

    @staticmethod
    def _content_length(response: Any, prefix: str) -> int | None:
        headers = getattr(response, "headers", None)
        value = headers.get("Content-Length") if headers is not None and hasattr(headers, "get") else None
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError) as exc:
            raise ModelProviderError(f"{prefix}_invalid_response") from exc

    @staticmethod
    def _timeout(value: float | None) -> float:
        requested = 30.0 if value is None else float(value)
        return max(1.0, min(requested, _BoundedCloudHTTP.MAX_TIMEOUT_SECONDS))

    @staticmethod
    def _model(value: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 200:
            raise ValueError("cloud_model_invalid")
        if any(character.isspace() for character in value):
            raise ValueError("cloud_model_invalid")
        return value.strip()


class GroqProvider(_BoundedCloudHTTP):
    """Groq OpenAI-compatible Chat Completions adapter."""

    name = "groq"
    BASE_URL = "https://api.groq.com/openai/v1"

    def __init__(
        self,
        *,
        model: str = "openai/gpt-oss-120b",
        api_key: str | None = None,
        enabled: bool = False,
        timeout_seconds: float = 30.0,
        reasoning_effort: str = "low",
        urlopen: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        super().__init__(urlopen=urlopen)
        self.model = self._model(model)
        self.enabled = bool(enabled)
        self.timeout_seconds = self._timeout(timeout_seconds)
        self.reasoning_effort = reasoning_effort if reasoning_effort in {
            "none", "default", "minimal", "low", "medium", "high", "xhigh", "max",
        } else "low"
        self._api_key = (api_key if api_key is not None else os.getenv("GROQ_API_KEY", "")).strip()
        self.requests = 0
        self.failures = 0
        self.last_latency_ms: float | None = None
        self._generation_slot = asyncio.Semaphore(2)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        started = time.perf_counter()
        self.requests += 1
        try:
            if not self.enabled:
                raise ModelProviderError("groq_not_enabled")
            if not self._api_key:
                raise ModelProviderError("groq_api_key_missing")
            async with self._generation_slot:
                response = await asyncio.to_thread(self._generate_sync, request)
            return response
        except ModelProviderError:
            self.failures += 1
            raise
        finally:
            self.last_latency_ms = (time.perf_counter() - started) * 1000

    def _generate_sync(self, request: LLMRequest) -> LLMResponse:
        if any(message.media for message in request.messages):
            raise ModelProviderError("groq_multimodal_unsupported")
        payload: dict[str, Any] = {
            "model": request.model or self.model,
            "messages": self._messages(request.messages),
            "max_tokens": max(1, min(int(request.max_output_tokens), 4096)),
            "stream": False,
            "reasoning_effort": self.reasoning_effort,
        }
        if request.tools:
            payload["tools"] = [dict(tool) for tool in request.tools]
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(body) > 512 * 1024:
            raise ModelProviderError("groq_request_too_large")
        request_obj = urllib.request.Request(
            f"{self.BASE_URL}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        status, response_body = self._request_bytes(
            request_obj,
            self._timeout(request.timeout_seconds or self.timeout_seconds),
            prefix="groq",
        )
        if status != 200:
            raise ModelProviderError("groq_http_error")
        try:
            decoded = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelProviderError("groq_invalid_response") from exc
        if not isinstance(decoded, dict):
            raise ModelProviderError("groq_invalid_response")
        return self._normalize_response(request, decoded)

    @staticmethod
    def _messages(messages: tuple[LLMMessage, ...]) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        for message in messages:
            role = message.role.value
            content = message.content
            if message.role is LLMRole.TOOL:
                role = "user"
                content = f"[JARVIS tool result]\n{content}"
            result.append({"role": role, "content": content})
        return result

    @staticmethod
    def _normalize_response(request: LLMRequest, decoded: dict[str, Any]) -> LLMResponse:
        choices = decoded.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
            raise ModelProviderError("groq_invalid_response")
        choice = choices[0]
        message = choice.get("message")
        if not isinstance(message, Mapping):
            raise ModelProviderError("groq_invalid_response")
        content = message.get("content", "")
        if content is None:
            content = ""
        if not isinstance(content, str):
            raise ModelProviderError("groq_invalid_response")
        tool_calls = GroqProvider._normalize_tool_calls(message.get("tool_calls", ()))
        finish_reason = choice.get("finish_reason", "stop")
        if finish_reason is None:
            finish_reason = "stop"
        if not isinstance(finish_reason, str):
            raise ModelProviderError("groq_invalid_response")
        model = decoded.get("model", request.model or "openai/gpt-oss-120b")
        if not isinstance(model, str) or not model.strip():
            raise ModelProviderError("groq_invalid_response")
        usage = decoded.get("usage", {})
        if not isinstance(usage, Mapping):
            raise ModelProviderError("groq_invalid_response")
        try:
            normalized_usage = {
                "prompt_tokens": max(0, int(usage.get("prompt_tokens", 0) or 0)),
                "output_tokens": max(0, int(usage.get("completion_tokens", 0) or 0)),
            }
        except (TypeError, ValueError) as exc:
            raise ModelProviderError("groq_invalid_response") from exc
        return LLMResponse(
            request_id=request.request_id,
            text=content,
            model=model,
            finish_reason=finish_reason,
            tool_calls=tool_calls,
            usage=normalized_usage,
            provider=GroqProvider.name,
        )

    @staticmethod
    def _normalize_tool_calls(value: object) -> tuple[dict[str, object], ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ModelProviderError("groq_tool_call_invalid")
        normalized: list[dict[str, object]] = []
        for call in value:
            if not isinstance(call, Mapping) or not isinstance(call.get("function"), Mapping):
                raise ModelProviderError("groq_tool_call_invalid")
            function = call["function"]
            name = function.get("name")
            arguments = function.get("arguments", {})
            if not isinstance(name, str) or not name.strip():
                raise ModelProviderError("groq_tool_call_invalid")
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError as exc:
                    raise ModelProviderError("groq_tool_call_invalid") from exc
            if not isinstance(arguments, dict):
                raise ModelProviderError("groq_tool_call_invalid")
            normalized_call: dict[str, object] = {"function": {"name": name, "arguments": arguments}}
            if isinstance(call.get("id"), str) and call["id"]:
                normalized_call["id"] = call["id"]
            normalized.append(normalized_call)
        return tuple(normalized)

    async def health(self, model: str | None = None) -> ModelHealth:
        return await asyncio.to_thread(self._health_sync, model or self.model)

    def _health_sync(self, model: str) -> ModelHealth:
        checked = datetime.now(UTC)
        if not self.enabled:
            return ModelHealth(self.name, False, checked, "groq_not_enabled", model)
        if not self._api_key:
            return ModelHealth(self.name, False, checked, "groq_api_key_missing", model)
        url = f"{self.BASE_URL}/models/{urllib.parse.quote(self._model(model), safe='')}"
        request_obj = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {self._api_key}", "Accept": "application/json"},
            method="GET",
        )
        try:
            status, body = self._request_bytes(request_obj, 2.0, prefix="groq", allow_http_error=True)
        except ModelOfflineError:
            return ModelHealth(self.name, False, checked, "groq_unavailable", model)
        except ModelProviderError:
            return ModelHealth(self.name, False, checked, "groq_invalid_response", model)
        if status in {401, 403}:
            return ModelHealth(self.name, False, checked, "groq_auth_failed", model)
        if status == 404:
            return ModelHealth(self.name, False, checked, "groq_model_unavailable", model)
        if status != 200:
            return ModelHealth(self.name, False, checked, "groq_http_error", model)
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return ModelHealth(self.name, False, checked, "groq_invalid_response", model)
        if not isinstance(decoded, Mapping) or not isinstance(decoded.get("id"), str):
            return ModelHealth(self.name, False, checked, "groq_invalid_response", model)
        return ModelHealth(self.name, True, checked, "groq_ready", model)


class GeminiProvider(_BoundedCloudHTTP):
    """Gemini GenerateContent adapter with transient inline media support."""

    name = "gemini"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
    MAX_INLINE_BYTES = 15 * 1024 * 1024

    def __init__(
        self,
        *,
        model: str = "gemini-3.5-flash",
        api_key: str | None = None,
        enabled: bool = False,
        timeout_seconds: float = 45.0,
        urlopen: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        super().__init__(urlopen=urlopen)
        self.model = self._model(model)
        self.enabled = bool(enabled)
        self.timeout_seconds = self._timeout(timeout_seconds)
        self._api_key = (api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")).strip()
        self.requests = 0
        self.failures = 0
        self.last_latency_ms: float | None = None
        self._generation_slot = asyncio.Semaphore(2)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        started = time.perf_counter()
        self.requests += 1
        try:
            if not self.enabled:
                raise ModelProviderError("gemini_not_enabled")
            if not self._api_key:
                raise ModelProviderError("gemini_api_key_missing")
            async with self._generation_slot:
                response = await asyncio.to_thread(self._generate_sync, request)
            return response
        except ModelProviderError:
            self.failures += 1
            raise
        finally:
            self.last_latency_ms = (time.perf_counter() - started) * 1000

    def _generate_sync(self, request: LLMRequest) -> LLMResponse:
        payload: dict[str, Any] = {
            "contents": self._contents(request.messages),
            "generationConfig": {"maxOutputTokens": max(1, min(int(request.max_output_tokens), 4096))},
        }
        system_parts = [
            {"text": message.content}
            for message in request.messages
            if message.role is LLMRole.SYSTEM and message.content
        ]
        if system_parts:
            payload["system_instruction"] = {"parts": system_parts}
        if request.tools:
            payload["tools"] = [{"function_declarations": self._function_declarations(request.tools)}]
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(body) > 19 * 1024 * 1024:
            raise ModelProviderError("gemini_request_too_large")
        model = self._model(request.model or self.model)
        request_obj = urllib.request.Request(
            f"{self.BASE_URL}/{urllib.parse.quote(model, safe='')}:generateContent",
            data=body,
            headers={"x-goog-api-key": self._api_key, "Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        status, response_body = self._request_bytes(
            request_obj,
            self._timeout(request.timeout_seconds or self.timeout_seconds),
            prefix="gemini",
        )
        if status != 200:
            raise ModelProviderError("gemini_http_error")
        try:
            decoded = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelProviderError("gemini_invalid_response") from exc
        if not isinstance(decoded, dict):
            raise ModelProviderError("gemini_invalid_response")
        return self._normalize_response(request, decoded)

    def _contents(self, messages: tuple[LLMMessage, ...]) -> list[dict[str, object]]:
        contents: list[dict[str, object]] = []
        inline_bytes = 0
        for message in messages:
            if message.role is LLMRole.SYSTEM:
                if message.media:
                    raise ModelProviderError("gemini_system_media_unsupported")
                continue
            role = "model" if message.role is LLMRole.ASSISTANT else "user"
            text = message.content
            if message.role is LLMRole.TOOL:
                text = f"[JARVIS tool result]\n{text}"
            parts: list[dict[str, object]] = []
            if text:
                parts.append({"text": text})
            for media in message.media:
                if not media.mime_type or not isinstance(media.data, bytes):
                    raise ModelProviderError("gemini_media_invalid")
                inline_bytes += len(media.data)
                if inline_bytes > self.MAX_INLINE_BYTES:
                    raise ModelProviderError("gemini_inline_media_too_large")
                parts.append({
                    "inline_data": {
                        "mime_type": media.mime_type,
                        "data": base64.b64encode(media.data).decode("ascii"),
                    },
                })
            if not parts:
                parts.append({"text": ""})
            contents.append({"role": role, "parts": parts})
        if not contents:
            contents.append({"role": "user", "parts": [{"text": ""}]})
        return contents

    @staticmethod
    def _function_declarations(tools: tuple[Mapping[str, Any], ...]) -> list[dict[str, Any]]:
        declarations: list[dict[str, Any]] = []
        for tool in tools:
            function = tool.get("function") if isinstance(tool, Mapping) else None
            if not isinstance(function, Mapping):
                raise ModelProviderError("gemini_tool_schema_invalid")
            name = function.get("name")
            description = function.get("description", "")
            parameters = function.get("parameters", {"type": "object"})
            if not isinstance(name, str) or not name.strip() or not isinstance(description, str) or not isinstance(parameters, Mapping):
                raise ModelProviderError("gemini_tool_schema_invalid")
            declarations.append({"name": name, "description": description, "parameters": dict(parameters)})
        return declarations

    @staticmethod
    def _normalize_response(request: LLMRequest, decoded: dict[str, Any]) -> LLMResponse:
        candidates = decoded.get("candidates")
        if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], Mapping):
            if decoded.get("promptFeedback") or decoded.get("prompt_feedback"):
                raise ModelProviderError("gemini_content_blocked")
            raise ModelProviderError("gemini_invalid_response")
        candidate = candidates[0]
        content = candidate.get("content")
        parts = content.get("parts") if isinstance(content, Mapping) else None
        if not isinstance(parts, list):
            raise ModelProviderError("gemini_invalid_response")
        text_parts: list[str] = []
        tool_calls: list[dict[str, object]] = []
        for part in parts:
            if not isinstance(part, Mapping):
                raise ModelProviderError("gemini_invalid_response")
            text = part.get("text")
            if text is not None:
                if not isinstance(text, str):
                    raise ModelProviderError("gemini_invalid_response")
                text_parts.append(text)
            function_call = part.get("functionCall", part.get("function_call"))
            if function_call is not None:
                if not isinstance(function_call, Mapping) or not isinstance(function_call.get("name"), str):
                    raise ModelProviderError("gemini_tool_call_invalid")
                arguments = function_call.get("args", {})
                if not isinstance(arguments, dict):
                    raise ModelProviderError("gemini_tool_call_invalid")
                tool_calls.append({"function": {"name": function_call["name"], "arguments": arguments}})
        finish_reason = candidate.get("finishReason", candidate.get("finish_reason", "STOP"))
        finish_reason = {
            "STOP": "stop",
            "MAX_TOKENS": "length",
            "SAFETY": "content_filter",
            "RECITATION": "content_filter",
        }.get(str(finish_reason), str(finish_reason).lower())
        usage = decoded.get("usageMetadata", decoded.get("usage_metadata", {}))
        if not isinstance(usage, Mapping):
            usage = {}
        try:
            normalized_usage = {
                "prompt_tokens": max(0, int(usage.get("promptTokenCount", usage.get("prompt_token_count", 0)) or 0)),
                "output_tokens": max(0, int(usage.get("candidatesTokenCount", usage.get("candidates_token_count", 0)) or 0)),
            }
        except (TypeError, ValueError) as exc:
            raise ModelProviderError("gemini_invalid_response") from exc
        return LLMResponse(
            request_id=request.request_id,
            text="".join(text_parts),
            model=request.model,
            finish_reason="tool_calls" if tool_calls else finish_reason,
            tool_calls=tuple(tool_calls),
            usage=normalized_usage,
            provider=GeminiProvider.name,
        )

    async def health(self, model: str | None = None) -> ModelHealth:
        return await asyncio.to_thread(self._health_sync, model or self.model)

    def _health_sync(self, model: str) -> ModelHealth:
        checked = datetime.now(UTC)
        if not self.enabled:
            return ModelHealth(self.name, False, checked, "gemini_not_enabled", model)
        if not self._api_key:
            return ModelHealth(self.name, False, checked, "gemini_api_key_missing", model)
        safe_model = self._model(model)
        request_obj = urllib.request.Request(
            f"{self.BASE_URL}/{urllib.parse.quote(safe_model, safe='')}",
            headers={"x-goog-api-key": self._api_key, "Accept": "application/json"},
            method="GET",
        )
        try:
            status, body = self._request_bytes(request_obj, 2.0, prefix="gemini", allow_http_error=True)
        except ModelOfflineError:
            return ModelHealth(self.name, False, checked, "gemini_unavailable", safe_model)
        except ModelProviderError:
            return ModelHealth(self.name, False, checked, "gemini_invalid_response", safe_model)
        if status in {401, 403}:
            return ModelHealth(self.name, False, checked, "gemini_auth_failed", safe_model)
        if status == 404:
            return ModelHealth(self.name, False, checked, "gemini_model_unavailable", safe_model)
        if status != 200:
            return ModelHealth(self.name, False, checked, "gemini_http_error", safe_model)
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return ModelHealth(self.name, False, checked, "gemini_invalid_response", safe_model)
        if not isinstance(decoded, Mapping) or not isinstance(decoded.get("name"), str):
            return ModelHealth(self.name, False, checked, "gemini_invalid_response", safe_model)
        return ModelHealth(self.name, True, checked, "gemini_ready", safe_model)
