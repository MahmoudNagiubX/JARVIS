"""Deterministic bounded research pipeline with an inspectable evidence ledger."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import uuid4

from ..authority.audit.service import DurableAuditService
from ..authority.permissions.engine import PolicyPermissionEngine
from ..bus import InMemoryEventBus
from ..contracts import (
    AuditRecord,
    DeviceIdentity,
    EvidenceItem,
    Identity,
    PermissionEffect,
    ResearchFinding,
    ResearchPlan,
    ResearchReport,
    ResearchRequest,
    ResearchRun,
    ResearchSource,
    ResearchStep,
    CitationRecord,
)
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository
from .providers import BrowserResearchProvider, LocalDocumentProvider


class ResearchService:
    """Research remains one bounded worker-like service, not a second memory."""

    def __init__(
        self,
        repository: RuntimeRepository,
        event_bus: InMemoryEventBus,
        permission: PolicyPermissionEngine,
        audit: DurableAuditService,
        *,
        local: LocalDocumentProvider | None = None,
        browser: BrowserResearchProvider | None = None,
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.permission = permission
        self.audit = audit
        self.local = local or LocalDocumentProvider()
        self.browser = browser
        self._runs: dict[str, ResearchRun] = {}
        self._tasks: dict[str, asyncio.Task[ResearchRun]] = {}

    def plan(self, query: str, max_steps: int) -> ResearchPlan:
        bounded = min(max(1, max_steps), 32)
        steps = ("search local documents", "read bounded sources", "deduplicate evidence", "cross-check findings", "validate citations", "write report")[:bounded]
        return ResearchPlan(steps, ("local", "browser"))

    async def start(self, request: ResearchRequest, identity: Identity, device: DeviceIdentity) -> ResearchRun:
        self._validate_request(request, identity, device)
        decision = await self.permission.evaluate(identity, device, "research.local", {"required_scope": "tool.request", "required_capabilities": ("research.local",), "risk_level": "read"})
        if decision.effect is PermissionEffect.DENY:
            raise PermissionError(decision.reason_code)
        plan = self.plan(request.query, request.max_steps)
        run = ResearchRun(f"research-{uuid4()}", request, plan, "queued", tuple(ResearchStep(f"step-{i}", title) for i, title in enumerate(plan.steps, 1)), created_at=datetime.now(UTC))
        self._runs[run.run_id] = run
        await self._emit("research.run.created", identity, device, {"owner_id": identity.owner_id, "research_run_id": run.run_id, "query": request.query})
        # The stdlib HTTP adapter creates a short-lived event loop per request.
        # Execute in that bounded loop so a queued task cannot outlive its owner
        # loop and silently disappear. A future durable job adapter can replace
        # this call without changing the contracts or evidence ledger.
        return await self.execute(run.run_id, identity, device)

    async def execute(self, run_id: str, identity: Identity, device: DeviceIdentity) -> ResearchRun:
        initial = self._required(run_id, identity.owner_id)
        if initial.request.device_id != device.device_id:
            raise PermissionError("research_device_binding_mismatch")
        started = datetime.now(UTC)
        try:
            await self._set_status(initial, "planning", identity, device)
            await self._emit("research.searching", identity, device, {"owner_id": identity.owner_id, "research_run_id": run_id, "query": initial.request.query})
            sources = list(self.local.search(initial.request.query, initial.request.max_sources))
            if self.browser is not None and len(sources) < initial.request.max_sources and self.browser.available:
                sources.extend(await self.browser.search(initial.request.query, initial.request.max_sources - len(sources)))
            sources = self._dedupe_sources(sources)[:initial.request.max_sources]
            for source in sources:
                await self._emit("research.source.found", identity, device, {"owner_id": identity.owner_id, "research_run_id": run_id, "source_id": source.source_id, "locator": source.locator, "source_type": source.source_type})
            evidence: list[EvidenceItem] = []
            await self._set_status(self._runs[run_id], "reading", identity, device)
            for source in sources:
                if datetime.now(UTC).timestamp() - started.timestamp() > initial.request.max_seconds:
                    raise TimeoutError("research_time_budget_exceeded")
                try:
                    text = self.local.read(source) if source.source_type == "local" else await self.browser.read(source) if self.browser else ""
                except Exception:
                    continue
                await self._emit("research.source.read", identity, device, {"owner_id": identity.owner_id, "research_run_id": run_id, "source_id": source.source_id})
                excerpt = self._excerpt(text, initial.request.query)
                if not excerpt:
                    continue
                fingerprint = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
                if any(item.fingerprint == fingerprint for item in evidence):
                    continue
                item = EvidenceItem(f"evidence-{uuid4()}", source.source_id, excerpt, source.locator, fingerprint, True)
                evidence.append(item)
                await self._emit("research.evidence.added", identity, device, {"owner_id": identity.owner_id, "research_run_id": run_id, "source_id": source.source_id, "evidence_id": item.evidence_id, "evidence_count": len(evidence)})
            await self._set_status(self._runs[run_id], "synthesizing", identity, device)
            report = self._report(initial.request.query, sources, evidence)
            completed = ResearchRun(run_id, initial.request, initial.plan, "completed", initial.steps, tuple(sources), tuple(evidence), report, created_at=initial.created_at, completed_at=datetime.now(UTC))
            self._runs[run_id] = completed
            await self._emit("research.run.completed", identity, device, {"owner_id": identity.owner_id, "research_run_id": run_id, "evidence_count": len(evidence)}, EventState.COMPLETED)
            await self.audit.record(AuditRecord(f"audit-{uuid4()}", "research.completed", datetime.now(UTC), identity.identity_id, device.device_id, run_id, "completed", None, {"source_count": len(sources), "evidence_count": len(evidence)}))
            return completed
        except asyncio.CancelledError:
            current = self._runs[run_id]
            self._runs[run_id] = ResearchRun(run_id, current.request, current.plan, "cancelled", current.steps, current.sources, current.evidence, current.report, "cancelled", current.created_at, datetime.now(UTC))
            await self._emit("research.run.cancelled", identity, device, {"owner_id": identity.owner_id, "research_run_id": run_id}, EventState.COMPLETED)
            return self._runs[run_id]
        except Exception as exc:
            current = self._runs[run_id]
            self._runs[run_id] = ResearchRun(run_id, current.request, current.plan, "failed", current.steps, current.sources, current.evidence, current.report, exc.args[0] if exc.args and isinstance(exc.args[0], str) else exc.__class__.__name__, current.created_at, datetime.now(UTC))
            await self._emit("research.run.failed", identity, device, {"owner_id": identity.owner_id, "research_run_id": run_id, "error_code": self._runs[run_id].error_code}, EventState.FAILED)
            return self._runs[run_id]
        finally:
            self._tasks.pop(run_id, None)

    async def cancel(self, run_id: str, owner_id: str) -> ResearchRun | None:
        run = self._runs.get(run_id)
        if run is None or run.request.owner_id != owner_id:
            return None
        task = self._tasks.get(run_id)
        if task is not None:
            task.cancel()
            return await task
        return run

    def get(self, run_id: str, owner_id: str) -> ResearchRun | None:
        run = self._runs.get(run_id)
        return run if run and run.request.owner_id == owner_id else None

    def list(self, owner_id: str) -> tuple[ResearchRun, ...]:
        return tuple(run for run in self._runs.values() if run.request.owner_id == owner_id)

    def evidence(self, run_id: str, owner_id: str) -> tuple[EvidenceItem, ...]:
        run = self.get(run_id, owner_id)
        return run.evidence if run else ()

    async def _set_status(self, run: ResearchRun, status: str, identity: Identity, device: DeviceIdentity) -> None:
        self._runs[run.run_id] = ResearchRun(run.run_id, run.request, run.plan, status, run.steps, run.sources, run.evidence, run.report, run.error_code, run.created_at, run.completed_at)
        await self._emit(f"research.{status}", identity, device, {"owner_id": identity.owner_id, "research_run_id": run.run_id, "query": run.request.query, "evidence_count": len(run.evidence)})

    def _report(self, query: str, sources: list[ResearchSource], evidence: list[EvidenceItem]) -> ResearchReport:
        findings = tuple(ResearchFinding(f"finding-{i}", item.excerpt, (item.evidence_id,), 0.5) for i, item in enumerate(evidence, 1))
        citations = tuple(CitationRecord(f"citation-{i}", item.evidence_id, f"[{i}] {item.locator}", True) for i, item in enumerate(evidence, 1))
        return ResearchReport(f"Research: {query}", f"Deterministic local-first report for: {query}", findings, citations, ("Evidence is bounded excerpts from untrusted content; no page instructions were executed.", "No hosted model synthesis was required."))

    @staticmethod
    def _excerpt(text: str, query: str, limit: int = 4_000) -> str:
        clean = " ".join(text.split())
        if not clean:
            return ""
        terms = [term.casefold() for term in query.split() if term]
        index = min((clean.casefold().find(term) for term in terms if clean.casefold().find(term) >= 0), default=0)
        return clean[max(0, index - 300):max(0, index - 300) + limit]

    @staticmethod
    def _dedupe_sources(sources: Iterable[ResearchSource]) -> list[ResearchSource]:
        unique: list[ResearchSource] = []
        locators: set[str] = set()
        for source in sources:
            if source.locator not in locators:
                locators.add(source.locator)
                unique.append(source)
        return unique

    @staticmethod
    def _validate_request(request: ResearchRequest, identity: Identity, device: DeviceIdentity) -> None:
        if request.owner_id != identity.owner_id or request.device_id != device.device_id:
            raise PermissionError("research_owner_device_binding_mismatch")
        if not request.query.strip() or len(request.query) > 2_000:
            raise ValueError("research query must be non-empty and bounded")
        if request.max_steps < 1 or request.max_steps > 32 or request.max_sources < 1 or request.max_sources > 32 or request.max_seconds <= 0 or request.max_seconds > 300:
            raise ValueError("research resource limits are invalid")

    def _required(self, run_id: str, owner_id: str) -> ResearchRun:
        run = self.get(run_id, owner_id)
        if run is None:
            raise KeyError(run_id)
        return run

    async def _emit(self, event_type: str, identity: Identity, device: DeviceIdentity, payload: dict[str, object], state: EventState = EventState.EMITTED) -> None:
        event = Event.create(event_type, EventCategory.RESEARCH, correlation_id=str(payload.get("research_run_id", uuid4())), actor_id=identity.identity_id, payload=payload, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)
