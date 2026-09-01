from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest

from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.desktop.acceptance import AcceptanceStep, PhysicalAcceptanceWizard
from jarvis.desktop.assets import AssetProvisioningCancelled, AssetProvisioningUnavailable, VoiceAssetManager
from jarvis.desktop.audio import AudioDevice, AudioDeviceCatalog
from jarvis.desktop.config import DesktopProductConfig, ProductConfigError
from jarvis.desktop.diagnostics import DesktopDiagnostics
from jarvis.desktop.instance import SingleInstanceLock
from jarvis.desktop.lifecycle import (
    PRODUCT_SECRET_KEY,
    DesktopPhase,
    JarvisDesktopLifecycle,
)
from jarvis.desktop.model import LocalModelDiscovery
from jarvis.desktop.logging import DesktopOperationalLogger
from jarvis.desktop.secret_store import MemorySecretStore, SecretStoreUnavailable, platform_secret_store
from jarvis.desktop.startup import UserStartupManager
from jarvis.desktop.tray import TrayController
from jarvis.voice.config import VoiceDeviceSelector


class _AudioCatalog:
    def choose_default(self, direction: str) -> VoiceDeviceSelector:
        return VoiceDeviceSelector("Windows WASAPI", "Default " + direction)


def _base_config(database: Path) -> JarvisConfig:
    return JarvisConfig(
        environment="development",
        database_path=str(database),
        model_provider="mock",
        deployment_profile="development",
    )


def _lifecycle(tmp_path: Path, store: MemorySecretStore | None = None) -> JarvisDesktopLifecycle:
    database = tmp_path / "data" / "jarvis.sqlite3"
    return JarvisDesktopLifecycle(
        config_path=tmp_path / "localappdata" / "JARVIS" / "config" / "settings.json",
        secret_store=store or MemorySecretStore(),
        base_config_factory=lambda: _base_config(database),
        asset_manager=VoiceAssetManager(tmp_path / "localappdata" / "JARVIS" / "voice"),
        audio_catalog=_AudioCatalog(),
        startup_manager=UserStartupManager(tmp_path / "startup"),
        instance_lock=SingleInstanceLock(tmp_path / "localappdata" / "JARVIS" / "run" / "instance.lock"),
        model_discovery=LocalModelDiscovery(runtime_root=tmp_path / "no-runtime", model_roots=(tmp_path / "no-models",)),
    )


def _run(awaitable):
    return asyncio.run(awaitable)


def test_safe_config_round_trip_and_forbidden_fields(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    config = replace(
        DesktopProductConfig(),
        identity_id="identity-1",
        device_id="device-1",
        input_device=VoiceDeviceSelector("Windows WASAPI", "Microphone"),
        output_device=VoiceDeviceSelector("Windows WASAPI", "Speakers"),
        llama_cpp_model_path=Path("D:/Models/qwen.gguf"),
    )
    config.save(path)
    loaded = DesktopProductConfig.load(path)
    assert loaded == config
    assert "credential" not in path.read_text(encoding="utf-8").casefold()
    with pytest.raises(ProductConfigError):
        DesktopProductConfig.from_dict({"config_version": 1, "raw_credential": "secret"})


def test_config_invalid_version_fails_safe(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"config_version": 99}), encoding="utf-8")
    with pytest.raises(ProductConfigError):
        DesktopProductConfig.load(path)


def test_runtime_and_voice_config_are_derived_without_voice_environment() -> None:
    config = DesktopProductConfig(
        input_device=VoiceDeviceSelector("api", "mic"),
        output_device=VoiceDeviceSelector("api", "speaker"),
    )
    runtime = config.runtime_config(JarvisConfig())
    voice = config.voice_config()
    assert runtime.model_provider == "mock"
    assert runtime.voice_input_adapter == "sounddevice"
    assert voice.input_device == config.input_device
    assert voice.output_device == config.output_device


def test_memory_secret_store_has_expected_port() -> None:
    store = MemorySecretStore()
    assert store.get("missing") is None
    store.set(PRODUCT_SECRET_KEY, "public.secret")
    assert store.get(PRODUCT_SECRET_KEY) == "public.secret"
    store.delete(PRODUCT_SECRET_KEY)
    assert store.get(PRODUCT_SECRET_KEY) is None


def test_platform_secret_store_does_not_fallback_to_plaintext_off_windows() -> None:
    if __import__("os").name != "nt":
        with pytest.raises(SecretStoreUnavailable):
            platform_secret_store()


