"""Explicit OpenAI Responses API provider.

This adapter is opt-in only. It reads ``OPENAI_API_KEY`` at the provider
boundary, never exposes the key in errors or health data, and uses the
official HTTPS Responses endpoint without adding a second model authority.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from ..contracts import LLMMessage, LLMRequest, LLMResponse
from .health import ModelHealth
from .providers import ModelProviderError, ModelOfflineError


class OpenAIProvider:
    """Bounded adapter for the OpenAI Responses API.

    The provider does not fall back to OpenAI, discover arbitrary endpoints,
    or execute tools. Tool calls are returned to the existing AgentRuntime,
    which remains responsible for permission, approval, execution, and
    verification.
    """

    name = "openai"
    ENDPOINT = "https://api.openai.com/v1"
    MAX_RESPONSE_BYTES = 4 * 1024 * 1024
    MAX_REQUEST_BYTES = 512 * 1024
    MIN_TIMEOUT_SECONDS = 1.0
    MAX_TIMEOUT_SECONDS = 180.0
    MODEL_MAX_LENGTH = 200

    def __init__(
        self,
        *,
        model: str = "gpt-5.2",
        api_key: str | None = None,
        enabled: bool = True,
        timeout_seconds: float = 30.0,
        urlopen: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        self.model = self._validate_model(model)
        self.enabled = bool(enabled)
        self.timeout_seconds = self._timeout(timeout_seconds)
        self._api_key = (api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")).strip()
        self._urlopen = urlopen
        self.requests = 0
        self.failures = 0
        self.last_latency_ms: float | None = None
        self._generation_slot = asyncio.Semaphore(2)

    @classmethod
    def _validate_model(cls, model: str) -> str:
        if not isinstance(model, str) or not model.strip() or len(model.strip()) > cls.MODEL_MAX_LENGTH:
            raise ValueError("openai_model_invalid")
        if any(character.isspace() for character in model):
            raise ValueError("openai_model_invalid")
        return model.strip()

    @classmethod
    def _timeout(cls, value: float | None) -> float:
        requested = cls.MAX_TIMEOUT_SECONDS if value is None else float(value)
        return max(cls.MIN_TIMEOUT_SECONDS, min(requested, cls.MAX_TIMEOUT_SECONDS))

    async def generate(self, request: LLMRequest) -> LLMResponse:
        started = time.perf_counter()
        self.requests += 1
        try:
            if not self.enabled:
                raise ModelProviderError("openai_not_enabled")
            if not self._api_key:
                raise ModelProviderError("openai_api_key_missing")
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
            "model": request.model or self.model,
            "input": self._input_items(request.messages),
            "max_output_tokens": max(1, min(int(request.max_output_tokens), 4096)),
            # The provider is intentionally stateless; callers keep durable
            # state in the existing JARVIS repositories, not in a provider
            # conversation.
            "store": False,
        }
        if request.tools:
            payload["tools"] = self._tools(request.tools)
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(body) > self.MAX_REQUEST_BYTES:
            raise ModelProviderError("openai_request_too_large")
        request_obj = urllib.request.Request(
            f"{self.ENDPOINT}/responses",
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        decoded = self._request_json(request_obj, self._timeout(request.timeout_seconds or self.timeout_seconds))
        return self._normalize_response(request, decoded)

    @staticmethod
    def _input_items(messages: tuple[LLMMessage, ...]) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        for message in messages:
            role = message.role.value
            # The provider-neutral contract does not carry a Responses
            # function-call id for tool results. Preserve the evidence as a
            # clearly marked user item so the next model step remains usable
            # without inventing a call id or bypassing AgentRuntime.
            if role == "tool":
                role = "user"
                content = f"[JARVIS tool result]\n{message.content}"
            else:
                content = message.content
            items.append({"role": role, "content": content})
        return items

    @staticmethod
    def _tools(tools: tuple[Mapping[str, Any], ...]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        for tool in tools:
            if not isinstance(tool, Mapping) or tool.get("type") != "function":
                raise ModelProviderError("openai_tool_schema_invalid")
            function = tool.get("function")
            if not isinstance(function, Mapping):
                raise ModelProviderError("openai_tool_schema_invalid")
            name = function.get("name")
            description = function.get("description", "")
            parameters = function.get("parameters")
            if not isinstance(name, str) or not name.strip() or not isinstance(description, str):
                raise ModelProviderError("openai_tool_schema_invalid")
            if not isinstance(parameters, Mapping):
                raise ModelProviderError("openai_tool_schema_invalid")
            converted.append({
                "type": "function",
                "name": name,
                "description": description,
                "parameters": dict(parameters),
            })
        return converted

    def _normalize_response(self, request: LLMRequest, decoded: dict[str, Any]) -> LLMResponse:
        output = decoded.get("output")
        if not isinstance(output, list):
            raise ModelProviderError("openai_invalid_response")
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for item in output:
            if not isinstance(item, Mapping):
                raise ModelProviderError("openai_invalid_response")
            item_type = item.get("type")
            if item_type == "message":
                content = item.get("content", ())
                if not isinstance(content, list):
                    raise ModelProviderError("openai_invalid_response")
                for part in content:
                    if not isinstance(part, Mapping):
                        raise ModelProviderError("openai_invalid_response")
                    if part.get("type") == "output_text":
                        text = part.get("text")
                        if not isinstance(text, str):
                            raise ModelProviderError("openai_invalid_response")
                        text_parts.append(text)
            elif item_type == "function_call":
                name = item.get("name")
                arguments = item.get("arguments", "{}")
                if not isinstance(name, str) or not name.strip() or not isinstance(arguments, str):
                    raise ModelProviderError("openai_tool_call_invalid")
                try:
                    parsed_arguments = json.loads(arguments)
                except json.JSONDecodeError as exc:
                    raise ModelProviderError("openai_tool_call_invalid") from exc
                if not isinstance(parsed_arguments, dict):
                    raise ModelProviderError("openai_tool_call_invalid")
                call_id = item.get("call_id")
                normalized: dict[str, Any] = {
                    "function": {"name": name, "arguments": parsed_arguments},
                }
                if isinstance(call_id, str) and call_id:
                    normalized["id"] = call_id
                tool_calls.append(normalized)
            elif item_type not in {"reasoning", "summary", None}:
                # Unknown output types are not silently treated as text.
                continue
        model = decoded.get("model", request.model or self.model)
        if not isinstance(model, str) or not model.strip():
            raise ModelProviderError("openai_invalid_response")
        status = decoded.get("status", "completed")
        if status not in {"completed", "in_progress", "queued"}:
            raise ModelProviderError("openai_incomplete_response")
        finish_reason = "tool_calls" if tool_calls else "stop"
        return LLMResponse(
            request_id=request.request_id,
            text="".join(text_parts),
            model=model,
            finish_reason=finish_reason,
            tool_calls=tuple(tool_calls),
            usage=self._normalize_usage(decoded.get("usage", {})),
            provider=self.name,
        )

    @staticmethod
    def _normalize_usage(value: object) -> dict[str, int]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise ModelProviderError("openai_invalid_response")
        input_tokens = value.get("input_tokens", 0)
        output_tokens = value.get("output_tokens", 0)
        try:
            return {
                "prompt_tokens": max(0, int(input_tokens or 0)),
                "output_tokens": max(0, int(output_tokens or 0)),
            }
        except (TypeError, ValueError) as exc:
            raise ModelProviderError("openai_invalid_response") from exc

    async def health(self, model: str | None = None) -> ModelHealth:
        return await asyncio.to_thread(self._health_sync, model or self.model)

    def _health_sync(self, model: str) -> ModelHealth:
        checked = datetime.now(UTC)
        if not self.enabled:
            return ModelHealth(self.name, False, checked, "openai_not_enabled", model)
        if not self._api_key:
            return ModelHealth(self.name, False, checked, "openai_api_key_missing", model)
        safe_model = self._validate_model(model)
        url = f"{self.ENDPOINT}/models/{urllib.parse.quote(safe_model, safe='')}"
        request_obj = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {self._api_key}", "Accept": "application/json"},
            method="GET",
        )
        try:
            status, body = self._request_bytes(request_obj, 2.0, allow_http_error=True)
        except ModelOfflineError:
            return ModelHealth(self.name, False, checked, "openai_unavailable", safe_model)
        except ModelProviderError:
            return ModelHealth(self.name, False, checked, "openai_invalid_response", safe_model)
        if status == 401:
            return ModelHealth(self.name, False, checked, "openai_auth_failed", safe_model)
        if status == 403:
            return ModelHealth(self.name, False, checked, "openai_access_denied", safe_model)
        if status == 404:
            return ModelHealth(self.name, False, checked, "openai_model_unavailable", safe_model)
        if status != 200:
            return ModelHealth(self.name, False, checked, "openai_http_error", safe_model)
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return ModelHealth(self.name, False, checked, "openai_invalid_response", safe_model)
        if not isinstance(decoded, Mapping) or not isinstance(decoded.get("id"), str):
            return ModelHealth(self.name, False, checked, "openai_invalid_response", safe_model)
        return ModelHealth(self.name, True, checked, "openai_ready", safe_model)

    def _request_json(self, request: urllib.request.Request, timeout: float) -> dict[str, Any]:
        status, body = self._request_bytes(request, timeout)
        if status != 200:
            raise ModelProviderError("openai_http_error")
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelProviderError("openai_invalid_response") from exc
        if not isinstance(decoded, dict):
            raise ModelProviderError("openai_invalid_response")
        return decoded

    def _request_bytes(
        self,
        request: urllib.request.Request,
        timeout: float,
        *,
        allow_http_error: bool = False,
    ) -> tuple[int, bytes]:
        try:
            with self._urlopen(request, timeout=timeout) as response:
                content_length = self._content_length(response)
                if content_length is not None and content_length > self.MAX_RESPONSE_BYTES:
                    raise ModelProviderError("openai_response_too_large")
                body = response.read(self.MAX_RESPONSE_BYTES + 1)
                if len(body) > self.MAX_RESPONSE_BYTES:
                    raise ModelProviderError("openai_response_too_large")
                return int(getattr(response, "status", 200)), body
        except urllib.error.HTTPError as exc:
            if allow_http_error:
                try:
                    return int(exc.code), exc.read(self.MAX_RESPONSE_BYTES + 1)[: self.MAX_RESPONSE_BYTES]
                except OSError:
                    return int(exc.code), b""
            if exc.code in {408, 429, 500, 502, 503, 504}:
                raise ModelOfflineError("openai_unavailable") from exc
            raise ModelProviderError("openai_http_error") from exc
        except ModelProviderError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ModelOfflineError("openai_unavailable") from exc

    @staticmethod
    def _content_length(response: Any) -> int | None:
        headers = getattr(response, "headers", None)
        value = headers.get("Content-Length") if headers is not None and hasattr(headers, "get") else None
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError) as exc:
            raise ModelProviderError("openai_invalid_response") from exc
