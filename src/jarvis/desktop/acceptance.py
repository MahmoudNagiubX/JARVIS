"""In-app physical acceptance state and sanitized evidence only."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class AcceptanceStep(StrEnum):
    SPEAKER = "speaker"
    MICROPHONE = "microphone"
    WAKE = "wake"
    ENGLISH = "english"
    ARABIC = "arabic"
    MIXED = "mixed"
    FOLLOW_UP = "follow_up"
    BARGE_IN = "barge_in"
    PRIVACY_TIMEOUT = "privacy_timeout"


@dataclass(frozen=True, slots=True)
class AcceptanceResult:
    step: str
    status: str
    count: int | None = None
    expected: int | None = None
    median_latency_ms: float | None = None
    safe_label: str | None = None


@dataclass(slots=True)
class PhysicalAcceptanceWizard:
    """Collect PASS/PARTIAL/FAIL facts without collecting private content."""

    results: list[AcceptanceResult] = field(default_factory=list)

    def record(
        self,
        step: AcceptanceStep,
        status: str,
        *,
        count: int | None = None,
        expected: int | None = None,
        median_latency_ms: float | None = None,
        safe_label: str | None = None,
    ) -> AcceptanceResult:
        if status not in {"PASS", "PARTIAL", "FAIL"}:
            raise ValueError("acceptance status must be PASS, PARTIAL, or FAIL")
        if count is not None and (count < 0 or count > 10_000):
            raise ValueError("acceptance count is outside bounds")
        if expected is not None and (expected < 0 or expected > 10_000):
            raise ValueError("acceptance expected count is outside bounds")
        if median_latency_ms is not None and not 0 <= median_latency_ms <= 120_000:
            raise ValueError("acceptance latency is outside bounds")
        label = safe_label.strip() if isinstance(safe_label, str) else None
        if label and (len(label) > 100 or any(char in label for char in "\r\n")):
            raise ValueError("acceptance label is unsafe")
        result = AcceptanceResult(step.value, status, count, expected, median_latency_ms, label)
        self.results.append(result)
        return result

    @property
    def complete(self) -> bool:
        return all(any(item.step == step.value and item.status == "PASS" for item in self.results) for step in AcceptanceStep)

    def sanitized_document(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "generated_at": datetime.now(UTC).isoformat(),
            "physical_status": "PASS" if self.complete else "PENDING",
            "results": [asdict(item) for item in self.results],
            "retention": {"raw_audio": 0, "transcripts": 0, "window_titles": 0, "credentials": 0},
        }

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.sanitized_document(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path
