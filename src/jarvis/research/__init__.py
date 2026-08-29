"""Bounded local-first research runtime."""

from .providers import BrowserResearchProvider, LocalDocumentProvider, SearXNGResearchProvider
from .service import ResearchService

__all__ = ["BrowserResearchProvider", "LocalDocumentProvider", "ResearchService", "SearXNGResearchProvider"]
