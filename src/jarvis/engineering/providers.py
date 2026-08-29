"""Provider seams for engineering tools; implementations are injected."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import replace

from ..contracts import EngineeringAction, EngineeringResult, EngineeringWorkspace


EngineeringExecutor = Callable[[EngineeringAction, EngineeringWorkspace], Awaitable[EngineeringResult] | EngineeringResult]


class _InjectedEngineeringProvider:
    def __init__(self, name: str, capabilities: tuple[str, ...], executor: EngineeringExecutor | None = None) -> None:
        self.name = name
        self._capabilities = capabilities
        self._executor = executor

    @property
    def available(self) -> bool:
        return self._executor is not None

    def capabilities(self) -> tuple[str, ...]:
        return self._capabilities

    async def execute(self, action: EngineeringAction, workspace: EngineeringWorkspace) -> EngineeringResult:
        if self._executor is None:
            return EngineeringResult(action.action_id or "unassigned", "failed", error_code=f"{self.name}_adapter_not_configured")
        result = self._executor(action, workspace)
        if inspect.isawaitable(result):
            result = await result
        return result


class JupyterEngineeringProvider(_InjectedEngineeringProvider):
    """Adapter boundary informed by the read-only Jupyter MCP donor audit."""

    def __init__(self, executor: EngineeringExecutor | None = None) -> None:
        super().__init__("jupyter", ("list", "inspect", "read", "insert", "edit", "execute", "restart", "output", "plot", "error"), executor)


class KiCadEngineeringProvider(_InjectedEngineeringProvider):
    """KiCad IPC/provider boundary; no donor or desktop process is imported."""

    def __init__(self, executor: EngineeringExecutor | None = None) -> None:
        super().__init__("kicad", ("inspect_board", "read_schematic", "edit", "erc", "plot"), executor)


class InMemoryEngineeringProvider(_InjectedEngineeringProvider):
    """Deterministic test provider, intentionally not a production adapter."""

    def __init__(self) -> None:
        async def execute(action: EngineeringAction, workspace: EngineeringWorkspace) -> EngineeringResult:
            output = {"provider": "in_memory", "action": action.action, "target": action.target, "workspace": workspace.workspace_id}
            return EngineeringResult(action.action_id or "unassigned", "completed", output=output, verified=True)

        super().__init__("in_memory", ("list", "inspect", "read", "insert", "edit", "execute", "output"), execute)
