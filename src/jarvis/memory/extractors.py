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
        if len(normalized) < 5 or lowered in {"hello", "hi", "thanks", "thank you", "ok", "okay", "شكرا", "تمام", "أهلا", "اهلا"}:
            return ()
        source = MemorySource.CONVERSATION.value
        candidates: list[MemoryCandidate] = []

        # Verbosity
        if re.search(r"keep (your|the) answers? short|be concise|short answers|خلي إجاباتك مختصرة|خليك مختصر|إجابات قصيرة", lowered):
            candidates.append(MemoryCandidate(owner_id, "Mahmoud prefers concise answers.", "preference", source, source_reference, {"key": "verbosity", "value": "concise"}, 0.98, tags=("style",)))

        # Name / Identity
        match = re.search(r"(?:call me|my name is|اسمي هو|اسمي|ناديلي|أنا اسمي|انا اسمي)\s+([A-Za-z\u0600-\u06FF][\w\u0600-\u06FF -]{1,50})", normalized, re.I)
        if match:
            name = match.group(1).strip(" .,!?\"")
            candidates.append(MemoryCandidate(owner_id, f"Preferred name is {name}.", "profile", source, source_reference, {"key": "preferred_name", "value": name}, 0.98, tags=("identity",)))

        # Preferred editor / technical tools
        editor_match = re.search(r"(?:preferred editor\s*(?:is|=|:)|my preferred editor is|الـeditor المفضل\s*(?:هو|=|:)?|محرر النصوص المفضل\s*(?:هو|=|:)?)\s*([A-Za-z0-9 _-]+)", normalized, re.I)
        if editor_match:
            editor = editor_match.group(1).strip(" .,!?\"")
            candidates.append(MemoryCandidate(owner_id, f"Preferred editor is {editor}.", "preference", source, source_reference, {"key": "preferred_editor", "value": editor}, 0.95, tags=("tools", "preference")))
        elif re.search(r"\b(i prefer|i like|my preference is|أنا بفضل|انا بفضل|تفضيلاتي هي|تفضيلاتي)\b", lowered):
            candidates.append(MemoryCandidate(owner_id, normalized, "preference", source, source_reference, {"key": "freeform_preference", "value": normalized}, 0.85, tags=("preference",)))

        # Project tech stack & database (e.g. Project Phoenix uses PostgreSQL / مشروع فينيكس بيستخدم PostgreSQL)
        tech_match = re.search(r"(?:project\s+)?([A-Za-z0-9_-]+)\s+uses\s+([A-Za-z0-9 _-]+)", normalized, re.I)
        if tech_match and not lowered.startswith("i prefer"):
            proj = tech_match.group(1).strip()
            tech = tech_match.group(2).strip(" .,!?\"")
            key_name = f"project_{proj.lower()}_db" if any(db in tech.lower() for db in ("sql", "db", "postgres", "mongo", "redis", "sqlite")) else f"project_{proj.lower()}_tech"
            candidates.append(MemoryCandidate(owner_id, f"Project {proj} uses {tech}.", "project", source, source_reference, {"key": key_name, "project": proj, "technology": tech, "value": tech}, 0.92, tags=("project", "tech")))

        # Arabic project tech pattern (المشروع ده بيستخدم ... / مشروع ... بيستخدم ...)
        ar_tech_match = re.search(r"(?:مشروع\s+([A-Za-z0-9_\u0600-\u06FF-]+)\s+بيستخدم|المشروع(?: ده)? بيستخدم)\s+([A-Za-z0-9 _\u0600-\u06FF-]+)", normalized, re.I)
        if ar_tech_match:
            proj_name = (ar_tech_match.group(1) or "current").strip()
            tech_val = ar_tech_match.group(2).strip(" .,!?\"")
            key_name = f"project_{proj_name.lower()}_db" if any(db in tech_val.lower() for db in ("sql", "db", "postgres", "mongo", "redis", "sqlite")) else f"project_{proj_name.lower()}_tech"
            candidates.append(MemoryCandidate(owner_id, normalized, "project", source, source_reference, {"key": key_name, "project": proj_name, "technology": tech_val, "value": tech_val}, 0.92, tags=("project", "tech")))

        # Active project
        proj_match = re.search(r"(?:working on|project is|project:|شغال على مشروع|شغال في مشروع)\s*([^.!?]{2,100})", normalized, re.I)
        if proj_match and not tech_match and not ar_tech_match:
            project = proj_match.group(1).strip()
            candidates.append(MemoryCandidate(owner_id, f"Mahmoud is working on {project}.", "project", source, source_reference, {"key": "active_project", "value": project}, 0.88, tags=("work",)))

        # Goal extraction
        goal_match = re.search(r"(?:goal:|my goal is|الهدف بتاعي|هدفي هو|هدفي:|الهدف:)\s*([^.!?]{2,100})", normalized, re.I)
        if goal_match:
            goal_text = goal_match.group(1).strip()
            candidates.append(MemoryCandidate(owner_id, normalized, "goal", source, source_reference, {"key": "active_goal", "value": goal_text}, 0.88, tags=("goal",)))

        # Task & deadline
        deadline_match = re.search(r"(?:deadline\s*(?:is|=|:)|موعد التسليم\s*(?:هو|=|:)?)\s*([^.!?]{2,100})", normalized, re.I)
        if deadline_match:
            deadline_val = deadline_match.group(1).strip()
            candidates.append(MemoryCandidate(owner_id, normalized, "task", source, source_reference, {"key": "project_deadline", "value": deadline_val}, 0.88, tags=("deadline", "task")))
        elif re.search(r"\b(deadline|due|فكرني قبل الـdeadline|فكرني)\b", lowered):
            candidates.append(MemoryCandidate(owner_id, normalized, "task", source, source_reference, {"key": "deadline_context", "value": normalized}, 0.82, tags=("deadline",)))

        # Explicit Remember / Facts
        remember_ar = any(normalized.startswith(p) for p in ("افتكر إن", "افتكر ان", "إفتكر إن", "إفتكر ان", "افتكر", "تذكر أن", "تذكر ان", "تذكر", "خليك فاكر إن", "خليك فاكر ان", "خليك فاكر", "متنساش إن", "متنساش ان", "متنساش"))
        remember_en = lowered.startswith("remember that") or lowered.startswith("important:") or lowered.startswith("keep in mind that") or lowered.startswith("note that")
        if (remember_en or remember_ar) and not candidates:
            candidates.append(MemoryCandidate(owner_id, normalized, "fact", source, source_reference, {"key": "explicit_fact", "value": normalized}, 0.85))

        if lowered.startswith("decision:"):
            candidates.append(MemoryCandidate(owner_id, normalized, "decision", source, source_reference, {}, 0.9))
        if lowered.startswith("goal:") and not any(c.category == "goal" for c in candidates):
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
