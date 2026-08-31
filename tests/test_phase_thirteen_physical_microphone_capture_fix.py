from __future__ import annotations

import asyncio
import math
from pathlib import Path

import pytest

from jarvis.desktop.acceptance import AcceptanceStep, PhysicalAcceptanceController
from jarvis.desktop.audio import (
    AudioDeviceCatalog,
    MicrophoneMeterUpdate,
    MicrophoneProbeResult,
)
from jarvis.voice.adapters import SoundDeviceInput, VoiceDeviceError, resample_pcm_16le
from jarvis.voice.config import VoiceDeviceSelector


class _ProbeStream:
    def __init__(self, backend, **kwargs):
        self.backend = backend
        self.kwargs = kwargs
        self.stopped = False
        self.closed = False
        backend.stream = self

    def start(self):
        self.backend.started += 1

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True

    def emit(self, samples, status=None):
        self.kwargs["callback"](samples, len(samples), None, status)


class _ProbeBackend:
    def __init__(self):
        self.stream = None
        self.started = 0
        self.rec_called = False

    def query_devices(self, index=None):
        if index is None:
            return [{"hostapi": 0, "name": "Microphone", "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 16_000}]
        return {"hostapi": 0, "name": "Microphone", "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 16_000}

    def query_hostapis(self):
        return [{"name": "Windows WASAPI"}]

    def check_input_settings(self, **kwargs):
        self.input_settings = kwargs

    def InputStream(self, **kwargs):
        return _ProbeStream(self, **kwargs)

    def rec(self, *args, **kwargs):
        del args, kwargs
        self.rec_called = True
        raise AssertionError("the microphone probe must use InputStream, not rec")


def _selector() -> VoiceDeviceSelector:
    return VoiceDeviceSelector("Windows WASAPI", "Microphone")


def _catalog_with_signal(*, include_status: bool = False):
    backend = _ProbeBackend()

    def wait(seconds: float) -> None:
        assert seconds == pytest.approx(3.0)
        assert backend.stream is not None
        if include_status:
            backend.stream.emit([0.0] * 1280, status="input overflow")
        for _ in range(7):
            backend.stream.emit([0.01] * 1280)
        for _ in range(30):
            backend.stream.emit([0.25] * 1280)

    return backend, AudioDeviceCatalog(backend, probe_wait=wait)


def test_microphone_probe_is_a_bounded_three_second_stream_with_safe_metrics_only():
    backend, catalog = _catalog_with_signal()
    updates: list[MicrophoneMeterUpdate] = []

    result = catalog.probe_microphone(_selector(), on_update=updates.append)

    assert not backend.rec_called
    assert result.duration_seconds == pytest.approx(2.96)
    assert result.frames_seen == 37 * 1280
    assert result.peak == pytest.approx(0.25)
    assert result.rms == pytest.approx(0.247, abs=0.002)
    assert result.usable_signal
    assert result.speech_delta_db > 20
    assert updates
    assert all(not hasattr(update, "pcm") for update in updates)


def test_microphone_probe_uses_rms_not_absolute_peak_and_rejects_ambient_only_signal():
    backend = _ProbeBackend()

    def wait(_seconds: float) -> None:
        assert backend.stream is not None
        for _ in range(7):
            backend.stream.emit([0.02, -0.02] * 640)
        for _ in range(30):
            backend.stream.emit([0.02, -0.02] * 640)

    result = AudioDeviceCatalog(backend, probe_wait=wait).probe_microphone(_selector())

    assert result.peak == pytest.approx(0.02)
    assert result.rms == pytest.approx(0.02)
    assert result.peak_dbfs == pytest.approx(20 * math.log10(0.02))
    assert result.rms_dbfs == pytest.approx(20 * math.log10(0.02))
    assert result.speech_delta_db == pytest.approx(0.0, abs=1e-9)
    assert not result.usable_signal


def test_microphone_probe_rejects_tiny_nonzero_signal_even_with_silent_ambient():
    backend = _ProbeBackend()

    def wait(_seconds: float) -> None:
        assert backend.stream is not None
        for _ in range(7):
            backend.stream.emit([0.0] * 1280)
        for _ in range(30):
            backend.stream.emit([0.015] * 1280)

    result = AudioDeviceCatalog(backend, probe_wait=wait).probe_microphone(_selector())

    assert result.speech_delta_db > 200
    assert not result.usable_signal


def test_probe_duration_is_bounded_and_raw_pcm_is_never_returned_or_persisted():
    backend, catalog = _catalog_with_signal()
    with pytest.raises(ValueError):
        catalog.probe_microphone(_selector(), seconds=0.25)
    with pytest.raises(ValueError):
        catalog.probe_microphone(_selector(), seconds=5.01)
    result = catalog.probe_microphone(_selector(), seconds=3.0)
    assert isinstance(result, MicrophoneProbeResult)
    assert not any(name in result.__dict__ for name in ("pcm", "samples", "audio")) if hasattr(result, "__dict__") else True


def test_sounddevice_input_continues_after_transient_portaudio_status_and_counts_frames(monkeypatch):
    backend, _catalog = _catalog_with_signal()
    module = backend
    monkeypatch.setitem(__import__("sys").modules, "sounddevice", module)
    device = SoundDeviceInput(_selector())
    received: list[bytes] = []
    device.start(received.append)
    assert backend.stream is not None
    backend.stream.emit(b"\x00\x00" * 4, status="input overflow")
    backend.stream.emit(b"\xcd\x0c" * 4)
    assert len(received) == 2
    assert device.callback_fault_count == 1
    assert not device.take_fault()
    device.stop()


def test_signal_metrics_survive_48khz_to_16khz_resampling_without_pcm_retention():
    source = (int(0.4 * 32767).to_bytes(2, "little", signed=True)) * 4800
    normalized = resample_pcm_16le(source, 48_000, 16_000)
    values = [int.from_bytes(normalized[i : i + 2], "little", signed=True) / 32768 for i in range(0, len(normalized), 2)]
    assert len(normalized) == len(source) // 3
    assert max(abs(value) for value in values) == pytest.approx(0.4, abs=0.001)


def test_runner_diagnostics_are_safe_and_include_input_and_wake_counters():
    from jarvis.voice.runtime import LocalVoiceRuntime

    class Input:
        sample_rate = 48_000

        def start(self, callback):
            self.callback = callback

        def stop(self):
            pass

        def take_fault(self):
            return False

    class Output:
        def start(self):
            pass

        async def stop(self):
            pass

        def close(self):
            pass

        def take_fault(self):
            return False

    class Wake:
        threshold = 0.5

        def __init__(self):
            self.last_score = 0.73

        def detect_pcm(self, audio):
            del audio
            return False

    class Endpoint:
        speech_active = False

        def discard(self):
            pass

        def feed(self, audio):
            del audio
            return None

    runner = LocalVoiceRuntime(object(), Input(), Output(), Wake(), Endpoint())
    runner._capture_callback(b"\x01\x00" * 4)
    assert not runner._detect_wake(b"\x00\x00")
    assert runner.input_frames_received == 4
    assert runner.input_bytes_received == 8
    assert runner.last_input_frame_monotonic is not None
    assert runner.wake_frames_received == 1
    assert runner.last_wake_score == pytest.approx(0.73)
    assert "pcm" not in str(runner.diagnostics).casefold()


def test_candidate_ranking_prefers_stronger_realtek_signal_over_weak_bluetooth_and_keeps_selector_stable():
    from jarvis.desktop.audio import MicrophoneCandidateResult

    weak = MicrophoneCandidateResult(
        VoiceDeviceSelector("MME", "Headset"),
        MicrophoneProbeResult(0.03, 0.01, -30, -40, -41, 1, 3, 48_000, False, False),
        callback_fault_count=0,
    )
    strong = MicrophoneCandidateResult(
        VoiceDeviceSelector("Windows WASAPI", "Microphone Array (Realtek(R) Audio)"),
        MicrophoneProbeResult(0.40, 0.20, -8, -14, -50, 36, 3, 48_000, False, True),
        callback_fault_count=0,
    )
    ranked = AudioDeviceCatalog.rank_input_candidates((weak, strong))
    assert ranked[0].selector == strong.selector
    assert ranked[0].selector.name == "Microphone Array (Realtek(R) Audio)"


def test_acceptance_mic_pass_requires_usable_probe_and_wake_pass_requires_backend_detections():
    controller = PhysicalAcceptanceController(require_microphone_probe=True, require_wake_detections=True)
    controller.set_microphone_probe(MicrophoneProbeResult(0, 0, -240, -240, -240, 0, 3, 48_000, False, False))
    controller.record_current("PASS")
    with pytest.raises(ValueError):
        controller.record_current("PASS")
    controller = PhysicalAcceptanceController(require_microphone_probe=True, require_wake_detections=True)
    controller.record_current("PASS")
    controller.set_microphone_probe(MicrophoneProbeResult(0.3, 0.2, -10, -14, -50, 36, 3, 48_000, False, True))
    controller.record_current("PASS")
    with pytest.raises(ValueError):
        controller.record_current("PASS", count=0, expected=10)


def test_lifecycle_pauses_existing_runner_and_restores_it_after_probe_failure_or_success():
    from jarvis.desktop.config import DesktopProductConfig
    from jarvis.desktop.lifecycle import JarvisDesktopLifecycle
    from jarvis.voice.runtime import VoiceRunnerState

    class Runner:
        state = VoiceRunnerState.RUNNING

        def __init__(self):
            self.pauses = 0
            self.resumes = 0

        async def pause(self):
            self.pauses += 1
            self.state = VoiceRunnerState.PAUSED

        async def resume(self):
            self.resumes += 1
            self.state = VoiceRunnerState.RUNNING

    backend, catalog = _catalog_with_signal()
    lifecycle = JarvisDesktopLifecycle(audio_catalog=catalog)
    lifecycle.settings = DesktopProductConfig(input_device=_selector())
    lifecycle.runner = Runner()

    async def scenario():
        result = await lifecycle.test_microphone()
        assert result.usable_signal
        assert lifecycle.runner.pauses == 1
        assert lifecycle.runner.resumes == 1

    class FailingCatalog:
        def probe_microphone(self, *args, **kwargs):
            del args, kwargs
            raise VoiceDeviceError("voice_microphone_probe_failed")

    async def failing_scenario():
        lifecycle.audio_catalog = FailingCatalog()
        with pytest.raises(VoiceDeviceError):
            await lifecycle.test_microphone()
        assert lifecycle.runner.pauses == 2
        assert lifecycle.runner.resumes == 2

    asyncio.run(scenario())
    asyncio.run(failing_scenario())


def test_use_best_microphone_persists_selector_and_rebinds_existing_runner(tmp_path: Path):
    from jarvis.desktop.config import DesktopProductConfig
    from jarvis.desktop.lifecycle import JarvisDesktopLifecycle

    class Runner:
        state = "paused"

        def __init__(self):
            self.rebound = None

        async def rebind_audio(self, audio_input, audio_output):
            self.rebound = (audio_input.selector, audio_output.selector)

    input_selector = _selector()
    output_selector = VoiceDeviceSelector("Windows DirectSound", "Headphones")
    best_selector = VoiceDeviceSelector("Windows WASAPI", "Microphone Array (Realtek(R) Audio)")
    lifecycle = JarvisDesktopLifecycle(config_path=tmp_path / "config" / "settings.json")
    lifecycle.settings = DesktopProductConfig(input_device=input_selector, output_device=output_selector)
    lifecycle.runtime = object()
    lifecycle.runner = Runner()

    asyncio.run(lifecycle.use_best_microphone(best_selector))

    assert lifecycle.settings.input_device == best_selector
    assert lifecycle.runner.rebound == (best_selector, output_selector)
    saved = (tmp_path / "config" / "settings.json").read_text(encoding="utf-8")
    assert "Microphone Array (Realtek(R) Audio)" in saved
    assert '"device_index"' not in saved


def test_tk_microphone_probe_starts_after_speak_prompt_and_updates_ui_off_main_thread():
    from jarvis.desktop.ui import DesktopWindow

    class Root:
        def __init__(self):
            self.callbacks = []

        def after(self, _delay, callback):
            self.callbacks.append(callback)

    class Detail:
        def __init__(self):
            self.values = []

        def configure(self, *, text):
            self.values.append(text)

    class Lifecycle:
        async def test_microphone(self, **kwargs):
            kwargs["on_update"](MicrophoneMeterUpdate(0.3, 0.2, -10, -14, 0.8, 12_800))
            return MicrophoneProbeResult(0.3, 0.2, -10, -14, -50, 36, 3, 48_000, False, True)

    root = Root()
    detail = Detail()
    window = DesktopWindow(Lifecycle(), run_async=lambda awaitable: asyncio.run(awaitable))
    window.root = root
    window.detail_label = detail
    window._test_microphone()
    assert detail.values[0] == "Speak now..."
    assert window._microphone_probe_thread is not None
    window._microphone_probe_thread.join(timeout=1)
    for callback in root.callbacks:
        callback()
    assert any("Signal: GOOD" in value for value in detail.values)


def test_find_best_microphone_probes_all_input_profiles_and_ranks_actual_signal():
    class Backend(_ProbeBackend):
        def __init__(self):
            super().__init__()
            self.devices = [
                {"hostapi": 0, "name": "Headset", "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 16_000},
                {"hostapi": 1, "name": "Microphone Array (Realtek(R) Audio)", "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 48_000},
            ]

        def query_devices(self, index=None):
            return self.devices if index is None else self.devices[index]

        def query_hostapis(self):
            return [{"name": "MME"}, {"name": "Windows WASAPI"}]

    backend = Backend()

    def wait(_seconds):
        assert backend.stream is not None
        index = backend.stream.kwargs["device"]
        level = 0.03 if index == 0 else 0.3
        rate = 16_000 if index == 0 else 48_000
        for _ in range(round(rate * 0.5 / 1280)):
            backend.stream.emit([0.01] * 1280)
        for _ in range(round(rate * 2.4 / 1280)):
            backend.stream.emit([level] * 1280)

    catalog = AudioDeviceCatalog(backend, probe_wait=wait)
    ranked = catalog.probe_input_candidates(seconds=2.0)
    assert [item.selector.name for item in ranked] == [
        "Microphone Array (Realtek(R) Audio)",
        "Headset",
    ]
    assert all(not hasattr(item, "device_index") for item in ranked)


def test_vad_and_wake_expose_only_safe_frames_scores_and_status():
    from jarvis.voice.adapters import OpenWakeWordDetector, SileroVad, SpeechEndpointDetector

    class Session:
        def run(self, _outputs, inputs):
            del inputs
            return [[0.8]], None

    vad = SileroVad(Path("unused.onnx"), 0.5)
    vad._session = Session()
    vad._state = object()
    endpoint = SpeechEndpointDetector(vad)
    endpoint.feed(b"\x00\x00" * 512)
    assert endpoint.vad_diagnostics == {
        "vad_frames_processed": 1,
        "vad_last_score": 0.8,
        "vad_detected_speech": True,
    }

    class WakeModel:
        def predict(self, _audio):
            return {"hey_jarvis": 0.73}

    wake = OpenWakeWordDetector(Path("unused.onnx"), 0.5, cooldown_seconds=0)
    wake._model = WakeModel()
    assert wake.detect_pcm(b"\x00\x00")
    assert wake.last_score == pytest.approx(0.73)


def test_duplex_probe_opens_selected_input_and_output_together_and_fails_closed():
    class Stream:
        def __init__(self, backend, **kwargs):
            self.backend = backend
            self.kwargs = kwargs
            self.closed = False
            backend.streams.append(self)

        def start(self):
            if self.backend.fail_output and self.kwargs.get("device") == 1:
                raise RuntimeError("output unavailable")

        def stop(self):
            pass

        def close(self):
            self.closed = True

    class Backend:
        def __init__(self, fail_output=False):
            self.fail_output = fail_output
            self.streams = []
            self.devices = [
                {"hostapi": 0, "name": "Headset", "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 16_000},
                {"hostapi": 0, "name": "Headset", "max_input_channels": 0, "max_output_channels": 2, "default_samplerate": 48_000},
            ]

        def query_devices(self, index=None):
            return self.devices if index is None else self.devices[index]

        def query_hostapis(self):
            return [{"name": "Windows WASAPI"}]

        def check_input_settings(self, **kwargs):
            del kwargs

        def check_output_settings(self, **kwargs):
            del kwargs

        def InputStream(self, **kwargs):
            return Stream(self, **kwargs)

        def OutputStream(self, **kwargs):
            return Stream(self, **kwargs)

    input_selector = VoiceDeviceSelector("Windows WASAPI", "Headset")
    output_selector = VoiceDeviceSelector("Windows WASAPI", "Headset")
    backend = Backend()
    assert AudioDeviceCatalog(backend).check_duplex(input_selector, output_selector) == "PASS"
    assert AudioDeviceCatalog(Backend(fail_output=True)).check_duplex(input_selector, output_selector) == "PARTIAL"
