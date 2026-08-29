"""Progressive loading of bounded local Markdown skill instructions."""

from __future__ import annotations

from pathlib import Path

from .models import Skill


class SkillLoader:
    def __init__(self, *, max_bytes: int = 16_384) -> None:
        self.max_bytes = max(1_024, min(max_bytes, 64_000))

    def load(self, skill: Skill) -> Skill:
        if skill.instructions is not None:
            return skill
        if skill.instructions_path is None:
            return skill
        path = Path(skill.instructions_path).expanduser().resolve(strict=True)
        if path.suffix.casefold() != ".md" or path.stat().st_size > self.max_bytes:
            raise ValueError("skill instructions must be a bounded Markdown file")
        return Skill(skill.manifest, skill.steps, str(path), path.read_text(encoding="utf-8"))