def test_explicit_setup_auto_enrolls_existing_or_empty_local_store(tmp_path: Path) -> None:
    store = MemorySecretStore()
    lifecycle = _lifecycle(tmp_path, store)
    status = _run(lifecycle.setup("Mahmoud", enable_voice=False))
    assert status.reason == "setup_complete"
    assert status.identity_id and status.device_id
    assert store.get(PRODUCT_SECRET_KEY)
    settings = DesktopProductConfig.load(lifecycle.config_path)
    assert settings.identity_id == status.identity_id
    assert settings.device_id == status.device_id
    assert "raw" not in lifecycle.config_path.read_text(encoding="utf-8").casefold()
    database = tmp_path / "data" / "jarvis.sqlite3"
    assert store.get(PRODUCT_SECRET_KEY).encode() not in database.read_bytes()


def test_restart_restores_credential_and_reuses_same_product_device(tmp_path: Path) -> None:
    store = MemorySecretStore()
    async def scenario() -> None:
        first = _lifecycle(tmp_path, store)
        setup = await first.setup(enable_voice=False)
        started = await first.start()
        assert started.phase is DesktopPhase.READY
        await first.stop()
        second = _lifecycle(tmp_path, store)
        restarted = await second.start()
        assert restarted.phase is DesktopPhase.READY
        assert restarted.device_id == setup.device_id
        assert second.runtime.repository.first_device(second.device.owner_id)
        await second.stop()

    _run(scenario())


def test_missing_product_secret_is_degraded_and_repair_preserves_unrelated_device(tmp_path: Path) -> None:
    store = MemorySecretStore()
    lifecycle = _lifecycle(tmp_path, store)
    setup = _run(lifecycle.setup(enable_voice=False))
    store.delete(PRODUCT_SECRET_KEY)
    degraded = _run(lifecycle.start())
    assert degraded.phase is DesktopPhase.DEGRADED
    assert degraded.reason == "device_credential_requires_repair"
    repaired = _run(lifecycle.repair_device())
    assert repaired.reason == "device_repaired"
    assert repaired.device_id != setup.device_id
    runtime = create_runtime(_base_config(tmp_path / "data" / "jarvis.sqlite3"))
    try:
        devices = runtime.repository.devices(repaired.identity_id and runtime.repository.first_owner()["id"])
        assert len(devices) >= 2
        assert any(item["id"] == setup.device_id for item in devices)
    finally:
        runtime.database.close()


def test_corrupt_product_secret_requires_repair_without_bootstrap(tmp_path: Path) -> None:
    store = MemorySecretStore()
    lifecycle = _lifecycle(tmp_path, store)
    setup = _run(lifecycle.setup(enable_voice=False))
    store.set(PRODUCT_SECRET_KEY, "corrupt")
    status = _run(lifecycle.start())
    assert status.phase is DesktopPhase.DEGRADED
    assert status.identity_id == setup.identity_id
    assert status.reason == "device_credential_requires_repair"


def test_setup_does_not_create_a_second_device_when_secure_credential_is_valid(tmp_path: Path) -> None:
    store = MemorySecretStore()
    lifecycle = _lifecycle(tmp_path, store)
    first = _run(lifecycle.setup(enable_voice=False))
    again = _run(lifecycle.setup(enable_voice=False))
    assert again.device_id == first.device_id
    runtime = create_runtime(_base_config(tmp_path / "data" / "jarvis.sqlite3"))
    try:
        owner = runtime.repository.first_owner()
        assert owner is not None
        assert len(runtime.repository.devices(owner["id"])) == 1
    finally:
        runtime.database.close()


def test_product_device_uses_minimal_scopes_and_expected_capabilities(tmp_path: Path) -> None:
    store = MemorySecretStore()
    lifecycle = _lifecycle(tmp_path, store)
    setup = _run(lifecycle.setup(enable_voice=False))
    runtime = create_runtime(_base_config(tmp_path / "data" / "jarvis.sqlite3"))
    try:
        row = runtime.repository.device(setup.device_id)
        assert row is not None
        assert json.loads(row["scopes_json"]) == ["tool.request"]
        assert json.loads(row["capabilities_json"]) == [
            "browser.extract_text", "browser.find_element", "browser.inspect_accessibility_tree",
            "browser.navigate", "browser.open_url", "browser.read_page", "browser.tabs",
            "computer.input", "computer.observe", "perception.screen", "research.local",
        ]
    finally:
        runtime.database.close()


def test_empty_background_start_requests_setup_and_does_not_create_owner(tmp_path: Path) -> None:
    lifecycle = _lifecycle(tmp_path)
    status = _run(lifecycle.start())
    assert status.phase is DesktopPhase.SETUP_REQUIRED
    assert status.reason == "desktop settings have not been created"
    assert not lifecycle.config_path.exists()


