"""Zero-touch setup, settings, diagnostics, and physical acceptance UI."""

from __future__ import annotations

import asyncio
import queue
import threading
from collections.abc import Awaitable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..voice.config import VoiceDeviceSelector
from .acceptance import AcceptanceStep, PhysicalAcceptanceController
from .audio import MicrophoneCandidateResult, MicrophoneMeterUpdate, MicrophoneProbeResult
from .diagnostics import DesktopDiagnostics
from .lifecycle import DesktopPhase, JarvisDesktopLifecycle


@dataclass(frozen=True, slots=True)
class DesktopUiSnapshot:
    phase: str
    statuses: tuple[tuple[str, str], ...]
    microphone_options: tuple[str, ...]
    speaker_options: tuple[str, ...]
    microphone: str | None
    speaker: str | None
    voice_enabled: bool
    autostart: bool
    follow_up_seconds: float
    repair_available: bool


class DesktopViewModel:
    """Headless UI seam; it exposes no credentials, transcripts, or audio."""

    def __init__(self, lifecycle: JarvisDesktopLifecycle) -> None:
        self.lifecycle = lifecycle

    def snapshot(self) -> DesktopUiSnapshot:
        status = self.lifecycle.status
        settings = self.lifecycle.settings
        if settings is None:
            try:
                settings = self.lifecycle._load_settings(defaults=True)  # type: ignore[attr-defined]
            except Exception:
                settings = None
        input_options: list[str] = []
        output_options: list[str] = []
        try:
            devices = self.lifecycle.audio_catalog.enumerate()
            input_options = [_selector_label(item.selector) for item in devices if item.direction == "input"]
            output_options = [_selector_label(item.selector) for item in devices if item.direction == "output"]
        except Exception:
            pass
        input_selector = _selector_label(settings.input_device) if settings and settings.input_device else None
        output_selector = _selector_label(settings.output_device) if settings and settings.output_device else None
        validation = settings.last_validation if settings else {}
        statuses = (
            ("Core", "READY" if self.lifecycle.runtime is not None else "PENDING"),
            ("Identity", "READY" if status.identity_id else "PENDING"),
            ("Local Device", "READY" if status.device_id else "PENDING"),
            ("Local Brain", "READY" if status.brain_ready else ("PREPARING" if status.phase is DesktopPhase.STARTING else "UNAVAILABLE")),
            ("Microphone", "READY" if input_selector else "SELECT"),
            ("Speaker", "READY" if output_selector else "SELECT"),
            ("Wake", "READY" if validation.get("wake") == "ready" else ("OFF" if settings and not settings.voice_enabled else "PENDING")),
            ("STT", "READY" if validation.get("stt") == "ready" else ("OFF" if settings and not settings.voice_enabled else "PENDING")),
            ("TTS", "READY" if validation.get("english_tts") == "ready" and validation.get("arabic_tts") == "ready" else ("OFF" if settings and not settings.voice_enabled else "PENDING")),
        )
        return DesktopUiSnapshot(
            phase=status.phase.value.upper(),
            statuses=statuses,
            microphone_options=tuple(dict.fromkeys(input_options)),
            speaker_options=tuple(dict.fromkeys(output_options)),
            microphone=input_selector,
            speaker=output_selector,
            voice_enabled=settings.voice_enabled if settings else True,
            autostart=settings.autostart if settings else self.lifecycle.startup_manager.enabled(),
            follow_up_seconds=settings.follow_up_seconds if settings else 30.0,
            repair_available=status.phase is DesktopPhase.DEGRADED and bool(status.identity_id),
        )


