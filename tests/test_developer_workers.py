from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis.contracts import DeveloperWorkerProvider
from jarvis.config import JarvisConfig
from jarvis.developer.service import CodexDeveloperWorkerAdapter, DeveloperWorkerGateway, _ProcessExecution


class DeveloperWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_codex_adapter_uses_read_only_scoped_command_and_redacts_output(self) -> None:
        observed: dict[str, object] = {}

        async def executor(command: tuple[str, ...], scope: Path, timeout: float) -> _ProcessExecution:
            observed.update(command=command, scope=scope, timeout=timeout)
            output = json.dumps({"type": "item.completed", "item": {"text": "review complete; api_key=super-secret"}}).encode()
            return _ProcessExecution(0, output)

        with tempfile.TemporaryDirectory() as folder:
            Path(folder, ".git").mkdir()
            adapter = CodexDeveloperWorkerAdapter("codex", process_executor=executor)
            result = await adapter.run("summarize the bounded project status", folder, 999)

            command = observed["command"]
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["changes"], [])
            self.assertNotIn("super-secret", str(result["summary"]))
            self.assertIn("[REDACTED]", str(result["summary"]))
            self.assertEqual(command[0:7], ("codex", "exec", "--sandbox", "read-only", "--ephemeral", "--json", "--cd"))
            self.assertEqual(command[7], str(Path(folder).resolve()))
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
            self.assertNotIn("--approve-for-me", command)
            self.assertEqual(observed["scope"], Path(folder).resolve())
            self.assertEqual(observed["timeout"], 300.0)


    async def test_codex_adapter_fails_closed_for_missing_scope_and_sensitive_tasks(self) -> None:
        async def must_not_execute(*_: object) -> _ProcessExecution:
            self.fail("must not execute")

        with tempfile.TemporaryDirectory() as folder:
            Path(folder, ".git").mkdir()
            adapter = CodexDeveloperWorkerAdapter("codex", process_executor=must_not_execute)
            missing_scope = await adapter.run("summarize the project", None, 10)
            sensitive_task = await adapter.run("inspect the API key configuration", folder, 10)

            self.assertEqual(missing_scope["status"], "rejected")
            self.assertEqual(missing_scope["error_code"], "worker_workspace_scope_required")
            self.assertEqual(sensitive_task["status"], "rejected")
            self.assertEqual(sensitive_task["error_code"], "worker_task_rejected")


    async def test_codex_adapter_normalizes_timeout_and_process_failure(self) -> None:
        async def timed_out(*_: object) -> _ProcessExecution:
            return _ProcessExecution(-9, timed_out=True)

        async def failed(*_: object) -> _ProcessExecution:
            return _ProcessExecution(17, stderr=b"credential=value-that-must-not-be-stored")

        with tempfile.TemporaryDirectory() as folder:
            Path(folder, ".git").mkdir()
            timeout_result = await CodexDeveloperWorkerAdapter("codex", process_executor=timed_out).run("inspect the project", folder, 10)
            failure_result = await CodexDeveloperWorkerAdapter("codex", process_executor=failed).run("inspect the project", folder, 10)

            self.assertEqual(timeout_result["status"], "failed")
            self.assertEqual(timeout_result["error_code"], "developer_worker_timeout")
            self.assertEqual(failure_result["status"], "failed")
            self.assertEqual(failure_result["error_code"], "codex_exit_17")
            self.assertNotIn("credential", str(failure_result.get("summary", "")).casefold())


    async def test_gateway_runs_object_adapter_without_bypassing_provider_discovery(self) -> None:
        async def executor(task: str, scope: str | None, timeout: float) -> dict[str, object]:
            return {"status": "completed", "task": task, "scope": scope, "timeout": timeout}

        class ObjectAdapter:
            async def run(self, task: str, scope: str | None, timeout: float) -> dict[str, object]:
                return await executor(task, scope, timeout)

        with tempfile.TemporaryDirectory() as folder:
            gateway = DeveloperWorkerGateway(adapter=ObjectAdapter())
            gateway._providers = (DeveloperWorkerProvider("codex", "codex", True, "test"),)
            result = await gateway.run("codex", "inspect the project", folder, timeout_seconds=600)
            self.assertEqual(result["status"], "completed")

            # The callable adapter seam remains available for existing deployments.
            callable_gateway = DeveloperWorkerGateway(adapter=executor)
            callable_gateway._providers = (DeveloperWorkerProvider("codex", "codex", True, "test"),)
            callable_result = await callable_gateway.run("codex", "inspect the project", folder, timeout_seconds=600)
            self.assertEqual(callable_result["timeout"], 300.0)

    def test_codex_activation_is_explicit_and_environment_driven(self) -> None:
        with patch.dict(os.environ, {"JARVIS_CODEX_WORKER_ENABLED": "true"}, clear=False):
            config = JarvisConfig.from_env()
        self.assertTrue(config.codex_worker_enabled)

        with patch("jarvis.developer.service.shutil.which", return_value="C:\\tools\\codex.exe"):
            discovery_only = DeveloperWorkerGateway()
            enabled = DeveloperWorkerGateway(enabled=True)
        self.assertIsNone(discovery_only.adapter)
        self.assertIsInstance(enabled.adapter, CodexDeveloperWorkerAdapter)
