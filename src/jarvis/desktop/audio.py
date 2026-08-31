"""Safe local audio catalog and transient probe boundaries."""

from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Any, Callable, Iterable

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


@dataclass(frozen=True, slots=True)
class MicrophoneMeterUpdate:
    """Safe live-meter data; no sample content crosses the probe boundary."""

    peak: float
    rms: float
    peak_dbfs: float
    rms_dbfs: float
    duration_seconds: float
    frames_seen: int


@dataclass(frozen=True, slots=True)
class MicrophoneProbeResult:
    """Metrics from one bounded explicit speech opportunity."""

    peak: float
    rms: float
    peak_dbfs: float
    rms_dbfs: float
    ambient_rms_dbfs: float
    speech_delta_db: float
    duration_seconds: float
    frames_seen: int
    clipping: bool
    usable_signal: bool


@dataclass(frozen=True, slots=True)
class MicrophoneCandidateResult:
    selector: VoiceDeviceSelector
    result: MicrophoneProbeResult
    callback_fault_count: int = 0


PROBE_MIN_SECONDS = 2.0
PROBE_DEFAULT_SECONDS = 3.0
PROBE_MAX_SECONDS = 5.0
DBFS_EPSILON = 1e-12
MIN_USABLE_SPEECH_RMS = 0.02


def _dbfs(amplitude: float) -> float:
    return 20.0 * math.log10(max(abs(float(amplitude)), DBFS_EPSILON))


def _sample_value(sample: Any) -> float:
    if isinstance(sample, (int, float)):
        return float(sample)
    try:
        return float(sample[0])
    except (IndexError, KeyError, TypeError):
        return float(sample)


def _normalized_samples(indata: Any) -> tuple[float, ...]:
    if isinstance(indata, (bytes, bytearray, memoryview)):
        raw = bytes(indata)
        return tuple(
            int.from_bytes(raw[index : index + 2], "little", signed=True) / 32768.0
            for index in range(0, len(raw) - 1, 2)
        )
    try:
        return tuple(_sample_value(sample) for sample in indata)
    except TypeError:
        return (_sample_value(indata),)


def _meter_update(
    *,
    peak: float,
    sum_squares: float,
    frames_seen: int,
    sample_rate: int,
) -> MicrophoneMeterUpdate:
    rms = math.sqrt(sum_squares / frames_seen) if frames_seen else 0.0
    return MicrophoneMeterUpdate(
        peak=max(0.0, min(1.0, peak)),
        rms=max(0.0, min(1.0, rms)),
        peak_dbfs=_dbfs(peak),
        rms_dbfs=_dbfs(rms),
        duration_seconds=frames_seen / sample_rate if sample_rate else 0.0,
        frames_seen=frames_seen,
    )


