"""One desktop lifecycle coordinator over the existing JARVIS authorities."""

from __future__ import annotations

import asyncio
import threading
import webbrowser
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable

from ..authority.identity.service import EnrollmentGrant
from ..bootstrap import JarvisRuntime, create_runtime
from ..config import JarvisConfig
from ..contracts import Identity, VoiceSessionContext
from ..models.llama_runtime import LlamaRuntimeStatus
from ..models.routing import ModelRoute
from ..voice.runtime import LocalVoiceRuntime, VoiceRunnerState, build_local_voice_runtime
from .assets import VoiceAssetManager
from .audio import AudioDeviceCatalog
from .config import DesktopProductConfig, ProductConfigError, product_config_path
from .instance import SingleInstanceLock
from .logging import DesktopOperationalLogger
from .model import LocalModelDiscovery
from .secrets import LocalSecretStore, SecretStoreUnavailable, platform_secret_store
from .startup import UserStartupManager


PRODUCT_SECRET_KEY = "desktop-device-credential"
PRODUCT_DEVICE_NAME = "NIGHTFURY Local Desktop"
PRODUCT_SCOPES = ("tool.request",)
PRODUCT_CAPABILITIES = ("computer.observe", "computer.input", "perception.screen")


class DesktopPhase(StrEnum):
    CREATED = "created"
    SETUP_REQUIRED = "setup_required"
    STARTING = "starting"
    READY = "ready"
    PAUSED = "paused"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class DesktopStatus:
    phase: DesktopPhase
    reason: str
    identity_id: str | None = None
    device_id: str | None = None
    brain_ready: bool = False
    voice_state: str = "unavailable"
    model: Any | None = None
    hud_url: str | None = None


RuntimeFactory = Callable[[JarvisConfig], JarvisRuntime]
VoiceRunnerFactory = Callable[[Any, Any], LocalVoiceRuntime]


