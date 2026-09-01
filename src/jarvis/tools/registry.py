"""Static versioned capability catalog inspired by BMO Phase 08."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
import os
import subprocess
import sys
from typing import Any

from ..contracts import BrowserAction, ToolContext, ToolResult, ToolResultRetention, ToolResultStatus

ToolHandler = Callable[[Mapping[str, Any], ToolContext], ToolResult | Awaitable[ToolResult]]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    tool_id: str
    name: str
    version: str
    description: str
    risk_level: str
    required_scope: str
    required_capabilities: frozenset[str]
    timeout_seconds: float
    idempotent: bool
    handler: ToolHandler
    requires_approval: bool = False
    enabled: bool = True
    autonomy_level: int = 1
    parameters_schema: Mapping[str, object] = field(default_factory=lambda: {"type": "object", "additionalProperties": False})
    retention: ToolResultRetention = ToolResultRetention.DURABLE
    argument_retention: ToolResultRetention = ToolResultRetention.DURABLE

    def json_schema(self) -> dict[str, object]:
        return dict(self.parameters_schema)

    def validate_arguments(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(arguments, Mapping):
            raise ValueError("arguments_must_be_object")
        normalized = dict(arguments)
        if any(token in key.casefold() for key in normalized for token in ("secret", "token", "password", "credential")):
            raise ValueError("sensitive_arguments_not_supported_in_phase02")
        if self.name.endswith("status.read") and normalized:
            raise ValueError("status_read_takes_no_arguments")
        if self.name.endswith("echo.reversible") or self.name.endswith("echo.consequential"):
            if not isinstance(normalized.get("message"), str) or not normalized["message"].strip():
                raise ValueError("message_required")
            if len(normalized["message"]) > 2000:
                raise ValueError("message_too_long")
        if self.name == "project.tests.run":
            project_path = normalized.get("project_path")
            if not isinstance(project_path, str) or not project_path.strip():
                raise ValueError("project_path_required")
            if len(project_path) > 1000:
                raise ValueError("project_path_too_long")
            test_file = normalized.get("test_file")
            if test_file is not None and (not isinstance(test_file, str) or len(test_file) > 300 or ".." in Path(test_file).parts):
                raise ValueError("test_file_invalid")
        if self.name == "screen.observe":
            mode = normalized.get("mode", "semantic")
            if mode not in {"semantic", "screen"}:
                raise ValueError("perception_mode_invalid")
            region = normalized.get("region")
            if region is not None and (not isinstance(region, Mapping) or set(region) != {"x", "y", "width", "height"}):
                raise ValueError("perception_region_invalid")
        properties = self.parameters_schema.get("properties", {})
        required = self.parameters_schema.get("required", ())
        if isinstance(properties, Mapping) and self.parameters_schema.get("additionalProperties") is False:
            unknown = set(normalized) - set(properties)
            if unknown:
                raise ValueError(f"unknown_arguments:{sorted(unknown)}")
        if isinstance(required, (list, tuple)):
            missing = [key for key in required if key not in normalized]
            if missing:
                raise ValueError(f"missing_arguments:{sorted(missing)}")
        return normalized


class ToolRegistry:
    def __init__(self, specs: tuple[ToolSpec, ...] = ()) -> None:
        self._specs: dict[tuple[str, str], ToolSpec] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: ToolSpec) -> None:
        key = (spec.name, spec.version)
        if key in self._specs:
            raise ValueError(f"duplicate tool: {spec.name}@{spec.version}")
        self._specs[key] = spec

    def get(self, name: str, version: str = "1") -> ToolSpec | None:
        return self._specs.get((name, version))

    def list(self) -> tuple[ToolSpec, ...]:
        return tuple(sorted(self._specs.values(), key=lambda spec: (spec.name, spec.version)))


def _status(_: Mapping[str, Any], __: ToolContext) -> ToolResult:
    return ToolResult(ToolResultStatus.SUCCEEDED, {"ok": True, "state": "ready"}, verified=True)


def _echo(arguments: Mapping[str, Any], __: ToolContext) -> ToolResult:
    return ToolResult(ToolResultStatus.SUCCEEDED, {"ok": True, "message": arguments["message"]}, verified=True)


def _run_tests(arguments: Mapping[str, Any], __: ToolContext) -> ToolResult:
    """Run only the fixed stdlib unittest discovery command in a repo."""
    path = Path(str(arguments["project_path"])).expanduser().resolve()
    if not path.is_dir() or not (path / "tests").is_dir():
        return ToolResult(ToolResultStatus.DENIED, error_code="tests_directory_missing")
    test_file = str(arguments.get("test_file", ""))
    if not test_file and (path / "tests" / "test_bootstrap.py").is_file():
        test_file = "test_bootstrap.py"
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"]
    environment = os.environ.copy()
    source_path = path / "src"
    if source_path.is_dir():
        environment["PYTHONPATH"] = os.pathsep.join(
            item for item in (str(source_path), environment.get("PYTHONPATH", "")) if item
        )
    if test_file:
        target = (path / "tests" / test_file).resolve()
        if path not in target.parents or not target.is_file():
            return ToolResult(ToolResultStatus.DENIED, error_code="test_file_missing")
        command.extend(["-p", target.name])
    try:
        result = subprocess.run(
            command,
            cwd=path,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(ToolResultStatus.FAILED, error_code="test_timeout")
    output = (result.stdout + result.stderr)[-4000:]
    if result.returncode != 0:
        return ToolResult(ToolResultStatus.FAILED, {"returncode": result.returncode, "output": output}, "tests_failed")
    return ToolResult(ToolResultStatus.SUCCEEDED, {"returncode": 0, "output": output}, verified=True)


def default_registry() -> ToolRegistry:
    return ToolRegistry(
        (
            ToolSpec(
                "tool-status-read-v1", "status.read", "1", "Read bounded JARVIS status.",
                "read", "tool.request", frozenset(), 5.0, True, _status,
                parameters_schema={"type": "object", "properties": {}, "additionalProperties": False},
            ),
            ToolSpec(
                "tool-echo-reversible-v1", "echo.reversible", "1", "Return a bounded reversible test value.",
                "reversible", "tool.request", frozenset(), 5.0, True, _echo,
                parameters_schema={"type": "object", "properties": {"message": {"type": "string", "maxLength": 2000}}, "required": ["message"], "additionalProperties": False},
            ),
            ToolSpec(
                "tool-echo-consequential-v1", "echo.consequential", "1", "Return a consequential approval fixture.",
                "consequential", "tool.request", frozenset(), 5.0, True, _echo, True,
                parameters_schema={"type": "object", "properties": {"message": {"type": "string", "maxLength": 2000}}, "required": ["message"], "additionalProperties": False},
            ),
            ToolSpec(
                "tool-project-tests-run-v1", "project.tests.run", "1", "Run bounded local unittest discovery.",
                "safe", "tool.request", frozenset(), 35.0, False, _run_tests, False, True, 1,
                parameters_schema={"type": "object", "properties": {"project_path": {"type": "string", "maxLength": 1000}, "test_file": {"type": "string", "maxLength": 300}}, "required": ["project_path"], "additionalProperties": False},
            ),
        )
    )


def register_browser_tools(registry: ToolRegistry, browser_actions: object) -> None:
    """Expose browser reads and interactions through the existing authority."""

    async def execute(action: str, arguments: Mapping[str, object], context: ToolContext) -> ToolResult:
        if context.identity is None or context.device is None:
            return ToolResult(ToolResultStatus.DENIED, error_code="identity_or_device_missing")
        result = await browser_actions.execute(
            BrowserAction(action, dict(arguments)),
            context.identity,
            context.device,
            session_id=context.session_id,
            correlation_id=context.correlation_id,
        )
        try:
            status = ToolResultStatus(result.status)
        except ValueError:
            status = ToolResultStatus.FAILED
        if status is ToolResultStatus.APPROVAL_REQUIRED:
            return ToolResult(status, error_code=result.error_code, approval_id=result.approval_id)
        return ToolResult(status, result.output, result.error_code, result.verified, result.approval_id)

    schemas: tuple[tuple[str, str, Mapping[str, object], tuple[str, ...]], ...] = (
        ("open_url", "Open a bounded public web URL in a JARVIS browser session.", {"type": "object", "properties": {"url": {"type": "string", "maxLength": 4096}}, "required": ["url"], "additionalProperties": False}, ("url",)),
        ("navigate", "Navigate an existing browser session to a bounded public URL.", {"type": "object", "properties": {"session_id": {"type": "string", "maxLength": 100}, "url": {"type": "string", "maxLength": 4096}}, "required": ["session_id", "url"], "additionalProperties": False}, ("session_id", "url")),
        ("read_page", "Read bounded untrusted text from an existing browser session.", {"type": "object", "properties": {"session_id": {"type": "string", "maxLength": 100}}, "required": ["session_id"], "additionalProperties": False}, ("session_id",)),
        ("extract_text", "Extract bounded untrusted page text from an existing browser session.", {"type": "object", "properties": {"session_id": {"type": "string", "maxLength": 100}}, "required": ["session_id"], "additionalProperties": False}, ("session_id",)),
        ("find_element", "Find a bounded element or link in an untrusted browser page.", {"type": "object", "properties": {"session_id": {"type": "string", "maxLength": 100}, "text": {"type": "string", "maxLength": 200}, "selector": {"type": "string", "maxLength": 200}}, "required": ["session_id"], "additionalProperties": False}, ("session_id",)),
        ("inspect_accessibility_tree", "Read a bounded untrusted accessibility tree from a browser session.", {"type": "object", "properties": {"session_id": {"type": "string", "maxLength": 100}}, "required": ["session_id"], "additionalProperties": False}, ("session_id",)),
        ("tabs", "List bounded JARVIS browser tabs.", {"type": "object", "properties": {}, "additionalProperties": False}, ()),
        ("click", "Click one bounded selector after the browser approval gate.", {"type": "object", "properties": {"session_id": {"type": "string", "maxLength": 100}, "selector": {"type": "string", "maxLength": 200}}, "required": ["session_id", "selector"], "additionalProperties": False}, ("session_id", "selector")),
        ("type", "Type bounded text after the browser approval gate; content is never durable.", {"type": "object", "properties": {"session_id": {"type": "string", "maxLength": 100}, "selector": {"type": "string", "maxLength": 200}, "text": {"type": "string", "maxLength": 2000}}, "required": ["session_id", "selector", "text"], "additionalProperties": False}, ("session_id", "selector", "text")),
        ("select", "Select a bounded option after the browser approval gate; value is never durable.", {"type": "object", "properties": {"session_id": {"type": "string", "maxLength": 100}, "selector": {"type": "string", "maxLength": 200}, "value": {"type": "string", "maxLength": 200}}, "required": ["session_id", "selector", "value"], "additionalProperties": False}, ("session_id", "selector", "value")),
    )
    for action, description, schema, required in schemas:
        registry.register(ToolSpec(
            f"tool-browser-{action.replace('_', '-')}-v1",
            f"browser.{action}",
            "1",
            description,
            "read" if action in {"open_url", "navigate", "read_page", "extract_text", "find_element", "inspect_accessibility_tree", "tabs"} else "safe",
            "tool.request",
            frozenset({f"browser.{action}"}),
            30.0,
            action in {"open_url", "read_page", "extract_text", "find_element", "inspect_accessibility_tree", "tabs"},
            lambda arguments, context, _action=action: execute(_action, arguments, context),
            parameters_schema=schema,
            retention=ToolResultRetention.EPHEMERAL,
            argument_retention=ToolResultRetention.EPHEMERAL,
        ))


def register_perception_tools(registry: ToolRegistry, perception: object) -> None:
    """Register visual tools in the existing product-owned registry."""

    async def desktop_context(arguments: Mapping[str, Any], context: ToolContext) -> ToolResult:
        if context.identity is None or context.device is None:
            return ToolResult(ToolResultStatus.DENIED, error_code="identity_or_device_missing")
        target = await perception.resolve_target(context.identity, context.device, arguments.get("target_device_id"))
        if target is None:
            return ToolResult(ToolResultStatus.DENIED, error_code="target_device_missing")
        result = await perception.observe_desktop_context(context.identity, context.device, target_device=target, session_id=context.session_id)
        return ToolResult(_tool_status(result.status), _json_safe(result), result.error_code, verified=result.status == "completed")

    async def observe_screen(arguments: Mapping[str, Any], context: ToolContext) -> ToolResult:
        if context.identity is None or context.device is None:
            return ToolResult(ToolResultStatus.DENIED, error_code="identity_or_device_missing")
        if "window_ref" in arguments and arguments["window_ref"] is not None and not isinstance(arguments["window_ref"], str):
            return ToolResult(ToolResultStatus.DENIED, error_code="window_ref_required")
        target = await perception.resolve_target(context.identity, context.device, arguments.get("target_device_id"))
        if target is None:
            return ToolResult(ToolResultStatus.DENIED, error_code="target_device_missing")
        region_value = arguments.get("region")
        from ..contracts import VisualRegion
        region = VisualRegion(*(int(region_value[key]) for key in ("x", "y", "width", "height"))) if isinstance(region_value, Mapping) else None
        result = await perception.observe_screen(context.identity, context.device, target_device=target, window_ref=arguments.get("window_ref") if isinstance(arguments.get("window_ref"), str) else None, region=region, mode=str(arguments.get("mode", "semantic")), session_id=context.session_id)
        return ToolResult(_tool_status(result.status), _json_safe(result), result.error_code, verified=result.status == "completed")

    async def latest_screen(arguments: Mapping[str, Any], context: ToolContext) -> ToolResult:
        if context.identity is None or context.device is None:
            return ToolResult(ToolResultStatus.DENIED, error_code="identity_or_device_missing")
        target = await perception.resolve_target(context.identity, context.device, arguments.get("target_device_id"))
        if target is None:
            return ToolResult(ToolResultStatus.DENIED, error_code="target_device_missing")
        result = await perception.latest_observation(
            context.identity,
            context.device,
            target_device=target,
            observation_id=arguments.get("observation_id") if isinstance(arguments.get("observation_id"), str) else None,
            session_id=context.session_id,
        )
        return ToolResult(_tool_status(result.status), _json_safe(result), result.error_code, verified=result.status == "completed")

    registry.register(ToolSpec(
        "tool-desktop-context-read-v1", "desktop.context.read", "1", "Read bounded active desktop metadata.",
        "read", "tool.request", frozenset(), 10.0, True, desktop_context,
        parameters_schema={"type": "object", "properties": {"target_device_id": {"type": "string", "maxLength": 200}}, "additionalProperties": False},
        retention=ToolResultRetention.EPHEMERAL,
    ))
    registry.register(ToolSpec(
        "tool-screen-observe-v1", "screen.observe", "1", "Observe the current screen on demand using safe structured perception.",
        "read", "tool.request", frozenset(), 15.0, False, observe_screen,
        parameters_schema={"type": "object", "properties": {"target_device_id": {"type": "string", "maxLength": 200}, "window_ref": {"type": "string", "maxLength": 100}, "region": {"type": "object"}, "mode": {"type": "string", "enum": ["semantic", "screen"]}}, "additionalProperties": False},
        retention=ToolResultRetention.EPHEMERAL,
    ))
    registry.register(ToolSpec(
        "tool-screen-latest-v1", "screen.latest", "1", "Read a still-valid cached screen observation.",
        "read", "tool.request", frozenset(), 5.0, True, latest_screen,
        parameters_schema={"type": "object", "properties": {"observation_id": {"type": "string", "maxLength": 200}, "target_device_id": {"type": "string", "maxLength": 200}}, "additionalProperties": False},
        retention=ToolResultRetention.EPHEMERAL,
    ))


def register_computer_tools(
    registry: ToolRegistry,
    computer_actions: object,
    *,
    target_resolver: Callable[[str, str], Awaitable[tuple[object, str | None] | None]] | None = None,
) -> None:
    """Expose only the grounded computer actions through the existing registry."""

    from ..contracts import ComputerAction

    async def target_for(arguments: Mapping[str, Any], context: ToolContext) -> tuple[object, str | None] | None:
        if context.identity is None or context.device is None:
            return None
        target_id = arguments.get("target_device_id")
        if target_id is None:
            return context.device, None
        if not isinstance(target_id, str) or not target_id.strip():
            return None
        if target_resolver is None:
            return (context.device, None) if target_id == context.device.device_id else None
        resolved = await target_resolver(context.identity.owner_id, target_id)
        return resolved

    async def execute_action(
        action: str,
        parameters: Mapping[str, object],
        arguments: Mapping[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        if context.identity is None or context.device is None:
            return ToolResult(ToolResultStatus.DENIED, error_code="identity_or_device_missing")
        resolved = await target_for(arguments, context)
        if resolved is None:
            return ToolResult(ToolResultStatus.DENIED, error_code="target_device_missing")
        target, adapter = resolved
        result = await computer_actions.execute(
            ComputerAction(action, dict(parameters), False),
            context.identity,
            context.device,
            target_device=target,
            execution_adapter=adapter,
            session_id=context.session_id,
            correlation_id=context.correlation_id,
        )
        try:
            status = ToolResultStatus(result.status)
        except ValueError:
            status = ToolResultStatus.FAILED
        if status is ToolResultStatus.APPROVAL_REQUIRED:
            return ToolResult(status, error_code=result.error_code, approval_id=result.approval_id)
        return ToolResult(status, dict(result.output), result.error_code, result.verified, result.approval_id)

    async def audio(arguments: Mapping[str, Any], context: ToolContext) -> ToolResult:
        operation = arguments.get("operation")
        if operation in {"volume_up", "volume_down"}:
            steps = arguments.get("steps", 1)
            if not isinstance(steps, int) or isinstance(steps, bool) or not 1 <= steps <= 10:
                return ToolResult(ToolResultStatus.DENIED, error_code="audio_steps_invalid")
            return await execute_action("change_volume", {"direction": operation.removeprefix("volume_"), "steps": steps}, arguments, context)
        if operation in {"mute", "unmute"}:
            if set(arguments) - {"operation", "target_device_id"}:
                return ToolResult(ToolResultStatus.DENIED, error_code="unknown_arguments")
            return await execute_action(operation, {}, arguments, context)
        return ToolResult(ToolResultStatus.DENIED, error_code="audio_operation_invalid")

    async def window(arguments: Mapping[str, Any], context: ToolContext) -> ToolResult:
        if arguments.get("operation") not in {"minimize", "maximize", "restore"}:
            return ToolResult(ToolResultStatus.DENIED, error_code="window_operation_invalid")
        if not isinstance(arguments.get("window_ref"), str) or not str(arguments["window_ref"]).startswith("window-"):
            return ToolResult(ToolResultStatus.DENIED, error_code="window_ref_required")
        return await execute_action("window_action", {"operation": arguments["operation"], "window_ref": arguments["window_ref"]}, arguments, context)

    async def clipboard_read(arguments: Mapping[str, Any], context: ToolContext) -> ToolResult:
        return await execute_action("clipboard_read", {}, arguments, context)

    async def clipboard_write(arguments: Mapping[str, Any], context: ToolContext) -> ToolResult:
        value = arguments.get("text")
        if not isinstance(value, str) or not value or len(value) > 16_000 or "\x00" in value:
            return ToolResult(ToolResultStatus.DENIED, error_code="clipboard_text_invalid")
        return await execute_action("clipboard_write", {"text": value}, arguments, context)

    async def keyboard_type(arguments: Mapping[str, Any], context: ToolContext) -> ToolResult:
        value = arguments.get("text")
        window_ref = arguments.get("window_ref")
        if not isinstance(window_ref, str) or not window_ref.startswith("window-"):
            return ToolResult(ToolResultStatus.DENIED, error_code="window_ref_required")
        if not isinstance(value, str) or not value or len(value) > 2_000 or "\x00" in value:
            return ToolResult(ToolResultStatus.DENIED, error_code="keyboard_text_invalid")
        return await execute_action("keyboard_action", {"operation": "type_text", "window_ref": window_ref, "text": value}, arguments, context)

    registry.register(ToolSpec(
        "tool-computer-audio-adjust-v1", "computer.audio.adjust", "1", "Adjust local Windows audio by bounded media-key steps.",
        "safe", "tool.request", frozenset({"computer.input"}), 10.0, True, audio,
        parameters_schema={"type": "object", "properties": {"operation": {"type": "string", "enum": ["volume_up", "volume_down", "mute", "unmute"]}, "steps": {"type": "integer", "minimum": 1, "maximum": 10}, "target_device_id": {"type": "string", "maxLength": 200}}, "required": ["operation"], "additionalProperties": False},
    ))
    registry.register(ToolSpec(
        "tool-computer-window-control-v1", "computer.window.control", "1", "Control one previously observed Windows window.",
        "safe", "tool.request", frozenset({"computer.input"}), 15.0, False, window,
        parameters_schema={"type": "object", "properties": {"operation": {"type": "string", "enum": ["minimize", "maximize", "restore"]}, "window_ref": {"type": "string", "maxLength": 100}, "target_device_id": {"type": "string", "maxLength": 200}}, "required": ["operation", "window_ref"], "additionalProperties": False},
        argument_retention=ToolResultRetention.EPHEMERAL,
    ))
    registry.register(ToolSpec(
        "tool-computer-clipboard-read-v1", "computer.clipboard.read", "1", "Read transient Unicode clipboard text.",
        "read", "tool.request", frozenset({"computer.observe"}), 10.0, True, clipboard_read,
        parameters_schema={"type": "object", "properties": {"target_device_id": {"type": "string", "maxLength": 200}}, "additionalProperties": False},
        retention=ToolResultRetention.EPHEMERAL,
    ))
    registry.register(ToolSpec(
        "tool-computer-clipboard-write-v1", "computer.clipboard.write", "1", "Write bounded transient Unicode clipboard text.",
        "safe", "tool.request", frozenset({"computer.input"}), 15.0, False, clipboard_write,
        parameters_schema={"type": "object", "properties": {"text": {"type": "string", "maxLength": 16000}, "target_device_id": {"type": "string", "maxLength": 200}}, "required": ["text"], "additionalProperties": False},
        argument_retention=ToolResultRetention.EPHEMERAL,
    ))
    registry.register(ToolSpec(
        "tool-computer-keyboard-type-v1", "computer.keyboard.type", "1", "Type literal text into one grounded Windows window.",
        "safe", "tool.request", frozenset({"computer.input"}), 15.0, False, keyboard_type,
        parameters_schema={"type": "object", "properties": {"window_ref": {"type": "string", "maxLength": 100}, "text": {"type": "string", "maxLength": 2000}, "target_device_id": {"type": "string", "maxLength": 200}}, "required": ["window_ref", "text"], "additionalProperties": False},
        argument_retention=ToolResultRetention.EPHEMERAL,
    ))


def _tool_status(status: str) -> ToolResultStatus:
    if status == "completed":
        return ToolResultStatus.SUCCEEDED
    if status == "denied":
        return ToolResultStatus.DENIED
    return ToolResultStatus.FAILED


def _json_safe(value: object) -> object:
    from dataclasses import asdict, is_dataclass
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
