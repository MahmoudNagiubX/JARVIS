"""Privacy and retention policy for automatic memory."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..contracts import MemoryCandidate, MemorySensitivity


@dataclass(frozen=True, slots=True)
class MemoryPolicyDecision:
    allowed: bool
    reason: str
    normalized_content: str


class MemoryPolicy:
    """Conservative product-owned policy; no cloud memory backend is used."""

    _blocked_patterns = (
        re.compile(r"\b(password|passcode|secret|api[ _-]?key|access[ _-]?token)\b", re.I),
        re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    )
    _categories = {
        "profile", "preference", "project", "task", "goal", "relationship",
        "workflow", "technical_context", "device_context", "habit", "fact",
        "decision", "conversation_summary",
    }

    def evaluate(self, candidate: MemoryCandidate) -> MemoryPolicyDecision:
        content = " ".join(candidate.content.split())
        if not content:
            return MemoryPolicyDecision(False, "empty_content", content)
        if len(content) > 2000:
            return MemoryPolicyDecision(False, "content_too_long", content[:2000])
        if candidate.category not in self._categories:
            return MemoryPolicyDecision(False, "category_not_allowed", content)
        try:
            confidence = float(candidate.confidence)
        except (TypeError, ValueError):
            return MemoryPolicyDecision(False, "confidence_invalid", content)
        if not 0.0 <= confidence <= 1.0:
            return MemoryPolicyDecision(False, "confidence_out_of_range", content)
        if candidate.sensitivity not in {item.value for item in MemorySensitivity}:
            return MemoryPolicyDecision(False, "sensitivity_invalid", content)
        if candidate.sensitivity == MemorySensitivity.SECRET.value:
            return MemoryPolicyDecision(False, "secret_memory_forbidden", content)
        if any(pattern.search(content) for pattern in self._blocked_patterns):
            return MemoryPolicyDecision(False, "credential_like_content_forbidden", content)
        if candidate.source == "audio" or candidate.category in {"raw_audio", "screen_recording", "camera"}:
            return MemoryPolicyDecision(False, "raw_media_retention_forbidden", content)
        return MemoryPolicyDecision(True, "policy_allowed", content)
