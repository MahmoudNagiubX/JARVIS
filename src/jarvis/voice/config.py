"""Explicit, disabled-by-default configuration for local physical voice."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


_TRUE = {"true", "1", "yes", "on"}
_FALSE = {"false", "0", "no", "off"}


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name, str(default).lower()).strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ValueError(f"{name} must be boolean")


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)).strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


@dataclass(frozen=True, slots=True)
class VoiceDeviceSelector:
    """Stable device identity: host API, endpoint name, and direction."""

    host_api: str
    name: str

    def validate(self, direction: str) -> None:
        if direction not in {"input", "output"}:
            raise ValueError("voice device direction must be input or output")
        if not self.host_api.strip() or not self.name.strip():
            raise ValueError(f"voice {direction} device selector requires host API and name")


@dataclass(frozen=True, slots=True)
class VoiceRuntimeConfig:
    """Physical voice settings; never loaded by normal runtime bootstrap."""

    enabled: bool = False
    input_device: VoiceDeviceSelector | None = None
    output_device: VoiceDeviceSelector | None = None
    wake_model_path: Path | None = None
    wake_threshold: float = 0.5
    vad_model_path: Path | None = None
    vad_threshold: float = 0.5
    vad_end_silence_ms: int = 800
    stt_model_path: Path | None = None
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"
    tts_engine: str = "piper"
    tts_en_model_path: Path | None = None
    tts_ar_model_path: Path | None = None
    follow_up_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "VoiceRuntimeConfig":
        enabled = _bool("JARVIS_VOICE_ENABLED", False)
        input_host = os.getenv("JARVIS_VOICE_INPUT_HOST_API", "").strip()
        input_name = os.getenv("JARVIS_VOICE_INPUT_DEVICE", "").strip()
        output_host = os.getenv("JARVIS_VOICE_OUTPUT_HOST_API", "").strip()
        output_name = os.getenv("JARVIS_VOICE_OUTPUT_DEVICE", "").strip()
        return cls(
            enabled=enabled,
            input_device=VoiceDeviceSelector(input_host, input_name) if input_host or input_name else None,
            output_device=VoiceDeviceSelector(output_host, output_name) if output_host or output_name else None,
            wake_model_path=_path("JARVIS_VOICE_WAKE_MODEL_PATH"),
            wake_threshold=_float("JARVIS_VOICE_WAKE_THRESHOLD", 0.5),
            vad_model_path=_path("JARVIS_VOICE_VAD_MODEL_PATH"),
            vad_threshold=_float("JARVIS_VOICE_VAD_THRESHOLD", 0.5),
            vad_end_silence_ms=_int("JARVIS_VOICE_VAD_END_SILENCE_MS", 800),
            stt_model_path=_path("JARVIS_VOICE_STT_MODEL_PATH"),
            stt_device=os.getenv("JARVIS_VOICE_STT_DEVICE", "cpu").strip().lower(),
            stt_compute_type=os.getenv("JARVIS_VOICE_STT_COMPUTE_TYPE", "int8").strip().lower(),
            tts_engine=os.getenv("JARVIS_VOICE_TTS_ENGINE", "piper").strip().lower(),
            tts_en_model_path=_path("JARVIS_VOICE_TTS_EN_MODEL_PATH"),
            tts_ar_model_path=_path("JARVIS_VOICE_TTS_AR_MODEL_PATH"),
            follow_up_seconds=_float("JARVIS_VOICE_FOLLOW_UP_SECONDS", 30.0),
        ).validated()

    def validated(self) -> "VoiceRuntimeConfig":
        if not 0.05 <= self.wake_threshold <= 0.99:
            raise ValueError("JARVIS_VOICE_WAKE_THRESHOLD must be between 0.05 and 0.99")
        if not 0.05 <= self.vad_threshold <= 0.99:
            raise ValueError("JARVIS_VOICE_VAD_THRESHOLD must be between 0.05 and 0.99")
        if not 600 <= self.vad_end_silence_ms <= 900:
            raise ValueError("JARVIS_VOICE_VAD_END_SILENCE_MS must be between 600 and 900")
        if not 1 <= self.follow_up_seconds <= 120:
            raise ValueError("JARVIS_VOICE_FOLLOW_UP_SECONDS must be between 1 and 120")
        if self.stt_device not in {"cpu", "cuda"}:
            raise ValueError("JARVIS_VOICE_STT_DEVICE must be cpu or cuda")
        if self.tts_engine != "piper":
            raise ValueError("JARVIS_VOICE_TTS_ENGINE must be piper")
        if not self.enabled:
            return self
        if self.input_device is None or self.output_device is None:
            raise ValueError("enabled voice requires input and output device selectors")
        self.input_device.validate("input")
        self.output_device.validate("output")
        required_paths = {
            "wake": self.wake_model_path,
            "vad": self.vad_model_path,
            "stt": self.stt_model_path,
            "English TTS": self.tts_en_model_path,
            "Arabic TTS": self.tts_ar_model_path,
        }
        missing = [name for name, path in required_paths.items() if path is None or not path.exists()]
        if missing:
            raise ValueError(f"enabled voice requires existing local assets: {', '.join(missing)}")
        return self


def _path(name: str) -> Path | None:
    value = os.getenv(name, "").strip()
    return Path(value) if value else None
