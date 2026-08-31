from __future__ import annotations

import asyncio
import sys
import time
import types
from dataclasses import replace

import pytest

from jarvis.desktop.acceptance import PhysicalAcceptanceController
from jarvis.contracts import VoiceSessionState
from jarvis.voice.runtime import LocalVoiceRuntime, VoiceRunnerState


class _Input:
    sample_rate = 16_000

    def start(self, callback):
        self.callback = callback

    def stop(self):
        pass

    def take_fault(self):
        return False


class _Output:
    def start(self):
        pass

    async def stop(self):
        pass

    def close(self):
        pass

    def take_fault(self):
        return False


class _Wake:
    threshold = 0.5

    def __init__(self, detected: bool = False):
        self.detected = detected
        self.last_score = 0.73

    def detect_pcm(self, _audio: bytes) -> bool:
        result, self.detected = self.detected, False
        return result


class _Endpoint:
    speech_active = False

    def __init__(self):
        self.feed_calls = 0
        self.discard_calls = 0

    def feed(self, _audio: bytes):
        self.feed_calls += 1
        return None

    def discard(self):
        self.discard_calls += 1


class _Voice:
    state = VoiceSessionState.SLEEPING

    def __init__(self):
        self.wake_calls = 0
        self.process_calls = 0
        self.return_to_sleeping_calls = 0

    async def return_to_sleeping(self):
        self.return_to_sleeping_calls += 1
        self.state = VoiceSessionState.SLEEPING

    async def wake_detected(self):
        self.wake_calls += 1
        self.state = VoiceSessionState.LISTENING
        return True

    async def process_audio(self, _audio, _identity=None, _device=None):
        self.process_calls += 1


def _runner(*, detected: bool = False):
    voice = _Voice()
    wake = _Wake(detected)
    endpoint = _Endpoint()
    runner = LocalVoiceRuntime(voice, _Input(), _Output(), wake, endpoint)
    runner._state = VoiceRunnerState.RUNNING
    return runner, voice, endpoint


