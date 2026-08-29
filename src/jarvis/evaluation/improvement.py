"""Controlled improvement proposals; source mutation is intentionally absent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class ImprovementProposal:
    proposal_id: str
    finding: str
    proposed_change: str
    scoped_repository: str | None
    required_tests: tuple[str, ...]
    status: str = "proposed"
    requires_human_approval: bool = True


class ControlledImprovementPolicy:
    """The only output is a reviewable proposal for the normal dev workflow."""

    def propose(self, proposal_id: str, finding: str, proposed_change: str, *, repository: str | None = None, tests: tuple[str, ...] = ()) -> ImprovementProposal:
        if not finding.strip() or not proposed_change.strip():
            raise ValueError("finding and proposed change are required")
        return ImprovementProposal(proposal_id, finding.strip(), proposed_change.strip(), repository, tests)

    def can_apply_automatically(self, proposal: ImprovementProposal) -> bool:
        return False
