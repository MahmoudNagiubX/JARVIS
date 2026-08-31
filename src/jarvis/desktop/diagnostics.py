"""Safe diagnostics and one-click repair status for the desktop UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..models.routing import ModelRoute
from .assets import VoiceAssetManager
from .config import DesktopProductConfig, ProductConfigError
from .lifecycle import PRODUCT_SECRET_KEY, JarvisDesktopLifecycle


@dataclass(frozen=True, slots=True)
class DiagnosticResult:
    name: str
    status: str
    reason: str = ""


class DesktopDiagnostics:
    def __init__(self, lifecycle: JarvisDesktopLifecycle) -> None:
        self.lifecycle = lifecycle

    async def run(self) -> tuple[DiagnosticResult, ...]:
        results: list[DiagnosticResult] = []
        settings: DesktopProductConfig | None = None
        try:
            settings = DesktopProductConfig.load(self.lifecycle.config_path)
            results.append(DiagnosticResult("configuration", "PASS"))
        except ProductConfigError as exc:
            results.append(DiagnosticResult("configuration", "FAIL", str(exc)))
        runtime = self.lifecycle.runtime
        if runtime is None:
            results.extend(self._offline_checks(settings))
            return tuple(results)
        results.append(DiagnosticResult("core_db", "PASS" if not runtime.database.closed else "FAIL"))
        owner = runtime.repository.first_owner()
        results.append(DiagnosticResult("identity", "PASS" if owner else "FAIL", "owner_missing" if not owner else ""))
        secret = self.lifecycle.secret_store.get(PRODUCT_SECRET_KEY) if self.lifecycle.secret_store else None
        results.append(DiagnosticResult("device_credential", "PASS" if secret else "FAIL", "repair_required" if not secret else ""))
        try:
            model = await runtime.models.health(ModelRoute.GENERAL_REASONING)
            results.append(DiagnosticResult("local_brain", "PASS" if model.available else "FAIL", model.reason))
        except Exception as exc:
            results.append(DiagnosticResult("local_brain", "FAIL", exc.__class__.__name__))
        if settings is not None:
            assets = self.lifecycle.asset_manager.configured_or_discovered(settings.voice_config())
            results.extend(DiagnosticResult(item.name, "PASS" if item.ready else "FAIL", item.reason) for item in assets.statuses())
        results.append(DiagnosticResult("microphone", "PASS" if settings and settings.input_device else "FAIL", "selector_missing" if not settings or not settings.input_device else ""))
        results.append(DiagnosticResult("speaker", "PASS" if settings and settings.output_device else "FAIL", "selector_missing" if not settings or not settings.output_device else ""))
        return tuple(results)

    @staticmethod
    def _offline_checks(settings: DesktopProductConfig | None) -> list[DiagnosticResult]:
        if settings is None:
            return [DiagnosticResult("core_db", "UNKNOWN", "runtime_not_started")]
        assets = self.lifecycle.asset_manager.configured_or_discovered(settings.voice_config())
        return [
            DiagnosticResult("core_db", "UNKNOWN", "runtime_not_started"),
            DiagnosticResult("identity", "PASS" if settings.identity_id else "FAIL", "identity_missing" if not settings.identity_id else ""),
            DiagnosticResult("device_credential", "UNKNOWN", "runtime_not_started"),
            *(DiagnosticResult(item.name, "PASS" if item.ready else "FAIL", item.reason) for item in assets.statuses()),
            DiagnosticResult("microphone", "PASS" if settings.input_device else "FAIL", "selector_missing" if not settings.input_device else ""),
            DiagnosticResult("speaker", "PASS" if settings.output_device else "FAIL", "selector_missing" if not settings.output_device else ""),
        ]
