"""Approved-root lecture resolution and ordered study planning."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from ..computer.file_access import FileAccessPolicy
from ..contracts import (
    StudyLectureCandidate,
    StudyPlan,
    StudyResolution,
    StudyResolutionStatus,
    StudyStep,
)


_LECTURE_SUFFIXES = frozenset({".pdf", ".ppt", ".pptx", ".doc", ".docx", ".md", ".txt", ".html", ".mp4", ".mkv"})
_MAX_CANDIDATES = 32
_MAX_RESOLUTIONS = 64
_RESOLUTION_TTL = timedelta(minutes=15)
_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class _StoredResolution:
    owner_id: str
    expires_at: datetime
    candidates: dict[str, Path]


class StudyService:
    """Resolve owner-approved lecture material without broad filesystem access."""

    def __init__(self, file_access_policy: FileAccessPolicy) -> None:
        self.file_access_policy = file_access_policy
        self._resolutions: dict[str, _StoredResolution] = {}

    def resolve(self, owner_id: str, query: str, *, root: str | None = None) -> StudyResolution:
        self._prune()
        normalized_query = self._normalize_query(query)
        if not normalized_query:
            return StudyResolution("", str(query)[:200], StudyResolutionStatus.NOT_FOUND, reason="lecture_query_required")
        roots, reason = self._roots(root)
        if not roots:
            return StudyResolution("", normalized_query, StudyResolutionStatus.NOT_CONFIGURED, reason=reason)

        query_tokens = tuple(_TOKEN_RE.findall(normalized_query))
        scored: list[tuple[int, Path]] = []
        seen: set[str] = set()
        for approved_root in roots:
            matches, _ = self.file_access_policy.iter_search_candidates(approved_root, "*")
            for raw in matches:
                path = Path(raw)
                if path.suffix.casefold() not in _LECTURE_SUFFIXES or not path.is_file():
                    continue
                key = str(path).casefold()
                if key in seen:
                    continue
                seen.add(key)
                score = self._score(path, normalized_query, query_tokens)
                if score > 0:
                    scored.append((score, path))
        scored.sort(key=lambda item: (-item[0], str(item[1]).casefold()))
        if not scored:
            return StudyResolution(
                f"study-resolution-{uuid4()}",
                normalized_query,
                StudyResolutionStatus.NOT_FOUND,
                reason="lecture_not_found_in_approved_roots",
            )

        best_score = scored[0][0]
        best = [path for score, path in scored if score == best_score][:_MAX_CANDIDATES]
        candidates = tuple(self._candidate(path) for path in best)
        resolution_id = f"study-resolution-{uuid4()}"
        stored = {candidate.candidate_ref: path for candidate, path in zip(candidates, best, strict=True)}
        self._resolutions[resolution_id] = _StoredResolution(owner_id, datetime.now(UTC) + _RESOLUTION_TTL, stored)
        if len(candidates) != 1:
            return StudyResolution(
                resolution_id,
                normalized_query,
                StudyResolutionStatus.AMBIGUOUS,
                candidates,
                reason="multiple_exact_lecture_candidates",
            )
        return StudyResolution(
            resolution_id,
            normalized_query,
            StudyResolutionStatus.RESOLVED,
            candidates,
            selected_ref=candidates[0].candidate_ref,
        )

    def prepare(
        self,
        owner_id: str,
        query: str,
        *,
        root: str | None = None,
        notes_target: str | None = None,
        research_query: str | None = None,
        youtube_topic: str | None = None,
        spotify_playlist: str | None = None,
        checklist: tuple[str, ...] = (),
    ) -> StudyPlan:
        resolution = self.resolve(owner_id, query, root=root)
        lecture_ready = resolution.status is StudyResolutionStatus.RESOLVED
        steps: list[StudyStep] = [StudyStep(
            "lecture",
            "lecture",
            "Open the exact lecture material",
            "ready" if lecture_ready else resolution.status.value,
            resolution.selected_ref,
        )]
        steps.append(StudyStep(
            "notes",
            "notes",
            "Open the configured study notes target",
            "configured" if notes_target else "not_configured",
            self._bounded_target(notes_target),
            optional=True,
        ))
        steps.append(StudyStep(
            "research",
            "research",
            "Gather bounded supporting sources",
            "configured" if research_query else "not_configured",
            self._bounded_target(research_query),
            optional=True,
        ))
        steps.append(StudyStep(
            "video",
            "video",
            "Find a bounded supporting YouTube video",
            "configured" if youtube_topic else "not_configured",
            self._bounded_target(youtube_topic),
            optional=True,
        ))
        steps.append(StudyStep(
            "music",
            "music",
            "Open the exact configured study playlist",
            "configured" if spotify_playlist else "not_configured",
            self._bounded_target(spotify_playlist),
            optional=True,
        ))
        selected_checklist = tuple(item.strip()[:200] for item in checklist if isinstance(item, str) and item.strip())[:12]
        if not selected_checklist:
            selected_checklist = (
                "Write three questions before reviewing notes",
                "Explain the lecture without looking at the source",
                "Record one follow-up task",
            )
        for index, item in enumerate(selected_checklist, start=1):
            steps.append(StudyStep(f"check-{index}", "checklist", item, "ready" if lecture_ready else "blocked", optional=False))
        if resolution.status is StudyResolutionStatus.RESOLVED:
            status, reason = "ready", None
        elif resolution.status is StudyResolutionStatus.AMBIGUOUS:
            status, reason = "needs_disambiguation", resolution.reason
        else:
            status, reason = "blocked", resolution.reason
        return StudyPlan(f"study-plan-{uuid4()}", resolution.query, status, resolution, tuple(steps), reason)

    def path_for_open(self, owner_id: str, resolution_id: str, candidate_ref: str | None = None) -> Path | None:
        self._prune()
        stored = self._resolutions.get(resolution_id)
        if stored is None or stored.owner_id != owner_id:
            return None
        selected = candidate_ref or (next(iter(stored.candidates)) if len(stored.candidates) == 1 else None)
        path = stored.candidates.get(selected) if selected else None
        if path is None:
            return None
        decision = self.file_access_policy.evaluate(str(path))
        return decision.resolved_path if decision.allowed and decision.resolved_path and decision.resolved_path.is_file() else None

    def _roots(self, raw_root: str | None) -> tuple[tuple[Path, ...], str]:
        if raw_root is None or not raw_root.strip():
            return self.file_access_policy.roots, "study_root_not_configured"
        decision = self.file_access_policy.evaluate_search_root(raw_root)
        if not decision.allowed or decision.resolved_path is None:
            return (), decision.reason_code or "study_root_not_allowed"
        return (decision.resolved_path,), ""

    @staticmethod
    def _normalize_query(value: object) -> str:
        return " ".join(_TOKEN_RE.findall(str(value).casefold()))[:200]

    @staticmethod
    def _score(path: Path, query: str, tokens: tuple[str, ...]) -> int:
        stem = " ".join(_TOKEN_RE.findall(path.stem.casefold()))
        if stem == query:
            return 100
        if query in stem:
            return 80
        if tokens and all(token in stem for token in tokens):
            return 60
        number_tokens = tuple(token for token in tokens if token.isdigit())
        if number_tokens and all(token in stem for token in number_tokens) and "lecture" in tokens:
            return 30
        return 0

    @staticmethod
    def _candidate(path: Path) -> StudyLectureCandidate:
        digest = hashlib.sha256(str(path).casefold().encode("utf-8", errors="replace")).hexdigest()[:16]
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        return StudyLectureCandidate(f"lecture-{digest}", path.stem[:200], path.suffix.casefold().removeprefix("."), size)

    @staticmethod
    def _bounded_target(value: str | None) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        return value.strip()[:300]

    def _prune(self) -> None:
        now = datetime.now(UTC)
        self._resolutions = {key: value for key, value in self._resolutions.items() if value.expires_at > now}
        if len(self._resolutions) > _MAX_RESOLUTIONS:
            for key in tuple(self._resolutions)[: len(self._resolutions) - _MAX_RESOLUTIONS]:
                self._resolutions.pop(key, None)
