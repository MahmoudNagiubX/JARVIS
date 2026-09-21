"""Narrow, server-owned native application fast path.

This module only classifies an exact, high-confidence command.  It never
launches a process itself: resolution returns an opaque ``app_ref`` and the
existing ToolExecutionService -> ComputerActionService pipeline remains the
only execution authority.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from ...computer.applications import ApplicationLookup, InstalledApplicationRegistry
from ...contracts import DeviceIdentity, Identity, ToolContext
from ...tools.service import ToolCallResult, ToolExecutionService, ToolExecutionStatus


@dataclass(frozen=True, slots=True)
class NativeAppCommand:
    """A deliberately small command grammar result."""

    application_query: str


@dataclass(frozen=True, slots=True)
class NativeAppFastPathResult:
    """Bounded result returned to AgentRuntime without model-facing details."""

    handled: bool
    outcome: str = "fallback"
    application_query: str | None = None
    display_name: str | None = None
    app_ref: str | None = None
    tool_result: ToolCallResult | None = None
    reason: str | None = None
    timings_ms: Mapping[str, float] = field(default_factory=dict)


class NativeAppFastPath:
    """Classify and execute only exact native-app launch/focus requests."""

    _COMMAND = re.compile(r"^(?:open|launch|start|افتح|شغل)\s+(.+)$", re.IGNORECASE)
    _FORBIDDEN_QUERY = re.compile(r"[\\/:;,\"'`]|^(?:and|then|with|و|ثم|مع)\s|\s(?:and|then|with|و|ثم|مع)\s", re.IGNORECASE)

    def __init__(self, registry: InstalledApplicationRegistry, tools: ToolExecutionService) -> None:
        self.registry = registry
        self.tools = tools

    def classify(self, text: str) -> NativeAppCommand | None:
        """Return a command only when the complete input matches the grammar."""

        if not isinstance(text, str):
            return None
        normalized = " ".join(text.strip().split())
        match = self._COMMAND.fullmatch(normalized)
        if match is None:
            return None
        query = match.group(1).strip()
        if not query or len(query) > 80 or len(query.split()) > 5 or self._FORBIDDEN_QUERY.search(query):
            return None
        return NativeAppCommand(query)

    async def execute(
        self,
        text: str,
        identity: Identity,
        device: DeviceIdentity,
        *,
        session_id: str,
        correlation_id: str,
        run_id: str,
        request_received_ns: int | None = None,
    ) -> NativeAppFastPathResult:
        request_received = request_received_ns or time.monotonic_ns()
        timestamps: dict[str, int] = {"request_received": request_received}

        def mark(stage: str) -> None:
            timestamps.setdefault(stage, time.monotonic_ns())

        command = self.classify(text)
        if command is None:
            return NativeAppFastPathResult(False, reason="not_an_exact_native_app_command")
        mark("intent_classified")

        lookup: ApplicationLookup = self.registry.find(command.application_query)
        if lookup.status == "ambiguous":
            # Ambiguity is intentionally handed back to the normal model path;
            # the model may explain the ambiguity, but it cannot guess a target.
            return NativeAppFastPathResult(False, application_query=command.application_query, reason="application_identity_ambiguous")
        if lookup.status != "matched" or lookup.application is None:
            mark("verification_completed")
            return NativeAppFastPathResult(
                True,
                outcome="failed",
                application_query=command.application_query,
                reason="application_not_installed",
                timings_ms=self._timings(timestamps, request_received),
            )

        application = lookup.application
        app_ref = application.app_ref
        display_name = application.display_name
        mark("app_ref_resolved")
        context = ToolContext(
            identity,
            device,
            session_id,
            correlation_id,
            metadata={"_native_action_timing": mark},
        )
        result = await self.tools.execute(
            "computer.open_application",
            {"app_ref": app_ref},
            context,
            run_id=run_id,
        )
        mark("verification_completed")
        if result.status is ToolExecutionStatus.APPROVAL_REQUIRED:
            outcome = "paused"
        elif result.status is ToolExecutionStatus.COMPLETED:
            outcome = "succeeded"
        else:
            outcome = "failed"
        return NativeAppFastPathResult(
            True,
            outcome=outcome,
            application_query=command.application_query,
            display_name=display_name,
            app_ref=app_ref,
            tool_result=result,
            reason=result.error_code,
            timings_ms=self._timings(timestamps, request_received),
        )

    @staticmethod
    def _timings(timestamps: Mapping[str, int], request_received: int) -> dict[str, float]:
        return {
            stage: round(max(0, value - request_received) / 1_000_000, 3)
            for stage, value in timestamps.items()
        }
