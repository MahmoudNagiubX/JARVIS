"""Bounded JSON-RPC MCP stdio client with owned process lifecycle."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from .models import MCPDiscoveredTool, MCPRisk, MCPServerConfig, MCPServerHealth, MCPServerState, now_utc


class MCPError(Exception):
    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code


class MCPProtocolError(MCPError):
    pass


class MCPServerCrashedError(MCPError):
    pass


class MCPTimeoutError(MCPError, TimeoutError):
    pass


class MCPPayloadTooLarge(MCPError, ValueError):
    pass


class MCPDisabledError(MCPError):
    pass


class MCPStdioClient:
    """One lazily-started child process per configured local MCP server."""

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self.process: asyncio.subprocess.Process | None = None
        self.tools: tuple[MCPDiscoveredTool, ...] = ()
        self.health = MCPServerHealth.initial(config.server_id, config.enabled)
        self._request_lock = asyncio.Lock()
        self._call_slots = asyncio.Semaphore(config.max_concurrent_calls)
        self._next_id = 0
        self._stderr_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if not self.config.enabled:
            self.health = replace(self.health, state=MCPServerState.DISABLED, checked_at=now_utc())
            raise MCPDisabledError("mcp_server_disabled")
        if self.process is not None and self.process.returncode is None:
            return
        if self.process is not None:
            await self.close()
        working_directory: str | None = None
        if self.config.working_directory:
            path = Path(self.config.working_directory).expanduser().resolve(strict=True)
            if not path.is_dir():
                raise MCPError("mcp_working_directory_invalid")
            working_directory = str(path)
        environment = {key: self.config.environment[key] for key in self.config.environment_allowlist if key in self.config.environment}
        self.health = replace(self.health, state=MCPServerState.STARTING, last_error=None, checked_at=now_utc())
        try:
            self.process = await asyncio.create_subprocess_exec(
                self.config.command,
                *self.config.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_directory,
                env=environment,
                limit=self.config.max_response_bytes + 1,
            )
            self._stderr_task = asyncio.create_task(self._drain_stderr())
            await asyncio.wait_for(self._initialize(), timeout=self.config.startup_timeout_seconds)
        except asyncio.TimeoutError as exc:
            await self._stop_process()
            self._failed("mcp_start_timeout")
            raise MCPTimeoutError("mcp_start_timeout") from exc
        except asyncio.CancelledError:
            await asyncio.shield(self._stop_process())
            self._failed("mcp_start_cancelled")
            raise
        except MCPError:
            await self._stop_process()
            raise
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            await self._stop_process()
            self._failed("mcp_start_failed")
            raise MCPError("mcp_start_failed", str(exc)) from exc
        self.health = replace(self.health, state=MCPServerState.READY, checked_at=now_utc())

    async def discover(self) -> tuple[MCPDiscoveredTool, ...]:
        await self.start()
        try:
            result = await self._request("tools/list", {})
        except MCPError as exc:
            self._failed(exc.code)
            raise
        raw_tools = result.get("tools") if isinstance(result, Mapping) else None
        if not isinstance(raw_tools, list) or len(raw_tools) > 128:
            self._failed("mcp_tool_list_invalid")
            raise MCPProtocolError("mcp_tool_list_invalid")
        discovered: list[MCPDiscoveredTool] = []
        seen: set[str] = set()
        try:
            for raw in raw_tools:
                if not isinstance(raw, Mapping):
                    raise ValueError("mcp_tool_entry_invalid")
                name = raw.get("name")
                description = raw.get("description", "")
                schema = raw.get("inputSchema", {"type": "object", "additionalProperties": False})
                if not isinstance(name, str) or name in seen:
                    raise ValueError("mcp_tool_name_duplicate_or_invalid")
                seen.add(name)
                hint = raw.get("risk")
                risk_hint = MCPRisk(str(hint)) if hint in {item.value for item in MCPRisk} else None
                discovered.append(MCPDiscoveredTool(self.config.server_id, name, str(description), schema, risk_hint))
        except (TypeError, ValueError) as exc:
            self._failed("mcp_tool_metadata_invalid")
            raise MCPProtocolError("mcp_tool_metadata_invalid", str(exc)) from exc
        self.tools = tuple(discovered)
        self.health = replace(self.health, state=MCPServerState.READY, tool_count=len(self.tools), checked_at=now_utc(), last_error=None)
        return self.tools

    async def call_tool(self, name: str, arguments: Mapping[str, object]) -> dict[str, object]:
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise MCPProtocolError("mcp_tool_name_invalid")
        if not isinstance(arguments, Mapping):
            raise MCPProtocolError("mcp_arguments_must_be_object")
        await self.start()
        async with self._call_slots:
            try:
                result = await self._request("tools/call", {"name": name, "arguments": dict(arguments)}, timeout=self.config.execution_timeout_seconds)
            except asyncio.CancelledError:
                await asyncio.shield(self._stop_process())
                self._failed("mcp_call_cancelled")
                raise
            except MCPTimeoutError:
                await asyncio.shield(self._stop_process())
                self._failed("mcp_call_timeout")
                raise
            except MCPError:
                self._failed("mcp_call_failed")
                raise
        if not isinstance(result, Mapping):
            raise MCPProtocolError("mcp_tool_result_invalid")
        return {"server_id": self.config.server_id, "tool": name, "data": dict(result), "untrusted_content": True}

    async def close(self) -> None:
        await self._stop_process()
        if self.health.state is not MCPServerState.DISABLED:
            self.health = replace(self.health, state=MCPServerState.STOPPED, checked_at=now_utc())

    async def _initialize(self) -> None:
        await self._request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "jarvis", "version": "0.15.0"},
            },
            timeout=self.config.startup_timeout_seconds,
        )
        await self._notify("notifications/initialized", {})

    async def _request(self, method: str, params: Mapping[str, object], *, timeout: float | None = None) -> dict[str, object]:
        async with self._request_lock:
            if self.process is None or self.process.returncode is not None or self.process.stdin is None or self.process.stdout is None:
                raise MCPServerCrashedError("mcp_process_not_running")
            self._next_id += 1
            request = {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": dict(params)}
            encoded = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if len(encoded) > self.config.max_request_bytes:
                raise MCPPayloadTooLarge("mcp_request_payload_too_large")
            try:
                self.process.stdin.write(encoded + b"\n")
                await asyncio.wait_for(self.process.stdin.drain(), timeout=timeout or self.config.execution_timeout_seconds)
                line = await asyncio.wait_for(self.process.stdout.readline(), timeout=timeout or self.config.execution_timeout_seconds)
            except asyncio.TimeoutError as exc:
                raise MCPTimeoutError("mcp_request_timeout") from exc
            except (asyncio.LimitOverrunError, ValueError) as exc:
                raise MCPPayloadTooLarge("mcp_response_payload_too_large") from exc
            if not line:
                raise MCPServerCrashedError("mcp_process_exited")
            if len(line) > self.config.max_response_bytes:
                raise MCPPayloadTooLarge("mcp_response_payload_too_large")
            try:
                response = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise MCPProtocolError("mcp_response_malformed") from exc
            if not isinstance(response, Mapping) or response.get("id") != self._next_id:
                raise MCPProtocolError("mcp_response_id_mismatch")
            if isinstance(response.get("error"), Mapping):
                error = response["error"]
                raise MCPProtocolError(str(error.get("code", "mcp_remote_error")), str(error.get("message", "MCP server returned an error")))
            result = response.get("result")
            if not isinstance(result, Mapping):
                raise MCPProtocolError("mcp_response_result_invalid")
            return dict(result)

    async def _notify(self, method: str, params: Mapping[str, object]) -> None:
        async with self._request_lock:
            if self.process is None or self.process.stdin is None:
                raise MCPServerCrashedError("mcp_process_not_running")
            encoded = json.dumps({"jsonrpc": "2.0", "method": method, "params": dict(params)}, separators=(",", ":")).encode("utf-8")
            if len(encoded) > self.config.max_request_bytes:
                raise MCPPayloadTooLarge("mcp_notification_payload_too_large")
            self.process.stdin.write(encoded + b"\n")
            await self.process.stdin.drain()

    async def _drain_stderr(self) -> None:
        if self.process is None or self.process.stderr is None:
            return
        while await self.process.stderr.read(4_096):
            pass

    async def _stop_process(self) -> None:
        process = self.process
        self.process = None
        if process is not None and process.returncode is None:
            if process.stdin is not None:
                process.stdin.close()
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=1.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            try:
                await self._stderr_task
            except asyncio.CancelledError:
                pass
            self._stderr_task = None

    def _failed(self, error_code: str) -> None:
        self.health = replace(self.health, state=MCPServerState.FAILED, last_error=error_code, checked_at=now_utc())
