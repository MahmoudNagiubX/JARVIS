"""A bounded local workspace provider exposed through the MCP boundary."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from ..contracts import ToolContext
from .models import MCPDiscoveredTool, MCPServerHealth, MCPServerState, now_utc


class LocalWorkspaceMCP:
    """Read registered workspace files and gate mutations at the host."""

    server_id = "workspace"
    execution_timeout_seconds = 10.0
    _allowed_suffixes = frozenset({".md", ".txt", ".rst", ".py", ".json", ".toml", ".yaml", ".yml"})

    def __init__(self, workspace: object, *, max_file_bytes: int = 250_000) -> None:
        self.workspace = workspace
        self.max_file_bytes = max(1_000, min(max_file_bytes, 2_000_000))
        self.tools = (
            MCPDiscoveredTool(self.server_id, "read_file", "Read one bounded file from a registered project", {"type": "object", "properties": {"project_id": {"type": "string", "maxLength": 200}, "path": {"type": "string", "maxLength": 500}}, "required": ["project_id", "path"], "additionalProperties": False}),
            MCPDiscoveredTool(self.server_id, "list_files", "List bounded entries in a registered project directory", {"type": "object", "properties": {"project_id": {"type": "string", "maxLength": 200}, "path": {"type": "string", "maxLength": 500}}, "required": ["project_id"], "additionalProperties": False}),
            MCPDiscoveredTool(self.server_id, "write_file", "Write bounded text inside a registered project", {"type": "object", "properties": {"project_id": {"type": "string", "maxLength": 200}, "path": {"type": "string", "maxLength": 500}, "content": {"type": "string", "maxLength": 16000}}, "required": ["project_id", "path", "content"], "additionalProperties": False}),
        )
        self.health = MCPServerHealth(self.server_id, MCPServerState.READY, len(self.tools), checked_at=now_utc())

    async def discover(self) -> tuple[MCPDiscoveredTool, ...]:
        self.health = MCPServerHealth(self.server_id, MCPServerState.READY, len(self.tools), checked_at=now_utc())
        return self.tools

    async def call_tool_with_context(self, name: str, arguments: Mapping[str, object], context: ToolContext) -> dict[str, object]:
        if context.identity is None or context.device is None:
            return {"status": "denied", "error_code": "identity_or_device_missing"}
        project_id = arguments.get("project_id")
        if not isinstance(project_id, str) or not project_id.strip() or len(project_id) > 200:
            return {"status": "denied", "error_code": "workspace_project_id_required"}
        project = await self.workspace.get(context.identity.owner_id, project_id)
        if project is None or not project.approved:
            return {"status": "denied", "error_code": "workspace_project_not_registered"}
        root = Path(project.repo_path).expanduser().resolve(strict=True)
        if name == "list_files":
            target = self._safe_path(root, arguments.get("path", "."), allow_directory=True)
            if target is None:
                return {"status": "denied", "error_code": "workspace_path_outside_project"}
            entries = sorted(item.name for item in target.iterdir() if not item.is_symlink())[:100]
            return {"path": str(target.relative_to(root)) if target != root else ".", "entries": entries}
        raw_path = arguments.get("path")
        target = self._safe_path(root, raw_path, allow_directory=False, allow_missing=name == "write_file")
        if target is None:
            return {"status": "denied", "error_code": "workspace_path_outside_project"}
        if name == "read_file":
            if not target.is_file() or target.suffix.casefold() not in self._allowed_suffixes:
                return {"status": "denied", "error_code": "workspace_file_not_allowed"}
            if target.stat().st_size > self.max_file_bytes:
                return {"status": "denied", "error_code": "workspace_file_too_large"}
            content = target.read_text(encoding="utf-8", errors="replace")
            title = next((line.removeprefix("#").strip() for line in content.splitlines() if line.startswith("#")), None)
            return {"path": str(target.relative_to(root)), "title": title, "content": content[: self.max_file_bytes]}
        if name == "write_file":
            content = arguments.get("content")
            if not isinstance(content, str) or not content or len(content) > 16_000 or "\x00" in content:
                return {"status": "denied", "error_code": "workspace_content_invalid"}
            if target.suffix.casefold() not in self._allowed_suffixes:
                return {"status": "denied", "error_code": "workspace_file_not_allowed"}
            target.write_text(content, encoding="utf-8")
            return {"path": str(target.relative_to(root)), "written": len(content)}
        return {"status": "failed", "error_code": "workspace_tool_not_found"}

    def _safe_path(self, root: Path, raw: object, *, allow_directory: bool, allow_missing: bool = False) -> Path | None:
        if not isinstance(raw, str) or not raw.strip() or len(raw) > 500:
            return None
        requested = Path(raw)
        if requested.is_absolute() or ".." in requested.parts:
            return None
        lexical = root.joinpath(*requested.parts)
        try:
            resolved = lexical.resolve(strict=not allow_missing)
        except OSError:
            return None
        if resolved != root and root not in resolved.parents:
            return None
        current = root
        for part in requested.parts:
            current = current / part
            if current.is_symlink():
                return None
        if allow_missing and not resolved.exists() and not resolved.parent.is_dir():
            return None
        if allow_directory:
            return resolved if resolved.is_dir() else None
        return resolved if resolved.is_file() else resolved

    async def close(self) -> None:
        self.health = MCPServerHealth(self.server_id, MCPServerState.STOPPED, len(self.tools), checked_at=now_utc())
