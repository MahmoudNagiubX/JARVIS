from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from jarvis.desktop.acceptance import AcceptanceStep, PhysicalAcceptanceController
from jarvis.desktop.diagnostics import DesktopDiagnostics
from jarvis.desktop.installation import sanitized_environment
from jarvis.desktop.lifecycle import PRODUCT_SECRET_KEY
from jarvis.desktop.secret_store import MemorySecretStore
from jarvis.desktop.startup import UserStartupManager
from jarvis.desktop.ui import DesktopWindow
from jarvis.bootstrap import create_runtime
from jarvis.config import JarvisConfig
from jarvis.voice.core import VoiceCore
from jarvis.voice.config import VoiceDeviceSelector

from .test_phase_thirteen_zero_touch_productization import _lifecycle, _run


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_secure_store_is_tracked_and_old_ignored_source_is_absent() -> None:
    secure_store = "src/jarvis/desktop/secret_store.py"
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", secure_store],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert tracked.returncode == 0, tracked.stderr
    ignored = subprocess.run(
        ["git", "check-ignore", secure_store],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert ignored.returncode != 0
    assert not (REPO_ROOT / "src/jarvis/desktop/secrets.py").exists()


def test_clean_tree_gate_script_imports_only_archived_sources() -> None:
    tree = subprocess.run(["git", "write-tree"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    result = subprocess.run(
        [sys.executable, "scripts/verify_clean_tree_import.py", "--ref", tree],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("OK")


def test_product_child_environment_removes_import_and_secret_overrides() -> None:
    environment = sanitized_environment({
        "PYTHONPATH": "src",
        "JARVIS_VOICE_CREDENTIAL": "must-not-cross-process",
        "JARVIS_VOICE_DEVICE_ID": "device",
        "SAFE_SETTING": "kept",
    })
    assert "PYTHONPATH" not in environment
    assert "JARVIS_VOICE_CREDENTIAL" not in environment
    assert "JARVIS_VOICE_DEVICE_ID" not in environment
    assert environment["SAFE_SETTING"] == "kept"


@pytest.mark.skipif(os.name != "nt", reason="Windows Start Menu shortcut")
def test_start_menu_shortcut_is_no_console_secret_free_and_idempotent(tmp_path: Path) -> None:
    manager = UserStartupManager(tmp_path / "Startup")
    first = manager.install_start_menu_shortcut(Path(sys.executable), tmp_path)
    second = manager.install_start_menu_shortcut(Path(sys.executable), tmp_path)
    assert first == second == manager.shortcut_path
    assert first.is_file()
    assert manager.last_shortcut_spec == {
        "target": str(UserStartupManager.pythonw_executable(Path(sys.executable)).resolve()),
        "arguments": "-m jarvis.desktop",
        "working_directory": str(tmp_path.resolve()),
        "window_style": 0,
    }
    assert "credential" not in repr(manager.last_shortcut_spec).casefold()
    manager.uninstall_start_menu_shortcut()
    assert not manager.shortcut_enabled()


def test_setup_creates_product_launcher_without_secret_arguments(tmp_path: Path) -> None:
    lifecycle = _lifecycle(tmp_path, MemorySecretStore())
    status = _run(lifecycle.setup(enable_voice=False))
    assert status.device_id
    assert lifecycle.startup_manager.enabled()
    if os.name == "nt":
        assert lifecycle.startup_manager.shortcut_enabled()
        assert lifecycle.startup_manager.last_shortcut_spec is not None
        assert "credential" not in repr(lifecycle.startup_manager.last_shortcut_spec).casefold()


def test_ui_view_model_exposes_setup_matrix_selectors_settings_and_actions(tmp_path: Path) -> None:
    lifecycle = _lifecycle(tmp_path, MemorySecretStore())
    window = DesktopWindow(lifecycle)
    snapshot = window.snapshot()
    assert tuple(name for name, _value in snapshot.statuses) == (
        "Core", "Identity", "Local Device", "Local Brain", "Microphone", "Speaker", "Wake", "STT", "TTS",
    )
    assert {"Test Microphone", "Test Speaker", "Repair This Device", "Acceptance Wizard", "Diagnostics", "Finish Setup"}.issubset(window.available_actions(setup=True))


def test_audio_selector_and_follow_up_settings_persist_through_lifecycle(tmp_path: Path) -> None:
    lifecycle = _lifecycle(tmp_path, MemorySecretStore())
    _run(lifecycle.setup(enable_voice=False))
    microphone = VoiceDeviceSelector("Windows WASAPI", "Mic")
    speaker = VoiceDeviceSelector("Windows WASAPI", "Speaker")
    _run(lifecycle.update_audio_devices(microphone, speaker))
    lifecycle.update_follow_up_seconds(42)
    assert lifecycle.settings is not None
    assert lifecycle.settings.input_device == microphone
    assert lifecycle.settings.output_device == speaker
    assert lifecycle.settings.follow_up_seconds == 42


def test_second_desktop_start_is_rejected_without_a_second_runtime(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = MemorySecretStore()
        first = _lifecycle(tmp_path, store)
        await first.setup(enable_voice=False)
        started = await first.start()
        assert started.phase.value == "ready"
        second = _lifecycle(tmp_path, store)
        duplicate = await second.start()
        assert duplicate.reason == "already_running"
        assert second.runtime is None
        await first.stop()

    _run(scenario())


def test_offline_diagnostics_handles_configured_product_without_runtime(tmp_path: Path) -> None:
    lifecycle = _lifecycle(tmp_path, MemorySecretStore())
    _run(lifecycle.setup(enable_voice=False))
    results = _run(DesktopDiagnostics(lifecycle).run())
    assert any(item.name == "configuration" and item.status == "PASS" for item in results)
    assert all(item.status != "FAIL" or item.name != "core_db" for item in results)


def test_fixed_speaker_test_uses_voicecore_without_agent_or_audio_retention() -> None:
    class Tts:
        sample_rate = 16_000

        async def synthesize(self, text: str) -> bytes:
            assert text == "JARVIS speaker test."
            return b"pcm"

    class Playback:
        def __init__(self) -> None:
            self.played: list[tuple[bytes, int]] = []

        async def play(self, audio: bytes, sample_rate: int) -> None:
            self.played.append((audio, sample_rate))

        async def stop(self) -> None:
            return None

    runtime = create_runtime(JarvisConfig(environment="test", database_path=":memory:"))
    playback = Playback()
    try:
        voice = VoiceCore(runtime.agent, runtime.event_bus, Tts(), Tts(), playback=playback)
        assert _run(voice.speak_safe_test())
        assert playback.played == [(b"pcm", 16_000)]
    finally:
        runtime.database.close()


def test_acceptance_controller_enforces_order_and_keeps_pending_until_all_human_steps_pass() -> None:
    controller = PhysicalAcceptanceController()
    assert controller.current_step is AcceptanceStep.SPEAKER
    controller.record_current("PARTIAL")
    assert controller.current_step is AcceptanceStep.SPEAKER
    assert not controller.complete
    for _ in range(len(AcceptanceStep)):
        controller.record_current("PASS")
    assert controller.complete
    assert controller.wizard.sanitized_document()["physical_status"] == "PASS"


def test_acceptance_initial_evidence_is_pending_and_contains_no_private_payload(tmp_path: Path) -> None:
    controller = PhysicalAcceptanceController()
    path = controller.save(tmp_path / "PHYSICAL_REALTIME_VOICE.json")
    document = path.read_text(encoding="utf-8").casefold()
    assert '"physical_status": "pending"' in document
    assert "raw_audio" in document
    assert "credentials" in document
    assert PRODUCT_SECRET_KEY not in document


def test_voice_runner_reports_bounded_wake_metric_without_audio_retention() -> None:
    source = (REPO_ROOT / "src/jarvis/voice/runtime.py").read_text(encoding="utf-8")
    assert "wake_detections" in source
    assert "_pcm: queue.Queue[bytes]" in source
    assert "write_bytes" not in source


def test_static_authority_shape_remains_single_and_no_desktop_sql_cleanup() -> None:
    source_root = REPO_ROOT / "src/jarvis"
    text = "\n".join(path.read_text(encoding="utf-8") for path in source_root.rglob("*.py"))
    assert text.count("InMemoryEventBus(") == 1
    assert text.count("ModelGateway(") == 1
    assert text.count("BackgroundScheduler(") == 1
    assert text.count("VoiceCore(") == 1
    desktop = "\n".join(path.read_text(encoding="utf-8") for path in (source_root / "desktop").glob("*.py"))
    assert "DELETE FROM" not in desktop
    assert "DROP TABLE" not in desktop
