"""Keyword retrieval with an optional vector-provider seam."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Sequence
from datetime import UTC, datetime
from typing import Protocol

from ..contracts import MemoryRecord, MemoryQuery


class EmbeddingProvider(Protocol):
    name: str

    def embed(self, text: str) -> Awaitable[Sequence[float]]: ...


def normalize_text(text: str) -> str:
    lowered = text.casefold()
    stripped = re.sub(r"[\u064b-\u0652\u0670\u0640]", "", lowered)
    normalized_alef = re.sub(r"[أإآٱ]", "ا", stripped)
    normalized_teh = re.sub(r"ة\b", "ه", normalized_alef)
    normalized_yaa = re.sub(r"ى\b", "ي", normalized_teh)
    return normalized_yaa


class KeywordMemoryRetriever:
    """Deterministic exact/keyword retrieval used when no local embedder exists."""

    @staticmethod
    def rank(records: Sequence[MemoryRecord], query: MemoryQuery) -> tuple[MemoryRecord, ...]:
        now = datetime.now(UTC)
        norm_query = normalize_text(query.text)
        terms = set(re.findall(r"[\w'-]+", norm_query))
        ranked: list[tuple[float, int, MemoryRecord]] = []
        for index, record in enumerate(records):
            if query.category and record.category != query.category:
                continue
            if query.source and record.source != query.source:
                continue
            if query.tags and not set(query.tags).issubset(set(record.tags)):
                continue
            if query.scope and record.scope != query.scope:
                continue
            if query.scopes and record.scope not in query.scopes:
                continue
            if not query.include_archived and record.archived:
                continue
            if record.valid_from and record.valid_from > now:
                continue
            if record.valid_until and record.valid_until <= now:
                continue
            if query.statuses and record.status not in query.statuses:
                continue

            # Check max item bytes
            record_bytes = len(record.content.encode("utf-8"))
            if query.max_item_bytes and record_bytes > query.max_item_bytes:
                continue

            norm_content = normalize_text(record.content)
            norm_struct = " ".join(normalize_text(str(v)) for v in record.structured_data.values())
            norm_tags = " ".join(normalize_text(t) for t in record.tags)
            all_record_text = f"{norm_content} {norm_struct} {norm_tags}"
            record_terms = set(re.findall(r"[\w'-]+", all_record_text))

            score = 0.0
            if query.text:
                matched_terms = terms & record_terms
                score += len(matched_terms) * 2.0
                if norm_query.strip() in norm_content or norm_query.strip() in norm_struct:
                    score += 5.0
                if not matched_terms and norm_query.strip() not in norm_content:
                    continue
            if record.pinned:
                score += 1.0
            score += float(record.confidence) * 0.5
            ranked.append((score, -index, record))

        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)

        result: list[MemoryRecord] = []
        current_total_bytes = 0
        max_items = max(1, min(query.limit, 100))
        for item in ranked:
            if len(result) >= max_items:
                break
            rec = item[2]
            rec_bytes = len(rec.content.encode("utf-8"))
            if query.max_total_bytes and (current_total_bytes + rec_bytes > query.max_total_bytes):
                continue
            result.append(rec)
            current_total_bytes += rec_bytes

        return tuple(result)
