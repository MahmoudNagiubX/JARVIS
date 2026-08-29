"""Deterministic mission planning below GoalEngine and above workers/tools."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from ..contracts import Mission, MissionBudget, MissionPlan, MissionStep


class MissionPlanner:
    """Produce an inspectable plan from the request and bounded local context."""

    def plan(
        self,
        mission: Mission,
        *,
        available_capabilities: Iterable[str] = (),
        world_state: Mapping[str, object] | None = None,
        memories: Iterable[Mapping[str, object]] = (),
        constraints: Mapping[str, object] | None = None,
    ) -> MissionPlan:
        del world_state, memories
        available = set(available_capabilities)
        requested = f"{mission.title} {mission.request}".casefold()
        titles = [
            ("inspect workspace and current evidence", "workspace.read", "read", False),
            ("run a bounded validation", "project.tests.run", "safe", False),
            ("summarize verified findings", None, "read", False),
        ]
        if any(word in requested for word in ("fix", "debug", "repair", "implement")):
            titles = [
                ("inspect workspace and current evidence", "workspace.read", "read", False),
                ("run a bounded validation", "project.tests.run", "safe", False),
                ("prepare a scoped change proposal", "developer.worker", "consequential", True),
                ("review the proposed diff", "workspace.read", "read", False),
                ("rerun bounded validation", "project.tests.run", "safe", False),
                ("summarize verified findings", None, "read", False),
            ]
        elif "research" in requested:
            titles = [
                ("search approved local evidence", "research.local", "read", False),
                ("read bounded sources", "research.local", "read", False),
                ("validate citations and limitations", "research.local", "read", False),
                ("summarize verified findings", None, "read", False),
            ]
        if constraints and isinstance(constraints.get("max_steps"), int):
            titles = titles[:max(1, int(constraints["max_steps"]))]
        titles = titles[:mission.budget.max_steps]
        steps = tuple(
            MissionStep(
                f"mission-step-{index}", title, required_capability=capability,
                risk_level=risk, approval_required=approval,
                expected_evidence=("event", "result") if capability else ("summary",),
            )
            for index, (title, capability, risk, approval) in enumerate(titles, 1)
        )
        risk = "consequential" if any(item.approval_required for item in steps) else "read"
        expected = tuple(sorted({evidence for item in steps for evidence in item.expected_evidence}))
        return MissionPlan(
            steps, risk_level=risk, expected_evidence=expected,
            completion_criteria=("all planned steps have verified results",),
        )
