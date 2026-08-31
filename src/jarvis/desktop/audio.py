"""Safe local audio catalog and transient probe boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..voice.adapters import VoiceDeviceError, resolve_sounddevice_device
from ..voice.config import VoiceDeviceSelector


@dataclass(frozen=True, slots=True)
class AudioDevice:
    host_api: str
    name: str
    direction: str
    channels: int
    is_default: bool = False

    @property
    def selector(self) -> VoiceDeviceSelector:
        return VoiceDeviceSelector(self.host_api, self.name)


class AudioDeviceCatalog:
    """Enumerate devices without retaining samples or numeric identifiers."""

    def __init__(self, sounddevice: Any | None = None) -> None:
        self.sounddevice = sounddevice

    def _module(self) -> Any:
        if self.sounddevice is None:
            import sounddevice as sounddevice

            self.sounddevice = sounddevice
        return self.sounddevice

    def enumerate(self) -> tuple[AudioDevice, ...]:
        sounddevice = self._module()
        devices = sounddevice.query_devices()
        host_apis = sounddevice.query_hostapis()
        defaults = getattr(sounddevice, "default", None)
        default_pair = getattr(defaults, "device", (None, None)) if defaults is not None else (None, None)
        result: list[AudioDevice] = []
        for index, item in enumerate(devices):
            host_index = int(item.get("hostapi", -1))
            host_name = str(host_apis[host_index].get("name", "")) if 0 <= host_index < len(host_apis) else ""
            name = str(item.get("name", ""))
            input_channels = int(item.get("max_input_channels", 0))
            output_channels = int(item.get("max_output_channels", 0))
            if input_channels > 0:
                result.append(AudioDevice(host_name, name, "input", input_channels, index == default_pair[0]))
            if output_channels > 0:
                result.append(AudioDevice(host_name, name, "output", output_channels, index == default_pair[1]))
        return tuple(result)

    def choose_default(self, direction: str) -> VoiceDeviceSelector | None:
        choices = [item for item in self.enumerate() if item.direction == direction]
        defaults = [item for item in choices if item.is_default]
        if len(defaults) == 1:
            return defaults[0].selector
        if len(choices) == 1:
            return choices[0].selector
        return None

    def resolve(self, selector: VoiceDeviceSelector, direction: str) -> int:
        return resolve_sounddevice_device(self._module(), selector, direction)

    def transient_input_level(self, selector: VoiceDeviceSelector, *, seconds: float = 0.25) -> float:
        """Return a bounded meter reading; samples are never written or returned."""

        if seconds <= 0 or seconds > 3:
            raise ValueError("audio probe duration is outside bounds")
        sounddevice = self._module()
        index = self.resolve(selector, "input")
        descriptor = sounddevice.query_devices(index)
        sample_rate = int(round(float(descriptor["default_samplerate"])))
        try:
            recording = sounddevice.rec(max(1, round(sample_rate * seconds)), samplerate=sample_rate, channels=1, dtype="float32", device=index)
            sounddevice.wait()
            values = getattr(recording, "__iter__", None)
            if values is None:
                return 0.0
            import math

            peak = max((abs(float(sample[0] if hasattr(sample, "__len__") else sample)) for sample in recording), default=0.0)
            return max(0.0, min(1.0, math.sqrt(peak * peak)))
        except Exception as exc:
            raise VoiceDeviceError("voice_microphone_probe_failed") from exc
        finally:
            try:
                del recording
            except UnboundLocalError:
                pass

    def test_speaker(self, selector: VoiceDeviceSelector) -> bool:
        """Verify output configuration only; the VoiceCore supplies test audio."""

        sounddevice = self._module()
        index = self.resolve(selector, "output")
        descriptor = sounddevice.query_devices(index)
        return int(descriptor.get("max_output_channels", 0)) > 0