def test_startup_registration_is_reversible_idempotent_and_secret_free(tmp_path: Path) -> None:
    manager = UserStartupManager(tmp_path / "startup")
    first = manager.register(executable=Path("C:/Python/python.exe"), working_directory=tmp_path)
    second = manager.register(executable=Path("C:/Python/python.exe"), working_directory=tmp_path)
    assert first == second
    content = first.read_text(encoding="utf-8")
    assert "pythonw.exe" in content
    assert "jarvis.desktop" in content
    assert "credential" not in content.casefold()
    manager.unregister()
    assert not manager.enabled()


def test_single_instance_lock_rejects_second_owner_and_releases(tmp_path: Path) -> None:
    path = tmp_path / "run" / "instance.lock"
    first = SingleInstanceLock(path)
    second = SingleInstanceLock(path)
    assert first.acquire()
    assert not second.acquire()
    first.release()
    assert second.acquire()
    second.release()


def test_voice_assets_discover_exact_local_names_and_never_auto_provision(tmp_path: Path) -> None:
    root = tmp_path / "voice"
    (root / "faster-whisper-en").mkdir(parents=True)
    (root / "wake").mkdir(parents=True)
    (root / "wake" / "embedding_model.onnx").write_bytes(b"asset")
    for name in ("hey-wake.onnx", "silero-vad.onnx", "voice-en.onnx", "voice-ar.onnx"):
        (root / name).write_bytes(b"asset")
    assets = VoiceAssetManager(root).configured_or_discovered(DesktopProductConfig().voice_config())
    assert assets.ready
    with pytest.raises(AssetProvisioningUnavailable):
        VoiceAssetManager(root).provision()
    with pytest.raises(AssetProvisioningCancelled):
        VoiceAssetManager(root).provision(lambda *_: None, cancelled=lambda: True)


