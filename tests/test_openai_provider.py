from __future__ import annotations

import asyncio
import json
import os
import unittest
import urllib.error
from collections import deque
from unittest.mock import patch
from urllib.request import Request

from jarvis.config import JarvisConfig
from jarvis.contracts import LLMMessage, LLMRequest, LLMRole
from jarvis.models.gateway import ModelGateway
from jarvis.models.openai import OpenAIProvider
from jarvis.models.routing import ModelRoute
from jarvis.models.providers import ModelProviderError


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


class OpenAIProviderTests(unittest.IsolatedAsyncioTestCase):
    def _request(self, *, tools: tuple[dict[str, object], ...] = ()) -> LLMRequest:
        return LLMRequest(
            "request-openai",
            (
                LLMMessage(LLMRole.SYSTEM, "You are JARVIS."),
                LLMMessage(LLMRole.USER, "Check the system status."),
            ),
            model="gpt-5.2",
            tools=tools,
            max_output_tokens=32,
            timeout_seconds=12,
        )

    async def test_disabled_and_missing_key_fail_closed_without_network(self) -> None:
        fake = _FakeOpen([])
        disabled = OpenAIProvider(api_key="secret", enabled=False, urlopen=fake)
        with self.assertRaisesRegex(ModelProviderError, "openai_not_enabled"):
            await disabled.generate(self._request())
        health = await disabled.health()
        self.assertFalse(health.available)
        self.assertEqual(health.reason, "openai_not_enabled")

        missing = OpenAIProvider(api_key="", enabled=True, urlopen=fake)
        with self.assertRaisesRegex(ModelProviderError, "openai_api_key_missing"):
            await missing.generate(self._request())
        self.assertEqual(len(fake.requests), 0)
        missing_health = await missing.health()
        self.assertEqual(missing_health.reason, "openai_api_key_missing")

    async def test_responses_payload_and_tool_calls_are_normalized(self) -> None:
        fake = _FakeOpen([
            _Response(json.dumps({
                "id": "resp-test",
                "model": "gpt-5.2",
                "status": "completed",
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": "Ready."}]},
                    {"type": "function_call", "call_id": "call-1", "name": "status.read", "arguments": "{}"},
                ],
                "usage": {"input_tokens": 11, "output_tokens": 4},
            }).encode())
        ])
        tool = {
            "type": "function",
            "function": {
                "name": "status.read",
                "description": "Read bounded status.",
                "parameters": {"type": "object", "additionalProperties": False},
            },
        }
        provider = OpenAIProvider(api_key="test-secret", urlopen=fake)
        response = await provider.generate(self._request(tools=(tool,)))

        self.assertEqual(response.text, "Ready.")
        self.assertEqual(response.provider, "openai")
        self.assertEqual(response.finish_reason, "tool_calls")
        self.assertEqual(response.tool_calls[0]["function"]["name"], "status.read")
        self.assertEqual(response.tool_calls[0]["function"]["arguments"], {})
        self.assertEqual(dict(response.usage), {"prompt_tokens": 11, "output_tokens": 4})
        request = fake.requests[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "gpt-5.2")
        self.assertFalse(payload["store"])
        self.assertEqual(payload["tools"][0]["name"], "status.read")
        self.assertEqual(payload["input"][1], {"role": "user", "content": "Check the system status."})
        self.assertEqual(request.get_header("Authorization"), "Bearer test-secret")
        self.assertEqual(fake.timeouts, [12.0])

    async def test_tool_result_is_bounded_as_input_without_inventing_call_id(self) -> None:
        fake = _FakeOpen([_Response(json.dumps({
            "model": "gpt-5.2",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "Done."}]}],
            "usage": {},
        }).encode())])
        provider = OpenAIProvider(api_key="test-secret", urlopen=fake)
        request = LLMRequest(
            "r",
            (LLMMessage(LLMRole.TOOL, '{"verified":true}'),),
            timeout_seconds=2,
        )
        await provider.generate(request)
        payload = json.loads(fake.requests[0].data.decode("utf-8"))
        self.assertEqual(payload["input"][0]["role"], "user")
        self.assertTrue(payload["input"][0]["content"].startswith("[JARVIS tool result]"))

    async def test_health_is_bounded_and_does_not_expose_key(self) -> None:
        fake = _FakeOpen([_Response(b'{"id":"gpt-5.2","object":"model"}')])
        provider = OpenAIProvider(api_key="do-not-leak", urlopen=fake)
        health = await provider.health()
        self.assertTrue(health.available)
        self.assertEqual(health.reason, "openai_ready")
        self.assertEqual(fake.timeouts, [2.0])
        self.assertNotIn("do-not-leak", repr(health))

        auth_failure = _FakeOpen([urllib.error.HTTPError(
            "https://api.openai.com/v1/models/gpt-5.2", 401, "unauthorized", {}, None,
        )])
        health = await OpenAIProvider(api_key="do-not-leak", urlopen=auth_failure).health()
        self.assertFalse(health.available)
        self.assertEqual(health.reason, "openai_auth_failed")

    async def test_request_errors_are_normalized_without_response_body(self) -> None:
        fake = _FakeOpen([urllib.error.HTTPError(
            "https://api.openai.com/v1/responses", 429, "rate limited", {}, None,
        )])
        provider = OpenAIProvider(api_key="do-not-leak", urlopen=fake)
        with self.assertRaisesRegex(ModelProviderError, "openai_unavailable") as raised:
            await provider.generate(self._request())
        self.assertNotIn("do-not-leak", str(raised.exception))

    async def test_gateway_uses_explicit_openai_selection_only(self) -> None:
        fake = _FakeOpen([_Response(json.dumps({
            "model": "owner-model",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "ok"}]}],
            "usage": {},
        }).encode())])
        provider = OpenAIProvider(model="owner-model", api_key="test-secret", urlopen=fake)
        gateway = ModelGateway(
            JarvisConfig(environment="test", model_provider="openai", openai_enabled=True, openai_model="owner-model"),
            {"openai": provider},
        )
        response = await gateway.generate(self._request(), ModelRoute.GENERAL_REASONING)
        self.assertEqual(response.provider, "openai")
        self.assertEqual(response.model, "owner-model")
        self.assertEqual(gateway.selection(ModelRoute.GENERAL_REASONING).model, "owner-model")

    def test_config_parses_explicit_openai_settings(self) -> None:
        with patch.dict(os.environ, {
            "JARVIS_MODEL_PROVIDER": "openai",
            "JARVIS_OPENAI_ENABLED": "true",
            "JARVIS_OPENAI_MODEL": "owner-model",
            "JARVIS_OPENAI_TIMEOUT_SECONDS": "17",
        }, clear=False):
            config = JarvisConfig.from_env()
        self.assertEqual(config.model_provider, "openai")
        self.assertTrue(config.openai_enabled)
        self.assertEqual(config.openai_model, "owner-model")
        self.assertEqual(config.openai_timeout_seconds, 17.0)


if __name__ == "__main__":
    unittest.main()
