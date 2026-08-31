"""Versioned, non-secret configuration for the installed desktop product."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

from ..config import JarvisConfig, validate_loopback_http_origin
from ..voice.config import VoiceDeviceSelector, VoiceRuntimeConfig


class ProductConfigError(ValueError):
    """A desktop settings file is missing, invalid, or unsafe."""


_FORBIDDEN_KEYS = {
    "credential", "raw_credential", "secret", "password", "token",
    "transcript", "transcripts", "audio", "pcm", "tool_output",
    "approval_payload", "approval_payloads",
}


def product_config_path(root: Path | None = None) -> Path:
    """Return the user-scoped settings path without creating it."""

    if root is not None:
        return Path(root).expanduser() / "config" / "settings.json"
    local_app_data = os.getenv("LOCALAPPDATA", "").strip()
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "JARVIS" / "config" / "settings.json"


def _selector(value: Mapping[str, Any] | None, direction: str) -> VoiceDeviceSelector | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ProductConfigError(f"{direction}_device must be an object")
    host_api = value.get("host_api")
    name = value.get("name")
    persisted_direction = value.get("direction", direction)
    if not isinstance(host_api, str) or not isinstance(name, str) or persisted_direction != direction:
        raise ProductConfigError(f"invalid {direction} device selector")
    result = VoiceDeviceSelector(host_api.strip(), name.strip())
    result.validate(direction)
    return result


def _path(value: Any, name: str) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ProductConfigError(f"{name} must be a non-empty path")
    return Path(value).expanduser()


@dataclass(frozen=True, slots=True)
class DesktopProductConfig:
    """Safe settings stored by JARVIS under the current user's profile."""

    config_version: int = 1
    identity_id: str | None = None
    device_id: str | None = None
    input_device: VoiceDeviceSelector | None = None
    output_device: VoiceDeviceSelector | None = None
    voice_enabled: bool = True
    wake_threshold: float = 0.5
    vad_threshold: float = 0.5
    vad_end_silence_ms: int = 800
    follow_up_seconds: float = 30.0
    wake_command_timeout_seconds: float = 5.0
    wake_model_path: Path | None = None
    vad_model_path: Path | None = None
    stt_model_path: Path | None = None
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"
    tts_engine: str = "piper"
    tts_en_model_path: Path | None = None
    tts_ar_model_path: Path | None = None
    llama_cpp_server_path: Path | None = None
    llama_cpp_model_path: Path | None = None
    model_endpoint: str = "http://127.0.0.1:11434"
    model_alias: str = "jarvis-local-qwen"
    model_context_size: int = 4096
    model_threads: int = 8
    model_gpu_layers: int | None = None
    autostart: bool = True
    ui_preference: str = "hud"
    last_validation: dict[str, str] = field(default_factory=dict)

    def validated(self) -> "DesktopProductConfig":
        if self.config_version != 1:
            raise ProductConfigError("unsupported desktop config version")
        for name, value in (("identity_id", self.identity_id), ("device_id", self.device_id)):
            if value is not None and (not value.strip() or len(value) > 200):
                raise ProductConfigError(f"{name} is invalid")
        if not 0.05 <= self.wake_threshold <= 0.99:
            raise ProductConfigError("wake threshold is outside supported bounds")
        if not 0.05 <= self.vad_threshold <= 0.99:
            raise ProductConfigError("VAD threshold is outside supported bounds")
        if not 600 <= self.vad_end_silence_ms <= 900:
            raise ProductConfigError("VAD silence is outside supported bounds")
        if not 1 <= self.follow_up_seconds <= 120:
            raise ProductConfigError("follow-up duration is outside supported bounds")
        if not 1 <= self.wake_command_timeout_seconds <= 15:
            raise ProductConfigError("wake timeout is outside supported bounds")
        if self.stt_device not in {"cpu", "cuda"} or self.tts_engine != "piper":
            raise ProductConfigError("unsupported speech runtime setting")
        if self.input_device is not None:
            self.input_device.validate("input")
        if self.output_device is not None:
            self.output_device.validate("output")
        if not self.model_endpoint or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@+\-]{0,99}", self.model_alias):
            raise ProductConfigError("model endpoint or alias is invalid")
        try:
            validate_loopback_http_origin(self.model_endpoint)
        except ValueError as exc:
            raise ProductConfigError("model endpoint must remain loopback-only") from exc
        if not 1024 <= self.model_context_size <= 32768:
            raise ProductConfigError("model context is outside supported bounds")
        if not 1 <= self.model_threads <= (os.cpu_count() or 1):
            raise ProductConfigError("model threads are outside supported bounds")
        if self.model_gpu_layers is not None and not -1 <= self.model_gpu_layers <= 256:
            raise ProductConfigError("model GPU layers are outside supported bounds")
        if self.ui_preference not in {"hud", "native"}:
            raise ProductConfigError("unsupported UI preference")
        if not isinstance(self.last_validation, dict) or any(not isinstance(key, str) or not isinstance(value, str) for key, value in self.last_validation.items()):
            raise ProductConfigError("last_validation must be an object")
        return self

    def to_dict(self) -> dict[str, Any]:
        self.validated()
        values: dict[str, Any] = {
            "config_version": self.config_version,
            "identity_id": self.identity_id,
            "device_id": self.device_id,
            "audio_input_selector": _selector_dict(self.input_device, "input"),
            "audio_output_selector": _selector_dict(self.output_device, "output"),
            "voice_enabled": self.voice_enabled,
            "wake_threshold": self.wake_threshold,
            "vad_threshold": self.vad_threshold,
            "vad_end_silence_ms": self.vad_end_silence_ms,
            "follow_up_seconds": self.follow_up_seconds,
            "wake_command_timeout_seconds": self.wake_command_timeout_seconds,
            "speech_assets": {
                "wake_model_path": _path_text(self.wake_model_path),
                "vad_model_path": _path_text(self.vad_model_path),
                "stt_model_path": _path_text(self.stt_model_path),
                "tts_en_model_path": _path_text(self.tts_en_model_path),
                "tts_ar_model_path": _path_text(self.tts_ar_model_path),
            },
            "stt_device": self.stt_device,
            "stt_compute_type": self.stt_compute_type,
            "tts_engine": self.tts_engine,
            "llama_cpp_executable_path": _path_text(self.llama_cpp_server_path),
            "qwen_gguf_path": _path_text(self.llama_cpp_model_path),
            "model_endpoint": self.model_endpoint,
            "model_alias": self.model_alias,
            "model_context_size": self.model_context_size,
            "model_threads": self.model_threads,
            "model_gpu_layers": self.model_gpu_layers,
            "autostart": self.autostart,
            "ui_preference": self.ui_preference,
            "last_validation": dict(self.last_validation),
        }
        _assert_safe_settings(values)
        return values

    @classmethod
    def from_dict(cls, values: Mapping[str, Any]) -> "DesktopProductConfig":
        if not isinstance(values, Mapping):
            raise ProductConfigError("desktop settings must be an object")
        _assert_safe_settings(values)
        assets = values.get("speech_assets", {})
        if not isinstance(assets, Mapping):
            raise ProductConfigError("speech_assets must be an object")
        result = cls(
            config_version=int(values.get("config_version", 0)),
            identity_id=_optional_text(values.get("identity_id"), "identity_id"),
            device_id=_optional_text(values.get("device_id"), "device_id"),
            input_device=_selector(values.get("audio_input_selector"), "input"),
            output_device=_selector(values.get("audio_output_selector"), "output"),
            voice_enabled=_bool_value(values.get("voice_enabled", True), "voice_enabled"),
            wake_threshold=float(values.get("wake_threshold", 0.5)),
            vad_threshold=float(values.get("vad_threshold", 0.5)),
            vad_end_silence_ms=int(values.get("vad_end_silence_ms", 800)),
            follow_up_seconds=float(values.get("follow_up_seconds", 30.0)),
            wake_command_timeout_seconds=float(values.get("wake_command_timeout_seconds", 5.0)),
            wake_model_path=_path(assets.get("wake_model_path"), "wake_model_path"),
            vad_model_path=_path(assets.get("vad_model_path"), "vad_model_path"),
            stt_model_path=_path(assets.get("stt_model_path"), "stt_model_path"),
            stt_device=str(values.get("stt_device", "cpu")).strip().lower(),
            stt_compute_type=str(values.get("stt_compute_type", "int8")).strip().lower(),
            tts_engine=str(values.get("tts_engine", "piper")).strip().lower(),
            tts_en_model_path=_path(assets.get("tts_en_model_path"), "tts_en_model_path"),
            tts_ar_model_path=_path(assets.get("tts_ar_model_path"), "tts_ar_model_path"),
            llama_cpp_server_path=_path(values.get("llama_cpp_executable_path"), "llama_cpp_executable_path"),
            llama_cpp_model_path=_path(values.get("qwen_gguf_path"), "qwen_gguf_path"),
            model_endpoint=str(values.get("model_endpoint", "http://127.0.0.1:11434")).strip(),
            model_alias=str(values.get("model_alias", "jarvis-local-qwen")).strip(),
            model_context_size=int(values.get("model_context_size", 4096)),
            model_threads=int(values.get("model_threads", 8)),
            model_gpu_layers=(int(values["model_gpu_layers"]) if values.get("model_gpu_layers") is not None else None),
            autostart=_bool_value(values.get("autostart", True), "autostart"),
            ui_preference=str(values.get("ui_preference", "hud")).strip().lower(),
            last_validation=_validation_values(values.get("last_validation", {})),
        )
        return result.validated()

    @classmethod
    def load(cls, path: Path | None = None) -> "DesktopProductConfig":
        target = path or product_config_path()
        try:
            with target.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except FileNotFoundError as exc:
            raise ProductConfigError("desktop settings have not been created") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise ProductConfigError("desktop settings could not be read") from exc
        return cls.from_dict(raw)

    def save(self, path: Path | None = None) -> Path:
        target = path or product_config_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        descriptor, temporary = tempfile.mkstemp(prefix="settings.", suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
        return target

    def runtime_config(self, base: JarvisConfig) -> JarvisConfig:
        """Apply only safe product model settings to the existing runtime config."""

        provider = base.model_provider
        if self.llama_cpp_server_path is not None and self.llama_cpp_model_path is not None:
            provider = "llama_cpp"
        return replace(
            base,
            model_provider=provider,
            primary_model=self.model_alias,
            ollama_base_url=self.model_endpoint,
            llama_cpp_server_path=str(self.llama_cpp_server_path) if self.llama_cpp_server_path else base.llama_cpp_server_path,
            llama_cpp_model_path=str(self.llama_cpp_model_path) if self.llama_cpp_model_path else base.llama_cpp_model_path,
            llama_cpp_context_size=self.model_context_size,
            llama_cpp_threads=self.model_threads,
            llama_cpp_gpu_layers=self.model_gpu_layers,
            local_model_autostart=bool(self.autostart and provider in {"llama_cpp", "gguf"}),
            voice_input_adapter="sounddevice" if self.voice_enabled else base.voice_input_adapter,
            voice_output_adapter="sounddevice" if self.voice_enabled else base.voice_output_adapter,
        )

    def voice_config(self) -> VoiceRuntimeConfig:
        return VoiceRuntimeConfig(
            enabled=self.voice_enabled,
            input_device=self.input_device,
            output_device=self.output_device,
            wake_model_path=self.wake_model_path,
            wake_threshold=self.wake_threshold,
            vad_model_path=self.vad_model_path,
            vad_threshold=self.vad_threshold,
            vad_end_silence_ms=self.vad_end_silence_ms,
            stt_model_path=self.stt_model_path,
            stt_device=self.stt_device,
            stt_compute_type=self.stt_compute_type,
            tts_engine=self.tts_engine,
            tts_en_model_path=self.tts_en_model_path,
            tts_ar_model_path=self.tts_ar_model_path,
            follow_up_seconds=self.follow_up_seconds,
            wake_command_timeout_seconds=self.wake_command_timeout_seconds,
        )


def _path_text(value: Path | None) -> str | None:
    return str(value) if value is not None else None


def _selector_dict(value: VoiceDeviceSelector | None, direction: str) -> dict[str, str] | None:
    if value is None:
        return None
    return {"host_api": value.host_api, "name": value.name, "direction": direction}


def _optional_text(value: Any, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProductConfigError(f"{name} must be text")
    return value


def _bool_value(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ProductConfigError(f"{name} must be boolean")
    return value


def _validation_values(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ProductConfigError("last_validation must be an object")
    if any(not isinstance(key, str) or not isinstance(child, str) for key, child in value.items()):
        raise ProductConfigError("last_validation values must be text")
    return dict(value)


def _assert_safe_settings(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if normalized in _FORBIDDEN_KEYS or any(marker in normalized for marker in ("credential", "transcript", "raw_audio", "secret")):
                raise ProductConfigError("forbidden secret or private runtime field in desktop settings")
            _assert_safe_settings(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _assert_safe_settings(child)
