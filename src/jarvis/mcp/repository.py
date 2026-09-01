"""A bounded repository inspection provider behind the MCP capability boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict

from ..contracts import ToolContext
from .models import MCPDiscoveredTool, MCPServerHealth, MCPServerState, now_utc


class LocalRepositoryMCP:
    """Expose existing approved workspace intelligence without adding shell access."""

    server_id = "repository"
    execution_timeout_seconds = 10.0

    def __init__(self, workspace: object) -> None:
        self.workspace = workspace
        self.tools = (
            MCPDiscoveredTool(
                self.server_id,
                "inspect_project",
                "Inspect metadata for an explicitly registered project",
                {
                    "type": "object",
                    "properties": {"project_id": {"type": "string", "maxLength": 200}},
                    "required": ["project_id"],
                    "additionalProperties": False,
                },
            ),
        )
        self.health = MCPServerHealth(self.server_id, MCPServerState.READY, len(self.tools), checked_at=now_utc())

    async def discover(self) -> tuple[MCPDiscoveredTool, ...]:
        self.health = MCPServerHealth(self.server_id, MCPServerState.READY, len(self.tools), checked_at=now_utc())
        return self.tools

    async def call_tool_with_context(self, name: str, arguments: Mapping[str, object], context: ToolContext) -> dict[str, object]:
        if context.identity is None or context.device is None:
            return {"status": "denied", "error_code": "identity_or_device_missing"}
        project_id = arguments.get("project_id")
        if name != "inspect_project" or not isinstance(project_id, str) or not project_id.strip() or len(project_id) > 200:
            return {"status": "denied", "error_code": "repository_project_id_required"}
        try:
            project = await self.workspace.inspect(context.identity.owner_id, project_id)
        except KeyError:
            return {"status": "denied", "error_code": "workspace_project_not_registered"}
        return {
            "project_id": project.project_id,
            "project_type": project.project_type,
            "current_branch": project.current_branch,
            "git_status": project.git_status,
            "recent_files": list(project.recent_files[:20]),
            "repo_map": asdict(project.repo_map),
        }

    async def close(self) -> None:
        self.health = MCPServerHealth(self.server_id, MCPServerState.STOPPED, len(self.tools), checked_at=now_utc())
