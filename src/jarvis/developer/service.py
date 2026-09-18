"""Discover and run optional developer workers behind a bounded adapter."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import shutil
import subprocess
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..contracts import DeveloperWorkerProvider


_UNSET = object()
_MAX_TASK_CHARS = 8_000
_MAX_OUTPUT_BYTES = 256 * 1024
_MAX_SUMMARY_CHARS = 2_000
_MAX_TIMEOUT_SECONDS = 300.0
_MAX_CHILD_TIMEOUT_SECONDS = 120.0
_SENSITIVE_TASK_MARKERS = (
    ".env",
    "api key",
    "apikey",
    "credential",
    "cookie",
    "password",
    "private key",
    "refresh token",
    "secret",
    "token",
)
_FORBIDDEN_WRITE_MARKERS = (
    "force push",
    "--force",
    "--force-with-lease",
    "reset --hard",
    "git config",
    "credential dump",
    "credential.helper",
    "dangerously-bypass-approvals-and-sandbox",
    "approve-for-me",
)
_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_ -]?key|access[_ -]?token|refresh[_ -]?token|password|secret|credential|cookie|authorization)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]+"),
    re.compile(r"\beyJ[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\b"),
)
_ALLOWED_ENVIRONMENT = frozenset(
    {
        "APPDATA",
        "CODEX_HOME",
        "HOME",
        "LOCALAPPDATA",
        "NO_COLOR",
        "PATH",
        "PATHEXT",
        "SystemRoot",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "WINDIR",
        "XDG_CONFIG_HOME",
    }
)
_ALLOWED_ENVIRONMENT_CASEFOLDED = frozenset(item.casefold() for item in _ALLOWED_ENVIRONMENT)


@dataclass(frozen=True, slots=True)
class _ProcessExecution:
    returncode: int
    stdout: bytes = b""
    stderr: bytes = b""
    timed_out: bool = False
    output_truncated: bool = False


ProcessExecutor = Callable[[tuple[str, ...], Path, float], Awaitable[_ProcessExecution]]
ChildExecutor = Callable[[str, Path, float], Awaitable[dict[str, object]]]


def _bounded_timeout(value: float) -> float:
    return min(max(float(value), 1.0), _MAX_TIMEOUT_SECONDS)


def _safe_output(value: str, *, limit: int = _MAX_SUMMARY_CHARS) -> str:
    text = value.replace("\x00", " ").strip()

    def redact(match: re.Match[str]) -> str:
        raw = match.group(0)
        if ":" in raw:
            prefix = raw.split(":", 1)[0]
        elif "=" in raw:
            prefix = raw.split("=", 1)[0]
        elif raw.casefold().startswith("bearer"):
            prefix = "Bearer"
        else:
            prefix = "value"
        return f"{prefix}=[REDACTED]"

    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(redact, text)
    return " ".join(text.split())[:limit]


def _text_values(value: object) -> list[str]:
    """Extract only human-readable fields from Codex JSONL events."""

    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(_text_values(item))
        return values
    if not isinstance(value, dict):
        return []
    values = []
    for key in ("text", "summary", "message", "content"):
        if key in value:
            values.extend(_text_values(value[key]))
    if not values:
        for key in ("item", "output", "response", "result", "delta", "last_message"):
            if key in value:
                values.extend(_text_values(value[key]))
    return values


def _summarize_output(stdout: bytes) -> str:
    """Return a small redacted summary; never persist raw provider output."""

    candidates: list[str] = []
    for line in stdout.decode("utf-8", errors="replace").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            candidates.extend(_text_values(payload))
    if not candidates:
        return "Codex read-only worker completed; structured output was not retained."
    return _safe_output(candidates[-1]) or "Codex read-only worker completed."


def _safe_environment() -> dict[str, str]:
    """Pass only process plumbing and Codex's non-secret home selector."""

    return {key: value for key, value in os.environ.items() if key.casefold() in _ALLOWED_ENVIRONMENT_CASEFOLDED}


