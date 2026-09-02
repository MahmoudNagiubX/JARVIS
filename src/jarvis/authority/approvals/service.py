"""Durable approval pause/resume state machine."""

from __future__ import annotations

from datetime import UTC, datetime

from ...contracts import ApprovalDecision, ApprovalRequest, ApprovalStatus
from ...persistence.repositories import RuntimeRepository


class DurableApprovalEngine:
    def __init__(self, repository: RuntimeRepository) -> None:
        self.repository = repository

    async def request(self, request: ApprovalRequest) -> ApprovalDecision:
        self.repository.insert_approval(request, ApprovalStatus.PENDING.value)
        return ApprovalDecision(request.approval_id, ApprovalStatus.PENDING, None, None)

    async def decide(self, approval_id: str, approved: bool, decided_by: str) -> ApprovalDecision:
        decision, _ = await self.decide_with_claim(approval_id, approved, decided_by)
        return decision

    async def decide_with_claim(
        self, approval_id: str, approved: bool, decided_by: str
    ) -> tuple[ApprovalDecision, bool]:
        """Atomically decide an approval and report whether this caller won."""

        row = self.repository.approval(approval_id)
        if row is None:
            raise KeyError(approval_id)
        now = datetime.now(UTC)
        if row["status"] != ApprovalStatus.PENDING.value:
            return self._decision(row), False
        if datetime.fromisoformat(row["expires_at"]) <= now:
            claimed = self.repository.update_approval(approval_id, ApprovalStatus.EXPIRED.value, decided_by, now, "approval_expired")
        else:
            claimed = self.repository.update_approval(
                approval_id,
                ApprovalStatus.APPROVED.value if approved else ApprovalStatus.REJECTED.value,
                decided_by,
                now,
                None,
            )
        row = self.repository.approval(approval_id)
        return self._decision(row), claimed

    async def get(self, approval_id: str) -> ApprovalDecision | None:
        row = self.repository.approval(approval_id)
        if row is None:
            return None
        if row["status"] == ApprovalStatus.PENDING.value and datetime.fromisoformat(row["expires_at"]) <= datetime.now(UTC):
            now = datetime.now(UTC)
            self.repository.update_approval(approval_id, ApprovalStatus.EXPIRED.value, "system", now, "approval_expired")
            row = self.repository.approval(approval_id)
        return self._decision(row)

    @staticmethod
    def _decision(row: dict[str, object] | None) -> ApprovalDecision:
        if row is None:
            raise KeyError("approval")
        decided_at = datetime.fromisoformat(row["decided_at"]) if row["decided_at"] else None
        return ApprovalDecision(row["id"], ApprovalStatus(row["status"]), row["decided_by"], decided_at, row["decision_reason"])
