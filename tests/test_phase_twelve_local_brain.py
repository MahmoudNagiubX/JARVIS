from __future__ import annotations

import asyncio
import json
import os
import tempfile
import threading
import unittest
import urllib.error
from collections import deque
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.request import Request

from jarvis.authority.identity.service import EnrollmentGrant
from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.contracts import LLMMessage, LLMRequest, LLMResponse, LLMRole, ToolResult, ToolResultStatus
from jarvis.models.gateway import ModelGateway
from jarvis.models.llama_runtime import LlamaCppRuntimeConfig, LlamaCppRuntimeSupervisor, LlamaRuntimeState
from jarvis.models.providers import LlamaCppProvider, ModelOfflineError, ModelProviderError
from jarvis.tools.registry import ToolRegistry, ToolSpec
from jarvis.tools.selection import ToolSchemaSelector


class _Response:
    def __init__(self, body: bytes, *, status: int = 200, content_length: int | None = None) -> None:
        self.status = status
        self.headers = {"Content-Length": str(content_length if content_length is not None else len(body))}
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


def _completion(body: object, *, model: str = "jarvis-local-qwen", usage: dict[str, int] | None = None) -> _Response:
    payload = {
        "id": "chatcmpl-test",
        "model": model,
        "choices": [{"index": 0, "message": body, "finish_reason": "stop"}],
        "usage": usage or {"prompt_tokens": 4, "completion_tokens": 3},
    }
    return _Response(json.dumps(payload).encode())


