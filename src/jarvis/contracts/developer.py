"""Optional external developer-worker discovery and adapter contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class DeveloperWorkerProvider:
    name: str
    executable: str
    available: bool
    reason: str
    bounded: bool = True


class DeveloperWorkerAdapter(Protocol):
    name: str

    async def run(
        self,
        task: str,
        workspace_scope: str | None,
        timeout_seconds: float,
        *,
        mode: str = "read_only",
        allow_antigravity_subdelegation: bool = False,
        expected_paths: tuple[str, ...] = (),
    ) -> dict[str, object]: ...
