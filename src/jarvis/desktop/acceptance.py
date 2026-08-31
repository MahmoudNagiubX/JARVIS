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


@dataclass(frozen=True, slots=True)
class AcceptanceStepView:
    step: AcceptanceStep
    title: str
    instruction: str
    status: str


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


_STEP_INSTRUCTIONS: dict[AcceptanceStep, tuple[str, str]] = {
    AcceptanceStep.SPEAKER: ("Speaker", "Play the fixed safe test and confirm: Did you hear JARVIS?"),
    AcceptanceStep.MICROPHONE: ("Microphone", "Speak normally and verify the transient level meter; no recording is stored."),
    AcceptanceStep.WAKE: ("Wake", 'Say "Hey Jarvis" 10 times and verify the safe detected-wake count.'),
    AcceptanceStep.ENGLISH: ("English", "Complete one real English microphone-to-agent-to-Qwen-to-speaker turn."),
    AcceptanceStep.ARABIC: ("Egyptian Arabic", "Say the Arabic real-tool prompt and verify the complete local tool turn."),
    AcceptanceStep.MIXED: ("Mixed Arabic-English", 'Say: "Hey Jarvis, قولي الstatus بتاعك."'),
    AcceptanceStep.FOLLOW_UP: ("Follow-Up", "Ask a second question without the wake word and verify the renewed window."),
    AcceptanceStep.BARGE_IN: ("Barge-In", 'While a bounded response plays, say "Hey Jarvis" and verify playback stops.'),
    AcceptanceStep.PRIVACY_TIMEOUT: ("Privacy Timeout", "Wake, remain silent, and verify return to sleep; later speech without wake is ignored."),
}


class PhysicalAcceptanceController:
    """Headless controller seam used by the in-app human acceptance wizard."""

    def __init__(
        self,
        wizard: PhysicalAcceptanceWizard | None = None,
        *,
        require_microphone_probe: bool = False,
        require_wake_detections: bool = False,
    ) -> None:
        self.wizard = wizard or PhysicalAcceptanceWizard()
        self._index = 0
        self.require_microphone_probe = require_microphone_probe
        self.require_wake_detections = require_wake_detections
        self._microphone_probe: Any | None = None

    def set_microphone_probe(self, result: Any) -> None:
        """Attach metrics-only evidence from the real live microphone probe."""

        self._microphone_probe = result

    @property
    def complete(self) -> bool:
        return self.wizard.complete

    @property
    def current_step(self) -> AcceptanceStep | None:
        return tuple(AcceptanceStep)[self._index] if self._index < len(AcceptanceStep) else None

    def steps(self) -> tuple[AcceptanceStepView, ...]:
        statuses = {step: self.status(step) for step in AcceptanceStep}
        return tuple(
            AcceptanceStepView(step, *_STEP_INSTRUCTIONS[step], statuses[step])
            for step in AcceptanceStep
        )

    def status(self, step: AcceptanceStep) -> str:
        for result in reversed(self.wizard.results):
            if result.step == step.value:
                return result.status
        return "PENDING"

    def instruction(self) -> str:
        step = self.current_step
        return _STEP_INSTRUCTIONS[step][1] if step is not None else "All physical acceptance steps are complete."

    def record_current(
        self,
        status: str,
        *,
        count: int | None = None,
        expected: int | None = None,
        median_latency_ms: float | None = None,
        safe_label: str | None = None,
    ) -> AcceptanceResult:
        step = self.current_step
        if step is None:
            raise ValueError("physical acceptance wizard is already complete")
        if step is AcceptanceStep.MICROPHONE and status == "PASS" and self.require_microphone_probe:
            if self._microphone_probe is None or not bool(getattr(self._microphone_probe, "usable_signal", False)):
                raise ValueError("microphone PASS requires a usable live probe")
        if step is AcceptanceStep.WAKE and status == "PASS" and self.require_wake_detections:
            if expected is None or count is None or count < expected:
                raise ValueError("wake PASS requires backend detections")
        result = self.wizard.record(
            step,
            status,
            count=count,
            expected=expected,
            median_latency_ms=median_latency_ms,
            safe_label=safe_label,
        )
        if status == "PASS":
            self._index += 1
        return result

    def save(self, path: Path) -> Path:
        return self.wizard.save(path)