async def _wait_until(predicate, timeout: float = 1.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("condition did not become true")
        await asyncio.sleep(0.001)


async def _complete_wake_test(pattern: list[bool]):
    runner, _voice, _endpoint = _runner()
    runner._wake_acceptance_attempt_seconds = 0.05
    await runner.start_wake_acceptance(attempts=len(pattern))
    for attempt, detected in enumerate(pattern, start=1):
        await _wait_until(
            lambda: runner.wake_acceptance_snapshot.active
            and runner.wake_acceptance_snapshot.attempt_index == attempt
        )
        if detected:
            runner.wake.detected = True
            await runner._process_pcm(b"wake-frame")
        await _wait_until(
            lambda: not runner.wake_acceptance_snapshot.active
            or runner.wake_acceptance_snapshot.attempt_index != attempt
        )
    await _wait_until(lambda: not runner.wake_acceptance_snapshot.active)
    return runner


def test_wake_acceptance_requires_explicit_start_and_uses_a_fresh_session_counter():
    async def scenario():
        runner, _voice, _endpoint = _runner()
        assert not runner.wake_acceptance_active
        runner._wake_detections = 11

        snapshot = await runner.start_wake_acceptance(attempts=2)

        assert snapshot.active
        assert snapshot.attempt_target == 2
        assert snapshot.attempt_index == 1
        assert snapshot.detections == 0
        assert snapshot.misses == 0
        await runner.stop_wake_acceptance()

    asyncio.run(scenario())


def test_diagnostic_detection_does_not_enter_normal_command_flow():
    async def scenario():
        runner, voice, endpoint = _runner(detected=True)
        await runner.start_wake_acceptance(attempts=1)

        await runner._process_pcm(b"diagnostic-frame")

        snapshot = runner.wake_acceptance_snapshot
        assert snapshot.detections == 1
        assert voice.wake_calls == 0
        assert voice.state is VoiceSessionState.SLEEPING
        assert endpoint.feed_calls == 0
        await runner.stop_wake_acceptance()

    asyncio.run(scenario())


def test_wake_acceptance_keeps_the_normal_command_timer_disarmed():
    async def scenario():
        runner, _voice, _endpoint = _runner()
        await runner.start_wake_acceptance(attempts=1)

        assert not runner.wake_command_timer_active
        await runner.stop_wake_acceptance()

    asyncio.run(scenario())


def test_wake_acceptance_attempts_are_isolated_and_do_not_double_count_one_attempt():
    async def scenario():
        runner, _voice, _endpoint = _runner()
        runner._wake_acceptance_attempt_seconds = 0.05
        await runner.start_wake_acceptance(attempts=2)

        runner.wake.detected = True
        await runner._process_pcm(b"first")
        runner.wake.detected = True
        await runner._process_pcm(b"duplicate-before-reset")
        await _wait_until(lambda: runner.wake_acceptance_snapshot.attempt_index == 2)
        runner.wake.detected = True
        await runner._process_pcm(b"second")
        await _wait_until(lambda: not runner.wake_acceptance_snapshot.active)

        snapshot = runner.wake_acceptance_snapshot
        assert snapshot.detections == 2
        assert snapshot.misses == 0

    asyncio.run(scenario())


def test_historical_lifetime_detections_are_excluded_from_acceptance_result():
    async def scenario():
        runner, _voice, _endpoint = _runner()
        runner._wake_detections = 99
        runner._wake_acceptance_attempt_seconds = 0.05
        await runner.start_wake_acceptance(attempts=1)
        runner.wake.detected = True
        await runner._process_pcm(b"fresh")
        await _wait_until(lambda: not runner.wake_acceptance_snapshot.active)

        assert runner.wake_detections == 99
        assert runner.wake_acceptance_snapshot.detections == 1

    asyncio.run(scenario())


def test_wake_acceptance_timeout_records_a_miss_and_advances_to_next_attempt():
    async def scenario():
        runner, _voice, _endpoint = _runner()
        runner._wake_acceptance_attempt_seconds = 0.01
        await runner.start_wake_acceptance(attempts=2)

        await _wait_until(
            lambda: runner.wake_acceptance_snapshot.active
            and runner.wake_acceptance_snapshot.attempt_index == 2
            and runner.wake_acceptance_snapshot.misses == 1
        )
        await runner.stop_wake_acceptance()

    asyncio.run(scenario())


def test_ten_attempt_wake_acceptance_completes_without_stt_agent_or_tts():
    async def scenario():
        runner = await _complete_wake_test([True] * 10)
        snapshot = runner.wake_acceptance_snapshot

        assert snapshot.attempt_index == 10
        assert snapshot.detections == 10
        assert snapshot.misses == 0
        assert snapshot.result == "PASS"
        assert runner.voice.wake_calls == 0
        assert runner.voice.process_calls == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [([True] * 8 + [False] * 2, "PASS"), ([True] * 7 + [False] * 3, "PARTIAL"), ([True] * 4 + [False] * 6, "FAIL")],
)
def test_wake_acceptance_result_mapping(pattern: list[bool], expected: str):
    async def scenario():
        runner = await _complete_wake_test(pattern)
        assert runner.wake_acceptance_snapshot.result == expected

    asyncio.run(scenario())


def test_wake_pass_is_blocked_until_the_backend_session_is_complete():
    controller = PhysicalAcceptanceController(require_wake_detections=True)
    controller.record_current("PASS")
    controller.record_current("PASS")
    controller.set_wake_acceptance(type("Snapshot", (), {"active": True, "result": None, "detections": 10, "attempt_target": 10})())

    with pytest.raises(ValueError, match="backend"):
        controller.record_current("PASS", count=10, expected=10)

    controller.set_wake_acceptance(type("Snapshot", (), {"active": False, "result": "CANCELLED", "detections": 10, "attempt_target": 10})())
    with pytest.raises(ValueError, match="completed"):
        controller.record_current("PARTIAL", count=10, expected=10)


def test_wake_acceptance_exposes_only_bounded_metrics_and_no_raw_audio():
    async def scenario():
        runner, _voice, _endpoint = _runner()
        await runner.start_wake_acceptance(attempts=1)
        snapshot = runner.wake_acceptance_snapshot

        assert set(snapshot.__dataclass_fields__) == {
            "active", "attempt_target", "attempt_index", "detections", "misses",
            "last_score", "best_score", "attempt_deadline", "started_at", "result",
        }
        assert "pcm" not in repr(snapshot).casefold()
        assert "audio" not in repr(snapshot).casefold()
        assert "pcm" not in repr(runner.diagnostics).casefold()
        await runner.stop_wake_acceptance()

    asyncio.run(scenario())


