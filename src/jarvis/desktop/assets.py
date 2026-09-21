"""Local speech-asset discovery and validation without implicit downloads."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..voice.config import VoiceRuntimeConfig


class AssetProvisioningUnavailable(RuntimeError):
    """No approved, product-owned asset source was supplied."""


class AssetProvisioningCancelled(RuntimeError):
    """The user cancelled a bounded asset provisioning operation."""


@dataclass(frozen=True, slots=True)
class VoiceAssetStatus:
    name: str
    path: Path | None
    ready: bool
    reason: str


@dataclass(frozen=True, slots=True)
class VoiceAssetSet:
    wake_model_path: Path | None
    vad_model_path: Path | None
    stt_model_path: Path | None
    tts_en_model_path: Path | None
    tts_ar_model_path: Path | None

    def statuses(self) -> tuple[VoiceAssetStatus, ...]:
        values = (
            ("wake", self.wake_model_path),
            ("vad", self.vad_model_path),
            ("stt", self.stt_model_path),
            ("english_tts", self.tts_en_model_path),
            ("arabic_tts", self.tts_ar_model_path),
        )
        return tuple(_status(name, path) for name, path in values)

    @property
    def ready(self) -> bool:
        return all(item.ready for item in self.statuses())

    def as_voice_config(self, base: VoiceRuntimeConfig) -> VoiceRuntimeConfig:
        return VoiceRuntimeConfig(
            enabled=base.enabled,
            input_device=base.input_device,
            output_device=base.output_device,
            wake_model_path=self.wake_model_path,
            wake_threshold=base.wake_threshold,
            vad_model_path=self.vad_model_path,
            vad_threshold=base.vad_threshold,
            vad_end_silence_ms=base.vad_end_silence_ms,
            stt_model_path=self.stt_model_path,
            stt_device=base.stt_device,
            stt_compute_type=base.stt_compute_type,
            tts_engine=base.tts_engine,
            tts_en_model_path=self.tts_en_model_path,
            tts_ar_model_path=self.tts_ar_model_path,
            follow_up_seconds=base.follow_up_seconds,
            wake_command_timeout_seconds=base.wake_command_timeout_seconds,
        )


class VoiceAssetManager:
    """Resolve explicitly configured assets, then conservative local names."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or _default_voice_root()

    def configured_or_discovered(self, config: VoiceRuntimeConfig) -> VoiceAssetSet:
        candidates = tuple(self.root.rglob("*")) if self.root.exists() else ()
        files = tuple(item for item in candidates if item.is_file())
        directories = tuple(item for item in candidates if item.is_dir())
        return VoiceAssetSet(
            _configured(config.wake_model_path, ("wake", "openwake", "hey_jarvis"), {".onnx"}) or _find(files, ("wake", "openwake", "hey_jarvis"), {".onnx"}),
            _configured(config.vad_model_path, ("silero", "vad"), {".onnx", ".jit"}) or _find(files, ("silero", "vad"), {".onnx", ".jit"}),
            _configured_stt(config.stt_model_path) or _find_stt(directories),
            _configured(config.tts_en_model_path, ("en", "english"), {".onnx"}) or _find(files, ("en", "english"), {".onnx"}),
            _configured(config.tts_ar_model_path, ("ar", "arabic"), {".onnx"}) or _find(files, ("ar", "arabic"), {".onnx"}),
        )

    def validate(self, config: VoiceRuntimeConfig) -> tuple[VoiceAssetStatus, ...]:
        return self.configured_or_discovered(config).statuses()

    def provision(
        self,
        provisioner: Callable[[Path, Callable[[str, float], None], Callable[[], bool]], None] | None = None,
        *,
        progress: Callable[[str, float], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> None:
        """Run only a caller-supplied approved provider; never auto-download here."""

        if provisioner is None:
            raise AssetProvisioningUnavailable("approved voice asset provisioning is not configured")
        self.root.mkdir(parents=True, exist_ok=True)
        progress = progress or (lambda _name, _value: None)
        cancelled = cancelled or (lambda: False)
        if cancelled():
            raise AssetProvisioningCancelled("voice asset provisioning cancelled")
        provisioner(self.root, progress, cancelled)


def _default_voice_root() -> Path:
    import os

    local = os.getenv("LOCALAPPDATA", "").strip()
    return (Path(local) if local else Path.home() / "AppData" / "Local") / "JARVIS" / "voice"


def _find(files: tuple[Path, ...], needles: tuple[str, ...], suffixes: set[str]) -> Path | None:
    for item in sorted(files, key=lambda value: str(value).casefold()):
        filename = item.name.casefold()
        if item.suffix.casefold() in suffixes and any(needle in filename for needle in needles):
            return item
    for item in sorted(files, key=lambda value: str(value).casefold()):
        lowered = str(item).casefold()
        if item.suffix.casefold() in suffixes and any(needle in lowered for needle in needles):
            return item
    return None


def _configured(path: Path | None, needles: tuple[str, ...], suffixes: set[str] | None) -> Path | None:
    if path is None or not path.exists():
        return None
    if suffixes is not None and path.is_file() and path.suffix.casefold() not in suffixes:
        return None
    if any(needle in path.name.casefold() for needle in needles):
        return path
    if path.is_dir() and any(needle in str(path).casefold() for needle in needles):
        return path
    return None


def _find_stt(directories: tuple[Path, ...]) -> Path | None:
    for item in sorted(directories, key=lambda value: str(value).casefold()):
        if _is_stt_model_directory(item) and any(token in item.name.casefold() for token in ("whisper", "faster-whisper", "stt")):
            return item
    return None


def _configured_stt(path: Path | None) -> Path | None:
    """Resolve a configured STT root to a loadable faster-whisper directory."""

    if path is None or not path.exists():
        return None
    if _is_stt_model_directory(path):
        return path
    if not path.is_dir():
        return None
    children = sorted((item for item in path.iterdir() if item.is_dir()), key=lambda value: str(value).casefold())
    for child in children:
        if _is_stt_model_directory(child) and any(token in child.name.casefold() for token in ("whisper", "faster-whisper", "stt")):
            return child
    return None


def _is_stt_model_directory(path: Path) -> bool:
    return path.is_dir() and (path / "config.json").is_file() and (path / "model.bin").is_file()


def _status(name: str, path: Path | None) -> VoiceAssetStatus:
    if path is None or not path.exists():
        return VoiceAssetStatus(name, path, False, "missing")
    if name == "wake":
        if path.is_file() and (path.parent / "melspectrogram.onnx").is_file() and (path.parent / "embedding_model.onnx").is_file():
            return VoiceAssetStatus(name, path, True, "ready")
        return VoiceAssetStatus(name, path, False, "wake_auxiliary_missing")
    if name == "stt":
        return VoiceAssetStatus(name, path, _is_stt_model_directory(path), "ready" if _is_stt_model_directory(path) else "stt_model_incomplete")
    if name in {"english_tts", "arabic_tts"}:
        sidecar = Path(str(path) + ".json")
        ready = path.is_file() and sidecar.is_file()
        return VoiceAssetStatus(name, path, ready, "ready" if ready else "tts_sidecar_missing")
    ready = path.is_file()
    return VoiceAssetStatus(name, path, ready, "ready" if ready else "invalid_file")
