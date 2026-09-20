"""Optional Groq and Gemini adapters for the hybrid model gateway.

Both adapters are standard-library HTTP boundaries. They are enabled only by
explicit configuration and receive credentials either through the desktop
secure-store injection boundary or the process-only compatibility path;
neither provider is a second JARVIS authority or an execution path for tools.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class GeminiHTTPDiagnostic:
    """Sanitized Google HTTP failure metadata safe for logs and CLI output."""

    http_status: int
    google_code: int | None
    google_status: str | None
    classification: str
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "http_status": self.http_status,
            "google_code": self.google_code,
            "google_status": self.google_status,
            "classification": self.classification,
            "reason": self.reason,
        }


class GeminiHTTPError(ModelProviderError):
    """Provider error carrying only sanitized Google HTTP metadata."""

    def __init__(self, diagnostic: GeminiHTTPDiagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(diagnostic.reason)


class GeminiResponseError(ModelProviderError):
    """Gemini response-shape failure with bounded structural evidence only."""

    def __init__(self, reason: str, summary: dict[str, object]) -> None:
        self.reason = reason
        self.summary = summary
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class GroqHTTPDiagnostic:
    """Sanitized Groq HTTP failure metadata safe for probe output."""

    http_status: int
    classification: str
    error_type: str | None
    error_code: str | None
    reason: str
    body_contains_1010: bool = False
    body_contains_browser_signature_banned: bool = False
    response_format: str = "unknown"

    def as_dict(self) -> dict[str, object]:
        return {
            "http_status": self.http_status,
            "classification": self.classification,
            "error_type": self.error_type,
            "error_code": self.error_code,
            "reason": self.reason,
            "body_contains_1010": self.body_contains_1010,
            "body_contains_browser_signature_banned": self.body_contains_browser_signature_banned,
            "response_format": self.response_format,
        }


class GroqHTTPError(ModelProviderError):
    """Provider error carrying only sanitized Groq HTTP metadata."""

    def __init__(self, diagnostic: GroqHTTPDiagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(diagnostic.reason)


class GroqProvider(_BoundedCloudHTTP):
    """Groq OpenAI-compatible Chat Completions adapter."""

    name = "groq"
    BASE_URL = "https://api.groq.com/openai/v1"
    USER_AGENT = "JARVIS/1.0"

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
        self.last_http_diagnostic: GroqHTTPDiagnostic | None = None
        self._request_traces: list[dict[str, object]] = []
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

    def credential_status(self) -> dict[str, object]:
        """Return only bounded key-presence metadata; never return the key."""

        value = self._api_key
        return {
            "present": bool(value),
            "length": min(len(value), 4096),
            "prefix_valid": bool(re.fullmatch(r"gsk_[A-Za-z0-9_-]{16,}", value)),
        }

    def reset_request_trace(self) -> None:
        """Forget prior bounded request metadata before an acceptance run."""

        self._request_traces.clear()

    def request_trace(self) -> list[dict[str, object]]:
        """Return safe request metadata without headers, bodies, or credentials."""

        return [dict(item) for item in self._request_traces]

    def _record_request_trace(self, request: urllib.request.Request, *, phase: str, timeout: float) -> None:
        """Record only the structural facts needed to audit the provider call."""

        self._request_traces.append({
            "phase": phase,
            "url": request.full_url,
            "method": request.get_method(),
            "authorization_present": bool(request.get_header("Authorization")),
            "accept_header": request.get_header("Accept"),
            "user_agent": request.headers.get("User-agent") or request.get_header("User-agent"),
            "content_type_present": bool(request.get_header("Content-Type")),
            "key_length": min(len(self._api_key), 4096),
            "prefix_valid": bool(re.fullmatch(r"gsk_[A-Za-z0-9_-]{16,}", self._api_key)),
            "timeout_seconds": timeout,
        })
        del self._request_traces[:-8]

    def _request_headers(self, *, content_type: bool = False) -> dict[str, str]:
        """Build one honest, bounded header set for every Groq API request."""

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "User-Agent": self.USER_AGENT,
        }
        if content_type:
            headers["Content-Type"] = "application/json"
        return headers

    def _generate_sync(self, request: LLMRequest) -> LLMResponse:
        self.last_http_diagnostic = None
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
            headers=self._request_headers(content_type=True),
            method="POST",
        )
        timeout = self._timeout(request.timeout_seconds or self.timeout_seconds)
        self._record_request_trace(request_obj, phase="generation", timeout=timeout)
        status, response_body = self._request_bytes(
            request_obj,
            timeout,
            prefix="groq",
            allow_http_error=True,
        )
        if status != 200:
            self.last_http_diagnostic = self._diagnose_http_error(status, response_body)
            raise GroqHTTPError(self.last_http_diagnostic)
        try:
            decoded = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelProviderError("groq_invalid_response") from exc
        if not isinstance(decoded, dict):
            raise ModelProviderError("groq_invalid_response")
        return self._normalize_response(request, decoded)

    @classmethod
    def _diagnose_http_error(cls, http_status: int, body: bytes) -> GroqHTTPDiagnostic:
        """Normalize only bounded Groq error metadata; never retain its message."""

        error_type: str | None = None
        error_code: str | None = None
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            decoded = None
        error = decoded.get("error") if isinstance(decoded, Mapping) else None
        if isinstance(error, Mapping):
            candidate_type = error.get("type")
            if isinstance(candidate_type, str):
                normalized_type = candidate_type.strip().lower()
                if re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", normalized_type):
                    error_type = normalized_type
            candidate_code = error.get("code")
            if isinstance(candidate_code, str):
                normalized_code = candidate_code.strip().lower()
                if re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", normalized_code):
                    error_code = normalized_code
            elif isinstance(candidate_code, int) and not isinstance(candidate_code, bool) and 100 <= candidate_code <= 599:
                error_code = str(candidate_code)

        body_contains_1010, body_contains_browser_signature_banned, response_format = cls._summarize_error_body(body)
        if http_status == 401:
            classification = "authentication_failure"
            prefix = "groq_http_401_authentication_failure"
        elif http_status == 403:
            classification = "permission_failure"
            prefix = "groq_http_403_permission_failure"
        elif http_status == 404:
            classification = "model_unavailable"
            prefix = "groq_http_404_model_unavailable"
        elif http_status == 408:
            classification = "timeout"
            prefix = "groq_http_408_timeout"
        elif http_status == 429:
            classification = "rate_limit_or_quota"
            prefix = "groq_http_429_rate_limit_or_quota"
        elif 500 <= http_status <= 599:
            classification = "service_unavailable"
            prefix = "groq_http_5xx_service_unavailable"
        else:
            classification = "http_error"
            prefix = f"groq_http_{http_status}_error"
        suffix_parts = [value for value in (error_type, error_code) if value]
        if body_contains_1010 and body_contains_browser_signature_banned:
            suffix_parts.append("cloudflare_1010_browser_signature_banned")
        suffix = ":".join(suffix_parts)
        reason = f"{prefix}:{suffix}" if suffix else prefix
        return GroqHTTPDiagnostic(
            http_status,
            classification,
            error_type,
            error_code,
            reason,
            body_contains_1010,
            body_contains_browser_signature_banned,
            response_format,
        )

    @staticmethod
    def _summarize_error_body(body: bytes) -> tuple[bool, bool, str]:
        """Classify a bounded error body without retaining or returning its text."""

        sample = body[:64 * 1024].decode("utf-8", errors="ignore")
        normalized = sample.casefold()
        contains_1010 = bool(re.search(r"\b1010\b", normalized))
        contains_browser_signature_banned = (
            "browser_signature_banned" in normalized or "browser signature banned" in normalized
        )
        try:
            decoded = json.loads(sample)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, Mapping):
            response_format = "groq_json"
        elif any(marker in normalized for marker in ("<!doctype html", "<html", "cloudflare", "attention required")):
            response_format = "cloudflare_html_or_text"
        elif decoded is not None:
            response_format = "other_json"
        else:
            response_format = "text_or_non_json"
        return contains_1010, contains_browser_signature_banned, response_format

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
        self.last_http_diagnostic = None
        safe_model = self._model(model)
        url = f"{self.BASE_URL}/models"
        request_obj = urllib.request.Request(
            url,
            headers=self._request_headers(),
            method="GET",
        )
        timeout = 2.0
        self._record_request_trace(request_obj, phase="catalog", timeout=timeout)
        try:
            status, body = self._request_bytes(request_obj, timeout, prefix="groq", allow_http_error=True)
        except ModelOfflineError:
            return ModelHealth(self.name, False, checked, "groq_unavailable", model)
        except ModelProviderError:
            return ModelHealth(self.name, False, checked, "groq_invalid_response", safe_model)
        if status != 200:
            self.last_http_diagnostic = self._diagnose_http_error(status, body)
            return ModelHealth(self.name, False, checked, self.last_http_diagnostic.reason, safe_model)
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return ModelHealth(self.name, False, checked, "groq_invalid_response", safe_model)
        data = decoded.get("data") if isinstance(decoded, Mapping) else None
        if not isinstance(data, list):
            return ModelHealth(self.name, False, checked, "groq_invalid_response", safe_model)
        model_record = next((item for item in data if isinstance(item, Mapping) and item.get("id") == safe_model), None)
        if not isinstance(model_record, Mapping) or model_record.get("active") is False:
            return ModelHealth(self.name, False, checked, "groq_model_unavailable", safe_model)
        return ModelHealth(self.name, True, checked, "groq_ready", safe_model)


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
        self.last_response_summary: dict[str, object] | None = None
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

    def credential_status(self) -> dict[str, object]:
        """Return only bounded key-presence metadata; never return the key."""

        value = self._api_key
        return {
            "present": bool(value),
            "length": min(len(value), 4096),
            "prefix_valid": bool(re.fullmatch(r"AIza[A-Za-z0-9_-]{16,}", value)),
        }

    def _generate_sync(self, request: LLMRequest) -> LLMResponse:
        self.last_response_summary = None
        max_output_tokens = max(1, min(int(request.max_output_tokens), 4096))
        generation_config: dict[str, object] = {"maxOutputTokens": max_output_tokens}
        thinking_level = request.provider_options.get("gemini_thinking_level")
        if thinking_level is not None:
            if not isinstance(thinking_level, str) or thinking_level.strip().lower() not in {"minimal", "low", "medium", "high"}:
                raise ModelProviderError("gemini_thinking_config_invalid")
            generation_config["thinkingConfig"] = {"thinkingLevel": thinking_level.strip().lower()}
        payload: dict[str, Any] = {
            "contents": self._contents(request.messages),
            "generationConfig": generation_config,
        }
        system_parts = [
            {"text": message.content}
            for message in request.messages
            if message.role is LLMRole.SYSTEM and message.content
        ]
        if system_parts:
            payload["systemInstruction"] = {"parts": system_parts}
        if request.tools:
            payload["tools"] = [{"functionDeclarations": self._function_declarations(request.tools)}]
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
            allow_http_error=True,
        )
        if status != 200:
            raise GeminiHTTPError(self._diagnose_http_error(status, response_body))
        try:
            decoded = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            summary = self._response_summary(None, http_status=status)
            self.last_response_summary = summary
            raise GeminiResponseError("gemini_invalid_response", summary) from exc
        summary = self._response_summary(decoded, http_status=status)
        self.last_response_summary = summary
        if not isinstance(decoded, dict):
            raise GeminiResponseError("gemini_invalid_response", summary)
        return self._normalize_response(request, decoded)

    @classmethod
    def _diagnose_http_error(cls, http_status: int, body: bytes) -> GeminiHTTPDiagnostic:
        """Normalize only bounded Google error metadata; never retain its message."""

        google_code: int | None = None
        google_status: str | None = None
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            decoded = None
        error = decoded.get("error") if isinstance(decoded, Mapping) else None
        if isinstance(error, Mapping):
            candidate_code = error.get("code")
            if isinstance(candidate_code, int) and not isinstance(candidate_code, bool) and 100 <= candidate_code <= 599:
                google_code = candidate_code
            candidate_status = error.get("status")
            if isinstance(candidate_status, str):
                normalized_status = candidate_status.strip().upper()
                if re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", normalized_status):
                    google_status = normalized_status

        if http_status == 400:
            classification = "failed_prerequisite" if google_status == "FAILED_PRECONDITION" else "invalid_request"
            prefix = f"gemini_http_400_{classification}"
        elif http_status == 401:
            classification = "authentication_failure"
            prefix = "gemini_http_401_authentication_failure"
        elif http_status == 403:
            classification = "permission_failure"
            prefix = "gemini_http_403_permission_failure"
        elif http_status == 404:
            classification = "model_or_resource_unavailable"
            prefix = "gemini_http_404_model_or_resource_unavailable"
        elif http_status == 429:
            classification = "rate_limit_or_quota"
            prefix = "gemini_http_429_rate_limit_or_quota"
        elif 500 <= http_status <= 599:
            classification = "service_unavailable"
            prefix = "gemini_http_5xx_service_unavailable"
        else:
            classification = "http_error"
            prefix = f"gemini_http_{http_status}_error"
        reason = f"{prefix}:{google_status}" if google_status else prefix
        return GeminiHTTPDiagnostic(http_status, google_code, google_status, classification, reason)

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
                    "inlineData": {
                        "mimeType": media.mime_type,
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
    def _safe_response_token(value: object) -> str | None:
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", value.strip()):
            return value.strip()
        return None

    @classmethod
    def _response_summary(cls, decoded: object, *, http_status: int) -> dict[str, object]:
        """Capture response shape and token counts without retaining content or signatures."""

        summary: dict[str, object] = {
            "http_status": http_status,
            "top_level_fields": [],
            "candidate_count": None,
            "finish_reason": None,
            "content_exists": False,
            "parts_count": None,
            "part_field_names": [],
            "usageMetadata": {},
            "promptFeedback": {},
        }
        if not isinstance(decoded, Mapping):
            return summary
        summary["top_level_fields"] = sorted(
            key for key in decoded
            if isinstance(key, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", key)
        )[:32]
        candidates = decoded.get("candidates")
        if not isinstance(candidates, list):
            return summary
        summary["candidate_count"] = len(candidates)
        candidate = candidates[0] if candidates and isinstance(candidates[0], Mapping) else None
        if candidate is None:
            return summary
        finish_reason = candidate.get("finishReason", candidate.get("finish_reason"))
        summary["finish_reason"] = cls._safe_response_token(finish_reason)
        content = candidate.get("content")
        summary["content_exists"] = isinstance(content, Mapping)
        parts = content.get("parts") if isinstance(content, Mapping) else None
        if isinstance(parts, list):
            summary["parts_count"] = len(parts)
            field_names: list[list[str]] = []
            for part in parts[:32]:
                if isinstance(part, Mapping):
                    field_names.append(sorted(
                        key for key in part
                        if isinstance(key, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", key)
                    )[:16])
                else:
                    field_names.append([])
            summary["part_field_names"] = field_names
        usage = decoded.get("usageMetadata", decoded.get("usage_metadata"))
        usage_summary: dict[str, int] = {}
        if isinstance(usage, Mapping):
            for canonical, aliases in {
                "promptTokenCount": ("promptTokenCount", "prompt_token_count"),
                "candidatesTokenCount": ("candidatesTokenCount", "candidates_token_count"),
                "thoughtsTokenCount": ("thoughtsTokenCount", "thoughts_token_count"),
                "totalTokenCount": ("totalTokenCount", "total_token_count"),
            }.items():
                for alias in aliases:
                    value = usage.get(alias)
                    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 1_000_000_000:
                        usage_summary[canonical] = value
                        break
        summary["usageMetadata"] = usage_summary
        prompt_feedback = decoded.get("promptFeedback", decoded.get("prompt_feedback"))
        block_reason = prompt_feedback.get("blockReason", prompt_feedback.get("block_reason")) if isinstance(prompt_feedback, Mapping) else None
        safe_block_reason = cls._safe_response_token(block_reason)
        if safe_block_reason:
            summary["promptFeedback"] = {"blockReason": safe_block_reason}
        return summary

    @classmethod
    def _normalize_response(cls, request: LLMRequest, decoded: dict[str, Any]) -> LLMResponse:
        summary = cls._response_summary(decoded, http_status=200)
        candidates = decoded.get("candidates")
        if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], Mapping):
            if decoded.get("promptFeedback") or decoded.get("prompt_feedback"):
                raise GeminiResponseError("gemini_content_blocked", summary)
            raise GeminiResponseError("gemini_invalid_response", summary)
        candidate = candidates[0]
        raw_finish_reason = candidate.get("finishReason", candidate.get("finish_reason", "STOP"))
        finish_reason_name = str(raw_finish_reason).upper()
        content = candidate.get("content")
        parts = content.get("parts") if isinstance(content, Mapping) else None
        if not isinstance(parts, list):
            if finish_reason_name == "MAX_TOKENS":
                raise GeminiResponseError("gemini_output_truncated", summary)
            if finish_reason_name in {"SAFETY", "RECITATION"}:
                raise GeminiResponseError("gemini_content_blocked", summary)
            raise GeminiResponseError("gemini_invalid_response", summary)
        text_parts: list[str] = []
        tool_calls: list[dict[str, object]] = []
        for part in parts:
            if not isinstance(part, Mapping):
                raise GeminiResponseError("gemini_invalid_response", summary)
            text = part.get("text")
            if text is not None:
                if not isinstance(text, str):
                    raise GeminiResponseError("gemini_invalid_response", summary)
                text_parts.append(text)
            function_call = part.get("functionCall", part.get("function_call"))
            if function_call is not None:
                if not isinstance(function_call, Mapping) or not isinstance(function_call.get("name"), str):
                    raise GeminiResponseError("gemini_tool_call_invalid", summary)
                arguments = function_call.get("args", {})
                if not isinstance(arguments, dict):
                    raise GeminiResponseError("gemini_tool_call_invalid", summary)
                tool_calls.append({"function": {"name": function_call["name"], "arguments": arguments}})
        visible_text = "".join(text_parts)
        if not visible_text.strip() and not tool_calls:
            if finish_reason_name == "MAX_TOKENS":
                raise GeminiResponseError("gemini_output_truncated", summary)
            if finish_reason_name in {"SAFETY", "RECITATION"} or decoded.get("promptFeedback") or decoded.get("prompt_feedback"):
                raise GeminiResponseError("gemini_content_blocked", summary)
            raise GeminiResponseError("gemini_empty_content", summary)
        finish_reason = raw_finish_reason
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
            raise GeminiResponseError("gemini_invalid_response", summary) from exc
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
        if status != 200:
            return ModelHealth(self.name, False, checked, self._diagnose_http_error(status, body).reason, safe_model)
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return ModelHealth(self.name, False, checked, "gemini_invalid_response", safe_model)
        if not isinstance(decoded, Mapping) or not isinstance(decoded.get("name"), str):
            return ModelHealth(self.name, False, checked, "gemini_invalid_response", safe_model)
        return ModelHealth(self.name, True, checked, "gemini_ready", safe_model)
