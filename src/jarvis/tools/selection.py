"""Deterministic model-facing tool selection without authority decisions."""

from __future__ import annotations

import json
from collections.abc import Iterable

from .registry import ToolRegistry, ToolSpec


class ToolSchemaSelector:
    """Select a bounded view of registered tools from trusted user intent only."""

    MAX_MODEL_TOOLS = 8
    VISUAL_TOOLS = ("desktop.context.read", "screen.observe", "screen.latest")
    COMPUTER_TOOLS = (
        "desktop.context.read",
        "computer.window.control",
        "computer.keyboard.type",
        "computer.clipboard.read",
        "computer.clipboard.write",
        "computer.audio.adjust",
    )
    STATUS_TOOLS = ("status.read",)
    VISUAL_MARKERS = (
        "screen", "desktop", "active application", "active window", "current window",
        "what is on", "look at", "see what", "which application is active",
    )
    COMPUTER_MARKERS = (
        "keyboard", "type", "typing", "clipboard", "window", "minimize", "maximize",
        "restore", "volume", "mute", "audio",
    )
    STATUS_MARKERS = ("status", "health", "ready", "state")

    def __init__(self, registry: ToolRegistry, *, max_model_tools: int = MAX_MODEL_TOOLS) -> None:
        if not 1 <= max_model_tools <= self.MAX_MODEL_TOOLS:
            raise ValueError("max_model_tools_out_of_bounds")
        self.registry = registry
        self.max_model_tools = max_model_tools

    def select(self, intent: str) -> tuple[dict[str, object], ...]:
        lowered = intent.casefold()
        available = {spec.name: spec for spec in self.registry.list() if spec.enabled}
        names: list[str] = []

        for name in sorted(available):
            if name.casefold() in lowered:
                names.append(name)
        if any(marker in lowered for marker in self.VISUAL_MARKERS):
            names.extend(self.VISUAL_TOOLS)
        if any(marker in lowered for marker in self.COMPUTER_MARKERS):
            names.extend(self.COMPUTER_TOOLS)
        if any(marker in lowered for marker in self.STATUS_MARKERS):
            names.extend(self.STATUS_TOOLS)

        selected: list[ToolSpec] = []
        seen: set[str] = set()
        for name in names:
            spec = available.get(name)
            if spec is None or name in seen:
                continue
            seen.add(name)
            selected.append(spec)
            if len(selected) >= self.max_model_tools:
                break
        return tuple(self._schema(spec) for spec in selected)

    @staticmethod
    def _schema(spec: ToolSpec) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.json_schema(),
            },
        }

    @classmethod
    def schema_bytes(cls, schemas: Iterable[dict[str, object]]) -> int:
        return len(json.dumps(tuple(schemas), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
