from __future__ import annotations

import asyncio
import json
import os
import unittest
import urllib.error
from collections import deque
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch
from urllib.request import Request

from jarvis.config import JarvisConfig
from jarvis.contracts import LLMInputMedia, LLMMessage, LLMRequest, LLMResponse, LLMRole
from jarvis.models.cloud import GeminiProvider, GroqProvider
from jarvis.models.gateway import ModelGateway
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
        with self.assertRaisesRegex(ModelProviderError, "groq_rate_limited") as raised:
            await provider.generate(LLMRequest("r", (LLMMessage(LLMRole.USER, "x"),)))
        self.assertNotIn("groq-secret", str(raised.exception))

    async def test_gemini_multimodal_payload_and_function_call_normalization(self) -> None:
        fake = _FakeOpen([_Response(json.dumps({
            "candidates": [{
                "content": {"parts": [
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
        self.assertEqual(payload["system_instruction"]["parts"][0]["text"], "Be concise.")
        self.assertEqual(payload["contents"][0]["parts"][1]["inline_data"]["mime_type"], "image/png")
        self.assertEqual(payload["tools"][0]["function_declarations"][0]["name"], "status.read")
        self.assertEqual(response.provider, "gemini")
        self.assertEqual(response.text, "I see it.")
        self.assertEqual(response.finish_reason, "tool_calls")
        self.assertEqual(response.tool_calls[0]["function"]["arguments"], {})


class HybridGatewayTests(unittest.IsolatedAsyncioTestCase):
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
