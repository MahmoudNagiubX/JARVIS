"""Local product-interpreter installation and import verification."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


class ProductInstallationError(RuntimeError):
    """The selected local product interpreter cannot run the desktop package."""


def repository_root() -> Path:
    """Resolve the source checkout that owns the installed product package."""

    return Path(__file__).resolve().parents[3]


def sanitized_environment(base: dict[str, str] | None = None) -> dict[str, str]:
    """Remove developer import and voice-secret environment overrides."""

    environment = dict(base if base is not None else os.environ)
    for key in tuple(environment):
        if key.casefold() == "pythonpath" or key.casefold().startswith("jarvis_voice_"):
            environment.pop(key, None)
    return environment


def interpreter_imports_product(
    executable: str | Path,
    *,
    root: Path | None = None,
    timeout_seconds: float = 20.0,
) -> bool:
    """Check importability using exactly the interpreter used by the launcher."""

    if timeout_seconds <= 0:
        raise ValueError("import check timeout must be positive")
    target_root = (root or repository_root()).resolve()
    try:
        completed = subprocess.run(
            [str(executable), "-c", "import jarvis.desktop"],
            cwd=target_root,
            env=sanitized_environment(),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            **_hidden_process_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def ensure_product_interpreter(
    executable: str | Path,
    *,
    root: Path | None = None,
    timeout_seconds: float = 120.0,
) -> Path:
    """Install this local checkout editable into an existing local voice venv.

    The command is explicitly offline and dependency-free.  It never mutates a
    global interpreter and never passes product credentials to a child process.
    """

    if timeout_seconds <= 0:
        raise ValueError("product installation timeout must be positive")
    target = Path(executable).expanduser()
    if not target.is_file():
        raise ProductInstallationError("selected product interpreter is missing")
    target_root = (root or repository_root()).resolve()
    if not (target_root / "pyproject.toml").is_file():
        raise ProductInstallationError("canonical local repository is missing pyproject.toml")
    if not interpreter_imports_product(target, root=target_root):
        try:
            completed = subprocess.run(
                [
                    str(target), "-m", "pip", "install", "--no-deps", "--no-build-isolation",
                    "--editable", str(target_root),
                ],
                cwd=target_root,
                env=sanitized_environment(),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
                **_hidden_process_kwargs(),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ProductInstallationError("local product installation could not be started") from exc
        if completed.returncode != 0 or not interpreter_imports_product(target, root=target_root):
            raise ProductInstallationError("local product installation did not produce an importable package")
    return target


def _hidden_process_kwargs() -> dict[str, int]:
    if os.name != "nt":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


__all__ = [
    "ProductInstallationError",
    "ensure_product_interpreter",
    "interpreter_imports_product",
    "repository_root",
    "sanitized_environment",
]
