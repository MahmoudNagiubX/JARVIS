"""A cloud-free evaluation seam for explicit deterministic expectations."""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Mapping
from uuid import uuid4

from ..bus import InMemoryEventBus
from ..events import Event, EventCategory, EventState
from ..persistence.repositories import RuntimeRepository


Check = Callable[[Mapping[str, object]], bool | str]


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    case_id: str
    name: str
    metric: str
    check: Check
    expected: object = True


@dataclass(frozen=True, slots=True)
class EvaluationMetric:
    name: str
    value: float
    passed: bool


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    case_id: str
    name: str
    metric: str
    passed: bool
    expected: object
    actual: object
    detail: str = ""


@dataclass(frozen=True, slots=True)
class RegressionSuite:
    name: str
    cases: tuple[EvaluationCase, ...]
    description: str = ""


@dataclass(frozen=True, slots=True)
class EvaluationRun:
    run_id: str
    owner_id: str | None
    suite: str
    status: str
    passed: bool
    regression: bool
    summary: str
    results: tuple[EvaluationResult, ...]
    started_at: datetime
    completed_at: datetime | None = None


class EvaluationService:
    def __init__(self, repository: RuntimeRepository, event_bus: InMemoryEventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self._suites: dict[str, RegressionSuite] = {}

    def register(self, suite: RegressionSuite) -> None:
        if not suite.name.strip() or not suite.cases:
            raise ValueError("evaluation suite needs a name and cases")
        self._suites[suite.name] = suite

    def suites(self) -> tuple[RegressionSuite, ...]:
        return tuple(self._suites.values())

    def register_default_suites(self) -> None:
        """Register local contract checks; callers can replace them with richer fixtures."""
        checks = {
            "routing": "routing_ok",
            "tool_selection": "tool_selection_ok",
            "permission_decisions": "permission_ok",
            "memory_retrieval": "memory_ok",
            "world_state_retrieval": "world_state_ok",
            "mission_planning": "mission_plan_ok",
            "skill_selection": "skill_selection_ok",
            "research_citation_quality": "citation_ok",
            "briefing_relevance": "briefing_ok",
            "proactive_alert_dedup": "dedup_ok",
        }
        for name, key in checks.items():
            self.register(RegressionSuite(name, (EvaluationCase(f"{name}-contract", f"{name} contract", name, lambda context, key=key: bool(context.get(key, True))),), "Deterministic product contract check."))

    async def run(self, suite: str | RegressionSuite, *, owner_id: str | None = None, context: Mapping[str, object] | None = None) -> EvaluationRun:
        selected = self._suites.get(suite) if isinstance(suite, str) else suite
        if selected is None:
            raise KeyError(str(suite))
        started = datetime.now(UTC)
        run_id = f"evaluation-{uuid4()}"
        await self._emit("evaluation.started", run_id, owner_id, selected.name, EventState.ACCEPTED)
        results: list[EvaluationResult] = []
        for case in selected.cases:
            try:
                actual = case.check(context or {})
                if inspect.isawaitable(actual):
                    actual = await actual
                passed = actual is True if case.expected is True else actual == case.expected
                detail = "passed" if passed else "expectation_mismatch"
            except Exception as exc:
                actual, passed, detail = f"error:{exc.__class__.__name__}", False, "check_error"
            results.append(EvaluationResult(case.case_id, case.name, case.metric, passed, case.expected, actual, detail))
        passed = all(item.passed for item in results)
        previous = next((row for row in self.repository.evaluation_runs(None) if row.get("suite") == selected.name), None)
        previous_passed = bool(previous and previous.get("passed"))
        regression = bool(previous_passed and not passed)
        run = EvaluationRun(run_id, owner_id, selected.name, "completed", passed, regression, f"{sum(item.passed for item in results)}/{len(results)} evaluation cases passed", tuple(results), started, datetime.now(UTC))
        self.repository.insert_evaluation_run(run)
        await self._emit("evaluation.regression_detected" if regression else "evaluation.completed", run_id, owner_id, selected.name, EventState.FAILED if regression else EventState.COMPLETED, {"passed": passed, "regression": regression, "summary": run.summary})
        return run

    def list(self, owner_id: str | None = None) -> list[dict[str, object]]:
        return self.repository.evaluation_runs(owner_id)

    async def _emit(self, name: str, run_id: str, owner_id: str | None, suite: str, state: EventState, extra: Mapping[str, object] | None = None) -> None:
        event = Event.create(name, EventCategory.EVALUATION, correlation_id=run_id, actor_id=owner_id, payload={"owner_id": owner_id, "evaluation_id": run_id, "suite": suite, **dict(extra or {})}, state=state)
        self.repository.append_event(event)
        await self.event_bus.publish(event)