class JarvisDesktopLifecycle:
    """Compose one runtime, one VoiceCore, and one local UI lifecycle."""

    def __init__(
        self,
        *,
        config_path: Path | None = None,
        secret_store: LocalSecretStore | None = None,
        runtime_factory: RuntimeFactory = create_runtime,
        base_config_factory: Callable[[], JarvisConfig] = JarvisConfig,
        voice_runner_factory: VoiceRunnerFactory = build_local_voice_runtime,
        asset_manager: VoiceAssetManager | None = None,
        audio_catalog: AudioDeviceCatalog | None = None,
        instance_lock: SingleInstanceLock | None = None,
        startup_manager: UserStartupManager | None = None,
        operational_logger: DesktopOperationalLogger | None = None,
        model_discovery: LocalModelDiscovery | None = None,
    ) -> None:
        self.config_path = config_path or product_config_path()
        self.secret_store = secret_store
        self.runtime_factory = runtime_factory
        self.base_config_factory = base_config_factory
        self.voice_runner_factory = voice_runner_factory
        self.asset_manager = asset_manager or VoiceAssetManager()
        self.audio_catalog = audio_catalog or AudioDeviceCatalog()
        lock_path = self.config_path.parent.parent / "run" / "instance.lock"
        self.instance_lock = instance_lock or SingleInstanceLock(lock_path)
        self.startup_manager = startup_manager or UserStartupManager()
        self.operational_logger = operational_logger
        self.model_discovery = model_discovery or LocalModelDiscovery()
        self.runtime: JarvisRuntime | Any | None = None
        self.runner: LocalVoiceRuntime | Any | None = None
        self.settings: DesktopProductConfig | None = None
        self.identity: Identity | None = None
        self.device: Any | None = None
        self._hud_server: Any | None = None
        self._hud_thread: threading.Thread | None = None
        self._status = DesktopStatus(DesktopPhase.CREATED, "not_started")

    @property
    def status(self) -> DesktopStatus:
        return self._status

    async def setup(self, owner_name: str = "Mahmoud", *, enable_voice: bool | None = None) -> DesktopStatus:
        """Complete explicit first-run setup using existing identity APIs."""

        settings = self._load_settings(defaults=True)
        self._log("desktop_setup_started")
        if enable_voice is not None:
            settings = replace(settings, voice_enabled=enable_voice)
        runtime = self._new_runtime(settings)
        new_secret = False
        try:
            owner = self._resolve_single_owner(runtime)
            if owner is None:
                identity = await runtime.identity.bootstrap_owner(owner_name)
            else:
                identity_row = runtime.repository.first_identity(owner["id"])
                if identity_row is None:
                    raise RuntimeError("owner exists without an active identity")
                identity = await runtime.identity.get_identity(identity_row["id"])
                if identity is None:
                    raise RuntimeError("owner identity is unavailable")
            credential, device = await self._reuse_or_enroll(runtime, settings, identity)
            new_secret = credential is not None
            if credential is not None:
                self._secret_store().set(PRODUCT_SECRET_KEY, credential)
            settings = replace(
                settings,
                identity_id=identity.identity_id,
                device_id=device.device_id,
            )
            settings = self._reconcile_audio_and_assets(settings)
            settings.save(self.config_path)
            if settings.autostart:
                self.startup_manager.register(executable=self._voice_python(), working_directory=Path.cwd())
            self.identity, self.device, self.settings = identity, device, settings
            self._close_unstarted_runtime(runtime)
            self.runtime = None
            self._status = DesktopStatus(
                DesktopPhase.CREATED,
                "setup_complete",
                identity.identity_id,
                device.device_id,
            )
            self._log("desktop_setup_completed")
            return self._status
        except Exception:
            if new_secret:
                self._secret_store().delete(PRODUCT_SECRET_KEY)
            self._close_unstarted_runtime(runtime)
            raise

    async def start(self) -> DesktopStatus:
        """Start the product without reading voice credentials from the environment."""

        if self._status.phase is DesktopPhase.READY:
            return self._refresh_status()
        if not self.instance_lock.acquire():
            self._status = DesktopStatus(DesktopPhase.DEGRADED, "already_running")
            return self._status
        self._log("desktop_start_started")
        try:
            settings = self._load_settings(defaults=False)
        except ProductConfigError as exc:
            self.instance_lock.release()
            self._status = DesktopStatus(DesktopPhase.SETUP_REQUIRED, _safe_reason(exc))
            return self._status
        self.settings = settings
        credential = self._secret_store().get(PRODUCT_SECRET_KEY)
        if not settings.identity_id or not settings.device_id:
            self.instance_lock.release()
            self._status = DesktopStatus(
                DesktopPhase.SETUP_REQUIRED,
                "desktop_enrollment_required",
                settings.identity_id,
                settings.device_id,
            )
            return self._status
        if not credential:
            self.instance_lock.release()
            self._status = DesktopStatus(
                DesktopPhase.DEGRADED,
                "device_credential_requires_repair",
                settings.identity_id,
                settings.device_id,
            )
            return self._status
        self._status = DesktopStatus(DesktopPhase.STARTING, "authenticating", settings.identity_id, settings.device_id)
        runtime = self._new_runtime(settings)
        self.runtime = runtime
        try:
            device = await runtime.identity.authenticate(credential, settings.device_id)
            identity = await runtime.identity.get_identity(settings.identity_id)
            if device is None or identity is None or device.owner_id != identity.owner_id:
                await self._degrade_after_runtime(runtime, "device_credential_requires_repair")
                return self._status
            self.identity, self.device = identity, device
            await runtime.start()
            self._start_hud()
            model_status, brain_ready = await self._model_status(runtime)
            settings = self._reconcile_audio_and_assets(settings)
            settings.save(self.config_path)
            self.settings = settings
            voice_state = "unavailable"
            reason = "ready"
            if settings.voice_enabled and brain_ready:
                try:
                    self.runner = self._build_runner(runtime, settings)
                    context = self._new_voice_context(runtime, settings, identity, device)
                    await self.runner.start(context, identity, device)
                    voice_state = getattr(self.runner.state, "value", str(self.runner.state))
                except Exception as exc:
                    voice_state = "degraded"
                    reason = f"voice_{_safe_reason(exc)}"
            elif not brain_ready:
                voice_state = "unavailable"
                reason = "local_brain_unavailable"
            else:
                voice_state = "paused"
                reason = "voice_disabled"
            if not brain_ready:
                reason = "local_brain_unavailable"
            phase = DesktopPhase.READY if brain_ready and voice_state in {"running", "paused"} else DesktopPhase.DEGRADED
            self._status = DesktopStatus(phase, reason, identity.identity_id, device.device_id, brain_ready, voice_state, model_status, self._hud_url())
            self._log(f"desktop_start_{phase.value}")
            return self._status
        except Exception as exc:
            await self._degrade_after_runtime(runtime, f"startup_{_safe_reason(exc)}")
            return self._status

    async def stop(self) -> DesktopStatus:
        if self._status.phase is DesktopPhase.STOPPED:
            return self._status
        self._status = replace(self._status, phase=DesktopPhase.STOPPING, reason="stopping")
        try:
            if self.runner is not None:
                await self.runner.stop()
                self.runner = None
            if self._hud_server is not None:
                self._hud_server.shutdown()
                self._hud_server = None
            if self.runtime is not None:
                if getattr(self.runtime, "state", None) is not None and getattr(self.runtime.state, "value", None) == "ready":
                    await self.runtime.shutdown()
                else:
                    self._close_unstarted_runtime(self.runtime)
                self.runtime = None
        finally:
            self.instance_lock.release()
            self._status = replace(self._status, phase=DesktopPhase.STOPPED, reason="stopped", voice_state="stopped")
            self._log("desktop_stopped")
        return self._status

    async def pause_voice(self) -> DesktopStatus:
        if self.runner is None:
            self._status = replace(self._status, phase=DesktopPhase.PAUSED, reason="voice_not_running", voice_state="paused")
            return self._status
        await self.runner.pause()
        self._status = replace(self._status, phase=DesktopPhase.PAUSED, reason="voice_paused", voice_state="paused")
        return self._status

    async def resume_voice(self) -> DesktopStatus:
        if self.runner is None:
            return replace(self._status, reason="voice_unavailable")
        await self.runner.resume()
        self._status = replace(self._status, phase=DesktopPhase.READY, reason="ready", voice_state="running")
        return self._status

    async def repair_device(self, owner_name: str = "Mahmoud") -> DesktopStatus:
        """Replace only the product credential/device; unrelated devices remain untouched."""

        settings = self._load_settings(defaults=True)
        runtime = self._new_runtime(settings)
        try:
            owner = self._resolve_single_owner(runtime)
            if owner is None:
                identity = await runtime.identity.bootstrap_owner(owner_name)
            else:
                identity_row = runtime.repository.first_identity(owner["id"])
                if identity_row is None:
                    raise RuntimeError("owner identity is unavailable")
                identity = await runtime.identity.get_identity(identity_row["id"])
                if identity is None:
                    raise RuntimeError("owner identity is unavailable")
            issued, device = await self._enroll(runtime, identity)
            self._secret_store().set(PRODUCT_SECRET_KEY, issued)
            settings = replace(settings, identity_id=identity.identity_id, device_id=device.device_id)
            settings.save(self.config_path)
            self._close_unstarted_runtime(runtime)
            self._status = DesktopStatus(DesktopPhase.CREATED, "device_repaired", identity.identity_id, device.device_id)
            return self._status
        except Exception:
            self._close_unstarted_runtime(runtime)
            raise

    def enable_autostart(self, enabled: bool) -> Path | None:
        settings = self.settings or self._load_settings(defaults=True)
        settings = replace(settings, autostart=enabled)
        settings.save(self.config_path)
        if enabled:
            return self.startup_manager.register(executable=self._voice_python(), working_directory=Path.cwd())
        self.startup_manager.unregister()
        return None

    def open_hud(self) -> bool:
        url = self._hud_url()
        return bool(url and webbrowser.open(url))

    def _load_settings(self, *, defaults: bool) -> DesktopProductConfig:
        try:
            return DesktopProductConfig.load(self.config_path)
        except ProductConfigError:
            if not defaults:
                raise
            return DesktopProductConfig()

    def _new_runtime(self, settings: DesktopProductConfig) -> Any:
        return self.runtime_factory(settings.runtime_config(self.base_config_factory()))

    @staticmethod
    def _resolve_single_owner(runtime: Any) -> dict[str, Any] | None:
        if runtime.repository.owner_count() > 1:
            raise RuntimeError("owner_selection_required")
        return runtime.repository.first_owner()

    async def _reuse_or_enroll(self, runtime: Any, settings: DesktopProductConfig, identity: Identity) -> tuple[str | None, Any]:
        stored = self._secret_store().get(PRODUCT_SECRET_KEY)
        if stored and settings.device_id:
            device = await runtime.identity.authenticate(stored, settings.device_id)
            if device is not None and device.owner_id == identity.owner_id:
                return None, device
        issued, device = await self._enroll(runtime, identity)
        return issued, device

    async def _enroll(self, runtime: Any, identity: Identity) -> tuple[str, Any]:
        enrollment = await runtime.identity.create_enrollment(
            EnrollmentGrant(
                owner_id=identity.owner_id,
                display_name=PRODUCT_DEVICE_NAME,
                device_kind="desktop",
                platform="windows",
                scopes=PRODUCT_SCOPES,
                capabilities=PRODUCT_CAPABILITIES,
                software_version="phase13-desktop",
            )
        )
        issued = await runtime.identity.redeem_enrollment(enrollment.code)
        device = await runtime.identity.device(issued.device_id)
        if device is None:
            raise RuntimeError("product device enrollment did not create a device")
        return issued.raw, device

    def _reconcile_audio_and_assets(self, settings: DesktopProductConfig) -> DesktopProductConfig:
        model = self.model_discovery.discover()
        settings = replace(
            settings,
            llama_cpp_server_path=settings.llama_cpp_server_path or model.executable_path,
            llama_cpp_model_path=settings.llama_cpp_model_path or model.model_path,
        )
        if not settings.voice_enabled:
            return settings
        input_device = settings.input_device or self._choose_audio("input")
        output_device = settings.output_device or self._choose_audio("output")
        base_voice = replace(settings.voice_config(), input_device=input_device, output_device=output_device)
        assets = self.asset_manager.configured_or_discovered(base_voice)
        return replace(
            settings,
            input_device=input_device,
            output_device=output_device,
            wake_model_path=assets.wake_model_path,
            vad_model_path=assets.vad_model_path,
            stt_model_path=assets.stt_model_path,
            tts_en_model_path=assets.tts_en_model_path,
            tts_ar_model_path=assets.tts_ar_model_path,
            last_validation={item.name: item.reason for item in assets.statuses()},
        )

    def _choose_audio(self, direction: str) -> Any | None:
        try:
            return self.audio_catalog.choose_default(direction)
        except Exception:
            return None

    def _build_runner(self, runtime: Any, settings: DesktopProductConfig) -> Any:
        voice_config = settings.voice_config().validated()
        return self.voice_runner_factory(runtime.voice, voice_config)

    @staticmethod
    def _new_voice_context(runtime: Any, settings: DesktopProductConfig, identity: Identity, device: Any) -> VoiceSessionContext:
        session = runtime.repository.create_session(identity.owner_id, device.device_id)
        conversation = runtime.repository.create_conversation(identity.owner_id, device.device_id, "JARVIS Desktop Voice")
        return VoiceSessionContext(
            session.id,
            device.device_id,
            settings.input_device.name if settings.input_device else None,
            settings.output_device.name if settings.output_device else None,
            owner_id=identity.owner_id,
            endpoint_id="windows-local-desktop",
            conversation_id=conversation.id,
        )

    async def _model_status(self, runtime: Any) -> tuple[Any | None, bool]:
        if runtime.config.model_provider in {"llama_cpp", "gguf"}:
            status = await runtime.models.runtime_health()
            return status, bool(status and status.ready)
        health = await runtime.models.health(ModelRoute.GENERAL_REASONING)
        return None, bool(health.available)

    async def _degrade_after_runtime(self, runtime: Any, reason: str) -> None:
        if getattr(runtime, "state", None) is not None and getattr(runtime.state, "value", None) == "ready":
            await runtime.shutdown()
        else:
            self._close_unstarted_runtime(runtime)
        self.runtime = None
        self.instance_lock.release()
        self._status = replace(self._status, phase=DesktopPhase.DEGRADED, reason=reason, voice_state="unavailable")

    def _start_hud(self) -> None:
        if self._hud_server is not None or self.runtime is None:
            return
        from ..api.core import CoreApplication
        from ..api.http import CoreHttpServer

        self._hud_server = CoreHttpServer(CoreApplication(self.runtime), host="127.0.0.1", port=0)
        self._hud_thread = threading.Thread(target=self._hud_server.serve_forever, name="jarvis-hud", daemon=True)
        self._hud_thread.start()

    def _hud_url(self) -> str | None:
        if self._hud_server is None:
            return None
        return f"http://{self._hud_server.address[0]}:{self._hud_server.address[1]}/hud"

    def _refresh_status(self) -> DesktopStatus:
        runner_state = getattr(getattr(self.runner, "state", None), "value", self._status.voice_state)
        if runner_state == VoiceRunnerState.PAUSED.value:
            phase = DesktopPhase.PAUSED
        else:
            phase = self._status.phase
        return replace(self._status, phase=phase, voice_state=runner_state, hud_url=self._hud_url())

    def _secret_store(self) -> LocalSecretStore:
        if self.secret_store is None:
            self.secret_store = platform_secret_store()
        return self.secret_store

    def _voice_python(self) -> Path | None:
        """Prefer the already-provisioned local voice environment when present."""

        candidate = self.asset_manager.root / "venv" / "Scripts" / "python.exe"
        return candidate if candidate.is_file() else None

    def _log(self, message: str) -> None:
        if self.operational_logger is not None:
            self.operational_logger.info(message)

    @staticmethod
    def _close_unstarted_runtime(runtime: Any) -> None:
        database = getattr(runtime, "database", None)
        if database is not None and not getattr(database, "closed", True):
            database.close()


def _safe_reason(exc: Exception) -> str:
    message = str(exc).strip()
    if not message or len(message) > 100 or any(char in message for char in "\\\n\r"):
        return exc.__class__.__name__
    return message
