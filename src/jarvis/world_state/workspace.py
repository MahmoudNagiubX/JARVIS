"""Explicit, read-only active workspace context collection."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..contracts import Observation
from .service import DurableWorldStateService


@dataclass(frozen=True, slots=True)
class WorkspaceSnapshot:
    project_path: str
    project_name: str
    branch: str | None
    changed_files: tuple[str, ...] = ()
    status: str = "unknown"
    metadata: dict[str, object] = field(default_factory=dict)


class WorkspaceContextService:
    """Collects an explicit project snapshot; it does not watch screenshots/files."""

    def __init__(self, world_state: DurableWorldStateService) -> None:
        self.world_state = world_state

    async def observe_project(self, owner_id: str, project_path: str) -> WorkspaceSnapshot:
        path = Path(project_path).expanduser().resolve()
        if not path.is_dir():
            raise ValueError("project path must be a directory")
        branch = self._git(path, "branch", "--show-current").strip() or None
        porcelain = self._git(path, "status", "--short")
        changed = tuple(line[3:] for line in porcelain.splitlines() if len(line) >= 4)
        snapshot = WorkspaceSnapshot(str(path), path.name, branch, changed, "dirty" if changed else "clean")
        await self.world_state.observe(
            Observation(
                f"workspace-{path}", "git", datetime.now(UTC),
                "workspace", {"active_project": path.name, "project_path": str(path), "branch": branch, "changed_files": list(changed), "status": snapshot.status},
                1.0, owner_id, str(path), 300, None, 65, "clear", None, "owner",
            ), owner_id,
        )
        return snapshot

    @staticmethod
    def _git(path: Path, *args: str) -> str:
        if shutil.which("git") is None:
            return ""
        result = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, timeout=5, check=False, shell=False)
        return result.stdout if result.returncode == 0 else ""
