"""Privacy constraints applied inside the canonical perception service."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..contracts import DesktopContextSnapshot, PerceptionPrivacyMode


@dataclass(slots=True)
class PerceptionPrivacyPolicy:
    mode: PerceptionPrivacyMode = PerceptionPrivacyMode.ON_DEMAND
    denied_processes: frozenset[str] = field(default_factory=lambda: frozenset({"winlogon.exe", "logonui.exe", "lsass.exe"}))
    denied_title_patterns: tuple[str, ...] = ("password", "credential", "private key", "sign in", "login")

    def set_mode(self, mode: PerceptionPrivacyMode | str) -> None:
        try:
            self.mode = PerceptionPrivacyMode(mode)
        except ValueError as exc:
            raise ValueError("unsupported perception privacy mode") from exc

    def allows_metadata(self) -> bool:
        return self.mode is not PerceptionPrivacyMode.OFF

    def allows_pixels(self) -> bool:
        return self.mode is PerceptionPrivacyMode.ON_DEMAND

    def check_snapshot(self, snapshot: DesktopContextSnapshot) -> str | None:
        if not self.allows_metadata():
            return "privacy_policy_denied"
        for window in snapshot.windows:
            if self.check_window(window.process_name, window.title):
                return "privacy_policy_denied"
        return None

    def check_window(self, process_name: str | None, title: str | None) -> str | None:
        process = (process_name or "").casefold()
        value = (title or "").casefold()
        if process in {item.casefold() for item in self.denied_processes}:
            return "privacy_policy_denied"
        if any(re.search(pattern, value, re.IGNORECASE) for pattern in self.denied_title_patterns):
            return "privacy_policy_denied"
        return None

    def check_capture(self) -> str | None:
        if not self.allows_pixels():
            return "privacy_policy_denied"
        return None