def test_local_model_discovery_is_bounded_and_references_existing_files(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime" / "nested"
    runtime_root.mkdir(parents=True)
    executable = runtime_root / "llama-server.exe"
    executable.write_bytes(b"server")
    model_root = tmp_path / "models"
    model_root.mkdir()
    model = model_root / "Qwen-local.gguf"
    model.write_bytes(b"model")
    found = LocalModelDiscovery(runtime_root=tmp_path / "runtime", model_roots=(model_root,)).discover()
    assert found.executable_path == executable
    assert found.model_path == model


def test_audio_catalog_returns_no_default_when_device_choice_is_ambiguous() -> None:
    class AmbiguousCatalog(AudioDeviceCatalog):
        def enumerate(self):
            return (
                AudioDevice("api", "Mic A", "input", 1),
                AudioDevice("api", "Mic B", "input", 1),
            )

    assert AmbiguousCatalog().choose_default("input") is None


def test_autostart_toggle_updates_safe_config_and_removes_entry(tmp_path: Path) -> None:
    lifecycle = _lifecycle(tmp_path)
    enabled = lifecycle.enable_autostart(True)
    assert enabled and enabled.exists()
    assert DesktopProductConfig.load(lifecycle.config_path).autostart
    lifecycle.enable_autostart(False)
    assert not enabled.exists()
    assert not DesktopProductConfig.load(lifecycle.config_path).autostart


def test_ambiguous_owner_store_fails_closed(tmp_path: Path) -> None:
    database = tmp_path / "data" / "jarvis.sqlite3"
    runtime = create_runtime(_base_config(database))
    try:
        runtime.repository.create_owner("Owner A")
        runtime.repository.create_owner("Owner B")
    finally:
        runtime.database.close()
    lifecycle = _lifecycle(tmp_path, MemorySecretStore())
    with pytest.raises(RuntimeError, match="owner_selection_required"):
        _run(lifecycle.setup(enable_voice=False))


def test_voice_enabled_product_degrades_without_assets_but_core_does_not_crash(tmp_path: Path) -> None:
    async def scenario() -> None:
        lifecycle = _lifecycle(tmp_path)
        setup = await lifecycle.setup(enable_voice=True)
        assert setup.device_id
        status = await lifecycle.start()
        assert status.phase is DesktopPhase.DEGRADED
        assert status.reason.startswith("voice_")
        await lifecycle.stop()

    _run(scenario())


def test_operational_logger_redacts_sensitive_terms_and_rotates_bounded_files(tmp_path: Path) -> None:
    logger = DesktopOperationalLogger(tmp_path / "logs" / "desktop.log")
    try:
        logger.info("credential=do-not-write")
        logger.info("ready")
    finally:
        logger.close()
    content = (tmp_path / "logs" / "desktop.log").read_text(encoding="utf-8")
    assert "do-not-write" not in content
    assert "ready" in content


def test_acceptance_completion_requires_every_step() -> None:
    wizard = PhysicalAcceptanceWizard()
    for step in AcceptanceStep:
        wizard.record(step, "PASS")
    assert wizard.complete
    assert wizard.sanitized_document()["physical_status"] == "PASS"


def test_audio_catalog_persists_stable_selector_not_numeric_id() -> None:
    class FakeSoundDevice:
        default = type("Default", (), {"device": (0, 1)})()

        @staticmethod
        def query_devices():
            return [
                {"hostapi": 0, "name": "Microphone", "max_input_channels": 1, "max_output_channels": 0},
                {"hostapi": 0, "name": "Speakers", "max_input_channels": 0, "max_output_channels": 2},
            ]

        @staticmethod
        def query_hostapis():
            return [{"name": "Windows WASAPI"}]

    catalog = AudioDeviceCatalog(FakeSoundDevice())
    devices = catalog.enumerate()
    assert devices == (
        AudioDevice("Windows WASAPI", "Microphone", "input", 1, True),
        AudioDevice("Windows WASAPI", "Speakers", "output", 2, True),
    )
    assert catalog.choose_default("input") == VoiceDeviceSelector("Windows WASAPI", "Microphone")


def test_lifecycle_runs_core_without_voice_environment_or_duplicate_ui_authority(tmp_path: Path) -> None:
    async def scenario() -> None:
        lifecycle = _lifecycle(tmp_path)
        await lifecycle.setup(enable_voice=False)
        status = await lifecycle.start()
        assert status.phase is DesktopPhase.READY
        assert status.hud_url and status.hud_url.endswith("/hud")
        assert lifecycle.runtime.voice is not None
        await lifecycle.stop()

    _run(scenario())


def test_pause_resume_delegates_to_existing_voice_runner() -> None:
    class Runner:
        state = "running"

        async def pause(self):
            self.state = type("State", (), {"value": "paused"})()

        async def resume(self):
            self.state = type("State", (), {"value": "running"})()

    lifecycle = JarvisDesktopLifecycle(secret_store=MemorySecretStore())
    lifecycle.runner = Runner()
    lifecycle._status = replace(lifecycle.status, phase=DesktopPhase.READY, voice_state="running")
    assert _run(lifecycle.pause_voice()).phase is DesktopPhase.PAUSED
    assert _run(lifecycle.resume_voice()).phase is DesktopPhase.READY


def test_tray_reflects_lifecycle_state_and_has_required_actions() -> None:
    lifecycle = JarvisDesktopLifecycle(secret_store=MemorySecretStore())
    tray = TrayController(lifecycle)
    assert tray.refresh().items == (
        "Open JARVIS", "Pause Voice", "Resume Voice", "Mute Output",
        "Diagnostics", "Settings", "Restart JARVIS", "Quit",
    )
    lifecycle._status = replace(lifecycle.status, phase=DesktopPhase.DEGRADED)
    assert tray.refresh().title == "JARVIS - Degraded"


def test_diagnostics_is_safe_before_runtime_start(tmp_path: Path) -> None:
    lifecycle = _lifecycle(tmp_path)
    results = _run(DesktopDiagnostics(lifecycle).run())
    assert any(item.name == "configuration" and item.status == "FAIL" for item in results)
    assert all("credential" not in item.reason.casefold() or item.name == "device_credential" for item in results)


def test_acceptance_wizard_only_writes_sanitized_counts_and_status(tmp_path: Path) -> None:
    wizard = PhysicalAcceptanceWizard()
    wizard.record(AcceptanceStep.WAKE, "PARTIAL", count=9, expected=10, median_latency_ms=240, safe_label="local wake")
    document = wizard.sanitized_document()
    assert document["physical_status"] == "PENDING"
    assert document["retention"] == {"raw_audio": 0, "transcripts": 0, "window_titles": 0, "credentials": 0}
    path = wizard.save(tmp_path / "PHYSICAL_REALTIME_VOICE.json")
    assert "local wake" in path.read_text(encoding="utf-8")
    assert "transcript" not in path.read_text(encoding="utf-8").casefold() or "transcripts" in path.read_text(encoding="utf-8").casefold()


def test_physical_acceptance_never_accepts_unbounded_or_private_labels() -> None:
    wizard = PhysicalAcceptanceWizard()
    with pytest.raises(ValueError):
        wizard.record(AcceptanceStep.MICROPHONE, "PASS", safe_label="x\nsecret")
    with pytest.raises(ValueError):
        wizard.record(AcceptanceStep.WAKE, "PASS", count=10_001)
