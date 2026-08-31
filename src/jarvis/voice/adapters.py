"""Local-only physical voice adapters.

Optional audio dependencies are imported only by explicit adapter lifecycle
methods.  Nothing in this module opens devices, loads a model, or contacts a
network endpoint while imported.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..contracts import VoiceTranscript
from .config import VoiceDeviceSelector


class VoiceDeviceError(RuntimeError):
    """A safe, stable reason for a configured local audio endpoint failure."""


@dataclass(frozen=True, slots=True)
class SignalMetrics:
    """Metrics-only view of an ephemeral mono PCM buffer."""

    peak: float
    rms: float
    peak_dbfs: float
    rms_dbfs: float


def pcm16_metrics(audio: bytes) -> SignalMetrics:
    """Measure PCM without exposing or retaining the samples."""

    if len(audio) < 2:
        return SignalMetrics(0.0, 0.0, -240.0, -240.0)
    count = len(audio) // 2
    peak = 0.0
    sum_squares = 0.0
    for offset in range(0, count * 2, 2):
        amplitude = abs(int.from_bytes(audio[offset : offset + 2], "little", signed=True)) / 32768.0
        peak = max(peak, amplitude)
        sum_squares += amplitude * amplitude
    rms = math.sqrt(sum_squares / count) if count else 0.0
    return SignalMetrics(peak, rms, _dbfs(peak), _dbfs(rms))


def _dbfs(amplitude: float) -> float:
    return 20.0 * math.log10(max(abs(float(amplitude)), 1e-12))


def resolve_sounddevice_device(sounddevice: object, selector: VoiceDeviceSelector, direction: str) -> int:
    """Resolve an exact host-API/name/direction selector for this run only."""

    selector.validate(direction)
    devices = sounddevice.query_devices()  # type: ignore[attr-defined]
    host_apis = sounddevice.query_hostapis()  # type: ignore[attr-defined]
    matches: list[int] = []
    channel_key = "max_input_channels" if direction == "input" else "max_output_channels"
    for index, device in enumerate(devices):
        host_api_index = int(device.get("hostapi", -1))
        host_name = ""
        if 0 <= host_api_index < len(host_apis):
            host_name = str(host_apis[host_api_index].get("name", ""))
        if (
            host_name.casefold() == selector.host_api.casefold()
            and str(device.get("name", "")).casefold() == selector.name.casefold()
            and int(device.get(channel_key, 0)) > 0
        ):
            matches.append(index)
    if not matches:
        raise VoiceDeviceError("voice_device_missing")
    if len(matches) > 1:
        raise VoiceDeviceError("voice_device_ambiguous")
    return matches[0]


def resample_pcm_16le(audio: bytes, source_rate: int, target_rate: int) -> bytes:
    """Resample ephemeral mono PCM in memory without temp files.

    The exact-factor paths avoid surprising driver fallback on endpoints that
    only expose 48 kHz.  General interpolation is only used for local TTS
    output whose model rate is not an integer multiple of the speaker rate.
    """

    if not audio or source_rate == target_rate:
        return audio
    if source_rate <= 0 or target_rate <= 0:
        raise ValueError("audio sample rates must be positive")
    import numpy as np

    samples = np.frombuffer(audio, dtype=np.int16)
    if source_rate % target_rate == 0:
        factor = source_rate // target_rate
        usable = len(samples) - (len(samples) % factor)
        if not usable:
            return b""
        return samples[:usable].reshape(-1, factor).mean(axis=1).astype(np.int16).tobytes()
    if target_rate % source_rate == 0:
        return np.repeat(samples, target_rate // source_rate).astype(np.int16).tobytes()
    output_count = max(1, round(len(samples) * target_rate / source_rate))
    positions = np.linspace(0, max(0, len(samples) - 1), output_count)
    return np.interp(positions, np.arange(len(samples)), samples).astype(np.int16).tobytes()


class SoundDeviceInput:
    """One configured local microphone; the callback only copies/enqueues PCM."""

    def __init__(self, selector: VoiceDeviceSelector) -> None:
        self.selector = selector
        self.sample_rate = 0
        self._stream: object | None = None
        self._callback_fault_count = 0
        self._last_callback_status: str | None = None

    def start(self, callback: Callable[[bytes], None]) -> None:
        import sounddevice as sd

        index = resolve_sounddevice_device(sd, self.selector, "input")
        descriptor = sd.query_devices(index)
        self.sample_rate = int(round(float(descriptor["default_samplerate"])))
        try:
            sd.check_input_settings(device=index, samplerate=self.sample_rate, channels=1, dtype="int16")
        except Exception as exc:
            raise VoiceDeviceError("voice_device_unsupported_format") from exc

        def _callback(indata: object, _frames: int, _time: object, status: object) -> None:
            if status:
                self._callback_fault_count += 1
                self._last_callback_status = str(status)[:120]
            # PortAudio overflow/underflow flags are recoverable status, not a
            # device-loss signal. Healthy frames after one must still flow.
            callback(bytes(indata))

        self._stream = sd.InputStream(
            device=index,
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=max(1, round(self.sample_rate * 0.08)),
            callback=_callback,
        )
        self._stream.start()  # type: ignore[union-attr]

    def take_fault(self) -> bool:
        # Status flags are reported through counters and deliberately do not
        # force the runner to tear down a healthy capture stream.
        return False

    @property
    def callback_fault_count(self) -> int:
        return self._callback_fault_count

    @property
    def last_callback_status(self) -> str | None:
        return self._last_callback_status

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()  # type: ignore[union-attr]
            self._stream.close()  # type: ignore[union-attr]
        self._stream = None


class SoundDevicePlayback:
    """Explicit local playback with no hidden playback in synthesis."""

    def __init__(self, selector: VoiceDeviceSelector, *, max_duration_seconds: float = 60.0) -> None:
        if max_duration_seconds <= 0:
            raise ValueError("voice playback duration bound must be positive")
        self.selector = selector
        self.max_duration_seconds = max_duration_seconds
        self.sample_rate = 0
        self._sounddevice: object | None = None
        self._device_index: int | None = None
        self._faulted = False

    def start(self) -> None:
        import sounddevice as sd

        index = resolve_sounddevice_device(sd, self.selector, "output")
        descriptor = sd.query_devices(index)
        self.sample_rate = int(round(float(descriptor["default_samplerate"])))
        try:
            sd.check_output_settings(device=index, samplerate=self.sample_rate, channels=1, dtype="int16")
        except Exception as exc:
            raise VoiceDeviceError("voice_device_unsupported_format") from exc
        self._sounddevice = sd
        self._device_index = index

    async def play(self, audio: bytes, sample_rate: int) -> None:
        if self._sounddevice is None or self._device_index is None or self.sample_rate <= 0:
            raise RuntimeError("voice playback has not started")
        import numpy as np

        output = resample_pcm_16le(audio, sample_rate, self.sample_rate)
        if not output:
            return
        if len(output) > int(self.sample_rate * 2 * self.max_duration_seconds):
            del output
            raise VoiceDeviceError("voice_playback_too_long")
        samples = np.frombuffer(output, dtype=np.int16)
        try:
            self._sounddevice.play(samples, samplerate=self.sample_rate, device=self._device_index, blocking=False)  # type: ignore[union-attr]
            await asyncio.to_thread(self._sounddevice.wait)  # type: ignore[union-attr]
        except Exception:
            self._faulted = True
            raise
        finally:
            # Drop both synthesized and resampled bytes as soon as playback ends.
            del output, samples

    async def stop(self) -> None:
        if self._sounddevice is not None:
            await asyncio.to_thread(self._sounddevice.stop)  # type: ignore[union-attr]

    def close(self) -> None:
        self._sounddevice = None
        self._device_index = None
        self.sample_rate = 0

    def take_fault(self) -> bool:
        faulted, self._faulted = self._faulted, False
        return faulted


class OpenWakeWordDetector:
    """Offline openWakeWord detector operating on 80 ms 16 kHz PCM frames."""

    def __init__(self, model_path: Path, threshold: float, cooldown_seconds: float = 1.0) -> None:
        self.model_path = model_path
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds
        self._model: object | None = None
        self._last_detection = -math.inf
        self._last_score = 0.0

    @property
    def last_score(self) -> float:
        return self._last_score

    def detect_pcm(self, audio: bytes) -> bool:
        if not audio:
            return False
        if self._model is None:
            self._model = self._load()
        import numpy as np

        scores = self._model.predict(np.frombuffer(audio, dtype=np.int16))  # type: ignore[union-attr]
        score = max((float(value) for value in scores.values()), default=0.0)
        self._last_score = score
        now = time.monotonic()
        if score < self.threshold or now - self._last_detection < self.cooldown_seconds:
            return False
        self._last_detection = now
        return True

    def _load(self) -> object:
        from openwakeword.model import Model

        directory = self.model_path.parent
        feature_paths = {
            "melspec_model_path": directory / "melspectrogram.onnx",
            "embedding_model_path": directory / "embedding_model.onnx",
        }
        if not self.model_path.is_file() or any(not path.is_file() for path in feature_paths.values()):
            raise FileNotFoundError("local openWakeWord assets are incomplete")
        return Model(
            wakeword_models=[str(self.model_path)],
            inference_framework="onnx",
            **{name: str(path) for name, path in feature_paths.items()},
        )


class SileroVad:
    """Stateful local Silero VAD; frame and model state remain memory-only."""

    def __init__(self, model_path: Path, threshold: float) -> None:
        self.model_path = model_path
        self.threshold = threshold
        self._session: object | None = None
        self._state: object | None = None
        self._remainder = bytearray()
        self._frames_processed = 0
        self._last_score = 0.0
        self._last_speech = False

    @property
    def frames_processed(self) -> int:
        return self._frames_processed

    @property
    def last_score(self) -> float:
        return self._last_score

    @property
    def last_speech(self) -> bool:
        return self._last_speech

    def is_speech(self, audio: bytes) -> bool:
        if self._session is None:
            self._load()
        import numpy as np

        self._remainder.extend(audio)
        frame_bytes = 512 * 2
        speech = False
        while len(self._remainder) >= frame_bytes:
            frame = bytes(self._remainder[:frame_bytes])
            del self._remainder[:frame_bytes]
            output, self._state = self._session.run(  # type: ignore[union-attr]
                None,
                {
                    "input": np.frombuffer(frame, dtype=np.int16).astype(np.float32)[None, :] / 32768.0,
                    "state": self._state,
                    "sr": np.array(16_000, dtype=np.int64),
                },
            )
            self._last_score = float(output[0][0])
            self._frames_processed += 1
            self._last_speech = self._last_score >= self.threshold
            speech = speech or self._last_speech
        return speech

    def reset(self) -> None:
        self._remainder.clear()
        self._state = None
        self._last_score = 0.0
        self._last_speech = False
        if self._session is not None:
            self._load_state()

    def _load(self) -> None:
        if not self.model_path.is_file():
            raise FileNotFoundError("local Silero VAD model is missing")
        import onnxruntime as ort

        self._session = ort.InferenceSession(str(self.model_path), providers=["CPUExecutionProvider"])
        self._load_state()

    def _load_state(self) -> None:
        import numpy as np

        self._state = np.zeros((2, 1, 128), dtype=np.float32)


class SpeechEndpointDetector:
    """Neural-VAD endpointing with bounded pre-roll and no partial retention."""

    sample_rate = 16_000
    max_utterance_seconds = 20.0
    hard_utterance_seconds = 30.0

    def __init__(
        self,
        vad: SileroVad,
        *,
        preroll_ms: int = 480,
        min_speech_ms: int = 240,
        end_silence_ms: int = 800,
    ) -> None:
        if not 250 <= preroll_ms <= 750 or not 200 <= min_speech_ms <= 300 or not 600 <= end_silence_ms <= 900:
            raise ValueError("voice endpointing bounds are outside the supported physical range")
        self.vad = vad
        self.preroll_ms = preroll_ms
        self.min_speech_ms = min_speech_ms
        self.end_silence_ms = end_silence_ms
        self._preroll: deque[bytes] = deque()
        self._utterance = bytearray()
        self._active = False
        self._speech_ms = 0.0
        self._silence_ms = 0.0

    @property
    def vad_diagnostics(self) -> dict[str, int | float | bool]:
        vad = self.vad
        return {
            "vad_frames_processed": int(getattr(vad, "frames_processed", 0)),
            "vad_last_score": float(getattr(vad, "last_score", 0.0)),
            "vad_detected_speech": bool(getattr(vad, "last_speech", self._active)),
        }

    @property
    def speech_active(self) -> bool:
        """Whether VAD has started the current in-memory utterance."""

        return self._active

    def feed(self, audio: bytes) -> bytes | None:
        if not audio or len(audio) % 2:
            return None
        duration_ms = len(audio) * 1000 / (2 * self.sample_rate)
        speech = self.vad.is_speech(audio)
        self._preroll.append(audio)
        self._trim_preroll()
        if not self._active:
            if not speech:
                return None
            self._active = True
            self._utterance.extend(b"".join(self._preroll))
            self._speech_ms = duration_ms
            self._silence_ms = 0.0
            return None
        self._utterance.extend(audio)
        if speech:
            self._speech_ms += duration_ms
            self._silence_ms = 0.0
        else:
            self._silence_ms += duration_ms
        total_ms = len(self._utterance) * 1000 / (2 * self.sample_rate)
        if total_ms >= self.max_utterance_seconds * 1000:
            return self._finish() if self._speech_ms >= self.min_speech_ms else self.discard()
        if self._silence_ms >= self.end_silence_ms:
            return self._finish() if self._speech_ms >= self.min_speech_ms else self.discard()
        if total_ms > self.hard_utterance_seconds * 1000:
            return self.discard()
        return None

    def discard(self) -> None:
        self._utterance.clear()
        self._preroll.clear()
        self._active = False
        self._speech_ms = 0.0
        self._silence_ms = 0.0
        self.vad.reset()
        return None

    def _finish(self) -> bytes:
        audio = bytes(self._utterance)
        self.discard()
        return audio

    def _trim_preroll(self) -> None:
        maximum = self.preroll_ms * self.sample_rate * 2 / 1000
        while sum(len(chunk) for chunk in self._preroll) > maximum:
            self._preroll.popleft()


class FasterWhisperSpeechToText:
    """faster-whisper constrained to an already-downloaded local directory."""

    def __init__(self, model_path: Path, *, device: str = "cpu", compute_type: str = "int8") -> None:
        self.model_path = model_path
        self.device = device
        self.compute_type = compute_type
        self._model: object | None = None

    async def transcribe(self, audio: bytes) -> VoiceTranscript:
        if not audio:
            return VoiceTranscript("", True, None)
        return await asyncio.to_thread(self._transcribe, audio)

    def _transcribe(self, audio: bytes) -> VoiceTranscript:
        if self._model is None:
            self._load()
        import numpy as np

        samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        segments, info = self._model.transcribe(  # type: ignore[union-attr]
            samples,
            beam_size=2,
            condition_on_previous_text=False,
            vad_filter=False,
        )
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())[:4000]
        return VoiceTranscript(text, True, getattr(info, "language", None))

    def _load(self) -> None:
        if not self.model_path.is_dir():
            raise FileNotFoundError("local faster-whisper model directory is missing")
        from faster_whisper import WhisperModel

        self._model = WhisperModel(
            str(self.model_path),
            device=self.device,
            compute_type=self.compute_type,
            local_files_only=True,
        )


class PiperTextToSpeech:
    """Local Piper synthesis returning PCM only; playback is a separate boundary."""

    def __init__(self, english_model_path: Path, arabic_model_path: Path) -> None:
        self.english_model_path = english_model_path
        self.arabic_model_path = arabic_model_path
        self._voices: dict[str, object] = {}
        self.sample_rate = 16_000

    async def synthesize(self, text: str) -> bytes:
        return await asyncio.to_thread(self._synthesize, text[:1200])

    def _synthesize(self, text: str) -> bytes:
        language = "ar" if _contains_arabic(text) else "en"
        voice = self._voice(language)
        chunks = list(voice.synthesize(text))
        if chunks:
            self.sample_rate = int(chunks[0].sample_rate)
        return b"".join(chunk.audio_int16_bytes for chunk in chunks)

    def _voice(self, language: str) -> object:
        if language not in self._voices:
            from piper import PiperVoice

            model_path = self.arabic_model_path if language == "ar" else self.english_model_path
            if not model_path.is_file():
                raise FileNotFoundError("local Piper voice model is missing")
            self._voices[language] = PiperVoice.load(str(model_path))
        return self._voices[language]


def _contains_arabic(value: str) -> bool:
    return any("\u0600" <= character <= "\u06ff" for character in value)
