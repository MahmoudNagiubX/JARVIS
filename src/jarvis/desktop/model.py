"""Bounded discovery of existing local llama.cpp and Qwen assets."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LocalModelReferences:
    executable_path: Path | None
    model_path: Path | None


class LocalModelDiscovery:
    """Reference existing files only; never downloads, copies, or imports them."""

    def __init__(self, *, runtime_root: Path | None = None, model_roots: tuple[Path, ...] | None = None) -> None:
        local = os.getenv("LOCALAPPDATA", "").strip()
        local_root = Path(local) if local else Path.home() / "AppData" / "Local"
        self.runtime_root = runtime_root or local_root / "JARVIS" / "runtimes" / "llama.cpp"
        self.model_roots = model_roots or (
            local_root / "JARVIS" / "models",
            Path.home() / "BMO" / "phase-08-5-models",
        )

    def discover(self) -> LocalModelReferences:
        executable = self._first_file(self.runtime_root, "llama-server.exe")
        if executable is None:
            executable = self._first_file(self.runtime_root, "llama-server")
        models: list[Path] = []
        for root in self.model_roots:
            if root.exists() and root.is_dir():
                models.extend(item for item in root.glob("*.gguf") if item.is_file())
        qwen = sorted((item for item in models if "qwen" in item.name.casefold()), key=lambda item: str(item).casefold())
        selected = qwen[0] if qwen else (sorted(models, key=lambda item: str(item).casefold())[0] if len(models) == 1 else None)
        return LocalModelReferences(executable, selected)

    @staticmethod
    def _first_file(root: Path, name: str) -> Path | None:
        if not root.exists() or not root.is_dir():
            return None
        matches = sorted((item for item in root.rglob(name) if item.is_file()), key=lambda item: str(item).casefold())
        return matches[0] if matches else None
