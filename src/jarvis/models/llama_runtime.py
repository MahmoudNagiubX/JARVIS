"""Bounded, product-owned lifecycle for an external llama.cpp server."""

from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from ..config import default_llama_cpp_threads, validate_loopback_http_origin


class LlamaRuntimeState(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    PROCESS_RUNNING = "process_running"
    READY = "ready"
    ATTACHED = "attached"
    UNAVAILABLE = "unavailable"
    PORT_CONFLICT = "port_conflict"


@dataclass(frozen=True, slots=True)
class LlamaCppRuntimeConfig:
    executable_path: Path
    model_path: Path
    endpoint: str
    model_alias: str = "jarvis-local-qwen"
    context_size: int = 4096
    threads: int = field(default_factory=default_llama_cpp_threads)
    gpu_layers: int | None = None
    ready_timeout_seconds: float = 30.0

    @classmethod
    def from_config(cls, config: Any, *, repository_root: Path | None = None) -> "LlamaCppRuntimeConfig":
        if config.llama_cpp_server_path is None or config.llama_cpp_model_path is None:
            raise ValueError("llama_cpp_runtime_not_configured")
        runtime = cls(
            Path(config.llama_cpp_server_path).expanduser(),
            Path(config.llama_cpp_model_path).expanduser(),
            config.ollama_base_url,
            config.primary_model,
            config.llama_cpp_context_size,
            config.llama_cpp_threads,
            config.llama_cpp_gpu_layers,
        )
        runtime.validate(repository_root=repository_root)
        return runtime

    def validate(self, *, repository_root: Path | None = None) -> None:
        executable = self.executable_path.expanduser().resolve(strict=False)
        model = self.model_path.expanduser().resolve(strict=False)
        root = (repository_root or Path.cwd()).expanduser().resolve(strict=False)
        if model == root or root in model.parents:
            raise ValueError("llama_cpp_model_must_be_external")
        if not executable.is_file():
            raise ValueError("llama_cpp_runtime_not_found")
        if model.suffix.casefold() != ".gguf":
            raise ValueError("llama_cpp_invalid_model")
        if not model.is_file():
            raise ValueError("llama_cpp_model_not_found")
        validate_loopback_http_origin(self.endpoint)
        if not 1024 <= self.context_size <= 32768:
            raise ValueError("llama_cpp_context_out_of_bounds")
        logical_cpus = os.cpu_count() or 1
        if not 1 <= self.threads <= logical_cpus:
            raise ValueError("llama_cpp_threads_out_of_bounds")
        if self.gpu_layers is not None and not -1 <= self.gpu_layers <= 256:
            raise ValueError("llama_cpp_gpu_layers_out_of_bounds")
        if not 1.0 <= self.ready_timeout_seconds <= 180.0:
            raise ValueError("llama_cpp_readiness_timeout_out_of_bounds")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@+\-]{0,99}", self.model_alias):
            raise ValueError("llama_cpp_model_alias_invalid")


@dataclass(frozen=True, slots=True)
class LlamaRuntimeStatus:
    state: LlamaRuntimeState
    provider: str
    ready: bool
    model_alias: str
    owned: bool
    reason: str
    pid: int | None = None
    observed_at: datetime | None = None


PopenFactory = Callable[..., subprocess.Popen[Any]]
UrlOpen = Callable[..., Any]


