"""Current-user secret storage for the product-managed device credential."""

from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wintypes
import os
from pathlib import Path
from typing import Protocol


class LocalSecretStore(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str) -> None: ...
    def delete(self, key: str) -> None: ...


class SecretStoreUnavailable(RuntimeError):
    """The host cannot provide a current-user protected secret store."""


class MemorySecretStore:
    """Explicit test/in-process store; never used as the Windows product default."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        if not key or not value:
            raise ValueError("secret key and value are required")
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


class WindowsCredentialManagerStore:
    """Small ctypes wrapper over CredMan generic current-user credentials."""

    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2

    class _Credential(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    def __init__(self, namespace: str = "JARVIS") -> None:
        if os.name != "nt":
            raise SecretStoreUnavailable("Windows Credential Manager is unavailable")
        self._advapi = ctypes.WinDLL("Advapi32.dll")
        self._kernel = ctypes.WinDLL("Kernel32.dll")
        self._namespace = namespace
        self._advapi.CredReadW.argtypes = [wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
        self._advapi.CredReadW.restype = wintypes.BOOL
        self._advapi.CredWriteW.argtypes = [ctypes.POINTER(self._Credential), wintypes.DWORD]
        self._advapi.CredWriteW.restype = wintypes.BOOL
        self._advapi.CredDeleteW.argtypes = [wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
        self._advapi.CredDeleteW.restype = wintypes.BOOL
        self._advapi.CredFree.argtypes = [ctypes.c_void_p]
        self._advapi.CredFree.restype = None

    def _target(self, key: str) -> str:
        if not key or any(char in key for char in "\\\x00"):
            raise ValueError("invalid secret key")
        return f"{self._namespace}\\{key}"

    def get(self, key: str) -> str | None:
        pointer = ctypes.c_void_p()
        if not self._advapi.CredReadW(self._target(key), self.CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
            return None
        try:
            credential = ctypes.cast(pointer, ctypes.POINTER(self._Credential)).contents
            blob = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
            return blob.decode("utf-8")
        except (UnicodeDecodeError, ValueError):
            return None
        finally:
            self._advapi.CredFree(pointer)

    def set(self, key: str, value: str) -> None:
        if not value:
            raise ValueError("secret value cannot be empty")
        target = self._target(key)
        blob = value.encode("utf-8")
        buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        credential = self._Credential(
            0, self.CRED_TYPE_GENERIC, target, None, wintypes.FILETIME(), len(blob), buffer,
            self.CRED_PERSIST_LOCAL_MACHINE, 0, None, None, "JARVIS",
        )
        if not self._advapi.CredWriteW(ctypes.byref(credential), 0):
            raise SecretStoreUnavailable("Windows Credential Manager rejected the credential")

    def delete(self, key: str) -> None:
        self._advapi.CredDeleteW(self._target(key), self.CRED_TYPE_GENERIC, 0)


class DpapiSecretStore:
    """DPAPI CurrentUser fallback with an encrypted, bounded local blob."""

    def __init__(self, root: Path | None = None) -> None:
        if os.name != "nt":
            raise SecretStoreUnavailable("DPAPI is unavailable")
        self.root = Path(root) if root else Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "JARVIS" / "secrets"
        self.root.mkdir(parents=True, exist_ok=True)
        self._crypt32 = ctypes.WinDLL("Crypt32.dll")
        self._kernel = ctypes.WinDLL("Kernel32.dll")

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    def _path(self, key: str) -> Path:
        if not key or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in key):
            raise ValueError("invalid secret key")
        return self.root / f"{key}.dpapi"

    def set(self, key: str, value: str) -> None:
        if not value:
            raise ValueError("secret value cannot be empty")
        raw = value.encode("utf-8")
        source = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
        protected = self._Blob()
        if not self._crypt32.CryptProtectData(ctypes.byref(self._Blob(len(raw), source)), "JARVIS", None, None, None, 0, ctypes.byref(protected)):
            raise SecretStoreUnavailable("DPAPI protection failed")
        try:
            payload = ctypes.string_at(protected.pbData, protected.cbData)
            self._path(key).write_bytes(base64.b64encode(payload))
        finally:
            self._kernel.LocalFree(protected.pbData)

    def get(self, key: str) -> str | None:
        try:
            encoded = self._path(key).read_bytes()
            encrypted = base64.b64decode(encoded, validate=True)
        except (FileNotFoundError, OSError, ValueError):
            return None
        source = (ctypes.c_ubyte * len(encrypted)).from_buffer_copy(encrypted)
        plain = self._Blob()
        if not self._crypt32.CryptUnprotectData(ctypes.byref(self._Blob(len(encrypted), source)), None, None, None, None, 0, ctypes.byref(plain)):
            return None
        try:
            return ctypes.string_at(plain.pbData, plain.cbData).decode("utf-8")
        except UnicodeDecodeError:
            return None
        finally:
            self._kernel.LocalFree(plain.pbData)

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink()
        except FileNotFoundError:
            pass


def platform_secret_store(root: Path | None = None) -> LocalSecretStore:
    """Prefer CredMan and use DPAPI only when CredMan cannot be initialized."""

    if os.name != "nt":
        raise SecretStoreUnavailable("the product secret store requires Windows")
    try:
        return WindowsCredentialManagerStore()
    except (OSError, AttributeError, SecretStoreUnavailable):
        return DpapiSecretStore(root)