class CodexSubdelegationBoundary:
    """Validate one optional child request made through a Codex boundary.

    This object deliberately has no executable discovery, authentication, or
    process-launch code. Production JARVIS leaves the executor unset unless a
    separately approved Codex integration supplies it. Tests can inject a
    deterministic callback to exercise the same scope, timeout, cancellation,
    and single-child rules without creating a runtime AntiGravity dependency.
    """

    def __init__(self, child_executor: ChildExecutor | None = None) -> None:
        self._child_executor = child_executor
        self._claimed = False

    async def request(
        self,
        *,
        parent_provider: str,
        task: str,
        workspace_scope: str | Path,
        timeout_seconds: float,
        expected_paths: tuple[str, ...] = (),
        cancel_event: asyncio.Event | None = None,
    ) -> dict[str, object]:
        trace = ["requested"]

        def outcome(status: str, error_code: str | None = None, **values: object) -> dict[str, object]:
            result: dict[str, object] = {
                "status": status,
                "provider": "codex",
                "verification_status": "unverified",
                "trace": list(trace),
            }
            if error_code is not None:
                result["error_code"] = error_code
            result.update(values)
            return result

        if parent_provider.casefold() != "codex":
            trace.append("rejected_parent")
            return outcome("rejected", "codex_parent_required")
        if self._claimed:
            trace.append("rejected_limit")
            return outcome("rejected", "codex_child_limit_reached")
        if self._child_executor is None:
            trace.append("unavailable")
            return outcome("unavailable", "codex_child_executor_not_configured")
        bounded_task = str(task).strip()
        if not bounded_task or len(bounded_task) > 4_000 or any(marker in bounded_task.casefold() for marker in _SENSITIVE_TASK_MARKERS):
            trace.append("rejected_task")
            return outcome("rejected", "codex_child_task_rejected")
        try:
            scope = Path(workspace_scope).expanduser().resolve(strict=True)
        except (OSError, RuntimeError, TypeError, ValueError):
            trace.append("rejected_scope")
            return outcome("rejected", "codex_child_workspace_scope_required")
        if not scope.is_dir() or not (scope / ".git").exists():
            trace.append("rejected_scope")
            return outcome("rejected", "codex_child_workspace_scope_required")
        normalized_expected = {CodexDeveloperWorkerAdapter._normalize_relative_path(item) for item in expected_paths}
        if any(item is None for item in normalized_expected):
            trace.append("rejected_paths")
            return outcome("rejected", "codex_child_expected_path_invalid")
        try:
            bounded_timeout = min(max(float(timeout_seconds), 0.01), _MAX_CHILD_TIMEOUT_SECONDS)
        except (TypeError, ValueError):
            trace.append("rejected_timeout")
            return outcome("rejected", "codex_child_timeout_invalid")

        self._claimed = True
        trace.append("claimed")
        child_id = f"codex-child-{uuid4()}"
        work = asyncio.create_task(self._child_executor(bounded_task, scope, bounded_timeout))
        cancel_task: asyncio.Task[bool] | None = None
        try:
            if cancel_event is None:
                try:
                    raw = await asyncio.wait_for(work, timeout=bounded_timeout)
                except asyncio.TimeoutError:
                    trace.append("timed_out")
                    return outcome("failed", "codex_child_timeout", child_id=child_id)
            else:
                cancel_task = asyncio.create_task(cancel_event.wait())
                done, _ = await asyncio.wait(
                    {work, cancel_task},
                    timeout=bounded_timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    trace.append("timed_out")
                    return outcome("failed", "codex_child_timeout", child_id=child_id)
                if cancel_task in done and cancel_event.is_set() and work not in done:
                    trace.append("cancelled")
                    return outcome("cancelled", "codex_child_cancelled", child_id=child_id)
                raw = work.result()
        except Exception as exc:
            trace.append("failed")
            return outcome("failed", f"codex_child_failed:{exc.__class__.__name__}", child_id=child_id)
        finally:
            if cancel_task is not None and not cancel_task.done():
                cancel_task.cancel()
                await asyncio.gather(cancel_task, return_exceptions=True)
            if not work.done():
                work.cancel()
                await asyncio.gather(work, return_exceptions=True)

        if not isinstance(raw, dict):
            trace.append("failed")
            return outcome("failed", "codex_child_result_invalid", child_id=child_id)
        raw_status = str(raw.get("status", "")).casefold()
        if raw_status not in {"completed", "succeeded"}:
            trace.append("failed")
            return outcome("failed", "codex_child_result_not_completed", child_id=child_id)
        changes: list[str] = []
        raw_changes = raw.get("changes", ())
        if not isinstance(raw_changes, (list, tuple)) or not all(isinstance(item, str) for item in raw_changes):
            trace.append("failed")
            return outcome("failed", "codex_child_changes_invalid", child_id=child_id)
        for item in raw_changes:
            normalized = CodexDeveloperWorkerAdapter._normalize_relative_path(item)
            if normalized is None:
                trace.append("failed")
                return outcome("failed", "codex_child_change_scope_invalid", child_id=child_id)
            changes.append(normalized)
        if normalized_expected and not normalized_expected.issubset(set(changes)):
            trace.append("failed")
            return outcome("failed", "codex_child_expected_change_missing", child_id=child_id, changes=changes)
        trace.append("completed")
        return outcome(
            "completed",
            child_id=child_id,
            summary=_safe_output(str(raw.get("summary", "Codex child completed."))),
            changes=changes,
            verification_reason="child output is untrusted; Codex parent must review and verify",
        )


class DeveloperWorkerGateway:
    """Capability discovery and explicit adapter boundary for developer workers."""

    def __init__(self, *, adapter: Any = _UNSET, enabled: bool = False) -> None:
        self._providers = self._discover()
        if adapter is _UNSET and enabled:
            codex = next((item for item in self._providers if item.name == "codex" and item.available), None)
            self.adapter = CodexDeveloperWorkerAdapter(codex.executable) if codex else None
        elif adapter is _UNSET:
            self.adapter = None
        else:
            self.adapter = adapter

    @staticmethod
    def _discover() -> tuple[DeveloperWorkerProvider, ...]:
        candidates = (("codex", "codex"),)
        providers: list[DeveloperWorkerProvider] = []
        for name, executable in candidates:
            resolved = shutil.which(executable)
            providers.append(DeveloperWorkerProvider(name, resolved or executable, bool(resolved), "installed" if resolved else "not_installed"))
        return tuple(providers)

    def providers(self) -> tuple[DeveloperWorkerProvider, ...]:
        return self._providers

    @property
    def enabled(self) -> bool:
        return self.adapter is not None

    async def run(
        self,
        provider: str,
        task: str,
        workspace_scope: str | None = None,
        *,
        timeout_seconds: float = 60.0,
        mode: str = "read_only",
        allow_antigravity_subdelegation: bool = False,
        expected_paths: tuple[str, ...] = (),
    ) -> dict[str, object]:
        selected = next((item for item in self._providers if item.name == provider), None)
        if selected is None or not selected.available:
            return {"status": "unavailable", "provider": provider, "error_code": "developer_cli_not_available"}
        if self.adapter is None:
            return {"status": "deferred", "provider": provider, "error_code": "developer_worker_adapter_not_configured"}
        bounded_timeout = _bounded_timeout(timeout_seconds)
        if hasattr(self.adapter, "run"):
            runner = self.adapter.run
            if mode == "read_only" and not allow_antigravity_subdelegation and not expected_paths:
                result = runner(task, workspace_scope, bounded_timeout)
            else:
                try:
                    result = runner(
                        task,
                        workspace_scope,
                        bounded_timeout,
                        mode=mode,
                        allow_antigravity_subdelegation=allow_antigravity_subdelegation,
                        expected_paths=expected_paths,
                    )
                except TypeError:
                    return {"status": "rejected", "provider": provider, "error_code": "developer_worker_mode_unsupported"}
        else:
            result = self.adapter(task, workspace_scope, bounded_timeout)
        return await result if inspect.isawaitable(result) else result

    async def request_codex_child(
        self,
        task: str,
        workspace_scope: str,
        *,
        timeout_seconds: float = 60.0,
        expected_paths: tuple[str, ...] = (),
        cancel_event: asyncio.Event | None = None,
    ) -> dict[str, object]:
        """Expose the optional child seam only through the Codex adapter."""

        selected = next((item for item in self._providers if item.name == "codex"), None)
        if selected is None or not selected.available:
            return {"status": "unavailable", "provider": "codex", "error_code": "developer_cli_not_available"}
        if not isinstance(self.adapter, CodexDeveloperWorkerAdapter):
            return {"status": "unavailable", "provider": "codex", "error_code": "codex_child_boundary_not_configured"}
        return await self.adapter.request_child(
            task,
            workspace_scope,
            timeout_seconds=timeout_seconds,
            expected_paths=expected_paths,
            cancel_event=cancel_event,
        )


class CodexDeveloperWorkerAdapter:
    """Run Codex in a bounded read-only or approved workspace-write scope."""

    name = "codex"

    def __init__(
        self,
        executable: str | None = None,
        *,
        process_executor: ProcessExecutor | None = None,
        child_boundary: CodexSubdelegationBoundary | None = None,
    ) -> None:
        self.executable = executable or shutil.which("codex")
        self._process_executor = process_executor
        self._child_boundary = child_boundary

    @property
    def available(self) -> bool:
        return bool(self.executable)

    async def request_child(
        self,
        task: str,
        workspace_scope: str,
        *,
        timeout_seconds: float = 60.0,
        expected_paths: tuple[str, ...] = (),
        cancel_event: asyncio.Event | None = None,
    ) -> dict[str, object]:
        """Request a child only through an explicitly supplied Codex seam.

        No default boundary is created here; a normal JARVIS deployment cannot
        launch or authenticate to AntiGravity by calling this method.
        """

        if self._child_boundary is None:
            return {"status": "unavailable", "provider": self.name, "error_code": "codex_child_boundary_not_configured"}
        return await self._child_boundary.request(
            parent_provider=self.name,
            task=task,
            workspace_scope=workspace_scope,
            timeout_seconds=timeout_seconds,
            expected_paths=expected_paths,
            cancel_event=cancel_event,
        )

    @staticmethod
    def _scope(workspace_scope: str | None) -> Path | None:
        if not workspace_scope:
            return None
        try:
            scope = Path(workspace_scope).expanduser().resolve(strict=True)
        except (OSError, RuntimeError, ValueError):
            return None
        if not scope.is_dir() or not (scope / ".git").exists():
            return None
        return scope

    @staticmethod
    def _task(task: str) -> str | None:
        value = str(task).strip()
        if not value or len(value) > _MAX_TASK_CHARS:
            return None
        lowered = value.casefold()
        if any(marker in lowered for marker in _SENSITIVE_TASK_MARKERS):
            return None
        return value

    def command(
        self,
        task: str,
        scope: Path,
        *,
        mode: str = "read_only",
        allow_antigravity_subdelegation: bool = False,
    ) -> tuple[str, ...]:
        assert self.executable is not None
        if mode not in {"read_only", "workspace_write"}:
            raise ValueError("developer_worker_mode_invalid")
        sandbox = "workspace-write" if mode == "workspace_write" else "read-only"
        write_rule = (
            " You may modify files only inside the approved workspace; do not rewrite Git history, "
            "force-push, access credentials, or change files outside the workspace."
            if mode == "workspace_write"
            else " Do not modify files."
        )
        delegation_rule = (
            " You may request one bounded AntiGravity child subtask through the approved Codex interface; "
            "the child has the same workspace boundary and its output is untrusted."
            if allow_antigravity_subdelegation
            else " Do not delegate to AntiGravity."
        )
        prompt = (
            "You are a bounded JARVIS developer worker. Work inside the provided "
            "workspace only. Do not inspect or reveal secrets, "
            "credentials, cookies, tokens, private keys, environment files, or data "
            f"outside the workspace.{write_rule}{delegation_rule} Return a concise factual "
            "summary and do not claim verification you did not perform.\n\nTask: "
            f"{task}"
        )
        return (
            self.executable,
            "exec",
            "--sandbox",
            sandbox,
            "--ephemeral",
            "--json",
            "--cd",
            str(scope),
            prompt,
        )

    async def run(
        self,
        task: str,
        workspace_scope: str | None,
        timeout_seconds: float,
        *,
        mode: str = "read_only",
        allow_antigravity_subdelegation: bool = False,
        expected_paths: tuple[str, ...] = (),
    ) -> dict[str, object]:
        if not self.available:
            return {"status": "unavailable", "provider": self.name, "error_code": "developer_cli_not_available"}
        scope = self._scope(workspace_scope)
        if scope is None:
            return {"status": "rejected", "provider": self.name, "error_code": "worker_workspace_scope_required"}
        bounded_task = self._task(task)
        if bounded_task is None:
            return {"status": "rejected", "provider": self.name, "error_code": "worker_task_rejected"}
        if mode not in {"read_only", "workspace_write"}:
            return {"status": "rejected", "provider": self.name, "error_code": "developer_worker_mode_invalid"}
        if mode == "workspace_write":
            lowered = bounded_task.casefold()
            if any(marker in lowered for marker in _FORBIDDEN_WRITE_MARKERS):
                return {"status": "rejected", "provider": self.name, "error_code": "developer_worker_git_policy_rejected"}
            before = self._git_changed_paths(scope)
            if before is None:
                return {"status": "rejected", "provider": self.name, "error_code": "worker_git_workspace_required"}
        else:
            before = None
        try:
            command = self.command(
                bounded_task,
                scope,
                mode=mode,
                allow_antigravity_subdelegation=allow_antigravity_subdelegation,
            )
        except ValueError as exc:
            return {"status": "rejected", "provider": self.name, "error_code": str(exc)}
        execution = await self._execute(command, scope, _bounded_timeout(timeout_seconds))
        if execution.timed_out:
            return {
                "status": "failed",
                "provider": self.name,
                "worker_id": f"codex-{uuid4()}",
                "summary": f"Codex {mode} worker timed out.",
                "changes": [],
                "error_code": "developer_worker_timeout",
            }
        if execution.returncode != 0:
            return {
                "status": "failed",
                "provider": self.name,
                "worker_id": f"codex-{uuid4()}",
                "summary": f"Codex {mode} worker exited with code {execution.returncode}.",
                "changes": [],
                "error_code": f"codex_exit_{execution.returncode}",
            }
        changes = []
        if mode == "workspace_write":
            after = self._git_changed_paths(scope)
            if after is None:
                return {"status": "failed", "provider": self.name, "error_code": "worker_git_postcondition_unavailable", "changes": []}
            changes = sorted(after - (before or set()))
            expected = {self._normalize_relative_path(item) for item in expected_paths}
            if any(item is None for item in expected):
                return {"status": "failed", "provider": self.name, "error_code": "worker_expected_path_invalid", "changes": changes}
            if expected and not expected.issubset(set(changes)):
                return {"status": "failed", "provider": self.name, "error_code": "worker_expected_change_missing", "changes": changes}
            if any(self._sensitive_relative_path(item) for item in changes):
                return {"status": "failed", "provider": self.name, "error_code": "worker_sensitive_path_changed", "changes": changes}
        return {
            "status": "completed",
            "provider": self.name,
            "worker_id": f"codex-{uuid4()}",
            "summary": _summarize_output(execution.stdout),
            "artifacts": [],
            "changes": changes,
            "output_truncated": execution.output_truncated,
            "mode": mode,
            "allow_antigravity_subdelegation": bool(allow_antigravity_subdelegation),
        }

    @staticmethod
    def _normalize_relative_path(value: str) -> str | None:
        candidate = str(value).replace("\\", "/").strip().lstrip("./")
        if not candidate or candidate.startswith("/") or candidate == ".." or candidate.startswith("../"):
            return None
        return candidate

    @staticmethod
    def _sensitive_relative_path(value: str) -> bool:
        lowered = value.casefold()
        return lowered == ".env" or lowered.startswith(".env.") or any(
            marker in lowered for marker in ("credential", "secret", "token", "private.key")
        )

    @staticmethod
    def _git_changed_paths(scope: Path) -> set[str] | None:
        try:
            result = subprocess.run(
                ("git", "-C", str(scope), "status", "--porcelain=v1", "--untracked-files=all"),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=3.0,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        paths: set[str] = set()
        for line in result.stdout.splitlines():
            if len(line) >= 4:
                raw = line[3:].strip().strip('"')
                if " -> " in raw:
                    raw = raw.rsplit(" -> ", 1)[-1]
                normalized = CodexDeveloperWorkerAdapter._normalize_relative_path(raw)
                if normalized is not None:
                    paths.add(normalized)
        return paths

    async def _execute(self, command: tuple[str, ...], scope: Path, timeout_seconds: float) -> _ProcessExecution:
        if self._process_executor is not None:
            return await self._process_executor(command, scope, timeout_seconds)
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(scope),
            env=_safe_environment(),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        assert process.stdout is not None
        assert process.stderr is not None
        stdout_task = asyncio.create_task(self._read_bounded(process.stdout))
        stderr_task = asyncio.create_task(self._read_bounded(process.stderr))
        timed_out = False
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            timed_out = True
            if process.returncode is None:
                await self._terminate_process_tree(process.pid)
                await process.wait()
        try:
            stdout_result, stderr_result = await asyncio.wait_for(asyncio.gather(stdout_task, stderr_task), timeout=2.0)
        except asyncio.TimeoutError:
            stdout_task.cancel()
            stderr_task.cancel()
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            stdout_result, stderr_result = (b"", False), (b"", False)
        return _ProcessExecution(
            int(process.returncode or 0),
            stdout_result[0],
            b"",
            timed_out,
            stdout_result[1] or stderr_result[1],
        )

    @staticmethod
    async def _terminate_process_tree(pid: int) -> None:
        """Terminate only the timed-out worker and its descendants."""

        if os.name == "nt":
            system_root = os.environ.get("SystemRoot", r"C:\Windows")
            taskkill = Path(system_root) / "System32" / "taskkill.exe"
            executable = str(taskkill) if taskkill.is_file() else shutil.which("taskkill")
            if executable:
                try:
                    cleanup = await asyncio.create_subprocess_exec(
                        executable,
                        "/PID",
                        str(pid),
                        "/T",
                        "/F",
                        stdin=asyncio.subprocess.DEVNULL,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    await asyncio.wait_for(cleanup.wait(), timeout=2.0)
                    return
                except (OSError, asyncio.TimeoutError):
                    pass
        # POSIX fallback and Windows hosts without taskkill.
        try:
            os.kill(pid, 9)
        except OSError:
            pass

    @staticmethod
    async def _read_bounded(stream: Any) -> tuple[bytes, bool]:
        data = await stream.read(_MAX_OUTPUT_BYTES + 1)
        return data[:_MAX_OUTPUT_BYTES], len(data) > _MAX_OUTPUT_BYTES


class OpenClawDeveloperWorkerAdapter:
    """Reserved ACP/OpenClaw seam; it never imports or starts OpenClaw."""

    name = "openclaw"

    def __init__(self, executor: Callable[[str, str | None, float], Awaitable[dict[str, object]] | dict[str, object]] | None = None) -> None:
        self.executor = executor

    @property
    def available(self) -> bool:
        return self.executor is not None

    async def run(
        self,
        task: str,
        workspace_scope: str | None,
        timeout_seconds: float,
        *,
        mode: str = "read_only",
        allow_antigravity_subdelegation: bool = False,
        expected_paths: tuple[str, ...] = (),
    ) -> dict[str, object]:
        if self.executor is None:
            return {"status": "deferred", "error_code": "openclaw_adapter_not_configured"}
        if mode != "read_only" or allow_antigravity_subdelegation or expected_paths:
            return {"status": "rejected", "error_code": "openclaw_mode_unsupported"}
        result = self.executor(task, workspace_scope, timeout_seconds)
        return await result if inspect.isawaitable(result) else result