class LlamaCppRuntimeSupervisor:
    """Start, observe, and stop only the llama-server process JARVIS owns."""

    def __init__(
        self,
        config: LlamaCppRuntimeConfig,
        *,
        popen_factory: PopenFactory = subprocess.Popen,
        urlopen: UrlOpen = urllib.request.urlopen,
        sleep: Callable[[float], Any] = asyncio.sleep,
    ) -> None:
        self.config = config
        self._popen_factory = popen_factory
        self._urlopen = urlopen
        self._sleep = sleep
        self._process: subprocess.Popen[Any] | None = None
        self._owned = False
        self._attached = False
        self._status = LlamaRuntimeStatus(
            LlamaRuntimeState.STOPPED,
            "llama_cpp",
            False,
            config.model_alias,
            False,
            "not_started",
        )

    @property
    def status(self) -> LlamaRuntimeStatus:
        return self._status

    @property
    def command(self) -> tuple[str, ...]:
        self.config.validate()
        host, port = validate_loopback_http_origin(self.config.endpoint)
        command = [
            str(self.config.executable_path.expanduser().resolve(strict=False)),
            "--model",
            str(self.config.model_path.expanduser().resolve(strict=False)),
            "--host",
            host,
            "--port",
            str(port),
            "--ctx-size",
            str(self.config.context_size),
            "--threads",
            str(self.config.threads),
            "--no-webui",
            "--alias",
            self.config.model_alias,
        ]
        if self.config.gpu_layers is not None:
            command.extend(("--n-gpu-layers", str(self.config.gpu_layers)))
        return tuple(command)

    async def start(self) -> LlamaRuntimeStatus:
        self.config.validate()
        if self._owned and self._process is not None and self._process.poll() is None:
            return await self._refresh_status()
        if self._attached:
            return await self._refresh_status()
        if await asyncio.to_thread(self._port_is_occupied):
            compatible, ready, reason = await asyncio.to_thread(self._probe_compatibility)
            if compatible:
                if reason == "model_mismatch":
                    self._set_status(LlamaRuntimeState.PORT_CONFLICT, False, reason)
                    return self._status
                self._attached = True
                self._owned = False
                self._set_status(LlamaRuntimeState.ATTACHED, ready, "attached_ready" if ready else reason)
                return self._status
            self._set_status(LlamaRuntimeState.PORT_CONFLICT, False, "incompatible_listener")
            return self._status
        self._set_status(LlamaRuntimeState.STARTING, False, "starting")
        try:
            self._process = self._popen_factory(
                list(self.command),
                shell=False,
                cwd=str(self.config.executable_path.expanduser().resolve(strict=False).parent),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, ValueError):
            self._set_status(LlamaRuntimeState.UNAVAILABLE, False, "start_failed")
            return self._status
        self._owned = True
        deadline = asyncio.get_running_loop().time() + self.config.ready_timeout_seconds
        self._set_status(LlamaRuntimeState.PROCESS_RUNNING, False, "process_running")
        while asyncio.get_running_loop().time() < deadline:
            if self._process.poll() is not None:
                self._set_status(LlamaRuntimeState.UNAVAILABLE, False, "process_exited")
                self._process = None
                self._owned = False
                return self._status
            compatible, ready, _reason = await asyncio.to_thread(self._probe_compatibility)
            if compatible and ready:
                self._set_status(LlamaRuntimeState.READY, True, "ready")
                return self._status
            await self._sleep(0.2)
        await self._stop_owned()
        self._set_status(LlamaRuntimeState.UNAVAILABLE, False, "readiness_timeout")
        return self._status

    async def health(self) -> LlamaRuntimeStatus:
        compatible, ready, reason = await asyncio.to_thread(self._probe_compatibility)
        if ready:
            state = LlamaRuntimeState.ATTACHED if self._attached else LlamaRuntimeState.READY
            self._set_status(state, True, "ready")
        elif self._owned and self._process is not None and self._process.poll() is None:
            self._set_status(LlamaRuntimeState.PROCESS_RUNNING, False, reason)
        elif compatible and self._attached:
            self._set_status(LlamaRuntimeState.ATTACHED, False, reason)
        else:
            self._set_status(LlamaRuntimeState.UNAVAILABLE, False, "unavailable")
        return self._status

    async def restart(self) -> LlamaRuntimeStatus:
        if self._attached and not self._owned:
            raise RuntimeError("llama_cpp_attached_not_owned")
        await self.stop()
        return await self.start()

    async def stop(self) -> LlamaRuntimeStatus:
        if self._owned:
            await self._stop_owned()
        self._process = None
        self._owned = False
        self._attached = False
        self._set_status(LlamaRuntimeState.STOPPED, False, "stopped")
        return self._status

    async def close(self) -> None:
        await self.stop()

    def _set_status(self, state: LlamaRuntimeState, ready: bool, reason: str) -> None:
        pid = self._process.pid if self._owned and self._process is not None else None
        self._status = LlamaRuntimeStatus(
            state,
            "llama_cpp",
            ready,
            self.config.model_alias,
            self._owned,
            reason,
            pid,
            datetime.now(UTC),
        )

    async def _refresh_status(self) -> LlamaRuntimeStatus:
        compatible, ready, reason = await asyncio.to_thread(self._probe_compatibility)
        if ready:
            self._set_status(LlamaRuntimeState.READY if self._owned else LlamaRuntimeState.ATTACHED, True, "ready")
        elif compatible:
            self._set_status(LlamaRuntimeState.PROCESS_RUNNING if self._owned else LlamaRuntimeState.ATTACHED, False, reason)
        else:
            self._set_status(LlamaRuntimeState.UNAVAILABLE, False, "unavailable")
        return self._status

    async def _stop_owned(self) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            return
        await asyncio.to_thread(self._terminate_process, process)

    @staticmethod
    def _terminate_process(process: subprocess.Popen[Any]) -> None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def _port_is_occupied(self) -> bool:
        host, port = validate_loopback_http_origin(self.config.endpoint)
        try:
            with socket.create_connection((host, port), timeout=0.25):
                return True
        except OSError:
            return False

    def _probe_compatibility(self) -> tuple[bool, bool, str]:
        health_status, health_body = self._get("/health")
        health_valid = health_status in {200, 503} and self._health_body_valid(health_body)
        models_status, models_body = self._get("/v1/models")
        models_valid, expected_model = self._models_valid(models_status, models_body)
        if expected_model:
            if health_status == 200 and health_valid:
                return True, True, "ready"
            return True, False, "model_loading"
        if health_valid or models_valid:
            return True, False, "model_mismatch"
        return False, False, "unavailable"

    @staticmethod
    def _health_body_valid(body: bytes) -> bool:
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        return isinstance(decoded, dict) and isinstance(decoded.get("status"), str)

    def _models_valid(self, status: int | None, body: bytes) -> tuple[bool, bool]:
        if status != 200:
            return False, False
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False, False
        data = decoded.get("data") if isinstance(decoded, dict) else None
        if not isinstance(data, list):
            return False, False
        aliases = {
            item.get("id")
            for item in data
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        return True, self.config.model_alias in aliases

    def _get(self, path: str) -> tuple[int | None, bytes]:
        parsed = urlsplit(self.config.endpoint)
        url = f"{parsed.scheme}://{parsed.netloc}{path}"
        request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
        try:
            with self._urlopen(request, timeout=2.0) as response:
                body = response.read(65537)
                if len(body) > 65536:
                    return None, b""
                return int(getattr(response, "status", 200)), body
        except urllib.error.HTTPError as exc:
            try:
                return int(exc.code), exc.read(65537)[:65536]
            except OSError:
                return int(exc.code), b""
            finally:
                exc.close()
        except (urllib.error.URLError, TimeoutError, OSError):
            return None, b""
