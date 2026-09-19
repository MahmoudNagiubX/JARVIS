"""Privacy and retention policy for automatic memory."""

from __future__ import annotations

import json
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
        re.compile(r"(password|passcode|secret|api[ _-]?key|access[ _-]?key|access[ _-]?token|bearer|refresh[ _-]?token|auth[ _-]?token|private[ _-]?key|session[ _-]?token)", re.I),
        re.compile(r"\b(sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{20,}|glpat-[a-zA-Z0-9]{20,})\b"),
        re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----"),
        re.compile(r"\bcookie\s*[:=]", re.I),
        re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    )
    _categories = {
        "profile", "preference", "project", "task", "goal", "relationship",
        "workflow", "technical_context", "device_context", "habit", "fact",
        "decision", "conversation_summary",
    }
    _untrusted_sources = {
        "browser", "web", "research", "untrusted_web", "untrusted_browser",
        "untrusted_research", "untrusted",
    }
    _MAX_METADATA_CHARS = 16_000

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
        metadata = self._candidate_metadata(candidate)
        if metadata is None:
            return MemoryPolicyDecision(False, "memory_metadata_too_large", content)
        if any(pattern.search(content) or pattern.search(metadata) for pattern in self._blocked_patterns):
            return MemoryPolicyDecision(False, "credential_like_content_forbidden", content)
        if candidate.source == "audio" or candidate.category in {"raw_audio", "screen_recording", "camera"}:
            return MemoryPolicyDecision(False, "raw_media_retention_forbidden", content)
        if candidate.source in self._untrusted_sources:
            # Untrusted sources (web/browser/research) cannot directly create owner memories
            # or inject policy overrides, regardless of confidence.
            lowered = content.casefold()
            if any(marker in lowered for marker in ("system:", "owner authorized", "disable approvals", "override policy", "remember permanently")):
                return MemoryPolicyDecision(False, "untrusted_memory_injection_forbidden", content)
            return MemoryPolicyDecision(False, "untrusted_source_direct_memory_forbidden", content)
        return MemoryPolicyDecision(True, "policy_allowed", content)

    @classmethod
    def _candidate_metadata(cls, candidate: MemoryCandidate) -> str | None:
        """Serialize bounded non-content fields for the same secret firewall."""

        try:
            value = json.dumps(
                {
                    "structured_data": dict(candidate.structured_data),
                    "source_reference": candidate.source_reference,
                    "tags": list(candidate.tags),
                },
                ensure_ascii=False,
                sort_keys=True,
                default=str,
                separators=(",", ":"),
            )
        except (TypeError, ValueError, RecursionError):
            return None
        return value if len(value) <= cls._MAX_METADATA_CHARS else None
