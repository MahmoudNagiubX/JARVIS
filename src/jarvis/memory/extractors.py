"""Bounded memory candidate extractors; persistence policy remains canonical."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Protocol
from uuid import uuid4

from ..contracts import LLMMessage, LLMRequest, LLMRole, MemoryCandidate, MemorySource
from ..models.gateway import ModelGateway
from ..models.routing import ModelRoute


class MemoryCandidateExtractor(Protocol):
    async def extract(self, owner_id: str, text: str, source_reference: str | None = None) -> tuple[MemoryCandidate, ...]: ...


class DeterministicMemoryExtractor:
    async def extract(self, owner_id: str, text: str, source_reference: str | None = None) -> tuple[MemoryCandidate, ...]:
        return self.extract_sync(owner_id, text, source_reference)

    @staticmethod
    def extract_sync(owner_id: str, text: str, source_reference: str | None = None) -> tuple[MemoryCandidate, ...]:
        normalized = " ".join(text.split())
        lowered = normalized.casefold()
        if len(normalized) < 5 or lowered in {"hello", "hi", "thanks", "thank you", "ok", "okay"}:
            return ()
        source = MemorySource.CONVERSATION.value
        candidates: list[MemoryCandidate] = []
        if re.search(r"keep (your|the) answers? short|be concise|short answers", lowered):
            candidates.append(MemoryCandidate(owner_id, "Mahmoud prefers concise answers.", "preference", source, source_reference, {"key": "verbosity", "value": "concise"}, 0.98, tags=("style",)))
        match = re.search(r"(?:call me|my name is) ([A-Za-z][\w -]{1,50})", normalized, re.I)
        if match:
            name = match.group(1).strip(" .,!?\"")
            candidates.append(MemoryCandidate(owner_id, f"Preferred name is {name}.", "profile", source, source_reference, {"key": "preferred_name", "value": name}, 0.98, tags=("identity",)))
        if re.search(r"\b(i prefer|i like|my preference is)\b", lowered):
            candidates.append(MemoryCandidate(owner_id, normalized, "preference", source, source_reference, {"key": "freeform_preference", "value": normalized}, 0.85))
        match = re.search(r"(?:working on|project is|project:)\s*([^.!?]{2,100})", normalized, re.I)
        if match:
            project = match.group(1).strip()
            candidates.append(MemoryCandidate(owner_id, f"Mahmoud is working on {project}.", "project", source, source_reference, {"key": "active_project", "value": project}, 0.88, tags=("work",)))
        if re.search(r"\bdeadline\b|\bdue\b", lowered):
            candidates.append(MemoryCandidate(owner_id, normalized, "task", source, source_reference, {"key": "deadline_context", "value": normalized}, 0.82, tags=("deadline",)))
        if lowered.startswith("remember that") or lowered.startswith("important:"):
            candidates.append(MemoryCandidate(owner_id, normalized, "fact", source, source_reference, {}, 0.82))
        if lowered.startswith("decision:"):
            candidates.append(MemoryCandidate(owner_id, normalized, "decision", source, source_reference, {}, 0.9))
        if lowered.startswith("goal:"):
            candidates.append(MemoryCandidate(owner_id, normalized, "goal", source, source_reference, {}, 0.88))
        return tuple(candidates[:12])


class LocalModelMemoryExtractor:
    """Use only an already-configured local ModelGateway; never downloads models."""

    def __init__(self, gateway: ModelGateway, route: ModelRoute = ModelRoute.GENERAL_REASONING) -> None:
        self.gateway = gateway
        self.route = route

    async def extract(self, owner_id: str, text: str, source_reference: str | None = None) -> tuple[MemoryCandidate, ...]:
        request = LLMRequest(
            f"memory-extract-{uuid4()}",
            (LLMMessage(LLMRole.SYSTEM, "Return only a JSON array of bounded memory candidates. Never include secrets, credentials, raw media, or sensitive traits."), LLMMessage(LLMRole.USER, text[:4000])),
            max_output_tokens=700,
        )
        response = await self.gateway.generate(request, self.route)
        if len(response.text) > 12000:
            raise ValueError("memory_extractor_output_too_long")
        parsed = json.loads(response.text)
        if not isinstance(parsed, list) or len(parsed) > 12:
            raise ValueError("memory_extractor_output_invalid")
        candidates: list[MemoryCandidate] = []
        for item in parsed:
            if not isinstance(item, Mapping) or any(token in str(item).casefold() for token in ("password", "secret", "token", "api_key", "credential")):
                raise ValueError("memory_extractor_sensitive_output")
            content = item.get("content")
            category = item.get("category", "fact")
            confidence = item.get("confidence", 0.7)
            if not isinstance(content, str) or not isinstance(category, str) or len(content) > 2000:
                raise ValueError("memory_extractor_candidate_invalid")
            if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
                raise ValueError("memory_extractor_confidence_invalid")
            structured = item.get("structured_data", {})
            tags = item.get("tags", [])
            if not isinstance(structured, Mapping) or len(json.dumps(dict(structured), default=str)) > 2000 or not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags[:12]):
                raise ValueError("memory_extractor_metadata_invalid")
            candidates.append(MemoryCandidate(owner_id, content, category, MemorySource.CONVERSATION.value, source_reference, dict(structured), float(confidence), "personal", tuple(tags[:12])))
        return tuple(candidates)


class CompositeMemoryExtractor:
    def __init__(self, deterministic: DeterministicMemoryExtractor | None = None, local: MemoryCandidateExtractor | None = None) -> None:
        self.deterministic = deterministic or DeterministicMemoryExtractor()
        self.local = local

    async def extract(self, owner_id: str, text: str, source_reference: str | None = None) -> tuple[MemoryCandidate, ...]:
        if self.local is not None:
            try:
                candidates = await self.local.extract(owner_id, text, source_reference)
                if candidates:
                    return candidates
            except Exception:
                pass
        return await self.deterministic.extract(owner_id, text, source_reference)