def test_wake_acceptance_tracks_live_last_and_best_confidence_safely():
    async def scenario():
        runner, _voice, _endpoint = _runner()
        await runner.start_wake_acceptance(attempts=1)
        runner.wake.last_score = 0.44
        await runner._process_pcm(b"low-score")
        runner.wake.last_score = 0.71
        await runner._process_pcm(b"high-score")

        snapshot = runner.wake_acceptance_snapshot
        assert snapshot.last_score == pytest.approx(0.71)
        assert snapshot.best_score == pytest.approx(0.71)
        await runner.stop_wake_acceptance()

    asyncio.run(scenario())


def test_normal_wake_behavior_is_restored_after_acceptance_completion():
    async def scenario():
        runner = await _complete_wake_test([True])
        voice = runner.voice
        assert voice.state is VoiceSessionState.SLEEPING

        runner.wake.detected = True
        await runner._process_pcm(b"normal-wake")

        assert voice.wake_calls == 1
        assert voice.state is VoiceSessionState.LISTENING

    asyncio.run(scenario())


def test_acceptance_failure_restores_normal_sleeping_mode():
    async def scenario():
        runner, voice, _endpoint = _runner()
        runner._wake_acceptance_attempt_seconds = 0.1
        await runner.start_wake_acceptance(attempts=1)
        runner.wake.detected = True
        runner.wake.detect_pcm = lambda _audio: (_ for _ in ()).throw(RuntimeError("wake detector failed"))

        with pytest.raises(RuntimeError, match="wake detector failed"):
            await runner._process_pcm(b"failure")

        assert not runner.wake_acceptance_active
        assert voice.state is VoiceSessionState.SLEEPING

    asyncio.run(scenario())


class _Widget:
    instances = []

    def __init__(self, parent=None, **kwargs):
        self.parent = parent
        self.options = dict(kwargs)
        self.children = []
        self.after_calls = []
        self.protocols = {}
        self.destroyed = False
        self.content = ""
        self.__class__.instances.append(self)
        if parent is not None and hasattr(parent, "children"):
            parent.children.append(self)

    def pack(self, **_kwargs):
        pass

    def configure(self, **kwargs):
        self.options.update(kwargs)

    config = configure

    def delete(self, *_args):
        self.content = ""

    def insert(self, _index, value):
        self.content += value

    def title(self, value):
        self.options["title"] = value

    def geometry(self, value):
        self.options["geometry"] = value

    def bind(self, *_args):
        pass

    def protocol(self, name, callback):
        self.protocols[name] = callback

    def after(self, delay, callback):
        self.after_calls.append((delay, callback))
        return len(self.after_calls)

    def destroy(self):
        self.destroyed = True

    def winfo_children(self):
        return tuple(self.children)

    def invoke(self):
        if self.options.get("state") != "disabled":
            return self.options["command"]()


class _FakeRunner:
    def __init__(self):
        from jarvis.voice.runtime import WakeAcceptanceSnapshot

        self.snapshot = WakeAcceptanceSnapshot(False, 10, 0, 0, 0, None, None, None, None, None)
        self.start_calls = 0
        self.stop_calls = 0
        self.diagnostics = {"last_wake_score": None, "wake_threshold": 0.5}

    @property
    def wake_acceptance_snapshot(self):
        return self.snapshot

    async def start_wake_acceptance(self):
        self.start_calls += 1
        self.snapshot = replace(self.snapshot, active=True, attempt_index=1, result=None, started_at=1.0)
        return self.snapshot

    async def stop_wake_acceptance(self):
        self.stop_calls += 1
        self.snapshot = replace(self.snapshot, active=False, result="CANCELLED")
        return self.snapshot


class _FakeLifecycle:
    def __init__(self, config_path):
        self.runner = _FakeRunner()
        self.config_path = config_path

    async def start_wake_acceptance(self):
        return await self.runner.start_wake_acceptance()

    async def stop_wake_acceptance(self):
        return await self.runner.stop_wake_acceptance()


