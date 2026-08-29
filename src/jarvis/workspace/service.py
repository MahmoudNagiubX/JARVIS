"""Deterministic project context for explicitly registered workspace roots."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..bus import InMemoryEventBus
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository
from ..world_state.workspace import WorkspaceContextService


@dataclass(frozen=True, slots=True)
class RepoMap:
    important_files: tuple[str, ...] = ()
    modules: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    entry_points: tuple[str, ...] = ()
    tests: tuple[str, ...] = ()
    configuration: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProjectMetadata:
    project_id: str
    owner_id: str
    repo_path: str
    project_type: str
    current_branch: str | None = None
    git_status: str = "unknown"
    recent_files: tuple[str, ...] = ()
    build_command: str | None = None
    test_command: str | None = None
    dev_command: str | None = None
    known_services: tuple[str, ...] = ()
    recent_failures: tuple[str, ...] = ()
    recent_successful_runs: tuple[str, ...] = ()
    active_tasks: tuple[str, ...] = ()
    related_goals: tuple[str, ...] = ()
    related_memories: tuple[str, ...] = ()
    repo_map: RepoMap = RepoMap()
    approved: bool = True
    updated_at: datetime | None = None


class WorkspaceIntelligenceService:
    """Owns metadata for approved roots; it never recursively indexes a disk."""

    def __init__(self, repository: RuntimeRepository, event_bus: InMemoryEventBus, context: WorkspaceContextService) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.context = context
        self._projects: dict[tuple[str, str], ProjectMetadata] = {}

    async def register(self, owner_id: str, repo_path: str, *, project_id: str | None = None) -> ProjectMetadata:
        path = self._approved_path(repo_path)
        if self.repository.owner(owner_id) is None:
            raise ValueError("workspace owner is unavailable")
        existing = self.repository.workspace_project(owner_id, str(path))
        project_id = project_id or (str(existing["id"]) if existing else f"project-{uuid4()}")
        metadata = self._discover(project_id, owner_id, path)
        self._projects[(owner_id, str(path))] = metadata
        self.repository.insert_workspace_project(metadata)
        await self._emit("workspace.project_detected", metadata, EventState.COMPLETED)
        return metadata

    async def inspect(self, owner_id: str, project_id: str) -> ProjectMetadata:
        metadata = self._find(owner_id, project_id)
        if metadata is None:
            raise KeyError(project_id)
        snapshot = await self.context.observe_project(owner_id, metadata.repo_path)
        updated = replace(metadata, current_branch=snapshot.branch, git_status=snapshot.status, recent_files=snapshot.changed_files, updated_at=datetime.now(UTC))
        self._projects[(owner_id, metadata.repo_path)] = updated
        self.repository.update_workspace_project(updated)
        await self._emit("workspace.project_opened", updated, EventState.COMPLETED)
        if metadata.current_branch != updated.current_branch:
            await self._emit("workspace.branch_changed", updated, EventState.COMPLETED, {"from": metadata.current_branch, "to": updated.current_branch})
        return updated

    async def list(self, owner_id: str) -> tuple[ProjectMetadata, ...]:
        for row in self.repository.workspace_projects(owner_id):
            self._hydrate(row)
        return tuple(sorted((item for (owner, _), item in self._projects.items() if owner == owner_id), key=lambda item: item.project_id))

    async def get(self, owner_id: str, project_id: str) -> ProjectMetadata | None:
        return self._find(owner_id, project_id)

    async def record_run(self, owner_id: str, project_id: str, *, kind: str, passed: bool, detail: str) -> ProjectMetadata:
        current = self._find(owner_id, project_id)
        if current is None:
            raise KeyError(project_id)
        event_name = f"workspace.{kind}_{'passed' if passed else 'failed'}"
        values = list(current.recent_successful_runs if passed else current.recent_failures)
        values.append(detail[:500])
        values = values[-20:]
        updated = replace(current, recent_successful_runs=tuple(values) if passed else current.recent_successful_runs, recent_failures=tuple(values) if not passed else current.recent_failures, updated_at=datetime.now(UTC))
        self._projects[(owner_id, current.repo_path)] = updated
        self.repository.update_workspace_project(updated)
        await self._emit(f"workspace.{kind}_started", updated, EventState.ACCEPTED)
        await self._emit(event_name, updated, EventState.COMPLETED if passed else EventState.FAILED, {"detail": detail[:500]})
        return updated

    def _find(self, owner_id: str, project_id: str) -> ProjectMetadata | None:
        for (owner, _), item in self._projects.items():
            if owner == owner_id and item.project_id == project_id:
                return item
        row = self.repository.workspace_project_by_id(owner_id, project_id)
        return self._hydrate(row) if row else None

    def _hydrate(self, row: Any) -> ProjectMetadata:
        data = json.loads(str(row["metadata_json"]))
        repo_map = RepoMap(**data.pop("repo_map", {}))
        data["repo_map"] = repo_map
        data["updated_at"] = datetime.fromisoformat(str(row["updated_at"])) if row.get("updated_at") else None
        data["approved"] = bool(row.get("approved", 1))
        item = ProjectMetadata(str(row["id"]), str(row["owner_id"]), str(row["repo_path"]), str(row["project_type"]), **{key: value for key, value in data.items() if key not in {"project_id", "owner_id", "repo_path", "project_type"}})
        self._projects[(item.owner_id, item.repo_path)] = item
        return item

    def _approved_path(self, raw: str) -> Path:
        path = Path(raw).expanduser().resolve()
        if not path.is_dir():
            raise ValueError("project root must be an existing directory")
        # The caller supplies an explicit root. We only inspect this directory
        # and its .git metadata; no recursive disk search is performed.
        return path

    def _discover(self, project_id: str, owner_id: str, path: Path) -> ProjectMetadata:
        names = {item.name for item in path.iterdir() if item.is_file() or item.is_dir()}
        config = tuple(sorted(name for name in names if name in {"pyproject.toml", "package.json", "Cargo.toml", "go.mod", "Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml", "README", "README.md", "README.rst", ".git"}))
        project_type, build, test, dev = "unknown", None, None, None
        if "pyproject.toml" in names:
            project_type, test = "python", "python -m unittest discover -s tests -q"
            build = "python -m compileall -q src" if "src" in names else None
            dev = "python -m jarvis --serve" if "src" in names else None
        elif "package.json" in names:
            project_type, test, build, dev = "node", "npm test", "npm run build", "npm run dev"
        elif "Cargo.toml" in names:
            project_type, test, build, dev = "rust", "cargo test", "cargo build", "cargo run"
        elif "go.mod" in names:
            project_type, test, build, dev = "go", "go test ./...", "go build ./...", "go run ."
        services = tuple(sorted(name for name in names if "compose" in name or name in {"Dockerfile", "Procfile"}))
        recent = self._git(path, "status", "--short").splitlines()[:20]
        changed = tuple(line[3:].strip() for line in recent if len(line) >= 4)
        branch = self._git(path, "branch", "--show-current").strip() or None
        modules = tuple(sorted(item.name for item in path.iterdir() if item.is_file() and item.suffix in {".py", ".ts", ".js", ".rs", ".go"}))[:40]
        tests = tuple(sorted(item.name for item in path.iterdir() if item.is_file() and (item.name.startswith("test") or "test" in item.name.casefold())))[:40]
        important = tuple(sorted(set(config) | set(modules[:10]) | set(tests[:10])))[:60]
        repo_map = RepoMap(important, modules, (), modules[:5], tests, config)
        return ProjectMetadata(project_id, owner_id, str(path), project_type, branch, "dirty" if changed else "clean", changed, build, test, dev, services, repo_map=repo_map, updated_at=datetime.now(UTC))

    async def _emit(self, event_type: str, metadata: ProjectMetadata, state: EventState, extra: dict[str, object] | None = None) -> None:
        event = Event.create(event_type, EventCategory.WORKSPACE, correlation_id=f"workspace-{metadata.project_id}", actor_id=metadata.owner_id, payload={"owner_id": metadata.owner_id, "project_id": metadata.project_id, "repo_path": metadata.repo_path, "project_type": metadata.project_type, **(extra or {})}, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)

    @staticmethod
    def _git(path: Path, *args: str) -> str:
        if shutil.which("git") is None:
            return ""
        try:
            result = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, timeout=5, check=False, shell=False)
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return result.stdout[:20_000] if result.returncode == 0 else ""
