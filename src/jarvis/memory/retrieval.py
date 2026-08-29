"""Keyword retrieval with an optional vector-provider seam."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Sequence
from typing import Protocol

from ..contracts import MemoryRecord, MemoryQuery


class EmbeddingProvider(Protocol):
    name: str

    def embed(self, text: str) -> Awaitable[Sequence[float]]: ...


class KeywordMemoryRetriever:
    """Deterministic exact/keyword retrieval used when no local embedder exists."""

    @staticmethod
    def rank(records: Sequence[MemoryRecord], query: MemoryQuery) -> tuple[MemoryRecord, ...]:
        terms = set(re.findall(r"[\w'-]+", query.text.casefold()))
        ranked: list[tuple[float, int, MemoryRecord]] = []
        for index, record in enumerate(records):
            if query.category and record.category != query.category:
                continue
            if query.source and record.source != query.source:
                continue
            if query.tags and not set(query.tags).issubset(set(record.tags)):
                continue
            if not query.include_archived and record.archived:
                continue
            content = record.content.casefold()
            record_terms = set(re.findall(r"[\w'-]+", content))
            score = 0.0
            if query.text:
                score += len(terms & record_terms) * 2.0
                if query.text.casefold().strip() in content:
                    score += 5.0
                if not terms & record_terms:
                    continue
            if record.pinned:
                score += 1.0
            ranked.append((score, -index, record))
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return tuple(item[2] for item in ranked[: max(1, min(query.limit, 100))])