def _show_acceptance(monkeypatch, tmp_path):
    import tkinter  # noqa: F401

    _Widget.instances = []
    tk = types.ModuleType("tkinter")
    tk.Toplevel = _Widget
    tk.Label = _Widget
    tk.Text = _Widget
    tk.Frame = _Widget
    tk.Button = _Widget
    tk.messagebox = types.SimpleNamespace(showinfo=lambda *_args: None, showerror=lambda *_args: None)
    monkeypatch.setitem(sys.modules, "tkinter", tk)
    monkeypatch.setitem(sys.modules, "tkinter.messagebox", tk.messagebox)

    lifecycle = _FakeLifecycle(tmp_path / "settings.json")
    from jarvis.desktop.ui import DesktopWindow

    window = DesktopWindow(lifecycle, run_async=lambda awaitable: asyncio.run(awaitable))
    window.root = _Widget()
    window.detail_label = _Widget()
    window._last_microphone_probe = type("Probe", (), {"usable_signal": True})()
    window.show_acceptance()
    wizard = next(item for item in _Widget.instances if item.options.get("title") == "JARVIS Physical Acceptance")
    buttons = {item.options.get("text"): item for item in _Widget.instances if "command" in item.options}
    return window, lifecycle, wizard, buttons


def _advance_to_wake(buttons):
    record = buttons["Record PASS"]
    record.options["command"]()
    record.options["command"]()


def test_wake_wizard_has_explicit_start_stop_and_periodic_live_polling(monkeypatch, tmp_path):
    window, lifecycle, wizard, buttons = _show_acceptance(monkeypatch, tmp_path)
    _advance_to_wake(buttons)

    assert "Start Wake Test" in buttons
    assert "Stop Test" in buttons
    assert any(delay == 100 for delay, _callback in wizard.after_calls)
    assert buttons["Record PASS"].options["state"] == "disabled"
    assert lifecycle.runner.start_calls == 0

    buttons["Start Wake Test"].invoke()

    assert lifecycle.runner.start_calls == 1
    assert buttons["Stop Test"].options["state"] != "disabled"
    assert buttons["Record PASS"].options["state"] == "disabled"
    window.close()


def test_wake_wizard_poll_renders_session_counter_and_live_confidence(monkeypatch, tmp_path):
    window, lifecycle, wizard, buttons = _show_acceptance(monkeypatch, tmp_path)
    _advance_to_wake(buttons)
    buttons["Start Wake Test"].invoke()
    lifecycle.runner.snapshot = replace(
        lifecycle.runner.snapshot,
        active=True,
        attempt_index=3,
        detections=2,
        last_score=0.44,
        best_score=0.71,
    )
    lifecycle.runner.diagnostics = {"last_wake_score": 0.44, "wake_threshold": 0.5}
    poll = next(callback for delay, callback in wizard.after_calls if delay == 100)
    poll()

    texts = [item.options.get("text", "") for item in _Widget.instances]
    assert any("Attempt: 3 / 10" in text and "Detected: 2 / 3" in text for text in texts)
    assert any("Current confidence: 0.44" in text and "Best confidence: 0.71" in text for text in texts)
    window.close()


def test_wake_wizard_only_allows_pass_after_backend_result(monkeypatch, tmp_path):
    window, lifecycle, wizard, buttons = _show_acceptance(monkeypatch, tmp_path)
    _advance_to_wake(buttons)
    record = buttons["Record PASS"]
    assert record.options["state"] == "disabled"

    lifecycle.runner.snapshot = replace(lifecycle.runner.snapshot, active=False, detections=10, result="PASS")
    poll = next(callback for delay, callback in wizard.after_calls if delay == 100)
    poll()

    assert record.options["state"] != "disabled"
    record.invoke()
    from jarvis.desktop.acceptance import AcceptanceStep

    assert window._acceptance_controller.status(AcceptanceStep.WAKE) == "PASS"
    window.close()


def test_closing_wake_wizard_cancels_backend_test(monkeypatch, tmp_path):
    window, lifecycle, wizard, buttons = _show_acceptance(monkeypatch, tmp_path)
    _advance_to_wake(buttons)
    buttons["Start Wake Test"].invoke()

    wizard.protocols["WM_DELETE_WINDOW"]()

    assert lifecycle.runner.stop_calls == 1
    assert wizard.destroyed
    window.close()
