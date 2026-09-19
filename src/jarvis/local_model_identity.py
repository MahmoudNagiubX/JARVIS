"""Identity rules for the required owner-provisioned local model."""

from __future__ import annotations

from pathlib import Path


REQUIRED_LOCAL_MODEL = "Qwen3.5-4B-Heretic"
"""The only local text model identity accepted by the current product profile."""


def is_required_local_model_path(value: str | Path) -> bool:
    """Return whether a path names a main 4B Heretic GGUF.

    Filename identity is deliberately conservative. Vision projectors and
    speculative-decoding files are separate GGUF artifacts, not the local
    text model, and generic/9B Qwen files must never be selected implicitly.
    The runtime still requires an actual existing file before it can start.
    """

    path = Path(value)
    name = path.name.casefold()
    if path.suffix.casefold() != ".gguf":
        return False
    if name.startswith(("mmproj-", "mtp-")):
        return False
    return "qwen3.5-4b-heretic" in name
