from __future__ import annotations

import asyncio
import json
import os
import unittest
import urllib.error
from collections import deque
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from urllib.request import Request

from jarvis.api.core import CoreApplication
from jarvis.bootstrap import create_runtime
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

            async def generate(self, request: LLMRequest, route: ModelRoute) -> LLMResponse:
                self.calls += 1
                return LLMResponse(request.request_id, "bounded cloud answer", request.model, "stop", provider="groq")

        models = _ProbeModels()
        result = await _run_provider_probe(SimpleNamespace(models=models), "groq")

        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["actual_provider"], "groq")
        self.assertEqual(result["actual_model"], "openai/gpt-oss-120b")
        self.assertEqual(result["fallback_used"], False)
        self.assertEqual(models.calls, 1)

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