class LlamaProviderTests(unittest.IsolatedAsyncioTestCase):
    def _request(self) -> LLMRequest:
        return LLMRequest(
            "request-1",
            (LLMMessage(LLMRole.USER, "hello"),),
            model="jarvis-local-qwen",
            max_output_tokens=16,
            timeout_seconds=12,
        )

    async def test_loopback_endpoint_rejects_remote_credentials_and_paths(self) -> None:
        for endpoint in (
            "http://192.0.2.1:8080",
            "http://user:pass@127.0.0.1:8080",
            "http://127.0.0.1:8080/v1",
            "http://127.0.0.1",
        ):
            with self.assertRaises(ValueError):
                LlamaCppProvider(endpoint)
        with self.assertRaisesRegex(ValueError, "llama_cpp_model_alias_invalid"):
            LlamaCppProvider("http://127.0.0.1:8080", model_alias="..\\secret\\model.gguf")

    async def test_plain_text_response_is_normalized(self) -> None:
        fake = _FakeOpen([_completion({"role": "assistant", "content": "ready"}, usage={"prompt_tokens": 5, "completion_tokens": 2})])
        response = await LlamaCppProvider("http://127.0.0.1:8080", urlopen=fake).generate(self._request())
        self.assertEqual(response.text, "ready")
        self.assertEqual(response.provider, "llama_cpp")
        self.assertEqual(response.model, "jarvis-local-qwen")
        self.assertEqual(response.finish_reason, "stop")
        self.assertEqual(dict(response.usage), {"prompt_tokens": 5, "output_tokens": 2})
        payload = json.loads(fake.requests[0].data.decode())
        self.assertEqual(payload["max_tokens"], 16)
        self.assertFalse(payload["stream"])

    async def test_json_string_tool_arguments_are_normalized(self) -> None:
        message = {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "get_test_status", "arguments": '{"detail":"brief"}'}}]}
        fake = _FakeOpen([_completion(message)])
        response = await LlamaCppProvider("http://127.0.0.1:8080", urlopen=fake).generate(self._request())
        self.assertEqual(response.tool_calls, ({"function": {"name": "get_test_status", "arguments": {"detail": "brief"}}},))

    async def test_dict_tool_arguments_are_preserved_as_dict(self) -> None:
        message = {"role": "assistant", "content": None, "tool_calls": [{"function": {"name": "get_test_status", "arguments": {"detail": "brief"}}}]}
        fake = _FakeOpen([_completion(message)])
        response = await LlamaCppProvider("http://127.0.0.1:8080", urlopen=fake).generate(self._request())
        self.assertEqual(response.text, "")
        self.assertEqual(response.tool_calls[0]["function"]["arguments"], {"detail": "brief"})

    async def test_health_uses_health_and_reports_safe_model_alias(self) -> None:
        fake = _FakeOpen([
            _Response(b'{"status":"ok"}'),
            _Response(b'{"object":"list","data":[{"id":"jarvis-local-qwen"}]}'),
        ])
        health = await LlamaCppProvider("http://127.0.0.1:8080", urlopen=fake).health()
        self.assertTrue(health.available)
        self.assertEqual(health.provider, "llama_cpp")
        self.assertEqual(health.model, "jarvis-local-qwen")
        self.assertNotIn("path", repr(health).casefold())

    async def test_health_loading_and_offline_are_truthful(self) -> None:
        loading = _FakeOpen([_Response(b'{"status":"loading model"}', status=503)])
        health = await LlamaCppProvider("http://127.0.0.1:8080", urlopen=loading).health()
        self.assertFalse(health.available)
        self.assertEqual(health.reason, "llama_cpp_model_not_ready")
        offline = _FakeOpen([urllib.error.URLError("offline")])
        health = await LlamaCppProvider("http://127.0.0.1:8080", urlopen=offline).health()
        self.assertFalse(health.available)
        self.assertEqual(health.reason, "llama_cpp_unavailable")

    async def test_malformed_and_missing_response_shapes_fail(self) -> None:
        for body in (b"not-json", json.dumps({"choices": []}).encode(), json.dumps({"choices": [{"message": []}]}).encode()):
            fake = _FakeOpen([_Response(body)])
            with self.assertRaises(ModelProviderError) as error:
                await LlamaCppProvider("http://127.0.0.1:8080", urlopen=fake).generate(self._request())
            self.assertEqual(str(error.exception), "llama_cpp_invalid_response")

    async def test_invalid_tool_call_shape_fails_at_provider_boundary(self) -> None:
        fake = _FakeOpen([_completion({"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "x", "arguments": "[1]"}}]})])
        with self.assertRaisesRegex(ModelProviderError, "llama_cpp_tool_call_invalid"):
            await LlamaCppProvider("http://127.0.0.1:8080", urlopen=fake).generate(self._request())

    async def test_oversized_content_length_and_body_are_rejected(self) -> None:
        fake = _FakeOpen([_Response(b"{}", content_length=LlamaCppProvider.MAX_RESPONSE_BYTES + 1)])
        with self.assertRaisesRegex(ModelProviderError, "llama_cpp_response_too_large"):
            await LlamaCppProvider("http://127.0.0.1:8080", urlopen=fake).generate(self._request())
        fake = _FakeOpen([_Response(b"x" * (LlamaCppProvider.MAX_RESPONSE_BYTES + 1))])
        with self.assertRaisesRegex(ModelProviderError, "llama_cpp_response_too_large"):
            await LlamaCppProvider("http://127.0.0.1:8080", urlopen=fake).generate(self._request())

    async def test_timeout_is_bounded_and_offline_is_normalized(self) -> None:
        fake = _FakeOpen([TimeoutError()])
        with self.assertRaises(ModelOfflineError):
            await LlamaCppProvider("http://127.0.0.1:8080", urlopen=fake).generate(
                LLMRequest("r", (LLMMessage(LLMRole.USER, "x"),), timeout_seconds=9999)
            )
        self.assertEqual(fake.timeouts, [180.0])

    async def test_provider_health_requires_the_expected_alias(self) -> None:
        fake = _FakeOpen([
            _Response(b'{"status":"ok"}'),
            _Response(b'{"object":"list","data":[{"id":"other-model"},{"id":"jarvis-local-qwen"}]}'),
        ])
        health = await LlamaCppProvider("http://127.0.0.1:8080", urlopen=fake).health()
        self.assertTrue(health.available)
        wrong = _FakeOpen([
            _Response(b'{"status":"ok"}'),
            _Response(b'{"object":"list","data":[{"id":"other-model"}]}'),
        ])
        health = await LlamaCppProvider("http://127.0.0.1:8080", urlopen=wrong).health()
        self.assertFalse(health.available)
        self.assertEqual(health.reason, "llama_cpp_model_mismatch")

    async def test_provider_concurrency_allows_one_active_generation_and_eight_waiters(self) -> None:
        entered = threading.Event()
        release = threading.Event()
        calls = 0
        lock = threading.Lock()

        def blocking_open(request: Request, *, timeout: float) -> _Response:
            del request, timeout
            nonlocal calls
            with lock:
                calls += 1
                current = calls
            if current == 1:
                entered.set()
                self.assertTrue(release.wait(3))
            return _completion({"role": "assistant", "content": "ready"})

        provider = LlamaCppProvider("http://127.0.0.1:8080", urlopen=blocking_open)
        tasks = [asyncio.create_task(provider.generate(self._request())) for _ in range(10)]
        await asyncio.to_thread(entered.wait, 2)
        await asyncio.sleep(0.1)
        self.assertLessEqual(provider._waiting_generations, provider.MAX_WAITERS)
        release.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        self.assertEqual(sum(isinstance(item, ModelProviderError) and str(item) == "local_model_busy" for item in results), 1)
        self.assertEqual(sum(isinstance(item, LLMResponse) for item in results), 9)

    async def test_provider_waiter_timeout_is_removed_without_leaking_slot(self) -> None:
        entered = threading.Event()
        release = threading.Event()

        def blocking_open(request: Request, *, timeout: float) -> _Response:
            del request, timeout
            entered.set()
            self.assertTrue(release.wait(3))
            return _completion({"role": "assistant", "content": "ready"})

        provider = LlamaCppProvider("http://127.0.0.1:8080", urlopen=blocking_open)
        first = asyncio.create_task(provider.generate(self._request()))
        await asyncio.to_thread(entered.wait, 2)
        timed_out = asyncio.create_task(provider.generate(LLMRequest(
            "request-timeout", (LLMMessage(LLMRole.USER, "hello"),), timeout_seconds=1.0,
        )))
        with self.assertRaisesRegex(ModelProviderError, "local_model_busy"):
            await timed_out
        self.assertEqual(provider._waiting_generations, 0)
        release.set()
        await first

    async def test_real_stdlib_http_boundary_covers_health_models_and_generation(self) -> None:
        received: list[dict[str, object]] = []

        class Handler(BaseHTTPRequestHandler):
            def _json(self, payload: object, status: int = 200) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/health":
                    self._json({"status": "ok"})
                elif self.path == "/v1/models":
                    self._json({"object": "list", "data": [{"id": "jarvis-local-qwen"}]})
                else:
                    self._json({"error": "not found"}, 404)

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers["Content-Length"] or "0")
                received.append(json.loads(self.rfile.read(length).decode("utf-8")))
                self._json({
                    "id": "chatcmpl-http",
                    "model": "jarvis-local-qwen",
                    "choices": [{"message": {"role": "assistant", "content": "real boundary"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 2},
                })

            def log_message(self, *_args: object) -> None:
                return None

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            endpoint = f"http://127.0.0.1:{server.server_address[1]}"
            provider = LlamaCppProvider(endpoint)
            health = await provider.health()
            response = await provider.generate(self._request())
            self.assertTrue(health.available)
            self.assertEqual(response.text, "real boundary")
            self.assertEqual(received[0]["model"], "jarvis-local-qwen")
            self.assertFalse(received[0]["stream"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


class _FakeProcess:
    def __init__(self, pid: int = 4242, *, exited: bool = False) -> None:
        self.pid = pid
        self.returncode = 1 if exited else None
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        return self.returncode or 0


class LlamaSupervisorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executable = self.root / "llama-server.exe"
        self.model = self.root / "model.gguf"
        self.executable.write_bytes(b"server")
        self.model.write_bytes(b"fake-model")

    async def asyncTearDown(self) -> None:
        self.temp.cleanup()

    def _config(self, port: int = 18901, **kwargs: object) -> LlamaCppRuntimeConfig:
        return LlamaCppRuntimeConfig(self.executable, self.model, f"http://127.0.0.1:{port}", ready_timeout_seconds=1.0, **kwargs)

    async def test_config_rejects_repo_model_non_gguf_missing_executable_and_bad_bounds(self) -> None:
        with self.assertRaisesRegex(ValueError, "llama_cpp_model_must_be_external"):
            LlamaCppRuntimeConfig(self.executable, Path.cwd() / "model.gguf", "http://127.0.0.1:18901").validate()
        with self.assertRaisesRegex(ValueError, "llama_cpp_invalid_model"):
            LlamaCppRuntimeConfig(self.executable, self.root / "model.bin", "http://127.0.0.1:18901").validate()
        with self.assertRaisesRegex(ValueError, "llama_cpp_runtime_not_found"):
            LlamaCppRuntimeConfig(self.root / "missing.exe", self.model, "http://127.0.0.1:18901").validate()
        with self.assertRaisesRegex(ValueError, "llama_cpp_context_out_of_bounds"):
            self._config(context_size=999).validate()
        with self.assertRaisesRegex(ValueError, "llama_cpp_model_alias_invalid"):
            self._config(model_alias="bad alias").validate()

    async def test_command_is_fixed_argv_loopback_and_no_arbitrary_flags(self) -> None:
        before = self.model.stat()
        command = LlamaCppRuntimeSupervisor(self._config(gpu_layers=-1)).command
        after = self.model.stat()
        self.assertEqual(command[0], str(self.executable.resolve()))
        self.assertIn("--model", command)
        self.assertIn("--host", command)
        self.assertIn("127.0.0.1", command)
        self.assertIn("--no-webui", command)
        self.assertIn("--n-gpu-layers", command)
        self.assertNotIn("--model-url", command)
        self.assertEqual((before.st_size, before.st_mtime_ns), (after.st_size, after.st_mtime_ns))

    async def test_start_uses_shell_false_and_double_start_does_not_spawn_twice(self) -> None:
        process = _FakeProcess()
        calls: list[tuple[list[str], dict[str, object]]] = []

        def popen(argv: list[str], **kwargs: object) -> _FakeProcess:
            calls.append((argv, kwargs))
            return process

        fake = _FakeOpen([
            _Response(b'{"status":"ok"}'),
            _Response(b'{"object":"list","data":[{"id":"jarvis-local-qwen"}]}'),
            _Response(b'{"status":"ok"}'),
            _Response(b'{"object":"list","data":[{"id":"jarvis-local-qwen"}]}'),
        ])
        supervisor = LlamaCppRuntimeSupervisor(self._config(), popen_factory=popen, urlopen=fake)
        first = await supervisor.start()
        second = await supervisor.start()
        self.assertEqual(first.state, LlamaRuntimeState.READY)
        self.assertEqual(second.state, LlamaRuntimeState.READY)
        self.assertEqual(len(calls), 1)
        self.assertFalse(calls[0][1]["shell"])
        self.assertEqual(calls[0][0][0], str(self.executable.resolve()))
        await supervisor.stop()
        self.assertTrue(process.terminated)

    async def test_close_cleans_owned_process(self) -> None:
        process = _FakeProcess()
        fake = _FakeOpen([
            _Response(b'{"status":"ok"}'),
            _Response(b'{"object":"list","data":[{"id":"jarvis-local-qwen"}]}'),
        ])
        supervisor = LlamaCppRuntimeSupervisor(
            self._config(port=18905),
            popen_factory=lambda *_args, **_kwargs: process,
            urlopen=fake,
        )
        status = await supervisor.start()
        self.assertTrue(status.ready)
        await supervisor.close()
        self.assertTrue(process.terminated)
        self.assertEqual(supervisor.status.state, LlamaRuntimeState.STOPPED)

    async def test_start_exited_process_and_readiness_timeout_are_bounded(self) -> None:
        exited = _FakeProcess(exited=True)
        fake = _FakeOpen([])
        supervisor = LlamaCppRuntimeSupervisor(self._config(port=18902), popen_factory=lambda *_args, **_kwargs: exited, urlopen=fake)
        status = await supervisor.start()
        self.assertEqual(status.reason, "process_exited")
        process = _FakeProcess()
        offline = _FakeOpen([urllib.error.URLError("offline")] * 16)
        supervisor = LlamaCppRuntimeSupervisor(self._config(port=18903), popen_factory=lambda *_args, **_kwargs: process, urlopen=offline)
        status = await supervisor.start()
        self.assertEqual(status.state, LlamaRuntimeState.UNAVAILABLE)
        self.assertEqual(status.reason, "readiness_timeout")
        self.assertTrue(process.terminated)

    async def test_attached_server_is_not_owned_or_stopped(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                body = b'{"status":"ok"}' if self.path == "/health" else b'{"object":"list","data":[{"id":"jarvis-local-qwen"}]}'
                self.send_response(200 if self.path in {"/health", "/v1/models"} else 404)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args: object) -> None:
                return None

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            config = self._config(port=server.server_address[1])
            supervisor = LlamaCppRuntimeSupervisor(config, popen_factory=lambda *_args, **_kwargs: self.fail("must attach"))
            status = await supervisor.start()
            self.assertEqual(status.state, LlamaRuntimeState.ATTACHED)
            self.assertFalse(status.owned)
            await supervisor.stop()
            self.assertEqual(status.pid, None)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    async def test_503_loading_response_is_compatible_but_not_ready(self) -> None:
        process = _FakeProcess()
        loading = _FakeOpen([
            _Response(b'{"status":"loading model"}', status=503),
            _Response(b'{"object":"list","data":[{"id":"jarvis-local-qwen"}]}'),
        ])
        supervisor = LlamaCppRuntimeSupervisor(
            self._config(port=18904),
            popen_factory=lambda *_args, **_kwargs: process,
            urlopen=loading,
        )
        status = await supervisor.health()
        self.assertEqual(status.state, LlamaRuntimeState.UNAVAILABLE)
        self.assertEqual(status.reason, "unavailable")

    async def test_incompatible_listener_reports_port_conflict(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                self.send_response(404)
                self.end_headers()

            def log_message(self, *_args: object) -> None:
                return None

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status = await LlamaCppRuntimeSupervisor(self._config(port=server.server_address[1]), popen_factory=lambda *_args, **_kwargs: self.fail("must not kill or spawn")).start()
            self.assertEqual(status.state, LlamaRuntimeState.PORT_CONFLICT)
            self.assertEqual(status.reason, "incompatible_listener")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    async def test_wrong_model_listener_is_not_attached_or_killed(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/health":
                    body = b'{"status":"ok"}'
                elif self.path == "/v1/models":
                    body = b'{"object":"list","data":[{"id":"other-model"}]}'
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args: object) -> None:
                return None

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status = await LlamaCppRuntimeSupervisor(
                self._config(port=server.server_address[1]),
                popen_factory=lambda *_args, **_kwargs: self.fail("must not attach or spawn"),
            ).start()
            self.assertEqual(status.state, LlamaRuntimeState.PORT_CONFLICT)
            self.assertEqual(status.reason, "model_mismatch")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    async def test_restart_is_refused_for_attached_server(self) -> None:
        supervisor = LlamaCppRuntimeSupervisor(self._config(), popen_factory=lambda *_args, **_kwargs: _FakeProcess())
        supervisor._attached = True
        with self.assertRaisesRegex(RuntimeError, "attached_not_owned"):
            await supervisor.restart()


class ToolSchemaSelectorTests(unittest.TestCase):
    NAMES = (
        "status.read",
        "desktop.context.read",
        "screen.observe",
        "screen.latest",
        "computer.window.control",
        "computer.keyboard.type",
        "computer.clipboard.read",
        "computer.clipboard.write",
        "computer.audio.adjust",
        "echo.reversible",
        "project.tests.run",
        "workspace.read",
    )

    @staticmethod
    def _noop(_arguments: object, _context: object) -> ToolResult:
        return ToolResult(ToolResultStatus.SUCCEEDED)

    def _selector(self, disabled: tuple[str, ...] = ()) -> ToolSchemaSelector:
        registry = ToolRegistry(tuple(
            ToolSpec(
                f"test-{name}", name, "1", f"Test {name}", "read", "tool.request", frozenset(),
                5.0, True, self._noop, enabled=name not in disabled,
            )
            for name in self.NAMES
        ))
        return ToolSchemaSelector(registry)

    @staticmethod
    def _names(schemas: tuple[dict[str, object], ...]) -> tuple[str, ...]:
        return tuple(schema["function"]["name"] for schema in schemas)

    def test_ordinary_chat_gets_no_tools(self) -> None:
        self.assertEqual(self._names(self._selector().select("tell me a short joke")), ())

    def test_exact_visual_tool_and_visual_intent_select_registered_group(self) -> None:
        exact = self._names(self._selector().select("Use desktop.context.read exactly once"))
        visual = self._names(self._selector().select("what is on my current screen"))
        self.assertIn("desktop.context.read", exact)
        self.assertEqual(visual, ToolSchemaSelector.VISUAL_TOOLS)

    def test_computer_and_status_intents_are_bounded(self) -> None:
        computer = self._names(self._selector().select("type this with the keyboard"))
        status = self._names(self._selector().select("read status"))
        self.assertEqual(computer, ToolSchemaSelector.COMPUTER_TOOLS)
        self.assertEqual(status, ToolSchemaSelector.STATUS_TOOLS)
        self.assertLessEqual(len(computer), ToolSchemaSelector.MAX_MODEL_TOOLS)

    def test_disabled_and_unknown_tools_cannot_bypass_registry(self) -> None:
        selected = self._names(self._selector(disabled=("desktop.context.read",)).select("desktop.context.read"))
        self.assertNotIn("desktop.context.read", selected)
        self.assertEqual(self._names(self._selector().select("please use made.up.tool now")), ())

    def test_maximum_count_and_second_turn_selection_are_stable(self) -> None:
        intent = " ".join(self.NAMES)
        selected = self._selector().select(intent)
        self.assertEqual(len(selected), ToolSchemaSelector.MAX_MODEL_TOOLS)
        self.assertEqual(self._names(selected), self._names(self._selector().select(intent)))
        original = self._names(self._selector().select("what is on my desktop"))
        tool_output = '{"result":"completed"}'
        self.assertEqual(original, self._names(self._selector().select("what is on my desktop")))
        self.assertEqual(self._names(self._selector().select(tool_output)), ())


class ModelGatewayAndAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_gguf_is_a_llama_cpp_compatibility_alias(self) -> None:
        fake = _FakeOpen([_completion({"role": "assistant", "content": "local"})])
        provider = LlamaCppProvider("http://127.0.0.1:8080", urlopen=fake)
        gateway = ModelGateway(JarvisConfig(environment="test", model_provider="gguf"), {"gguf": provider})
        response = await gateway.generate(LLMRequest("r", (LLMMessage(LLMRole.USER, "x"),)))
        from jarvis.models.routing import ModelRoute
        self.assertEqual(gateway.selection(ModelRoute.GENERAL_REASONING).provider, "llama_cpp")
        self.assertEqual(response.provider, "llama_cpp")

    async def test_live_llama_cpp_never_silently_falls_back_to_mock(self) -> None:
        gateway = ModelGateway(JarvisConfig(environment="live-workstation", model_provider="llama_cpp"))
        with self.assertRaisesRegex(ModelProviderError, "llama_cpp_runtime_not_configured"):
            await gateway.generate(LLMRequest("r", (LLMMessage(LLMRole.USER, "x"),)))

    async def test_config_reads_local_runtime_without_enabling_it_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "llama-server.exe"
            model = root / "model.gguf"
            executable.write_bytes(b"server")
            model.write_bytes(b"fake-model")
            with patch.dict(os.environ, {
                "JARVIS_MODEL_PROVIDER": "llama_cpp",
                "JARVIS_LLAMA_CPP_SERVER_PATH": str(executable),
                "JARVIS_LLAMA_CPP_MODEL_PATH": str(model),
                "JARVIS_MODEL_LOOPBACK_ENDPOINT": "http://127.0.0.1:19001",
                "JARVIS_LLAMA_CPP_CONTEXT_SIZE": "2048",
                "JARVIS_LLAMA_CPP_THREADS": "2",
                "JARVIS_LLAMA_CPP_GPU_LAYERS": "99",
                "JARVIS_LOCAL_MODEL_AUTOSTART": "false",
            }, clear=False):
                config = JarvisConfig.from_env()
            self.assertEqual(config.llama_cpp_context_size, 2048)
            self.assertEqual(config.llama_cpp_threads, 2)
            self.assertEqual(config.llama_cpp_gpu_layers, 99)
            self.assertFalse(config.local_model_autostart)
            runtime = create_runtime(config)
            self.assertIsNotNone(runtime.models.runtime_supervisor)
            self.assertEqual(runtime.models.runtime_supervisor.status.state, LlamaRuntimeState.STOPPED)
            await runtime.start()
            await runtime.shutdown()

    async def test_create_runtime_does_not_autostart_or_spawn_model(self) -> None:
        runtime = create_runtime(JarvisConfig(environment="test", model_provider="llama_cpp"))
        try:
            self.assertIsNone(runtime.models.runtime_supervisor)
        finally:
            await runtime.start()
            await runtime.shutdown()

    async def test_agent_uses_local_provider_boundary_for_text_and_tool_result_turn(self) -> None:
        runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await runtime.start()
        try:
            identity = await runtime.identity.bootstrap_owner("Local Brain Test Owner")
            grant = await runtime.identity.create_enrollment(EnrollmentGrant(
                identity.owner_id,
                "Local Brain Test Device",
                "desktop",
                "windows",
                ("tool.request",),
            ))
            issued = await runtime.identity.redeem_enrollment(grant.code)
            device = await runtime.identity.authenticate(issued.raw, issued.device_id)
            assert device is not None
            fake = _FakeOpen([
                _completion({"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "status.read", "arguments": {}}}]}),
                _completion({"role": "assistant", "content": "The local tool reported ready."}),
            ])
            provider = LlamaCppProvider("http://127.0.0.1:8080", model_alias="jarvis-local-qwen", urlopen=fake)
            gateway = ModelGateway(JarvisConfig(environment="test", model_provider="llama_cpp"), {"llama_cpp": provider})
            runtime.models = gateway
            runtime.agent.models = gateway
            outcome = await runtime.agent.process_text("tell me the current status", identity, device)
            self.assertEqual(outcome.state.value, "succeeded")
            self.assertEqual(outcome.response, "The local tool reported ready.")
            self.assertEqual(len(fake.requests), 2)
            self.assertEqual(runtime.repository.run(outcome.run_id).model_id, "jarvis-local-qwen")
            first_tools = json.loads(fake.requests[0].data.decode())["tools"]
            second_tools = json.loads(fake.requests[1].data.decode())["tools"]
            self.assertEqual(first_tools, second_tools)
        finally:
            await runtime.shutdown()


if __name__ == "__main__":
    unittest.main()
