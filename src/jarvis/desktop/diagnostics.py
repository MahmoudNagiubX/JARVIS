"""Safe diagnostics and one-click repair status for the desktop UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..models.routing import ModelRoute
from ..browser.profile import BrowserProfilePolicy, BrowserProfilePolicyError, validate_brave_executable_path
from .assets import VoiceAssetManager
from .config import DesktopProductConfig, ProductConfigError
from .lifecycle import PRODUCT_SECRET_KEY, JarvisDesktopLifecycle
from .secret_store import SecretStoreUnavailable, cloud_provider_secret_states


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
            results.extend(self._node_checks(settings))
            return tuple(results)
        results.append(DiagnosticResult("core_db", "PASS" if not runtime.database.closed else "FAIL"))
        owner = runtime.repository.first_owner()
        results.append(DiagnosticResult("identity", "PASS" if owner else "FAIL", "owner_missing" if not owner else ""))
        secret = self.lifecycle.secret_store.get(PRODUCT_SECRET_KEY) if self.lifecycle.secret_store else None
        results.append(DiagnosticResult("device_credential", "PASS" if secret else "FAIL", "repair_required" if not secret else ""))
        try:
            model = await runtime.models.health(ModelRoute.FAST_CONVERSATION)
            results.append(DiagnosticResult("local_brain", "PASS" if model.available else "FAIL", model.reason))
        except Exception as exc:
            results.append(DiagnosticResult("local_brain", "FAIL", exc.__class__.__name__))
        architecture = runtime.models.architecture_snapshot()
        for provider in ("groq", "gemini"):
            value = architecture.get(provider)
            state = value.get("state") if isinstance(value, dict) else None
            display_state = {
                "configured_unprobed": "configured",
                "configured": "configured",
                "missing_key": "missing_key",
                "ready": "ready",
            }.get(str(state), "unavailable")
            reason = value.get("reason", "provider_unavailable") if isinstance(value, dict) else "provider_unavailable"
            results.append(DiagnosticResult(f"{provider}_brain", display_state, str(reason)[:160]))
        if settings is not None:
            assets = self.lifecycle.asset_manager.configured_or_discovered(settings.voice_config())
            results.extend(DiagnosticResult(item.name, "PASS" if item.ready else "FAIL", item.reason) for item in assets.statuses())
        results.append(DiagnosticResult("microphone", "PASS" if settings and settings.input_device else "FAIL", "selector_missing" if not settings or not settings.input_device else ""))
        results.append(DiagnosticResult("speaker", "PASS" if settings and settings.output_device else "FAIL", "selector_missing" if not settings or not settings.output_device else ""))
        results.extend(self._runtime_checks(runtime))
        results.extend(self._node_checks(settings))
        return tuple(results)

    def _offline_checks(self, settings: DesktopProductConfig | None) -> list[DiagnosticResult]:
        if settings is None:
            return [DiagnosticResult("core_db", "UNKNOWN", "runtime_not_started"), *self._cloud_checks()]
        assets = self.lifecycle.asset_manager.configured_or_discovered(settings.voice_config())
        return [
            DiagnosticResult("core_db", "UNKNOWN", "runtime_not_started"),
            DiagnosticResult("identity", "PASS" if settings.identity_id else "FAIL", "identity_missing" if not settings.identity_id else ""),
            DiagnosticResult("device_credential", "UNKNOWN", "runtime_not_started"),
            *self._cloud_checks(),
            *(DiagnosticResult(item.name, "PASS" if item.ready else "FAIL", item.reason) for item in assets.statuses()),
            DiagnosticResult("microphone", "PASS" if settings.input_device else "FAIL", "selector_missing" if not settings.input_device else ""),
            DiagnosticResult("speaker", "PASS" if settings.output_device else "FAIL", "selector_missing" if not settings.output_device else ""),
        ]

    def _cloud_checks(self) -> list[DiagnosticResult]:
        try:
            states = cloud_provider_secret_states(self.lifecycle._secret_store())
        except (OSError, SecretStoreUnavailable):
            states = {"groq": "unavailable", "gemini": "unavailable"}
        return [
            DiagnosticResult(f"{provider}_brain", state, f"{provider}_{state}")
            for provider, state in states.items()
        ]

    def _node_checks(self, settings: DesktopProductConfig | None) -> list[DiagnosticResult]:
        status = self.lifecycle.status
        enabled = bool(settings and settings.distributed_fabric_enabled)
        state = status.node_transport_state if enabled else "disabled"
        return [
            DiagnosticResult("node_transport_state", "PASS" if state in {"online", "disabled"} else "FAIL", state),
            DiagnosticResult("node_bind_host", "PASS" if not enabled or settings is not None else "FAIL", settings.node_bind_host if enabled and settings else ""),
            DiagnosticResult("node_port", "PASS" if not enabled or settings is not None else "FAIL", str(settings.node_port) if enabled and settings else ""),
            DiagnosticResult("trusted_network_mode", "PASS", status.trusted_network_mode),
            DiagnosticResult("connected_node_count", "PASS", str(status.connected_node_count)),
        ]

    def _runtime_checks(self, runtime: Any) -> list[DiagnosticResult]:
        """Report backend readiness without probing owner content or mutating state."""
        results: list[DiagnosticResult] = []
        status = self.lifecycle.status
        results.append(DiagnosticResult(
            "ui_server",
            "PASS" if status.hud_url else "PARTIAL",
            "loopback_hud_ready" if status.hud_url else "ui_server_not_started",
        ))

        config = getattr(runtime, "config", None)
        backend = str(getattr(config, "browser_backend", "local"))
        if backend == "playwright":
            try:
                validate_brave_executable_path(getattr(config, "browser_executable_path", None))
                browser_status = "PASS"
                browser_reason = "exact_brave_path_valid"
            except BrowserProfilePolicyError as exc:
                browser_status = "PARTIAL"
                browser_reason = exc.code
            results.append(DiagnosticResult("browser_backend", browser_status, browser_reason))
            policy = BrowserProfilePolicy(
                getattr(config, "browser_profile_root", None),
                owner_persistent_opt_in=bool(getattr(config, "browser_owner_persistent_opt_in", False)),
            )
            if policy.owner_persistent_opt_in:
                try:
                    policy.persistent_user_data_dir(required=True)
                    profile_status, profile_reason = "PASS", "dedicated_profile_policy_ready"
                except BrowserProfilePolicyError as exc:
                    profile_status, profile_reason = "PARTIAL", exc.code
            else:
                profile_status, profile_reason = "PARTIAL", "owner_persistent_opt_in_required"
            results.append(DiagnosticResult("browser_profile", profile_status, profile_reason))
        else:
            results.extend((
                DiagnosticResult("browser_backend", "PASS", "local_controller"),
                DiagnosticResult("browser_profile", "PASS", "ephemeral_local_mode"),
            ))

        local_computer = getattr(getattr(runtime, "computer_actions", None), "controller", None)
        local_computer = getattr(local_computer, "local", local_computer)
        file_policy = getattr(local_computer, "file_access_policy", None)
        root_count = int(file_policy.status().get("root_count", 0)) if file_policy is not None else 0
        results.append(DiagnosticResult(
            "approved_file_roots",
            "PASS" if root_count else "PARTIAL",
            f"root_count={root_count}" if root_count else "file_root_not_configured",
        ))
        tools = getattr(runtime, "tools", None)
        computer_ready = bool(
            getattr(runtime, "computer_actions", None) is not None
            and tools is not None
            and tools.get("computer.keyboard.paste") is not None
            and tools.get("computer.files.manage") is not None
        )
        results.append(DiagnosticResult("computer_use", "PASS" if computer_ready else "FAIL", "typed_action_service_ready" if computer_ready else "computer_action_surface_incomplete"))

        scheduler = getattr(runtime, "scheduler", None)
        results.append(DiagnosticResult(
            "scheduler",
            "PASS" if scheduler is not None and scheduler.running else "PARTIAL",
            f"jobs={len(scheduler.jobs)}" if scheduler is not None and scheduler.running else "scheduler_not_running",
        ))
        event_bus = getattr(runtime, "event_bus", None)
        handler_errors = len(getattr(event_bus, "handler_errors", ())) if event_bus is not None else 0
        results.append(DiagnosticResult(
            "event_bus",
            "PASS" if event_bus is not None and not event_bus.closed and handler_errors == 0 else "PARTIAL",
            "ready" if event_bus is not None and not event_bus.closed and handler_errors == 0 else f"handler_errors={handler_errors}",
        ))
        results.append(DiagnosticResult(
            "backup",
            "PASS" if getattr(runtime, "backup", None) is not None else "FAIL",
            "service_ready" if getattr(runtime, "backup", None) is not None else "backup_service_missing",
        ))
        notifications = getattr(runtime, "notifications", None)
        results.append(DiagnosticResult(
            "notifications",
            "PASS" if notifications is not None and getattr(notifications, "delivery", None) is not None else "PARTIAL",
            "delivery_configured" if notifications is not None and getattr(notifications, "delivery", None) is not None else "local_store_ready_delivery_unconfigured",
        ))
        communications = getattr(runtime, "communications", None)
        channels = communications.list_channels() if communications is not None else ()
        results.append(DiagnosticResult(
            "integrations",
            "PASS" if len(channels) > 1 else "PARTIAL",
            f"channels={len(channels)}" if channels else "no_channels_configured",
        ))
        return results
