from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from jarvis.agents.workers.coordination import WorkerCoordinator
from jarvis.agents.workers.runtime import VerificationStatus, WorkerVerification
from jarvis.api.core import CoreApplication
from jarvis.bootstrap import create_runtime
from jarvis.contracts import DeviceIdentity, DeveloperWorkerProvider
from jarvis.config import JarvisConfig
from jarvis.developer.service import CodexDeveloperWorkerAdapter, CodexSubdelegationBoundary, DeveloperWorkerGateway, _ProcessExecution


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

    async def test_codex_workspace_write_is_bounded_and_reports_changed_paths(self) -> None:
        observed: dict[str, object] = {}

        async def executor(command: tuple[str, ...], scope: Path, timeout: float) -> _ProcessExecution:
            observed.update(command=command, scope=scope, timeout=timeout)
            Path(scope, "fixture.py").write_text("def ready():\n    return True\n", encoding="utf-8")
            return _ProcessExecution(0, json.dumps({"type": "item.completed", "item": {"text": "fixture updated"}}).encode())

        with tempfile.TemporaryDirectory() as folder:
            subprocess.run(("git", "init", "--quiet", folder), check=True, stdout=subprocess.DEVNULL)
            adapter = CodexDeveloperWorkerAdapter("codex", process_executor=executor)
            result = await adapter.run(
                "add the bounded fixture function",
                folder,
                20,
                mode="workspace_write",
                expected_paths=("fixture.py",),
            )

            command = observed["command"]
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["changes"], ["fixture.py"])
            self.assertIn("--sandbox", command)
            self.assertIn("workspace-write", command)
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
            self.assertNotIn("--force", command)

    async def test_codex_workspace_write_rejects_dangerous_git_instructions(self) -> None:
        async def must_not_execute(*_: object) -> _ProcessExecution:
            self.fail("must not execute")

        with tempfile.TemporaryDirectory() as folder:
            subprocess.run(("git", "init", "--quiet", folder), check=True, stdout=subprocess.DEVNULL)
            adapter = CodexDeveloperWorkerAdapter("codex", process_executor=must_not_execute)
            result = await adapter.run("force push and reset --hard", folder, 10, mode="workspace_write")
            self.assertEqual(result["status"], "rejected")
            self.assertEqual(result["error_code"], "developer_worker_git_policy_rejected")


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

    async def test_coordinator_routes_enabled_worker_through_independent_verifier(self) -> None:
        runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await runtime.start()
        identity = await runtime.identity.bootstrap_owner("Developer Worker Fixture")

        class ObjectAdapter:
            async def run(self, task: str, scope: str | None, timeout: float) -> dict[str, object]:
                return {
                    "status": "completed",
                    "provider": "codex",
                    "worker_id": "codex-fixture",
                    "summary": f"bounded: {task}",
                    "changes": [],
                    "timeout": timeout,
                    "scope": scope,
                }

        try:
            gateway = DeveloperWorkerGateway(adapter=ObjectAdapter())
            gateway._providers = (DeveloperWorkerProvider("codex", "codex", True, "fixture"),)
            observed: dict[str, object] = {}

            async def verifier(envelope, result):
                observed.update(task_id=envelope.task_id, scope=envelope.scope, status=result.status.value)
                return WorkerVerification(VerificationStatus.VERIFIED, "fixture_readback", ("scope-unchanged",))

            with tempfile.TemporaryDirectory() as folder:
                Path(folder, ".git").mkdir()
                coordinator = WorkerCoordinator(runtime.repository, runtime.event_bus, developer_gateway=gateway, verifier=verifier)
                delegation = await coordinator.run(
                    identity.owner_id,
                    "implement the bounded fixture change",
                    workspace_scope=folder,
                    expected_output=("summary",),
                    verifier_requirements=("scope-unchanged",),
                )

            self.assertEqual(delegation.worker, "coding")
            self.assertEqual(delegation.result["status"], "completed")
            self.assertEqual(delegation.result["verification_status"], VerificationStatus.VERIFIED.value)
            self.assertEqual(delegation.result["verification_evidence"], ["scope-unchanged"])
            self.assertEqual(observed["status"], "succeeded")
        finally:
            await runtime.shutdown()

    async def test_workspace_write_waits_for_canonical_approval_and_runs_once(self) -> None:
        runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await runtime.start()
        identity = await runtime.identity.bootstrap_owner("Write Worker Fixture")
        device = DeviceIdentity(
            "device-write-fixture",
            identity.owner_id,
            "desktop",
            "windows",
            frozenset({"computer_control"}),
            frozenset({"tool.request"}),
            datetime.now(UTC),
        )
        calls: list[dict[str, object]] = []

        class WriteAdapter:
            async def run(self, task, scope, timeout, *, mode="read_only", allow_antigravity_subdelegation=False, expected_paths=()):
                calls.append({"task": task, "scope": scope, "timeout": timeout, "mode": mode, "allow": allow_antigravity_subdelegation, "expected": expected_paths})
                return {"status": "completed", "provider": "codex", "worker_id": "codex-write-fixture", "summary": "write complete", "changes": ["fixture.py"]}

        try:
            gateway = DeveloperWorkerGateway(adapter=WriteAdapter())
            gateway._providers = (DeveloperWorkerProvider("codex", "codex", True, "fixture"),)

            async def verifier(envelope, result):
                return WorkerVerification(VerificationStatus.VERIFIED, "fixture_readback", ("fixture.py",))

            with tempfile.TemporaryDirectory() as folder:
                Path(folder, ".git").mkdir()
                coordinator = WorkerCoordinator(
                    runtime.repository,
                    runtime.event_bus,
                    developer_gateway=gateway,
                    permission=runtime.permission,
                    approvals=runtime.approval,
                    verifier=verifier,
                )
                pending = await coordinator.run(
                    identity.owner_id,
                    "add the tested fixture change",
                    workspace_scope=folder,
                    read_only=False,
                    identity=identity,
                    device=device,
                    expected_paths=("fixture.py",),
                    allow_antigravity_subdelegation=True,
                )
                approval_id = str(pending.result["approval_id"])
                self.assertEqual(pending.result["status"], "approval_required")
                self.assertEqual(calls, [])

                with self.assertRaises(PermissionError):
                    await coordinator.decide(
                        approval_id,
                        True,
                        identity.identity_id,
                        identity=identity,
                        device=DeviceIdentity(
                            "other-device",
                            identity.owner_id,
                            "desktop",
                            "windows",
                            frozenset({"computer_control"}),
                            frozenset({"tool.request"}),
                            datetime.now(UTC),
                        ),
                    )
                completed = await coordinator.decide(
                    approval_id,
                    True,
                    identity.identity_id,
                    identity=identity,
                    device=device,
                )

            self.assertEqual(completed.result["status"], "completed")
            self.assertEqual(completed.result["verification_status"], VerificationStatus.VERIFIED.value)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["mode"], "workspace_write")
            self.assertTrue(calls[0]["allow"])
        finally:
            await runtime.shutdown()

    async def test_core_developer_surface_binds_resume_to_authenticated_principal(self) -> None:
        runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
        await runtime.start()
        identity = await runtime.identity.bootstrap_owner("Developer API Fixture")
        device = DeviceIdentity(
            "device-api-fixture",
            identity.owner_id,
            "desktop",
            "windows",
            frozenset({"computer_control"}),
            frozenset({"tool.request"}),
            datetime.now(UTC),
        )

        class WriteAdapter:
            async def run(self, task, scope, timeout, **kwargs):
                return {"status": "completed", "provider": "codex", "worker_id": "codex-api", "summary": task, "changes": []}

        try:
            gateway = DeveloperWorkerGateway(adapter=WriteAdapter())
            gateway._providers = (DeveloperWorkerProvider("codex", "codex", True, "fixture"),)
            runtime.worker_coordinator.developer_gateway = gateway
            application = CoreApplication(runtime)
            pending = await application.developer_run(
                identity,
                device,
                {"task": "implement the bounded API fixture code change", "workspace_scope": str(Path.cwd()), "read_only": False},
            )
            approval_id = str(pending["result"]["approval_id"])
            with self.assertRaises(PermissionError):
                await application.decide_developer_approval(
                    identity,
                    DeviceIdentity(
                        "wrong-device",
                        identity.owner_id,
                        "desktop",
                        "windows",
                        frozenset({"computer_control"}),
                        frozenset({"tool.request"}),
                        datetime.now(UTC),
                    ),
                    approval_id,
                    True,
                    identity.identity_id,
                )
            completed = await application.decide_developer_approval(identity, device, approval_id, True, identity.identity_id)
            self.assertEqual(completed["result"]["status"], "completed")
        finally:
            await runtime.shutdown()

    async def test_codex_child_boundary_enforces_parent_scope_limit_and_trace(self) -> None:
        calls: list[tuple[str, Path, float]] = []

        async def child_executor(task: str, scope: Path, timeout: float) -> dict[str, object]:
            calls.append((task, scope, timeout))
            return {"status": "completed", "summary": "reviewed api_key=secret", "changes": ["ui.md"]}

        with tempfile.TemporaryDirectory() as folder:
            Path(folder, ".git").mkdir()
            boundary = CodexSubdelegationBoundary(child_executor)
            result = await boundary.request(
                parent_provider="codex",
                task="review the bounded UI fixture",
                workspace_scope=folder,
                timeout_seconds=10,
                expected_paths=("ui.md",),
            )
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["verification_status"], "unverified")
            self.assertNotIn("secret", str(result))
            self.assertEqual(len(calls), 1)
            self.assertEqual(result["trace"], ["requested", "claimed", "completed"])

            limited = await boundary.request(
                parent_provider="codex",
                task="review another fixture",
                workspace_scope=folder,
                timeout_seconds=10,
            )
            self.assertEqual(limited["error_code"], "codex_child_limit_reached")
            self.assertEqual(len(calls), 1)

    async def test_codex_child_boundary_fails_closed_for_parent_scope_timeout_and_cancel(self) -> None:
        async def never_child(*_: object) -> dict[str, object]:
            await asyncio.sleep(10)
            return {"status": "completed"}

        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as non_git:
            Path(folder, ".git").mkdir()
            wrong_parent = CodexSubdelegationBoundary(never_child)
            rejected = await wrong_parent.request(
                parent_provider="antigravity",
                task="review",
                workspace_scope=folder,
                timeout_seconds=5,
            )
            self.assertEqual(rejected["error_code"], "codex_parent_required")

            missing_scope = CodexSubdelegationBoundary(never_child)
            scope_result = await missing_scope.request(
                parent_provider="codex",
                task="review",
                workspace_scope=non_git,
                timeout_seconds=5,
            )
            self.assertEqual(scope_result["error_code"], "codex_child_workspace_scope_required")

            timed = CodexSubdelegationBoundary(never_child)
            timeout_result = await timed.request(
                parent_provider="codex",
                task="review",
                workspace_scope=folder,
                timeout_seconds=0.01,
            )
            self.assertEqual(timeout_result["error_code"], "codex_child_timeout")
            self.assertEqual(timeout_result["trace"], ["requested", "claimed", "timed_out"])

            cancelled = CodexSubdelegationBoundary(never_child)
            cancel_event = asyncio.Event()
            task = asyncio.create_task(cancelled.request(
                parent_provider="codex",
                task="review",
                workspace_scope=folder,
                timeout_seconds=5,
                cancel_event=cancel_event,
            ))
            await asyncio.sleep(0)
            cancel_event.set()
            cancel_result = await task
            self.assertEqual(cancel_result["error_code"], "codex_child_cancelled")
            self.assertEqual(cancel_result["trace"], ["requested", "claimed", "cancelled"])