class DesktopWindow:
    """Tk product shell delegating runtime authority to ``JarvisDesktopLifecycle``."""

    def __init__(self, lifecycle: JarvisDesktopLifecycle, *, run_async: Callable[[Awaitable[Any]], Any] | None = None) -> None:
        self.lifecycle = lifecycle
        self.run_async = run_async or asyncio.run
        self.view_model = DesktopViewModel(lifecycle)
        self.root: Any | None = None
        self._ui_thread_id: int | None = None
        self.state_label: Any | None = None
        self.detail_label: Any | None = None
        self.body: Any | None = None
        self._build_error: Exception | None = None
        self._row_values: dict[str, Any] = {}
        self._input_combo: Any | None = None
        self._output_combo: Any | None = None
        self._input_values: dict[str, VoiceDeviceSelector] = {}
        self._output_values: dict[str, VoiceDeviceSelector] = {}
        self._microphone_probe_thread: threading.Thread | None = None
        self._last_microphone_probe: MicrophoneProbeResult | None = None
        self._best_microphone: MicrophoneCandidateResult | None = None
        self._acceptance_controller: PhysicalAcceptanceController | None = None
        self._acceptance_close: Callable[[], Any] | None = None
        self._ui_events: queue.Queue[Callable[[], Any]] = queue.Queue()
        self._voice_var: Any | None = None
        self._autostart_var: Any | None = None
        self._follow_up_var: Any | None = None

    def snapshot(self) -> DesktopUiSnapshot:
        return self.view_model.snapshot()

    def available_actions(self, *, setup: bool = False) -> tuple[str, ...]:
        actions = [
            "Test Microphone",
            "Find Best Microphone",
            "Use Best Microphone",
            "Check Bluetooth Duplex",
            "Test Speaker",
            "Repair This Device",
            "Acceptance Wizard",
            "Diagnostics",
        ]
        if setup:
            actions.append("Finish Setup")
        else:
            actions.extend(("Open JARVIS HUD", "Pause Voice", "Resume Voice"))
        return tuple(actions)

    def _build(self) -> bool:
        if self.root is not None:
            return True
        try:
            import tkinter as tk
            from tkinter import ttk
        except Exception as exc:
            self._build_error = exc
            return False
        self.root = tk.Tk()
        self._ui_thread_id = threading.get_ident()
        self.root.title("JARVIS")
        self.root.geometry("720x720")
        self.root.configure(bg="#080b10")
        title = tk.Label(self.root, text="J.A.R.V.I.S.", fg="#67e8f9", bg="#080b10", font=("Consolas", 22, "bold"))
        title.pack(pady=(20, 4))
        self.state_label = tk.Label(self.root, text="STARTING", fg="#86efac", bg="#080b10", font=("Consolas", 18, "bold"))
        self.state_label.pack(pady=4)
        self.detail_label = tk.Label(self.root, text="", fg="#8aa0b4", bg="#080b10", justify="left", font=("Consolas", 10))
        self.detail_label.pack(pady=(4, 10))
        self.body = tk.Frame(self.root, bg="#080b10")
        self.body.pack(fill="both", expand=True, padx=24, pady=4)
        style = ttk.Style(self.root)
        style.configure("JARVIS.TButton", padding=7)
        return True

    def ensure_root(self) -> bool:
        """Create the one native root before tray callbacks can arrive."""

        return self._build()

    def show_setup(self, on_complete: Callable[[], None] | None = None) -> bool:
        if not self._build():
            return False
        self._render_product_panel(setup=True, on_complete=on_complete)
        return True

    def show_status(self) -> bool:
        if self.root is not None and not self._on_ui_thread():
            return self._queue_ui(self.show_status)
        if not self._build():
            return False
        self._render_product_panel(setup=False)
        self._restore_window()
        return True

    def _render_product_panel(self, *, setup: bool, on_complete: Callable[[], None] | None = None) -> None:
        import tkinter as tk
        from tkinter import ttk

        assert self.body is not None
        for child in self.body.winfo_children():
            child.destroy()
        snapshot = self.snapshot()
        heading = "JARVIS Setup" if setup else "JARVIS Settings"
        tk.Label(self.body, text=heading, fg="#d8e5ef", bg="#080b10", font=("Consolas", 15, "bold")).pack(anchor="w", pady=(0, 7))
        status_frame = tk.Frame(self.body, bg="#0d151e", padx=12, pady=8)
        status_frame.pack(fill="x", pady=(0, 8))
        self._row_values = {}
        for name, value in snapshot.statuses:
            row = tk.Frame(status_frame, bg="#0d151e")
            row.pack(fill="x")
            tk.Label(row, text=f"{name:<16}", width=16, anchor="w", fg="#9bb2c6", bg="#0d151e", font=("Consolas", 10)).pack(side="left")
            label = tk.Label(row, text=value, anchor="w", fg="#86efac" if value == "READY" else "#fbbf24", bg="#0d151e", font=("Consolas", 10, "bold"))
            label.pack(side="left")
            self._row_values[name] = label
        settings_frame = tk.Frame(self.body, bg="#080b10")
        settings_frame.pack(fill="x", pady=2)
        self._input_combo, self._input_values = self._selector_combo(settings_frame, "Microphone", snapshot.microphone_options, "input")
        self._output_combo, self._output_values = self._selector_combo(settings_frame, "Speaker", snapshot.speaker_options, "output")
        self._voice_var = tk.BooleanVar(value=snapshot.voice_enabled)
        tk.Checkbutton(settings_frame, text="Voice enabled", variable=self._voice_var, command=self._on_voice_toggle, fg="#d8e5ef", bg="#080b10", selectcolor="#122637", activebackground="#080b10", activeforeground="#d8e5ef").pack(anchor="w", pady=3)
        follow_row = tk.Frame(settings_frame, bg="#080b10")
        follow_row.pack(anchor="w", pady=3)
        tk.Label(follow_row, text="Follow-up seconds", fg="#9bb2c6", bg="#080b10", font=("Consolas", 10)).pack(side="left")
        self._follow_up_var = tk.DoubleVar(value=snapshot.follow_up_seconds)
        follow = ttk.Spinbox(follow_row, from_=1, to=120, increment=1, textvariable=self._follow_up_var, width=7, command=self._on_follow_up_change)
        follow.pack(side="left", padx=10)
        follow.bind("<FocusOut>", lambda _event: self._on_follow_up_change())
        self._autostart_var = tk.BooleanVar(value=snapshot.autostart)
        tk.Checkbutton(settings_frame, text="Start with Windows", variable=self._autostart_var, command=self._on_autostart_toggle, fg="#d8e5ef", bg="#080b10", selectcolor="#122637", activebackground="#080b10", activeforeground="#d8e5ef").pack(anchor="w", pady=3)
        buttons = tk.Frame(self.body, bg="#080b10")
        buttons.pack(fill="x", pady=10)
        self._button(buttons, "Test Microphone", self._test_microphone)
        self._button(buttons, "Find Best Microphone", self._find_best_microphone)
        self._button(buttons, "Use Best Microphone", self._use_best_microphone)
        self._button(buttons, "Check Bluetooth Duplex", self._check_bluetooth_duplex)
        self._button(buttons, "Test Speaker", self._test_speaker)
        self._button(buttons, "Acceptance Wizard", self.show_acceptance)
        self._button(buttons, "Diagnostics", self.show_diagnostics)
        if snapshot.repair_available or setup:
            self._button(buttons, "Repair This Device", self._repair_device)
        if setup:
            self._button(buttons, "Finish Setup", lambda: self._finish_setup(on_complete))
        else:
            self._button(buttons, "Open JARVIS HUD", self.lifecycle.open_hud)
            self._button(buttons, "Pause Voice", lambda: self._toggle_voice(force_pause=True))
            self._button(buttons, "Resume Voice", lambda: self._toggle_voice(force_pause=False))
        self.render()

    def _selector_combo(self, parent: Any, title: str, options: tuple[str, ...], direction: str) -> tuple[Any, dict[str, VoiceDeviceSelector]]:
        import tkinter as tk
        from tkinter import ttk

        row = tk.Frame(parent, bg="#080b10")
        row.pack(fill="x", pady=3)
        tk.Label(row, text=f"{title:<16}", width=16, anchor="w", fg="#9bb2c6", bg="#080b10", font=("Consolas", 10)).pack(side="left")
        values: dict[str, VoiceDeviceSelector] = {}
        try:
            devices = self.lifecycle.audio_catalog.enumerate()
            for device in devices:
                if device.direction == direction:
                    values[_selector_label(device.selector)] = device.selector
        except Exception:
            pass
        combo = ttk.Combobox(row, values=options, state="readonly", width=48)
        selected = self.snapshot().microphone if direction == "input" else self.snapshot().speaker
        if selected in options:
            combo.set(selected)
        elif options:
            combo.current(0)
        combo.bind("<<ComboboxSelected>>", self._on_selector_change)
        combo.pack(side="left", fill="x", expand=True)
        return combo, values

    @staticmethod
    def _button(parent: Any, label: str, command: Callable[[], Any]) -> Any:
        import tkinter as tk

        button = tk.Button(parent, text=label, command=command, bg="#122637", fg="#d8e5ef", relief="flat", padx=8, pady=5)
        button.pack(side="left", padx=(0, 5), pady=3)
        return button

    def _finish_setup(self, on_complete: Callable[[], None] | None) -> None:
        from tkinter import messagebox

        try:
            if on_complete:
                on_complete()
            self._render_product_panel(setup=False)
        except Exception as exc:
            messagebox.showerror("JARVIS setup", "Setup could not be completed safely.")
            self._safe_detail(f"Setup unavailable: {exc.__class__.__name__}")

    def _on_selector_change(self, _event: Any = None) -> None:
        input_device = self._input_values.get(self._input_combo.get()) if self._input_combo is not None else None
        output_device = self._output_values.get(self._output_combo.get()) if self._output_combo is not None else None
        try:
            self.run_async(self.lifecycle.update_audio_devices(input_device, output_device))
            self._last_microphone_probe = None
            self._best_microphone = None
            self.render()
        except Exception as exc:
            self._safe_detail(f"Audio selector unavailable: {exc.__class__.__name__}")

    def _on_voice_toggle(self) -> None:
        try:
            self.run_async(self.lifecycle.set_voice_enabled(bool(self._voice_var.get())))
            self.render()
        except Exception as exc:
            self._safe_detail(f"Voice setting unavailable: {exc.__class__.__name__}")

    def _on_follow_up_change(self) -> None:
        try:
            self.lifecycle.update_follow_up_seconds(float(self._follow_up_var.get()))
            self.render()
        except Exception as exc:
            self._safe_detail(f"Follow-up setting unavailable: {exc.__class__.__name__}")

    def _on_autostart_toggle(self) -> None:
        try:
            self.lifecycle.enable_autostart(bool(self._autostart_var.get()))
            self.render()
        except Exception as exc:
            self._safe_detail(f"Startup setting unavailable: {exc.__class__.__name__}")

    def _test_microphone(self) -> None:
        if self._microphone_probe_thread is not None and self._microphone_probe_thread.is_alive():
            return
        self._safe_detail("Speak now...")

        def on_update(update: MicrophoneMeterUpdate) -> None:
            self._after_ui(lambda: self._render_microphone_meter(update))

        def worker() -> None:
            try:
                result = self.run_async(self.lifecycle.test_microphone(on_update=on_update))
            except Exception as exc:
                self._after_ui(lambda: self._safe_detail(f"Microphone test unavailable: {exc.__class__.__name__}"))
                return
            self._after_ui(lambda: self._finish_microphone_probe(result))

        self._microphone_probe_thread = threading.Thread(target=worker, name="jarvis-microphone-probe", daemon=True)
        self._begin_ui_pump()
        self._microphone_probe_thread.start()

    def _render_microphone_meter(self, update: MicrophoneMeterUpdate) -> None:
        bars = max(0, min(20, round(update.rms * 50)))
        self._safe_detail(
            f"Listening...\n"
            f"{'█' * bars}{'·' * (20 - bars)}  {update.rms_dbfs:.1f} dBFS"
        )

    def _finish_microphone_probe(self, result: MicrophoneProbeResult) -> None:
        self._last_microphone_probe = result
        if self._acceptance_controller is not None:
            self._acceptance_controller.set_microphone_probe(result)
        quality = _signal_quality(result)
        sample_rate = getattr(getattr(self.lifecycle, "audio_catalog", None), "last_probe_sample_rate", 0)
        self._safe_detail(
            f"Signal: {quality}\n"
            f"Peak: {result.peak_dbfs:.1f} dBFS\n"
            f"Average: {result.rms_dbfs:.1f} dBFS\n"
            f"Speech delta: {result.speech_delta_db:.1f} dB\n"
            f"Native sample rate: {sample_rate} Hz"
        )

    def _find_best_microphone(self) -> None:
        if self._microphone_probe_thread is not None and self._microphone_probe_thread.is_alive():
            return
        self._safe_detail("Speak normally for a few seconds...")

        def on_update(update: MicrophoneMeterUpdate) -> None:
            self._after_ui(lambda: self._render_microphone_meter(update))

        def worker() -> None:
            try:
                candidates = self.run_async(self.lifecycle.find_best_microphone(on_update=on_update))
            except Exception as exc:
                self._after_ui(lambda: self._safe_detail(f"Microphone search unavailable: {exc.__class__.__name__}"))
                return
            self._after_ui(lambda: self._finish_best_microphone(candidates))

        self._microphone_probe_thread = threading.Thread(target=worker, name="jarvis-microphone-search", daemon=True)
        self._begin_ui_pump()
        self._microphone_probe_thread.start()

    def _finish_best_microphone(self, candidates: tuple[MicrophoneCandidateResult, ...]) -> None:
        self._best_microphone = candidates[0] if candidates else None
        if self._best_microphone is None:
            self._safe_detail("No usable microphone endpoint was found.")
            return
        result = self._best_microphone.result
        self._safe_detail(
            f"Best microphone: {_selector_label(self._best_microphone.selector)}\n"
            f"Signal: {_signal_quality(result)}\n"
            f"Speech delta: {result.speech_delta_db:.1f} dB\n"
            "Click Use Best Microphone to persist and rebind."
        )

    def _use_best_microphone(self) -> None:
        if self._best_microphone is None:
            self._safe_detail("Run Find Best Microphone first.")
            return
        selector = self._best_microphone.selector

        def worker() -> None:
            try:
                self.run_async(self.lifecycle.use_best_microphone(selector))
            except Exception as exc:
                self._after_ui(lambda: self._safe_detail(f"Microphone selection unavailable: {exc.__class__.__name__}"))
                return
            def finish() -> None:
                self._last_microphone_probe = self._best_microphone.result if self._best_microphone is not None else None
                self._safe_detail(f"Using microphone: {_selector_label(selector)}")

            self._after_ui(finish)

        self._microphone_probe_thread = threading.Thread(target=worker, name="jarvis-microphone-select", daemon=True)
        self._begin_ui_pump()
        self._microphone_probe_thread.start()

    def _check_bluetooth_duplex(self) -> None:
        if self._microphone_probe_thread is not None and self._microphone_probe_thread.is_alive():
            return

        def worker() -> None:
            try:
                result = self.run_async(self.lifecycle.check_bluetooth_duplex())
            except Exception as exc:
                self._after_ui(lambda: self._safe_detail(f"Bluetooth duplex unavailable: {exc.__class__.__name__}"))
                return
            self._after_ui(lambda: self._safe_detail(f"Bluetooth Duplex: {result}"))

        self._microphone_probe_thread = threading.Thread(target=worker, name="jarvis-bluetooth-duplex", daemon=True)
        self._begin_ui_pump()
        self._microphone_probe_thread.start()

    def _after_ui(self, callback: Callable[[], Any]) -> None:
        self._ui_events.put(callback)

    def _begin_ui_pump(self) -> None:
        if self.root is not None:
            self.root.after(50, self._drain_ui_events)

    def _drain_ui_events(self) -> None:
        while True:
            try:
                callback = self._ui_events.get_nowait()
            except queue.Empty:
                break
            callback()
        if self._microphone_probe_thread is not None and self._microphone_probe_thread.is_alive():
            self._begin_ui_pump()
        elif not self._ui_events.empty():
            self._begin_ui_pump()

    def _test_speaker(self) -> None:
        try:
            played = self.run_async(self.lifecycle.test_speaker())
            self._safe_detail("Speaker test played." if played else "Speaker test unavailable until local voice is ready.")
        except Exception as exc:
            self._safe_detail(f"Speaker test unavailable: {exc.__class__.__name__}")

    def _repair_device(self) -> None:
        try:
            self.run_async(self.lifecycle.repair_device())
            self._render_product_panel(setup=False)
        except Exception as exc:
            self._safe_detail(f"Device repair unavailable: {exc.__class__.__name__}")

    def _toggle_voice(self, *, force_pause: bool) -> None:
        try:
            self.run_async(self.lifecycle.pause_voice() if force_pause else self.lifecycle.resume_voice())
            self.render()
        except Exception as exc:
            self._safe_detail(f"Voice control unavailable: {exc.__class__.__name__}")

    def show_acceptance(self) -> None:
        if self.root is None:
            return
        import tkinter as tk
        from tkinter import messagebox

        controller = PhysicalAcceptanceController(require_microphone_probe=True, require_wake_detections=True)
        if self._last_microphone_probe is not None:
            controller.set_microphone_probe(self._last_microphone_probe)
        self._acceptance_controller = controller
        wizard = tk.Toplevel(self.root)
        wizard.title("JARVIS Physical Acceptance")
        wizard.geometry("720x560")
        wizard.configure(bg="#080b10")
        title = tk.Label(wizard, text="Physical Acceptance Wizard", fg="#67e8f9", bg="#080b10", font=("Consolas", 18, "bold"))
        title.pack(pady=(16, 8))
        step_label = tk.Label(wizard, text="", fg="#86efac", bg="#080b10", font=("Consolas", 14, "bold"))
        step_label.pack(pady=4)
        instruction = tk.Label(wizard, text="", fg="#d8e5ef", bg="#080b10", justify="left", wraplength=650, font=("Consolas", 11))
        instruction.pack(pady=8)
        count_label = tk.Label(wizard, text="", fg="#fbbf24", bg="#080b10", font=("Consolas", 10))
        count_label.pack(pady=4)
        steps_text = tk.Text(wizard, height=9, width=76, bg="#0d151e", fg="#9bb2c6", relief="flat")
        steps_text.configure(state="disabled")
        steps_text.pack(padx=16, pady=8)
        actions = tk.Frame(wizard, bg="#080b10")
        actions.pack(fill="x", padx=16, pady=8)
        closed = False

        def evidence_path() -> Path:
            return self.lifecycle.config_path.parent / "PHYSICAL_REALTIME_VOICE.json"

        def wake_snapshot() -> Any | None:
            runner = self.lifecycle.runner
            return getattr(runner, "wake_acceptance_snapshot", None) if runner is not None else None

        def refresh() -> None:
            if closed:
                return
            current = controller.current_step
            if current is None:
                step_label.configure(text="COMPLETE - HUMAN ACCEPTANCE PASS")
                instruction.configure(text="All required steps were explicitly marked PASS by the operator.")
            else:
                title_text = next(item.title for item in controller.steps() if item.step is current)
                step_label.configure(text=f"{controller._index + 1}/{len(AcceptanceStep)}  {title_text}")
                instruction.configure(text=controller.instruction())
            diagnostic = wake_snapshot()
            if current is AcceptanceStep.WAKE and diagnostic is not None:
                runner_diagnostics = getattr(self.lifecycle.runner, "diagnostics", {})
                threshold = runner_diagnostics.get("wake_threshold")
                threshold_text = f"{float(threshold):.2f}" if isinstance(threshold, (int, float)) else "--"
                last_text = f"{float(diagnostic.last_score):.2f}" if isinstance(diagnostic.last_score, (int, float)) else "--"
                best_text = f"{float(diagnostic.best_score):.2f}" if isinstance(diagnostic.best_score, (int, float)) else "--"
                if diagnostic.active:
                    count_label.configure(
                        text=(
                            f"Wake Test\n"
                            f"Attempt: {diagnostic.attempt_index} / {diagnostic.attempt_target}\n"
                            f"Detected: {diagnostic.detections} / {diagnostic.attempt_index}\n"
                            f"Current confidence: {last_text}\n"
                            f"Best confidence: {best_text}\n"
                            f"Threshold: {threshold_text}\n"
                            "State: LISTENING FOR WAKE"
                        )
                    )
                elif diagnostic.result is not None:
                    count_label.configure(
                        text=(
                            f"Wake test {diagnostic.result}: {diagnostic.detections} / "
                            f"{diagnostic.attempt_target}\n"
                            f"Best confidence: {best_text}  Threshold: {threshold_text}"
                        )
                    )
                else:
                    count_label.configure(text='Wake Test\nPress Start, then say "Hey Jarvis" once when prompted.')
            else:
                count_label.configure(text="Human observation is required; automated tests cannot mark PASS.")
            if current is AcceptanceStep.WAKE:
                start_button.configure(state="normal" if diagnostic is None or not diagnostic.active else "disabled")
                stop_button.configure(state="normal" if diagnostic is not None and diagnostic.active else "disabled")
                pass_ready = (
                    diagnostic is not None
                    and not diagnostic.active
                    and diagnostic.result == "PASS"
                    and diagnostic.detections >= diagnostic.attempt_target
                )
                record_pass_button.configure(state="normal" if pass_ready else "disabled")
                record_partial_button.configure(
                    state="normal" if diagnostic is not None and not diagnostic.active and diagnostic.result in {"PASS", "PARTIAL", "FAIL"} else "disabled"
                )
                record_fail_button.configure(
                    state="normal" if diagnostic is not None and not diagnostic.active and diagnostic.result in {"PASS", "PARTIAL", "FAIL"} else "disabled"
                )
            else:
                for button in (start_button, stop_button, record_pass_button, record_partial_button, record_fail_button):
                    button.configure(state="disabled")
            steps_text.configure(state="normal")
            steps_text.delete("1.0", "end")
            steps_text.insert("end", "\n".join(f"{item.title:<22} {item.status}" for item in controller.steps()))
            steps_text.configure(state="disabled")

        def record(status: str) -> None:
            try:
                current = controller.current_step
                if current is None:
                    return
                count = None
                expected = None
                if current is AcceptanceStep.WAKE:
                    diagnostic = wake_snapshot()
                    if diagnostic is None or diagnostic.active or diagnostic.result is None:
                        raise ValueError("wake acceptance backend test must complete")
                    controller.set_wake_acceptance(diagnostic)
                    count = diagnostic.detections
                    expected = diagnostic.attempt_target
                controller.record_current(status, count=count, expected=expected, safe_label="operator observed")
                controller.save(evidence_path())
                refresh()
                if controller.complete:
                    messagebox.showinfo("JARVIS acceptance", "Physical acceptance PASS recorded from all required human steps.")
            except Exception as exc:
                messagebox.showerror("JARVIS acceptance", f"Acceptance step could not be recorded: {exc.__class__.__name__}")

        def start_wake_test() -> None:
            if controller.current_step is not AcceptanceStep.WAKE:
                return
            try:
                diagnostic = self.run_async(self.lifecycle.start_wake_acceptance())
                controller.set_wake_acceptance(diagnostic)
            except Exception as exc:
                messagebox.showerror("JARVIS wake test", f"Wake test could not start: {exc.__class__.__name__}")
            refresh()

        def stop_wake_test() -> None:
            try:
                diagnostic = self.run_async(self.lifecycle.stop_wake_acceptance())
                controller.set_wake_acceptance(diagnostic)
            except Exception as exc:
                messagebox.showerror("JARVIS wake test", f"Wake test could not stop: {exc.__class__.__name__}")
            refresh()

        def close_acceptance() -> None:
            nonlocal closed
            if closed:
                return
            closed = True
            try:
                diagnostic = wake_snapshot()
                if diagnostic is not None and diagnostic.active:
                    self.run_async(self.lifecycle.stop_wake_acceptance())
            except Exception:
                pass
            finally:
                self._acceptance_close = None
                wizard.destroy()

        start_button = self._button(actions, "Start Wake Test", start_wake_test)
        stop_button = self._button(actions, "Stop Test", stop_wake_test)
        self._button(actions, "Test Microphone", self._test_microphone)
        self._button(actions, "Test Speaker", self._test_speaker)
        record_pass_button = self._button(actions, "Record PASS", lambda: record("PASS"))
        record_partial_button = self._button(actions, "Record PARTIAL", lambda: record("PARTIAL"))
        record_fail_button = self._button(actions, "Record FAIL", lambda: record("FAIL"))
        wizard.protocol("WM_DELETE_WINDOW", close_acceptance)
        self._acceptance_close = close_acceptance
        refresh()
        def poll() -> None:
            if closed:
                return
            refresh()
            wizard.after(100, poll)

        wizard.after(100, poll)

    def show_diagnostics(self) -> None:
        if self.root is not None and not self._on_ui_thread():
            self._queue_ui(self.show_diagnostics)
            return
        if self.root is None:
            return
        from tkinter import messagebox

        results = self.run_async(DesktopDiagnostics(self.lifecycle).run())
        messagebox.showinfo("JARVIS diagnostics", "\n".join(f"{item.name}: {item.status}" for item in results))

    def render(self) -> None:
        if self.state_label is None or self.detail_label is None:
            return
        snapshot = self.snapshot()
        self.state_label.configure(text=snapshot.phase)
        for name, value in snapshot.statuses:
            label = self._row_values.get(name)
            if label is not None:
                label.configure(text=value)
        status = self.lifecycle.status
        self.detail_label.configure(text=(
            f"Brain       {'Ready' if status.brain_ready else 'Unavailable'}\n"
            f"Voice       {status.voice_state.title()}\n"
            f"Memory      {'Ready' if self.lifecycle.runtime is not None else 'Unavailable'}\n"
            f"Computer    {'Available' if self.lifecycle.runtime is not None else 'Unavailable'}\n\n"
            f"{status.reason}"
        ))

    def _safe_detail(self, value: str) -> None:
        if self.detail_label is not None:
            self.detail_label.configure(text=value)

    def _on_ui_thread(self) -> bool:
        return self._ui_thread_id is None or threading.get_ident() == self._ui_thread_id

    def _queue_ui(self, callback: Callable[[], Any]) -> bool:
        if self.root is None:
            return False
        try:
            self.root.after(0, callback)
        except Exception:
            return False
        return True

    def _restore_window(self) -> None:
        if self.root is None:
            return
        for method_name in ("deiconify", "lift", "focus_force"):
            method = getattr(self.root, method_name, None)
            if callable(method):
                try:
                    method()
                except Exception:
                    pass

    def run(self) -> None:
        if self.root is not None:
            self.root.mainloop()

    def run_background(self) -> bool:
        """Keep the desktop process alive while the browser is the product UI."""

        if self.root is None and not self._build():
            return False
        if self.root is not None:
            self.root.withdraw()
            self.root.mainloop()
        return True

    def close(self) -> None:
        if self._acceptance_close is not None:
            close_acceptance = self._acceptance_close
            self._acceptance_close = None
            close_acceptance()
        if self.root is not None:
            self.root.destroy()
            self.root = None
            self._ui_thread_id = None


def _selector_label(selector: VoiceDeviceSelector) -> str:
    return f"{selector.host_api} / {selector.name}"


def _signal_quality(result: MicrophoneProbeResult) -> str:
    if result.usable_signal and not result.clipping:
        return "GOOD"
    if result.frames_seen and result.rms > 0.001:
        return "WEAK"
    return "FAIL"