class AudioDeviceCatalog:
    """Enumerate devices without retaining samples or numeric identifiers."""

    def __init__(
        self,
        sounddevice: Any | None = None,
        *,
        probe_wait: Callable[[float], None] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.sounddevice = sounddevice
        self.probe_wait = probe_wait or time.sleep
        self.monotonic = monotonic
        self.last_probe_callback_fault_count = 0
        self.last_probe_sample_rate = 0

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

    def probe_microphone(
        self,
        selector: VoiceDeviceSelector,
        *,
        seconds: float = PROBE_DEFAULT_SECONDS,
        on_update: Callable[[MicrophoneMeterUpdate], None] | None = None,
    ) -> MicrophoneProbeResult:
        """Run a bounded live speech probe with metrics-only output."""

        if not PROBE_MIN_SECONDS <= seconds <= PROBE_MAX_SECONDS:
            raise ValueError("audio probe duration is outside bounds")
        sounddevice = self._module()
        index = self.resolve(selector, "input")
        descriptor = sounddevice.query_devices(index)
        sample_rate = int(round(float(descriptor["default_samplerate"])))
        if sample_rate <= 0:
            raise VoiceDeviceError("voice_microphone_probe_failed")
        self.last_probe_sample_rate = sample_rate
        try:
            sounddevice.check_input_settings(
                device=index,
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
            )
        except Exception as exc:
            raise VoiceDeviceError("voice_device_unsupported_format") from exc

        frames_seen = 0
        total_peak = 0.0
        total_sum_squares = 0.0
        ambient_frames = 0
        ambient_sum_squares = 0.0
        speech_frames = 0
        speech_peak = 0.0
        speech_sum_squares = 0.0
        clipping = False
        callback_faults = 0
        last_update = -math.inf
        stream: Any | None = None

        def update(indata: Any, _frames: int, _time: Any, status: Any) -> None:
            nonlocal frames_seen, total_peak, total_sum_squares
            nonlocal ambient_frames, ambient_sum_squares
            nonlocal speech_frames, speech_peak, speech_sum_squares, clipping
            nonlocal callback_faults, last_update
            if status:
                callback_faults += 1
            samples = _normalized_samples(indata)
            if not samples:
                return
            baseline_limit = int(round(sample_rate * 0.5))
            for sample in samples:
                amplitude = abs(sample)
                total_peak = max(total_peak, amplitude)
                total_sum_squares += amplitude * amplitude
                clipping = clipping or amplitude >= 1.0
                if frames_seen < baseline_limit:
                    ambient_frames += 1
                    ambient_sum_squares += amplitude * amplitude
                else:
                    speech_frames += 1
                    speech_peak = max(speech_peak, amplitude)
                    speech_sum_squares += amplitude * amplitude
                frames_seen += 1
            now = self.monotonic()
            if on_update is not None and (now - last_update >= 0.05 or last_update == -math.inf):
                last_update = now
                try:
                    on_update(
                        _meter_update(
                            peak=speech_peak or total_peak,
                            sum_squares=speech_sum_squares or total_sum_squares,
                            frames_seen=speech_frames or frames_seen,
                            sample_rate=sample_rate,
                        )
                    )
                except Exception:
                    # A UI observer is never allowed to interrupt the capture callback.
                    pass

        try:
            stream = sounddevice.InputStream(
                device=index,
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                blocksize=max(1, round(sample_rate * 0.08)),
                callback=update,
            )
            stream.start()
            self.probe_wait(float(seconds))
        except Exception as exc:
            raise VoiceDeviceError("voice_microphone_probe_failed") from exc
        finally:
            try:
                if stream is not None:
                    stream.stop()
            finally:
                if stream is not None:
                    stream.close()

        self.last_probe_callback_fault_count = callback_faults
        duration_seconds = frames_seen / sample_rate if frames_seen else float(seconds)
        speech_peak = speech_peak or total_peak
        speech_rms = math.sqrt(speech_sum_squares / speech_frames) if speech_frames else math.sqrt(total_sum_squares / frames_seen) if frames_seen else 0.0
        ambient_rms = math.sqrt(ambient_sum_squares / ambient_frames) if ambient_frames else 0.0
        speech_dbfs = _dbfs(speech_rms)
        ambient_dbfs = _dbfs(ambient_rms)
        speech_delta = speech_dbfs - ambient_dbfs if ambient_frames and speech_frames else 0.0
        result = MicrophoneProbeResult(
            peak=max(0.0, min(1.0, speech_peak)),
            rms=max(0.0, min(1.0, speech_rms)),
            peak_dbfs=_dbfs(speech_peak),
            rms_dbfs=speech_dbfs,
            ambient_rms_dbfs=ambient_dbfs,
            speech_delta_db=speech_delta,
            duration_seconds=duration_seconds,
            frames_seen=frames_seen,
            clipping=clipping,
            usable_signal=bool(speech_frames and speech_rms >= MIN_USABLE_SPEECH_RMS and speech_delta >= 6.0),
        )
        if on_update is not None:
            try:
                on_update(
                    MicrophoneMeterUpdate(
                        result.peak,
                        result.rms,
                        result.peak_dbfs,
                        result.rms_dbfs,
                        result.duration_seconds,
                        result.frames_seen,
                    )
                )
            except Exception:
                pass
        return result

    def transient_input_level(self, selector: VoiceDeviceSelector, *, seconds: float = PROBE_DEFAULT_SECONDS) -> float:
        """Compatibility level accessor backed by the real bounded speech probe."""

        return self.probe_microphone(selector, seconds=seconds).peak

    def probe_input_candidates(
        self,
        selector: VoiceDeviceSelector | None = None,
        *,
        seconds: float = PROBE_DEFAULT_SECONDS,
        on_update: Callable[[MicrophoneMeterUpdate], None] | None = None,
    ) -> tuple[MicrophoneCandidateResult, ...]:
        """Probe each plausible input endpoint during an explicit calibration."""

        candidates: list[MicrophoneCandidateResult] = []
        for device in self._input_devices(selector):
            try:
                result = self.probe_microphone(device.selector, seconds=seconds, on_update=on_update)
            except VoiceDeviceError:
                continue
            candidates.append(
                MicrophoneCandidateResult(device.selector, result, self.last_probe_callback_fault_count)
            )
        return self.rank_input_candidates(candidates)

    @staticmethod
    def rank_input_candidates(
        candidates: Iterable[MicrophoneCandidateResult],
    ) -> tuple[MicrophoneCandidateResult, ...]:
        """Rank real signal first; host API preference is only a tiebreaker."""

        def host_tiebreaker(candidate: MicrophoneCandidateResult) -> int:
            return {"Windows WASAPI": 3, "Windows DirectSound": 2, "MME": 1}.get(candidate.selector.host_api, 0)

        return tuple(sorted(
            candidates,
            key=lambda candidate: (
                candidate.result.usable_signal,
                candidate.callback_fault_count == 0,
                candidate.result.speech_delta_db,
                candidate.result.rms_dbfs,
                candidate.result.peak_dbfs,
                host_tiebreaker(candidate),
            ),
            reverse=True,
        ))

    def _input_devices(self, selector: VoiceDeviceSelector | None) -> tuple[AudioDevice, ...]:
        seen: set[tuple[str, str]] = set()
        devices: list[AudioDevice] = []
        for device in self.enumerate():
            if device.direction != "input":
                continue
            is_selected = selector is not None and (
                device.host_api.casefold() == selector.host_api.casefold()
                and device.name.casefold() == selector.name.casefold()
            )
            normalized_name = device.name.casefold()
            if not is_selected and any(
                marker in normalized_name
                for marker in ("stereo mix", "pc speaker", "primary sound capture driver", "sound mapper")
            ):
                continue
            key = (device.host_api.casefold(), device.name.casefold())
            if key in seen:
                continue
            seen.add(key)
            devices.append(device)
        return tuple(devices)

    def check_duplex(
        self,
        input_selector: VoiceDeviceSelector,
        output_selector: VoiceDeviceSelector,
    ) -> str:
        """Open the selected input and output together without playing audio."""

        sounddevice = self._module()
        input_stream: Any | None = None
        output_stream: Any | None = None
        try:
            input_index = self.resolve(input_selector, "input")
            output_index = self.resolve(output_selector, "output")
            input_descriptor = sounddevice.query_devices(input_index)
            output_descriptor = sounddevice.query_devices(output_index)
            input_rate = int(round(float(input_descriptor["default_samplerate"])))
            output_rate = int(round(float(output_descriptor["default_samplerate"])))
            sounddevice.check_input_settings(device=input_index, samplerate=input_rate, channels=1, dtype="float32")
            sounddevice.check_output_settings(device=output_index, samplerate=output_rate, channels=1, dtype="float32")
            input_stream = sounddevice.InputStream(
                device=input_index,
                samplerate=input_rate,
                channels=1,
                dtype="float32",
                callback=lambda *_args: None,
            )
            output_stream = sounddevice.OutputStream(
                device=output_index,
                samplerate=output_rate,
                channels=1,
                dtype="float32",
                callback=lambda outdata, *_args: outdata.fill(0),
            )
            input_stream.start()
            output_stream.start()
            return "PASS"
        except Exception:
            return "PARTIAL"
        finally:
            for stream in (output_stream, input_stream):
                if stream is None:
                    continue
                try:
                    stream.stop()
                finally:
                    stream.close()

    def test_speaker(self, selector: VoiceDeviceSelector) -> bool:
        """Verify output configuration only; the VoiceCore supplies test audio."""

        sounddevice = self._module()
        index = self.resolve(selector, "output")
        descriptor = sounddevice.query_devices(index)
        return int(descriptor.get("max_output_channels", 0)) > 0
