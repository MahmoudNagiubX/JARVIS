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

    async def run(self, provider: str, task: str, workspace_scope: str | None = None, *, timeout_seconds: float = 60.0) -> dict[str, object]:
        selected = next((item for item in self._providers if item.name == provider), None)
        if selected is None or not selected.available:
            return {"status": "unavailable", "provider": provider, "error_code": "developer_cli_not_available"}
        if self.adapter is None:
            return {"status": "deferred", "provider": provider, "error_code": "developer_worker_adapter_not_configured"}
        bounded_timeout = _bounded_timeout(timeout_seconds)
        if hasattr(self.adapter, "run"):
            result = self.adapter.run(task, workspace_scope, bounded_timeout)
        else:
            result = self.adapter(task, workspace_scope, bounded_timeout)
        return await result if inspect.isawaitable(result) else result


class CodexDeveloperWorkerAdapter:
    """Run the installed Codex CLI as a read-only, workspace-scoped worker.

    This adapter intentionally has no write mode. A future write path must be
    resumed only after the canonical ApprovalEngine decision is consumed by
    WorkerCoordinator; a CLI flag cannot stand in for that authority.
    """

    name = "codex"

    def __init__(self, executable: str | None = None, *, process_executor: ProcessExecutor | None = None) -> None:
        self.executable = executable or shutil.which("codex")
        self._process_executor = process_executor

    @property
    def available(self) -> bool:
        return bool(self.executable)

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

    def command(self, task: str, scope: Path) -> tuple[str, ...]:
        assert self.executable is not None
        prompt = (
            "You are a bounded JARVIS developer worker. Work read-only inside the "
            "provided workspace only. Do not modify files, inspect or reveal secrets, "
            "credentials, cookies, tokens, private keys, environment files, or data "
            "outside the workspace. Return a concise factual summary and do not claim "
            "verification you did not perform.\n\nTask: "
            f"{task}"
        )
        return (
            self.executable,
            "exec",
            "--sandbox",
            "read-only",
            "--ephemeral",
            "--json",
            "--cd",
            str(scope),
            prompt,
        )

    async def run(self, task: str, workspace_scope: str | None, timeout_seconds: float) -> dict[str, object]:
        if not self.available:
            return {"status": "unavailable", "provider": self.name, "error_code": "developer_cli_not_available"}
        scope = self._scope(workspace_scope)
        if scope is None:
            return {"status": "rejected", "provider": self.name, "error_code": "worker_workspace_scope_required"}
        bounded_task = self._task(task)
        if bounded_task is None:
            return {"status": "rejected", "provider": self.name, "error_code": "worker_task_rejected"}
        execution = await self._execute(self.command(bounded_task, scope), scope, _bounded_timeout(timeout_seconds))
        if execution.timed_out:
            return {
                "status": "failed",
                "provider": self.name,
                "worker_id": f"codex-{uuid4()}",
                "summary": "Codex read-only worker timed out.",
                "changes": [],
                "error_code": "developer_worker_timeout",
            }
        if execution.returncode != 0:
            return {
                "status": "failed",
                "provider": self.name,
                "worker_id": f"codex-{uuid4()}",
                "summary": f"Codex read-only worker exited with code {execution.returncode}.",
                "changes": [],
                "error_code": f"codex_exit_{execution.returncode}",
            }
        return {
            "status": "completed",
            "provider": self.name,
            "worker_id": f"codex-{uuid4()}",
            "summary": _summarize_output(execution.stdout),
            "artifacts": [],
            "changes": [],
            "output_truncated": execution.output_truncated,
        }

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

    async def run(self, task: str, workspace_scope: str | None, timeout_seconds: float) -> dict[str, object]:
        if self.executor is None:
            return {"status": "deferred", "error_code": "openclaw_adapter_not_configured"}
        result = self.executor(task, workspace_scope, timeout_seconds)
        return await result if inspect.isawaitable(result) else result
