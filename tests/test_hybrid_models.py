from __future__ import annotations

import asyncio
import json
import os
import unittest
import urllib.error
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from urllib.request import Request

from jarvis.api.core import CoreApplication
from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.contracts import LLMInputMedia, LLMMessage, LLMRequest, LLMResponse, LLMRole
from jarvis.models.cloud import (
    GeminiHTTPDiagnostic,
    GeminiHTTPError,
    GeminiProvider,
    GroqHTTPError,
    GroqProvider,
)
from jarvis.models.gateway import ModelGateway
from jarvis.models.health import ModelHealth
from jarvis.models.routing import CapabilityRouter, ModelRoute
from jarvis.models.providers import ModelProviderError, MockModelProvider


class _Response:
    def __init__(self, body: bytes, *, status: int = 200) -> None:
        self.status = status
        self.headers = {"Content-Length": str(len(body))}
        self._body = body

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, limit: int = -1) -> bytes:
        return self._body if limit < 0 else self._body[:limit]


class _FakeOpen:
    def __init__(self, responses: list[object]) -> None:
        self.responses = deque(responses)
        self.requests: list[Request] = []
        self.timeouts: list[float] = []

    def __call__(self, request: Request, *, timeout: float) -> object:
        self.requests.append(request)
        self.timeouts.append(timeout)
        response = self.responses.popleft()
        if isinstance(response, BaseException):
            raise response
        return response


class _FailingProvider:
    name = "groq"

    def __init__(self, error: str) -> None:
        self.error = error
        self.calls = 0

    async def generate(self, request: LLMRequest) -> LLMResponse:
        del request
        self.calls += 1
        raise ModelProviderError(self.error)


class _RecordingProvider:
    def __init__(self, name: str, text: str) -> None:
        self.name = name
        self.text = text
        self.calls: list[LLMRequest] = []

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        return LLMResponse(request.request_id, self.text, request.model, "stop", provider=self.name)


@dataclass
class _Repository:
    events: list[object]

    def append_event(self, event: object) -> None:
        self.events.append(event)


class HybridRoutingTests(unittest.TestCase):
    def test_groq_probe_helper_keeps_secret_process_only_and_cleans_up(self) -> None:
        helper = (Path(__file__).parents[1] / "scripts" / "invoke_cloud_provider_probe.ps1").read_text(encoding="utf-8")

        self.assertIn("SecureStringToBSTR", helper)
        self.assertIn("SetEnvironmentVariable($environmentName, $plain, 'Process')", helper)
        self.assertIn("& python -m jarvis --model-provider-probe $Provider", helper)
        self.assertIn("SetEnvironmentVariable($environmentName, $null, 'Process')", helper)
        self.assertNotIn("'User'", helper)
        self.assertNotIn("'Machine'", helper)

    def test_exact_hybrid_model_contract_is_preserved(self) -> None:
        config = JarvisConfig(environment="test", model_provider="hybrid")
        self.assertEqual(config.local_model, "Qwen3.5-4B-Heretic")
        self.assertEqual(config.groq_model, "openai/gpt-oss-120b")
        self.assertEqual(config.gemini_model, "gemini-3.5-flash")

    def test_direct_openai_provider_is_rejected_and_legacy_env_is_not_consumed(self) -> None:
        with patch.dict(os.environ, {"JARVIS_MODEL_PROVIDER": "openai"}, clear=False):
            with self.assertRaisesRegex(ValueError, "JARVIS_MODEL_PROVIDER must be"):
                JarvisConfig.from_env()
        self.assertFalse(hasattr(JarvisConfig(), "openai_enabled"))

    def test_hybrid_environment_defaults_to_llama_loopback_not_ollama(self) -> None:
        with patch.dict(os.environ, {"JARVIS_MODEL_PROVIDER": "hybrid"}, clear=True):
            config = JarvisConfig.from_env()

        self.assertEqual(config.model_loopback_endpoint, "http://127.0.0.1:18765")

    def test_environment_rejects_non_heretic_local_model_identity(self) -> None:
        with patch.dict(os.environ, {
            "JARVIS_MODEL_PROVIDER": "hybrid",
            "JARVIS_LOCAL_MODEL": "Qwen3.5-4B",
        }, clear=True):
            with self.assertRaisesRegex(ValueError, "JARVIS_LOCAL_MODEL must be Qwen3.5-4B-Heretic"):
                JarvisConfig.from_env()

    def test_direct_llama_profile_rejects_a_non_heretic_fallback_alias(self) -> None:
        with self.assertRaisesRegex(ValueError, "local_model_identity_mismatch"):
            ModelGateway(JarvisConfig(
                environment="test",
                model_provider="llama_cpp",
                fallback_model="Qwen3.5-4B",
            ))

    def test_environment_rejects_non_required_cloud_model_ids(self) -> None:
        for variable, expected in (
            ("JARVIS_GROQ_MODEL", "JARVIS_GROQ_MODEL must be openai/gpt-oss-120b"),
            ("JARVIS_GEMINI_MODEL", "JARVIS_GEMINI_MODEL must be gemini-3.5-flash"),
        ):
            with self.subTest(variable=variable):
                with patch.dict(os.environ, {"JARVIS_MODEL_PROVIDER": "hybrid", variable: "wrong-model"}, clear=True):
                    with self.assertRaisesRegex(ValueError, expected):
                        JarvisConfig.from_env()

    def test_direct_hybrid_config_rejects_non_required_cloud_model_ids(self) -> None:
        with self.assertRaisesRegex(ValueError, "hybrid_cloud_model_identity_mismatch"):
            ModelGateway(JarvisConfig(environment="test", model_provider="hybrid", groq_model="wrong-model"))

    def test_capability_router_is_deterministic_and_does_not_call_a_model(self) -> None:
        router = CapabilityRouter()
        simple = router.decide(LLMRequest("1", (LLMMessage(LLMRole.USER, "open calculator"),)), ModelRoute.TOOL_ORCHESTRATION)
        complex_request = LLMRequest("2", (LLMMessage(LLMRole.USER, "plan and implement a coding workflow"),), tools=({"type": "function"},))
        complex_decision = router.decide(complex_request, ModelRoute.TOOL_ORCHESTRATION)
        visual = router.decide(
            LLMRequest("3", (LLMMessage(LLMRole.USER, "what is in this image", (LLMInputMedia("image/png", b"png"),)),)),
            ModelRoute.VISION,
        )
        self.assertEqual(simple.providers, ("local", "groq", "gemini"))
        self.assertEqual(complex_decision.providers, ("groq", "gemini", "local"))
        self.assertEqual(visual.providers, ("gemini",))

    def test_large_context_precedes_reasoning_route(self) -> None:
        request = LLMRequest("large", (
            LLMMessage(LLMRole.USER, "context " * 3_000),
            LLMMessage(LLMRole.USER, "recent context"),
            LLMMessage(LLMRole.ASSISTANT, "recent answer"),
            LLMMessage(LLMRole.USER, "reason about the result"),
        ))

        decision = CapabilityRouter().decide(request, ModelRoute.GENERAL_REASONING)

        self.assertEqual(decision.providers, ("gemini", "groq", "local"))
        self.assertEqual(decision.reason, "large_context")

    def test_architecture_snapshot_exposes_routes_without_exposing_keys(self) -> None:
        gateway = ModelGateway(JarvisConfig(environment="test", model_provider="hybrid"), {
            "local": _RecordingProvider("local", "local"),
            "groq": GroqProvider(api_key="groq-secret", enabled=True),
            "gemini": GeminiProvider(api_key="gemini-secret", enabled=True),
        })

        snapshot = gateway.architecture_snapshot()

        assert snapshot["routes"]["simple_fast_offline"]["model"] == "Qwen3.5-4B-Heretic"
        assert snapshot["routes"]["complex_reasoning_tools"]["model"] == "openai/gpt-oss-120b"
        assert snapshot["routes"]["vision_multimodal_large_context"]["model"] == "gemini-3.5-flash"
        blob = json.dumps(snapshot)
        self.assertNotIn("groq-secret", blob)
        self.assertNotIn("gemini-secret", blob)

    def test_health_projects_truthful_integration_and_worker_states(self) -> None:
        async def exercise() -> dict[str, object]:
            runtime = create_runtime(JarvisConfig(environment="test", model_provider="hybrid"))
            await runtime.start()
            try:
                return await CoreApplication(runtime).health()
            finally:
                await runtime.shutdown()

        health = asyncio.run(exercise())
        cards = {item["name"]: item for item in health["integrations"]}
        self.assertIn("Brave", cards)
        self.assertIn("Codex", cards)
        self.assertEqual(cards["AntiGravity via Codex"]["status"], "SERVICE_BLOCKED")
        self.assertEqual(cards["Groq"]["status"], "NOT_CONFIGURED")
        self.assertEqual(cards["Gemini"]["status"], "NOT_CONFIGURED")
        self.assertEqual(cards["Local Model"]["model"], "Qwen3.5-4B-Heretic")
        self.assertNotIn("api_key", json.dumps(health, default=str).casefold())


class CloudProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_groq_chat_payload_and_tool_call_normalization(self) -> None:
        fake = _FakeOpen([_Response(json.dumps({
            "model": "openai/gpt-oss-120b",
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "Ready",
                    "tool_calls": [{"id": "call-1", "function": {"name": "status.read", "arguments": "{}"}}],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 12, "completion_tokens": 5},
        }).encode())])
        provider = GroqProvider(api_key="groq-secret", enabled=True, urlopen=fake)
        response = await provider.generate(LLMRequest(
            "groq-1",
            (LLMMessage(LLMRole.SYSTEM, "system"), LLMMessage(LLMRole.USER, "status")),
            tools=({"type": "function", "function": {"name": "status.read", "parameters": {"type": "object"}}},),
            timeout_seconds=7,
        ))
        payload = json.loads(fake.requests[0].data.decode("utf-8"))
        self.assertEqual(payload["model"], "openai/gpt-oss-120b")
        self.assertEqual(payload["reasoning_effort"], "low")
        self.assertEqual(response.provider, "groq")
        self.assertEqual(response.finish_reason, "tool_calls")
        self.assertEqual(response.tool_calls[0]["function"]["name"], "status.read")
        self.assertEqual(dict(response.usage), {"prompt_tokens": 12, "output_tokens": 5})
        self.assertEqual(fake.timeouts, [7.0])

    async def test_groq_rate_limit_is_normalized_without_secret(self) -> None:
        fake = _FakeOpen([urllib.error.HTTPError(
            "https://api.groq.com/openai/v1/chat/completions", 429, "rate", {}, None,
        )])
        provider = GroqProvider(api_key="groq-secret", enabled=True, urlopen=fake)
        with self.assertRaisesRegex(ModelProviderError, "groq_http_429_rate_limit_or_quota") as raised:
            await provider.generate(LLMRequest("r", (LLMMessage(LLMRole.USER, "x"),)))
        self.assertNotIn("groq-secret", str(raised.exception))

    async def test_groq_health_uses_working_model_catalog_and_exact_required_id(self) -> None:
        fake = _FakeOpen([_Response(json.dumps({
            "object": "list",
            "data": [{"id": "openai/gpt-oss-120b", "active": True}],
        }).encode())])
        provider = GroqProvider(api_key="groq-secret", enabled=True, urlopen=fake)

        health = await provider.health("openai/gpt-oss-120b")

        self.assertTrue(health.available)
        self.assertEqual(health.provider, "groq")
        self.assertEqual(health.model, "openai/gpt-oss-120b")
        self.assertEqual(health.reason, "groq_ready")
        self.assertEqual(fake.requests[0].full_url, "https://api.groq.com/openai/v1/models")
        self.assertNotIn("/models/", fake.requests[0].full_url)

    async def test_groq_runtime_trace_matches_catalog_and_generation_contract(self) -> None:
        fake = _FakeOpen([
            _Response(json.dumps({
                "object": "list",
                "data": [{"id": "openai/gpt-oss-120b", "active": True}],
            }).encode()),
            _Response(json.dumps({
                "id": "chatcmpl-probe",
                "model": "openai/gpt-oss-120b",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "READY"},
                    "finish_reason": "stop",
                }],
            }).encode()),
        ])
        trace_key = "gsk_synthetic_trace_key_123456"
        provider = GroqProvider(api_key=trace_key, enabled=True, urlopen=fake)

        health = await provider.health("openai/gpt-oss-120b")
        await provider.generate(LLMRequest(
            "groq-trace",
            (LLMMessage(LLMRole.USER, "Reply READY."),),
            model="openai/gpt-oss-120b",
            max_output_tokens=64,
        ))

        self.assertTrue(health.available)
        trace = provider.request_trace()
        self.assertEqual([item["phase"] for item in trace], ["catalog", "generation"])
        self.assertEqual(trace[0]["method"], "GET")
        self.assertEqual(trace[0]["url"], "https://api.groq.com/openai/v1/models")
        self.assertEqual(trace[1]["method"], "POST")
        self.assertEqual(trace[1]["url"], "https://api.groq.com/openai/v1/chat/completions")
        for item in trace:
            self.assertTrue(item["authorization_present"])
            self.assertEqual(item["accept_header"], "application/json")
            self.assertEqual(item["user_agent"], "JARVIS/1.0")
            self.assertFalse(item["user_agent"].startswith("Python-urllib"))
            self.assertTrue(item["prefix_valid"])
            self.assertEqual(item["key_length"], len(trace_key))
        for request in fake.requests:
            self.assertEqual(request.get_header("User-agent"), "JARVIS/1.0")
            self.assertFalse(request.get_header("User-agent").startswith("Python-urllib"))
            self.assertTrue(request.get_header("Authorization"))
            self.assertEqual(request.get_header("Accept"), "application/json")
        trace_blob = json.dumps(trace)
        self.assertNotIn(trace_key, trace_blob)
        self.assertNotIn("Bearer", trace_blob)
        self.assertFalse(any("/models/" in request.full_url for request in fake.requests))

    async def test_groq_cloudflare_1010_summary_is_bounded_and_secret_safe(self) -> None:
        body = (
            b"<!DOCTYPE html><html><title>Attention Required</title>"
            b"<p>Error 1010: browser_signature_banned</p>"
            b"<p>Bearer groq-secret must never be retained</p></html>"
        )
        provider = GroqProvider(
            api_key="groq-secret",
            enabled=True,
            urlopen=_FakeOpen([_Response(body, status=403)]),
        )

        health = await provider.health("openai/gpt-oss-120b")

        self.assertFalse(health.available)
        diagnostic = provider.last_http_diagnostic
        self.assertIsNotNone(diagnostic)
        assert diagnostic is not None
        summary = diagnostic.as_dict()
        self.assertEqual(summary["http_status"], 403)
        self.assertTrue(summary["body_contains_1010"])
        self.assertTrue(summary["body_contains_browser_signature_banned"])
        self.assertEqual(summary["response_format"], "cloudflare_html_or_text")
        self.assertNotIn("groq-secret", json.dumps(summary))
        self.assertNotIn("Attention Required", json.dumps(summary))

    async def test_groq_success_clears_stale_http_diagnostic(self) -> None:
        fake = _FakeOpen([
            _Response(b"<html>Error 1010 browser_signature_banned</html>", status=403),
            _Response(json.dumps({
                "object": "list",
                "data": [{"id": "openai/gpt-oss-120b", "active": True}],
            }).encode()),
        ])
        provider = GroqProvider(api_key="groq-secret", enabled=True, urlopen=fake)

        first = await provider.health("openai/gpt-oss-120b")
        second = await provider.health("openai/gpt-oss-120b")

        self.assertFalse(first.available)
        self.assertTrue(second.available)
        self.assertIsNone(provider.last_http_diagnostic)

    async def test_groq_credential_status_is_safe_and_provider_reads_process_environment(self) -> None:
        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_synthetic_process_key_123456"}, clear=True):
            provider = GroqProvider(enabled=True, urlopen=_FakeOpen([]))

        self.assertEqual(provider.credential_status(), {
            "present": True,
            "length": len("gsk_synthetic_process_key_123456"),
            "prefix_valid": True,
        })
        self.assertNotIn("synthetic", json.dumps(provider.credential_status()))

    async def test_groq_http_diagnostics_are_structured_without_error_message_or_secret(self) -> None:
        body = json.dumps({
            "error": {
                "type": "authentication_error",
                "code": "invalid_api_key",
                "message": "Authorization header and groq-secret must never be emitted",
            },
        }).encode()
        provider = GroqProvider(api_key="groq-secret", enabled=True, urlopen=_FakeOpen([_Response(body, status=401)]))

        health = await provider.health("openai/gpt-oss-120b")

        self.assertFalse(health.available)
        self.assertEqual(health.reason, "groq_http_401_authentication_failure:authentication_error:invalid_api_key")
        self.assertNotIn("groq-secret", health.reason)
        self.assertNotIn("Authorization", health.reason)

    async def test_groq_generate_exposes_only_sanitized_http_diagnostic(self) -> None:
        body = json.dumps({
            "error": {
                "type": "rate_limit_error",
                "code": "rate_limit_exceeded",
                "message": "request body and groq-secret must never be emitted",
            },
        }).encode()
        provider = GroqProvider(api_key="groq-secret", enabled=True, urlopen=_FakeOpen([_Response(body, status=429)]))

        with self.assertRaisesRegex(ModelProviderError, "^groq_http_429_rate_limit_or_quota:rate_limit_error:rate_limit_exceeded$") as raised:
            await provider.generate(LLMRequest("groq-http", (LLMMessage(LLMRole.USER, "hello"),)))

        self.assertIsInstance(raised.exception, GroqHTTPError)
        diagnostic = getattr(raised.exception, "diagnostic")
        self.assertEqual(diagnostic.http_status, 429)
        self.assertEqual(diagnostic.classification, "rate_limit_or_quota")
        self.assertNotIn("groq-secret", str(raised.exception))
        self.assertNotIn("request body", str(raised.exception))

    async def test_gemini_multimodal_payload_and_function_call_normalization(self) -> None:
        fake = _FakeOpen([_Response(json.dumps({
            "candidates": [{
                "content": {"parts": [
                    {"thought": True, "thoughtSignature": "do-not-expose"},
                    {"text": "I see it."},
                    {"functionCall": {"name": "status.read", "args": {}}},
                ]},
                "finishReason": "STOP",
            }],
            "usageMetadata": {"promptTokenCount": 15, "candidatesTokenCount": 4},
        }).encode())])
        provider = GeminiProvider(api_key="gemini-secret", enabled=True, urlopen=fake)
        response = await provider.generate(LLMRequest(
            "gemini-1",
            (LLMMessage(LLMRole.SYSTEM, "Be concise."), LLMMessage(
                LLMRole.USER,
                "Read this screenshot.",
                (LLMInputMedia("image/png", b"png-bytes"),),
            )),
            tools=({"type": "function", "function": {"name": "status.read", "description": "status", "parameters": {"type": "object"}}},),
        ))
        payload = json.loads(fake.requests[0].data.decode("utf-8"))
        self.assertEqual(payload["systemInstruction"]["parts"][0]["text"], "Be concise.")
        self.assertNotIn("system_instruction", payload)
        self.assertEqual(payload["contents"][0]["parts"][1]["inlineData"]["mimeType"], "image/png")
        self.assertEqual(payload["tools"][0]["functionDeclarations"][0]["name"], "status.read")
        self.assertEqual(response.provider, "gemini")
        self.assertEqual(response.text, "I see it.")
        self.assertEqual(response.finish_reason, "tool_calls")
        self.assertEqual(response.tool_calls[0]["function"]["arguments"], {})
        self.assertNotIn("do-not-expose", json.dumps(provider.last_response_summary))

    async def test_gemini_probe_thinking_config_uses_realistic_budget_without_global_override(self) -> None:
        fake = _FakeOpen([_Response(json.dumps({
            "candidates": [{"content": {"parts": [{"text": "READY"}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 1},
        }).encode())])
        provider = GeminiProvider(api_key="gemini-secret", enabled=True, urlopen=fake)
        await provider.generate(LLMRequest(
            "gemini-thinking-probe",
            (LLMMessage(LLMRole.USER, "Reply with one short word."),),
            max_output_tokens=256,
            provider_options={"gemini_thinking_level": "minimal"},
        ))
        payload = json.loads(fake.requests[0].data.decode("utf-8"))
        self.assertEqual(payload["generationConfig"]["maxOutputTokens"], 256)
        self.assertEqual(payload["generationConfig"]["thinkingConfig"], {"thinkingLevel": "minimal"})

    async def test_gemini_max_tokens_without_visible_content_is_output_truncated(self) -> None:
        fake = _FakeOpen([_Response(json.dumps({
            "candidates": [{
                "content": {"parts": [{"thought": True, "thoughtSignature": "opaque"}]},
                "finishReason": "MAX_TOKENS",
            }],
            "usageMetadata": {
                "promptTokenCount": 8,
                "candidatesTokenCount": 0,
                "thoughtsTokenCount": 24,
                "totalTokenCount": 32,
            },
        }).encode())])
        provider = GeminiProvider(api_key="gemini-secret", enabled=True, urlopen=fake)
        with self.assertRaisesRegex(ModelProviderError, "^gemini_output_truncated$") as raised:
            await provider.generate(LLMRequest("gemini-truncated", (LLMMessage(LLMRole.USER, "hello"),)))
        summary = getattr(raised.exception, "summary")
        self.assertEqual(summary["candidate_count"], 1)
        self.assertEqual(summary["finish_reason"], "MAX_TOKENS")
        self.assertEqual(summary["parts_count"], 1)
        self.assertEqual(summary["usageMetadata"]["thoughtsTokenCount"], 24)
        self.assertNotIn("opaque", json.dumps(summary))

    async def test_gemini_safety_candidate_without_visible_content_is_content_blocked(self) -> None:
        fake = _FakeOpen([_Response(json.dumps({
            "candidates": [{"content": {"parts": []}, "finishReason": "SAFETY"}],
            "promptFeedback": {"blockReason": "SAFETY"},
        }).encode())])
        provider = GeminiProvider(api_key="gemini-secret", enabled=True, urlopen=fake)
        with self.assertRaisesRegex(ModelProviderError, "^gemini_content_blocked$"):
            await provider.generate(LLMRequest("gemini-safety", (LLMMessage(LLMRole.USER, "hello"),)))

    async def test_gemini_structural_summary_is_bounded_and_secret_safe(self) -> None:
        fake = _FakeOpen([_Response(json.dumps({
            "candidates": [{
                "content": {"parts": [
                    {"thought": True, "thoughtSignature": "private-signature", "text": "visible"},
                ]},
                "finishReason": "STOP",
            }],
            "usageMetadata": {
                "promptTokenCount": 11,
                "candidatesTokenCount": 2,
                "thoughtsTokenCount": 5,
                "totalTokenCount": 18,
            },
            "promptFeedback": {"blockReason": ""},
            "privateResponseText": "must-not-be-captured",
        }).encode())])
        provider = GeminiProvider(api_key="gemini-secret", enabled=True, urlopen=fake)
        response = await provider.generate(LLMRequest("gemini-summary", (LLMMessage(LLMRole.USER, "hello"),)))
        self.assertEqual(response.text, "visible")
        summary = provider.last_response_summary
        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary["http_status"], 200)
        self.assertIn("candidates", summary["top_level_fields"])
        self.assertEqual(summary["candidate_count"], 1)
        self.assertTrue(summary["content_exists"])
        self.assertEqual(summary["parts_count"], 1)
        self.assertEqual(summary["part_field_names"], [["text", "thought", "thoughtSignature"]])
        self.assertEqual(summary["usageMetadata"]["thoughtsTokenCount"], 5)
        self.assertEqual(summary["usageMetadata"]["totalTokenCount"], 18)
        self.assertNotIn("private-signature", json.dumps(summary))
        self.assertNotIn("must-not-be-captured", json.dumps(summary))

    async def test_gemini_http_statuses_are_classified_without_emitting_error_body(self) -> None:
        cases = (
            (400, "INVALID_ARGUMENT", "gemini_http_400_invalid_request"),
            (400, "FAILED_PRECONDITION", "gemini_http_400_failed_prerequisite"),
            (401, "UNAUTHENTICATED", "gemini_http_401_authentication_failure"),
            (403, "PERMISSION_DENIED", "gemini_http_403_permission_failure"),
            (404, "NOT_FOUND", "gemini_http_404_model_or_resource_unavailable"),
            (429, "RESOURCE_EXHAUSTED", "gemini_http_429_rate_limit_or_quota"),
            (503, "UNAVAILABLE", "gemini_http_5xx_service_unavailable"),
        )
        for http_status, google_status, expected_reason in cases:
            with self.subTest(http_status=http_status, google_status=google_status):
                body = json.dumps({
                    "error": {
                        "code": http_status,
                        "status": google_status,
                        "message": "request-body and gemini-secret must never be emitted",
                    },
                }).encode("utf-8")
                provider = GeminiProvider(api_key="gemini-secret", enabled=True, urlopen=_FakeOpen([_Response(body, status=http_status)]))

                health = await provider.health()

                self.assertFalse(health.available)
                self.assertEqual(health.reason, f"{expected_reason}:{google_status}")
                self.assertNotIn("gemini-secret", health.reason)
                self.assertNotIn("request-body", health.reason)

    async def test_gemini_generate_raises_sanitized_structured_http_error(self) -> None:
        body = json.dumps({
            "error": {
                "code": 400,
                "status": "INVALID_ARGUMENT",
                "message": "request-body and gemini-secret must never be emitted",
            },
        }).encode("utf-8")
        provider = GeminiProvider(
            api_key="gemini-secret",
            enabled=True,
            urlopen=_FakeOpen([_Response(body, status=400)]),
        )

        with self.assertRaisesRegex(ModelProviderError, r"^gemini_http_400_invalid_request:INVALID_ARGUMENT$") as raised:
            await provider.generate(LLMRequest("gemini-http", (LLMMessage(LLMRole.USER, "hello"),)))

        diagnostic = getattr(raised.exception, "diagnostic")
        self.assertEqual(diagnostic.http_status, 400)
        self.assertEqual(diagnostic.google_code, 400)
        self.assertEqual(diagnostic.google_status, "INVALID_ARGUMENT")
        self.assertNotIn("gemini-secret", str(raised.exception))
        self.assertNotIn("request-body", str(raised.exception))

    async def test_gemini_acceptance_probe_is_metadata_then_text_then_normal_png(self) -> None:
        from jarvis.__main__ import _run_provider_probe

        class _ProbeModels:
            def __init__(self) -> None:
                self.requests: list[LLMRequest] = []
                self.gateway_calls = 0

            def selection(self, route: ModelRoute) -> SimpleNamespace:
                return SimpleNamespace(model="gemini-3.5-flash")

            def architecture_snapshot(self) -> dict[str, object]:
                return {"gemini": {"state": "configured_unprobed", "reason": "gemini_health_not_probed"}}

            async def health(self, route: ModelRoute) -> ModelHealth:
                self.health_route = route
                return ModelHealth("gemini", True, datetime.now(UTC), "gemini_ready", "gemini-3.5-flash")

            async def generate(self, request: LLMRequest, route: ModelRoute) -> LLMResponse:
                self.gateway_calls += 1
                raise AssertionError("Gemini acceptance must not use hybrid fallback")

            async def generate_direct(self, provider_name: str, request: LLMRequest, route: ModelRoute) -> LLMResponse:
                self.assert_direct_provider = provider_name
                self.requests.append(request)
                return LLMResponse(request.request_id, "ready", request.model, "STOP", provider="gemini")

        models = _ProbeModels()
        result = await _run_provider_probe(SimpleNamespace(models=models), "gemini")

        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["model_access"]["result"], "PASS")
        self.assertEqual(result["text_generation"]["result"], "PASS")
        self.assertEqual(result["vision_generation"]["result"], "PASS")
        self.assertEqual(result["actual_provider"], "gemini")
        self.assertEqual(result["actual_model"], "gemini-3.5-flash")
        self.assertFalse(result["fallback_used"])
        self.assertEqual(models.assert_direct_provider, "gemini")
        self.assertEqual(models.gateway_calls, 0)
        self.assertEqual(models.health_route, ModelRoute.VISION)
        self.assertEqual(len(models.requests), 2)
        self.assertEqual([request.max_output_tokens for request in models.requests], [256, 256])
        self.assertEqual(
            [request.provider_options for request in models.requests],
            [{"gemini_thinking_level": "minimal"}, {"gemini_thinking_level": "minimal"}],
        )
        self.assertFalse(models.requests[0].messages[0].media)
        media = models.requests[1].messages[0].media
        self.assertEqual(media[0].mime_type, "image/png")
        self.assertGreater(len(media[0].data), 100)
        self.assertEqual(media[0].data[:8], b"\x89PNG\r\n\x1a\n")

    async def test_gemini_acceptance_probe_exposes_only_sanitized_http_diagnostics(self) -> None:
        from jarvis.__main__ import _run_provider_probe

        class _ProbeModels:
            def selection(self, route: ModelRoute) -> SimpleNamespace:
                return SimpleNamespace(model="gemini-3.5-flash")

            def architecture_snapshot(self) -> dict[str, object]:
                return {"gemini": {"state": "configured_unprobed", "reason": "gemini_health_not_probed"}}

            async def health(self, route: ModelRoute) -> ModelHealth:
                return ModelHealth("gemini", True, datetime.now(UTC), "gemini_ready", "gemini-3.5-flash")

            async def generate(self, request: LLMRequest, route: ModelRoute) -> LLMResponse:
                raise AssertionError("Gemini acceptance must not use hybrid fallback")

            async def generate_direct(self, provider_name: str, request: LLMRequest, route: ModelRoute) -> LLMResponse:
                raise GeminiHTTPError(GeminiHTTPDiagnostic(
                    400,
                    400,
                    "INVALID_ARGUMENT",
                    "invalid_request",
                    "gemini_http_400_invalid_request:INVALID_ARGUMENT",
                ))

        result = await _run_provider_probe(SimpleNamespace(models=_ProbeModels()), "gemini")
        blob = json.dumps(result)

        self.assertEqual(result["result"], "FAIL")
        self.assertEqual(result["text_generation"]["error"], "gemini_http_400_invalid_request:INVALID_ARGUMENT")
        self.assertIn("diagnostic", result["text_generation"])
        self.assertNotIn("api_key", blob.casefold())
        self.assertNotIn("request-body", blob)

    async def test_gemini_acceptance_probe_rejects_fallback_without_calling_gateway_fallback(self) -> None:
        from jarvis.__main__ import _run_provider_probe

        class _ProbeModels:
            def __init__(self) -> None:
                self.direct_calls = 0
                self.gateway_calls = 0

            def selection(self, route: ModelRoute) -> SimpleNamespace:
                return SimpleNamespace(model="gemini-3.5-flash")

            def architecture_snapshot(self) -> dict[str, object]:
                return {"gemini": {"state": "configured_unprobed", "reason": "gemini_health_not_probed"}}

            async def health(self, route: ModelRoute) -> ModelHealth:
                return ModelHealth("gemini", True, datetime.now(UTC), "gemini_ready", "gemini-3.5-flash")

            async def generate(self, request: LLMRequest, route: ModelRoute) -> LLMResponse:
                self.gateway_calls += 1
                raise AssertionError("hybrid fallback must not be reachable")

            async def generate_direct(self, provider_name: str, request: LLMRequest, route: ModelRoute) -> LLMResponse:
                self.direct_calls += 1
                return LLMResponse(request.request_id, "local fallback", "Qwen3.5-4B-Heretic", "stop", provider="llama_cpp")

        models = _ProbeModels()
        result = await _run_provider_probe(SimpleNamespace(models=models), "gemini")

        self.assertEqual(result["result"], "FAIL")
        self.assertEqual(result["text_generation"]["error"], "provider_model_or_content_mismatch")
        self.assertTrue(result["text_generation"]["fallback_used"])
        self.assertEqual(models.direct_calls, 1)
        self.assertEqual(models.gateway_calls, 0)


class HybridGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_groq_acceptance_probe_checks_key_metadata_then_direct_generation(self) -> None:
        from jarvis.__main__ import _run_provider_probe

        class _ProbeModels:
            def __init__(self) -> None:
                self.direct_requests: list[LLMRequest] = []
                self.gateway_calls = 0

            def selection(self, route: ModelRoute) -> SimpleNamespace:
                return SimpleNamespace(model="openai/gpt-oss-120b")

            def architecture_snapshot(self) -> dict[str, object]:
                return {"groq": {"state": "configured_unprobed", "reason": "groq_health_not_probed"}}

            def provider_credential_status(self, provider_name: str) -> dict[str, object]:
                self.credential_provider = provider_name
                return {"present": True, "length": 31, "prefix_valid": True}

            def provider_request_trace(self, provider_name: str) -> list[dict[str, object]]:
                self.trace_provider = provider_name
                return [{
                    "phase": "catalog",
                    "url": "https://api.groq.com/openai/v1/models",
                    "method": "GET",
                    "authorization_present": True,
                    "accept_header": "application/json",
                    "user_agent": "JARVIS/1.0",
                    "content_type_present": False,
                    "key_length": 31,
                    "prefix_valid": True,
                    "timeout_seconds": 2.0,
                }]

            def provider_http_diagnostic(self, provider_name: str) -> dict[str, object]:
                self.diagnostic_provider = provider_name
                return {
                    "http_status": 403,
                    "classification": "permission_failure",
                    "error_type": None,
                    "error_code": None,
                    "reason": "groq_http_403_permission_failure:cloudflare_1010_browser_signature_banned",
                    "body_contains_1010": True,
                    "body_contains_browser_signature_banned": True,
                    "response_format": "cloudflare_html_or_text",
                }

            async def health(self, route: ModelRoute) -> ModelHealth:
                self.health_route = route
                return ModelHealth("groq", True, datetime.now(UTC), "groq_ready", "openai/gpt-oss-120b")

            async def generate(self, request: LLMRequest, route: ModelRoute) -> LLMResponse:
                self.gateway_calls += 1
                raise AssertionError("Groq acceptance must not use hybrid fallback")

            async def generate_direct(self, provider_name: str, request: LLMRequest, route: ModelRoute) -> LLMResponse:
                self.direct_requests.append(request)
                self.direct_provider = provider_name
                return LLMResponse(request.request_id, "Ready", request.model, "stop", provider="groq")

        models = _ProbeModels()
        result = await _run_provider_probe(SimpleNamespace(models=models), "groq")

        self.assertEqual(result["credential"]["present"], True)
        self.assertEqual(result["model_access"]["result"], "PASS")
        self.assertEqual(result["text_generation"]["result"], "PASS")
        self.assertEqual(result["actual_provider"], "groq")
        self.assertEqual(result["actual_model"], "openai/gpt-oss-120b")
        self.assertFalse(result["fallback_used"])
        self.assertEqual(models.credential_provider, "groq")
        self.assertEqual(models.health_route, ModelRoute.GENERAL_REASONING)
        self.assertEqual(models.direct_provider, "groq")
        self.assertEqual(models.gateway_calls, 0)
        self.assertEqual(len(models.direct_requests), 1)
        self.assertEqual(models.direct_requests[0].model, "openai/gpt-oss-120b")
        self.assertEqual(result["request_trace"][0]["url"], "https://api.groq.com/openai/v1/models")
        self.assertEqual(models.trace_provider, "groq")
        self.assertTrue(result["model_access"]["diagnostic"]["body_contains_1010"])
        self.assertEqual(result["model_access"]["diagnostic"]["response_format"], "cloudflare_html_or_text")
        self.assertEqual(models.diagnostic_provider, "groq")
        self.assertEqual(Path(result["source_identity"]["jarvis_package_file"]).name, "__init__.py")
        self.assertEqual(Path(result["source_identity"]["cloud_module_file"]).name, "cloud.py")
        self.assertEqual(Path(result["source_identity"]["probe_implementation_file"]).name, "__main__.py")

    async def test_groq_acceptance_probe_rejects_non_groq_response_without_fallback_acceptance(self) -> None:
        from jarvis.__main__ import _run_provider_probe

        class _ProbeModels:
            def selection(self, route: ModelRoute) -> SimpleNamespace:
                return SimpleNamespace(model="openai/gpt-oss-120b")

            def architecture_snapshot(self) -> dict[str, object]:
                return {"groq": {"state": "configured_unprobed", "reason": "groq_health_not_probed"}}

            def provider_credential_status(self, provider_name: str) -> dict[str, object]:
                return {"present": True, "length": 31, "prefix_valid": True}

            async def health(self, route: ModelRoute) -> ModelHealth:
                return ModelHealth("groq", True, datetime.now(UTC), "groq_ready", "openai/gpt-oss-120b")

            async def generate(self, request: LLMRequest, route: ModelRoute) -> LLMResponse:
                raise AssertionError("hybrid fallback must not be reachable")

            async def generate_direct(self, provider_name: str, request: LLMRequest, route: ModelRoute) -> LLMResponse:
                return LLMResponse(request.request_id, "local fallback", "Qwen3.5-4B-Heretic", "stop", provider="llama_cpp")

        result = await _run_provider_probe(SimpleNamespace(models=_ProbeModels()), "groq")

        self.assertEqual(result["result"], "FAIL")
        self.assertEqual(result["text_generation"]["result"], "FAIL")
        self.assertEqual(result["text_generation"]["error"], "provider_model_or_content_mismatch")
        self.assertTrue(result["text_generation"]["fallback_used"])

    async def test_provider_probe_stops_at_missing_key_without_a_provider_call(self) -> None:
        from jarvis.__main__ import _run_provider_probe

        class _ProbeModels:
            def __init__(self) -> None:
                self.calls = 0

            def selection(self, route: ModelRoute) -> SimpleNamespace:
                return SimpleNamespace(model="openai/gpt-oss-120b" if route is ModelRoute.GENERAL_REASONING else "gemini-3.5-flash")

            def architecture_snapshot(self) -> dict[str, object]:
                return {"groq": {"state": "missing_key", "reason": "groq_api_key_missing"}}

            async def generate(self, request: LLMRequest, route: ModelRoute) -> LLMResponse:
                self.calls += 1
                return LLMResponse(request.request_id, "unexpected", request.model, "stop", provider="groq")

        models = _ProbeModels()
        result = await _run_provider_probe(SimpleNamespace(models=models), "groq")

        self.assertEqual(result["result"], "OWNER_ACTION_REQUIRED")
        self.assertEqual(models.calls, 0)

    async def test_provider_probe_reports_actual_provider_and_model_without_fallback(self) -> None:
        from jarvis.__main__ import _run_provider_probe

        class _ProbeModels:
            def __init__(self) -> None:
                self.calls = 0

            def selection(self, route: ModelRoute) -> SimpleNamespace:
                return SimpleNamespace(model="openai/gpt-oss-120b")

            def architecture_snapshot(self) -> dict[str, object]:
                return {"groq": {"state": "configured_unprobed", "reason": "groq_health_not_probed"}}

            def provider_credential_status(self, provider_name: str) -> dict[str, object]:
                return {"present": True, "length": 31, "prefix_valid": True}

            async def health(self, route: ModelRoute) -> ModelHealth:
                return ModelHealth("groq", True, datetime.now(UTC), "groq_ready", "openai/gpt-oss-120b")

            async def generate(self, request: LLMRequest, route: ModelRoute) -> LLMResponse:
                self.calls += 1
                return LLMResponse(request.request_id, "bounded cloud answer", request.model, "stop", provider="groq")

            async def generate_direct(self, provider_name: str, request: LLMRequest, route: ModelRoute) -> LLMResponse:
                self.calls += 1
                return LLMResponse(request.request_id, "bounded cloud answer", request.model, "stop", provider="groq")

        models = _ProbeModels()
        result = await _run_provider_probe(SimpleNamespace(models=models), "groq")

        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["actual_provider"], "groq")
        self.assertEqual(result["actual_model"], "openai/gpt-oss-120b")
        self.assertEqual(result["fallback_used"], False)
        self.assertEqual(models.calls, 1)

    async def test_direct_provider_generation_calls_only_the_requested_gemini_provider(self) -> None:
        local = _RecordingProvider("local", "local")
        groq = _RecordingProvider("groq", "groq")
        gemini = _RecordingProvider("gemini", "gemini")
        gateway = ModelGateway(
            JarvisConfig(environment="test", model_provider="hybrid"),
            {"local": local, "groq": groq, "gemini": gemini},
        )

        response = await gateway.generate_direct(
            "gemini",
            LLMRequest(
                "direct-gemini",
                (LLMMessage(LLMRole.USER, "describe"),),
                provider_options={"gemini_thinking_level": "minimal"},
            ),
            ModelRoute.VISION,
        )

        self.assertEqual(response.provider, "gemini")
        self.assertEqual(len(gemini.calls), 1)
        self.assertEqual(gemini.calls[0].model, "gemini-3.5-flash")
        self.assertEqual(gemini.calls[0].provider_options, {"gemini_thinking_level": "minimal"})
        self.assertEqual(len(groq.calls), 0)
        self.assertEqual(len(local.calls), 0)

    async def test_hybrid_without_explicit_local_runtime_does_not_assume_ollama(self) -> None:
        gateway = ModelGateway(JarvisConfig(environment="test", model_provider="hybrid"))

        health = await gateway.health(ModelRoute.FAST_CONVERSATION)

        self.assertFalse(health.available)
        self.assertEqual(health.provider, "unavailable")
        self.assertEqual(health.model, "Qwen3.5-4B-Heretic")
        self.assertEqual(health.reason, "llama_cpp_runtime_not_configured")

    async def test_core_health_reports_the_local_route_as_local_model(self) -> None:
        runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:", model_provider="hybrid"))
        gateway = ModelGateway(
            runtime.config,
            {
                "local": MockModelProvider(),
                "groq": MockModelProvider(),
                "gemini": MockModelProvider(),
            },
        )
        runtime.models = gateway
        await runtime.start()
        try:
            health = await CoreApplication(runtime).health()
        finally:
            await runtime.shutdown()

        self.assertEqual(health["local_model"]["model_alias"], "Qwen3.5-4B-Heretic")

    async def test_local_probe_defaults_to_fast_local_route(self) -> None:
        gateway = ModelGateway(
            JarvisConfig(environment="test", model_provider="hybrid"),
            {
                "local": MockModelProvider(),
                "groq": MockModelProvider(),
                "gemini": MockModelProvider(),
            },
        )

        from jarvis.models.probes import LocalModelCapabilityProbe

        result = await LocalModelCapabilityProbe(gateway).run(exercise_generation=True)

        self.assertTrue(result.available)
        self.assertEqual(result.model, "Qwen3.5-4B-Heretic")

    async def test_simple_request_stays_local_and_records_selection(self) -> None:
        repository = _Repository([])
        local = _RecordingProvider("local", "local answer")
        groq = _RecordingProvider("groq", "cloud answer")
        gemini = _RecordingProvider("gemini", "vision answer")
        gateway = ModelGateway(
            JarvisConfig(environment="test", model_provider="hybrid"),
            {"local": local, "groq": groq, "gemini": gemini},
            repository=repository,
        )
        response = await gateway.generate(
            LLMRequest("simple", (LLMMessage(LLMRole.USER, "open calculator"),)),
            ModelRoute.TOOL_ORCHESTRATION,
        )
        self.assertEqual(response.provider, "local")
        self.assertEqual(len(local.calls), 1)
        self.assertEqual(len(groq.calls), 0)
        self.assertEqual(len(gemini.calls), 0)
        self.assertEqual(repository.events[0].event_type, "model.route.selected")
        self.assertEqual(repository.events[0].payload["reason"], "simple_command_capability")

    async def test_system_prompt_markers_do_not_promote_simple_user_request_to_cloud(self) -> None:
        local = _RecordingProvider("local", "local answer")
        groq = _RecordingProvider("groq", "cloud answer")
        gemini = _RecordingProvider("gemini", "vision answer")
        gateway = ModelGateway(
            JarvisConfig(environment="test", model_provider="hybrid"),
            {"local": local, "groq": groq, "gemini": gemini},
        )
        response = await gateway.generate(
            LLMRequest(
                "simple-system-marker",
                (
                    LLMMessage(LLMRole.SYSTEM, "Answer briefly and do not explain."),
                    LLMMessage(LLMRole.USER, "hello"),
                ),
            ),
            ModelRoute.FAST_CONVERSATION,
        )
        self.assertEqual(response.provider, "local")
        self.assertEqual(len(local.calls), 1)
        self.assertEqual(len(groq.calls), 0)
        self.assertEqual(len(gemini.calls), 0)

    async def test_groq_failure_tries_gemini_then_stops_on_success(self) -> None:
        repository = _Repository([])
        groq = _FailingProvider("groq_rate_limited")
        gemini = _RecordingProvider("gemini", "fallback answer")
        local = _RecordingProvider("local", "local answer")
        gateway = ModelGateway(
            JarvisConfig(environment="test", model_provider="hybrid"),
            {"local": local, "groq": groq, "gemini": gemini},
            repository=repository,
        )
        response = await gateway.generate(
            LLMRequest("complex", (LLMMessage(LLMRole.USER, "plan a complex workflow"),)),
            ModelRoute.GENERAL_REASONING,
        )
        self.assertEqual(response.provider, "gemini")
        self.assertEqual(groq.calls, 1)
        self.assertEqual(len(gemini.calls), 1)
        self.assertEqual(len(local.calls), 0)
        self.assertEqual([event.event_type for event in repository.events], ["model.route.selected", "model.route.fallback", "model.route.selected"])

    async def test_groq_and_gemini_failure_falls_back_to_local(self) -> None:
        groq = _FailingProvider("groq_unavailable")
        gemini = _FailingProvider("gemini_rate_limited")
        local = _RecordingProvider("local", "offline answer")
        gateway = ModelGateway(
            JarvisConfig(environment="test", model_provider="hybrid"),
            {"local": local, "groq": groq, "gemini": gemini},
        )

        response = await gateway.generate(
            LLMRequest("clouds-down", (LLMMessage(LLMRole.USER, "plan a bounded workflow"),)),
            ModelRoute.GENERAL_REASONING,
        )

        self.assertEqual(response.provider, "local")
        self.assertEqual(groq.calls, 1)
        self.assertEqual(gemini.calls, 1)
        self.assertEqual(len(local.calls), 1)

    async def test_local_unavailable_with_healthy_groq_stays_on_groq(self) -> None:
        groq = _RecordingProvider("groq", "cloud answer")
        gemini = _RecordingProvider("gemini", "unused vision answer")
        local = _FailingProvider("local_unavailable")
        gateway = ModelGateway(
            JarvisConfig(environment="test", model_provider="hybrid"),
            {"local": local, "groq": groq, "gemini": gemini},
        )

        response = await gateway.generate(
            LLMRequest("local-down", (LLMMessage(LLMRole.USER, "reason about this plan"),)),
            ModelRoute.GENERAL_REASONING,
        )

        self.assertEqual(response.provider, "groq")
        self.assertEqual(len(groq.calls), 1)
        self.assertEqual(len(gemini.calls), 0)
        self.assertEqual(local.calls, 0)

    async def test_all_providers_unavailable_is_truthful(self) -> None:
        groq = _FailingProvider("groq_unavailable")
        gemini = _FailingProvider("gemini_unavailable")
        local = _FailingProvider("local_unavailable")
        gateway = ModelGateway(
            JarvisConfig(environment="test", model_provider="hybrid"),
            {"local": local, "groq": groq, "gemini": gemini},
        )

        with self.assertRaisesRegex(ModelProviderError, "local_unavailable"):
            await gateway.generate(
                LLMRequest("all-down", (LLMMessage(LLMRole.USER, "reason about this plan"),)),
                ModelRoute.GENERAL_REASONING,
            )

        self.assertEqual(groq.calls, 1)
        self.assertEqual(gemini.calls, 1)
        self.assertEqual(local.calls, 1)

    async def test_media_never_falls_back_to_text_only_provider(self) -> None:
        gemini = _FailingProvider("gemini_unavailable")
        gateway = ModelGateway(
            JarvisConfig(environment="test", model_provider="hybrid"),
            {"local": MockModelProvider(), "groq": MockModelProvider(), "gemini": gemini},
        )
        with self.assertRaisesRegex(ModelProviderError, "gemini_unavailable"):
            await gateway.generate(
                LLMRequest("image", (LLMMessage(LLMRole.USER, "describe", (LLMInputMedia("image/png", b"x"),)),)),
                ModelRoute.VISION,
            )


if __name__ == "__main__":
    unittest.main()
