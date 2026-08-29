"""Injected research providers. No hosted search client is a runtime dependency."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ..contracts import ResearchSource


class LocalDocumentProvider:
    name = "local"
    available = True
    allowed_suffixes = frozenset({".md", ".txt", ".rst", ".py", ".json", ".toml", ".yaml", ".yml"})

    def __init__(self, roots: Iterable[str] = (), *, max_file_bytes: int = 250_000) -> None:
        self.roots = tuple(Path(root).expanduser().resolve(strict=False) for root in roots) or (Path.cwd().resolve(),)
        self.max_file_bytes = max(1_000, min(max_file_bytes, 2_000_000))

    def search(self, query: str, max_sources: int) -> tuple[ResearchSource, ...]:
        terms = tuple(item.casefold() for item in query.split() if item.strip())
        if not terms:
            return ()
        found: list[ResearchSource] = []
        seen: set[str] = set()
        for root in self.roots:
            if not root.exists() or not root.is_dir():
                continue
            for path in root.rglob("*"):
                if len(found) >= max_sources:
                    return tuple(found)
                if not path.is_file() or path.suffix.casefold() not in self.allowed_suffixes or str(path) in seen:
                    continue
                try:
                    if path.stat().st_size > self.max_file_bytes:
                        continue
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                haystack = f"{path.name}\n{text}".casefold()
                if all(term in haystack for term in terms):
                    seen.add(str(path))
                    found.append(ResearchSource(f"source-{uuid4()}", str(path), path.name, self.name, datetime.now(UTC), trust="local-file"))
        return tuple(found)

    def read(self, source: ResearchSource) -> str:
        path = Path(source.locator).resolve(strict=True)
        if not any(path == root or root in path.parents for root in self.roots):
            raise PermissionError("local source outside configured roots")
        if path.suffix.casefold() not in self.allowed_suffixes or path.stat().st_size > self.max_file_bytes:
            raise ValueError("local source is not an allowed bounded document")
        return path.read_text(encoding="utf-8", errors="replace")


class BrowserResearchProvider:
    name = "browser"

    def __init__(self, searcher: Callable[[str, int], Awaitable[Iterable[ResearchSource]] | Iterable[ResearchSource]] | None = None, reader: Callable[[ResearchSource], Awaitable[str] | str] | None = None) -> None:
        self.searcher = searcher
        self.reader = reader

    @property
    def available(self) -> bool:
        return self.searcher is not None and self.reader is not None

    async def search(self, query: str, max_sources: int) -> tuple[ResearchSource, ...]:
        if self.searcher is None:
            return ()
        result = self.searcher(query, max_sources)
        if inspect.isawaitable(result):
            result = await result
        return tuple(result)[:max_sources]

    async def read(self, source: ResearchSource) -> str:
        if self.reader is None:
            raise RuntimeError("browser provider is not configured")
        result = self.reader(source)
        return await result if inspect.isawaitable(result) else result


class SearXNGResearchProvider(BrowserResearchProvider):
    """Optional injected SearXNG seam; it remains unavailable without wiring."""

    name = "searxng"

    def __init__(self, base_url: str | None = None, **kwargs: object) -> None:
        super().__init__(None, None)
        self.base_url = base_url
        self._configured = bool(base_url)
        self._kwargs = kwargs

    @property
    def available(self) -> bool:
        return self._configured
