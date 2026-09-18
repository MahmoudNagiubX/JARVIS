"""Browser executable and profile boundaries owned by JARVIS.

The profile policy is deliberately independent of Playwright.  It gives the
controller one small, testable place to reject normal browser profiles and to
resolve only the standard Brave installation candidates explicitly allowed by
Batch 10.
"""

from __future__ import annotations

import os
from pathlib import Path


class BrowserProfilePolicyError(ValueError):
    """A browser executable or user-data directory failed a local policy."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def standard_brave_executable_paths() -> tuple[Path, ...]:
    """Return only the three standard Windows Brave executable locations.

    This function computes exact candidates; it never searches a directory or
    enumerates the machine.
    """

    local_app_data = os.environ.get("LOCALAPPDATA")
    program_files = os.environ.get("PROGRAMFILES")
    program_files_x86 = os.environ.get("PROGRAMFILES(X86)")
    candidates = (
        Path(local_app_data) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe"
        if local_app_data
        else None,
        Path(program_files) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe"
        if program_files
        else None,
        Path(program_files_x86) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe"
        if program_files_x86
        else None,
    )
    return tuple(path for path in candidates if path is not None)


def validate_brave_executable_path(raw_path: str | Path | None) -> Path:
    """Validate an exact configured Brave path without broad discovery."""

    if raw_path is None or not str(raw_path).strip():
        raise BrowserProfilePolicyError("browser_executable_not_configured")
    try:
        resolved = Path(raw_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise BrowserProfilePolicyError("browser_executable_not_found") from exc
    if not resolved.is_file() or resolved.name.casefold() != "brave.exe":
        raise BrowserProfilePolicyError("browser_executable_invalid")
    allowed = {
        os.path.normcase(os.path.abspath(str(candidate)))
        for candidate in standard_brave_executable_paths()
    }
    if os.path.normcase(os.path.abspath(str(resolved))) not in allowed:
        raise BrowserProfilePolicyError("browser_executable_location_not_allowed")
    return resolved


def default_owner_profile_path() -> Path:
    """Return JARVIS's dedicated persistent-profile location."""

    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "JARVIS" / "Browser" / "OwnerPersistent"
    return Path.home() / ".jarvis" / "Browser" / "OwnerPersistent"


def _contains_path_sequence(parts: tuple[str, ...], sequence: tuple[str, ...]) -> bool:
    width = len(sequence)
    return any(parts[index : index + width] == sequence for index in range(len(parts) - width + 1))


class BrowserProfilePolicy:
    """Keep ephemeral and owner-persistent browser modes separate."""

    def __init__(self, profile_root: str | Path | None, *, owner_persistent_opt_in: bool) -> None:
        self._profile_root = profile_root
        self._owner_persistent_opt_in = bool(owner_persistent_opt_in)

    @property
    def owner_persistent_opt_in(self) -> bool:
        return self._owner_persistent_opt_in

    def persistent_user_data_dir(self, *, required: bool = False) -> Path | None:
        if not self._owner_persistent_opt_in:
            if required:
                raise BrowserProfilePolicyError("owner_persistent_opt_in_required")
            return None
        raw_path = self._profile_root if self._profile_root is not None else default_owner_profile_path()
        return self.validate_dedicated_profile_path(raw_path)

    @staticmethod
    def validate_dedicated_profile_path(raw_path: str | Path) -> Path:
        if not isinstance(raw_path, (str, Path)) or not str(raw_path).strip():
            raise BrowserProfilePolicyError("browser_profile_path_invalid")
        try:
            resolved = Path(raw_path).expanduser().resolve()
        except (OSError, RuntimeError) as exc:
            raise BrowserProfilePolicyError("browser_profile_path_invalid") from exc
        parts = tuple(part.casefold() for part in resolved.parts)
        forbidden_sequences = (
            ("bravesoftware", "brave-browser", "user data"),
            ("google", "chrome", "user data"),
            ("microsoft", "edge", "user data"),
        )
        if any(_contains_path_sequence(parts, sequence) for sequence in forbidden_sequences):
            raise BrowserProfilePolicyError("normal_browser_profile_not_allowed")
        if resolved == Path.home().resolve():
            raise BrowserProfilePolicyError("browser_profile_path_invalid")
        return resolved

