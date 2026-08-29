"""Discover optional CLIs without installing or invoking them."""

from __future__ import annotations

import inspect
import shutil
from collections.abc import Awaitable, Callable

from ..contracts import DeveloperWorkerProvider


class DeveloperWorkerGateway:
    """Capability discovery and explicit adapter boundary for developer workers."""

    def __init__(self, *, adapter: Callable[[str, str | None, float], Awaitable[dict[str, object]] | dict[str, object]] | None = None) -> None:
        self.adapter = adapter
        self._providers = self._discover()

    @staticmethod
    def _discover() -> tuple[DeveloperWorkerProvider, ...]:
        candidates = (("codex", "codex"), ("gemini", "gemini"), ("antigravity", "antigravity"))
        return tuple(DeveloperWorkerProvider(name, executable, bool(shutil.which(executable)), "installed" if shutil.which(executable) else "not_installed") for name, executable in candidates)

    def providers(self) -> tuple[DeveloperWorkerProvider, ...]:
        return self._providers

    async def run(self, provider: str, task: str, workspace_scope: str | None = None, *, timeout_seconds: float = 60.0) -> dict[str, object]:
        selected = next((item for item in self._providers if item.name == provider), None)
        if selected is None or not selected.available:
            return {"status": "unavailable", "provider": provider, "error_code": "developer_cli_not_available"}
        if self.adapter is None:
            return {"status": "deferred", "provider": provider, "error_code": "developer_worker_adapter_not_configured"}
        result = self.adapter(task, workspace_scope, min(max(timeout_seconds, 1.0), 300.0))
        return await result if inspect.isawaitable(result) else result


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
