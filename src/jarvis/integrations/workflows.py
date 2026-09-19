"""Native-first service workflow contracts over canonical JARVIS actions.

These helpers never own permissions, approvals, browser control, or message
delivery. They resolve exact owner targets and call the existing
``ComputerActionService`` for the harmless open/focus/readback boundary.
Authenticated semantic actions remain an explicit adapter seam and return a
truthful degraded state until configured.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..computer.applications import InstalledApplicationRegistry
from ..contracts import ComputerAction, DeviceIdentity, Identity


_DESTINATION_RE = re.compile(r"^(channel|dm):[A-Za-z0-9_.:-]{1,200}$")
_FORBIDDEN_DESTINATION_TERMS = frozenset({
    "last contact", "recent contact", "most recent", "recent dm", "first result", "top result", "first matching",
})


def _result_status(value: object) -> str:
    """Normalize a typed result status without widening the accepted surface."""

    raw = getattr(value, "value", value)
    return str(raw).casefold()


@dataclass(frozen=True, slots=True)
class IntegrationReceipt:
    service: str
    operation: str
    status: str
    reason: str | None = None
    app_ref: str | None = None
    target_ref: str | None = None
    verified: bool = False
    external_writes: int = 0
    sends: int = 0


@dataclass(frozen=True, slots=True)
class TargetResolution:
    status: str
    target_ref: str | None = None
    matches: tuple[str, ...] = ()
    reason: str | None = None


class NativeDesktopWorkflow:
    """Shared native open/focus/readback path for installed applications."""

    service = "desktop"

    def __init__(self, registry: InstalledApplicationRegistry, computer_actions: Any, *, application_alias: str) -> None:
        self.registry = registry
        self.computer_actions = computer_actions
        self.application_alias = application_alias

    async def open_and_focus(self, identity: Identity, device: DeviceIdentity) -> IntegrationReceipt:
        lookup = self.registry.find(self.application_alias)
        if lookup.status == "ambiguous":
            return IntegrationReceipt(self.service, "open_focus", "AMBIGUOUS", "application_identity_ambiguous")
        if lookup.status != "matched" or lookup.application is None:
            return IntegrationReceipt(self.service, "open_focus", "NOT_CONFIGURED", lookup.reason or "application_not_installed")
        app_ref = lookup.application.app_ref
        opened = await self.computer_actions.execute(
            ComputerAction("open_application", {"app_ref": app_ref}, False), identity, device,
        )
        if _result_status(getattr(opened, "status", "")) != "succeeded":
            status = _result_status(getattr(opened, "status", "failed"))
            return IntegrationReceipt(self.service, "open_focus", "APPROVAL_REQUIRED" if status == "approval_required" else "FAILED", getattr(opened, "error_code", None), app_ref)
        readback = await self.computer_actions.execute(
            ComputerAction("application_status", {"app_ref": app_ref}, False), identity, device,
        )
        output = getattr(readback, "output", {})
        running = isinstance(output, Mapping) and output.get("running") is True
        focused = isinstance(output, Mapping) and output.get("focused") is True
        if _result_status(getattr(readback, "status", "")) != "succeeded" or not running or not focused:
            return IntegrationReceipt(self.service, "open_focus", "FAILED", "application_readback_not_verified", app_ref)
        return IntegrationReceipt(self.service, "open_focus", "READY", None, app_ref, verified=bool(getattr(readback, "verified", False)))

    @staticmethod
    def exact_target(query: str, candidates: Sequence[Mapping[str, object]]) -> TargetResolution:
        """Resolve only one exact visible owner target; never choose first/recent."""

        normalized = query.strip().casefold()
        if not normalized:
            return TargetResolution("NOT_FOUND", reason="target_query_required")
        matches: list[str] = []
        for candidate in candidates:
            target_ref = candidate.get("target_ref") or candidate.get("candidate_ref")
            if not isinstance(target_ref, str) or not target_ref:
                continue
            values = [candidate.get(key) for key in ("label", "name", "title", "artist", "playlist", "channel")]
            if any(isinstance(value, str) and value.strip().casefold() == normalized for value in values):
                matches.append(target_ref)
        if len(matches) == 1:
            return TargetResolution("RESOLVED", matches[0], tuple(matches))
        if len(matches) > 1:
            return TargetResolution("AMBIGUOUS", matches=tuple(matches), reason="multiple_exact_targets")
        return TargetResolution("NOT_FOUND", reason="exact_target_not_found")


class SpotifyDesktopWorkflow(NativeDesktopWorkflow):
    service = "spotify"

    def __init__(self, registry: InstalledApplicationRegistry, computer_actions: Any) -> None:
        super().__init__(registry, computer_actions, application_alias="spotify")

    @staticmethod
    def resolve_media(query: str, candidates: Sequence[Mapping[str, object]]) -> TargetResolution:
        return NativeDesktopWorkflow.exact_target(query, candidates)


class DiscordDesktopWorkflow(NativeDesktopWorkflow):
    service = "discord"

    def __init__(self, registry: InstalledApplicationRegistry, computer_actions: Any) -> None:
        super().__init__(registry, computer_actions, application_alias="discord")

    @staticmethod
    def validate_destination(value: str) -> bool:
        normalized = value.strip().casefold()
        return bool(_DESTINATION_RE.fullmatch(value.strip())) and not any(term in normalized for term in _FORBIDDEN_DESTINATION_TERMS)


class WhatsAppDesktopWorkflow(NativeDesktopWorkflow):
    service = "whatsapp"

    def __init__(self, registry: InstalledApplicationRegistry, computer_actions: Any) -> None:
        super().__init__(registry, computer_actions, application_alias="whatsapp")

    @staticmethod
    def validate_self_chat(value: str) -> bool:
        return value.strip().casefold() in {"self", "myself", "message yourself", "me"}


class OneNoteDesktopWorkflow(NativeDesktopWorkflow):
    service = "onenote"

    def __init__(self, registry: InstalledApplicationRegistry, computer_actions: Any) -> None:
        super().__init__(registry, computer_actions, application_alias="onenote")

    @staticmethod
    def exact_page(notebook: str, section: str, page: str) -> tuple[str, str, str] | None:
        values = tuple(item.strip()[:200] for item in (notebook, section, page))
        return values if all(values) else None


class NotionDesktopWorkflow(NativeDesktopWorkflow):
    service = "notion"

    def __init__(self, registry: InstalledApplicationRegistry, computer_actions: Any) -> None:
        super().__init__(registry, computer_actions, application_alias="notion")

    @staticmethod
    def choose_surface(*, native_available: bool, browser_available: bool) -> str:
        if native_available:
            return "DESKTOP"
        if browser_available:
            return "BROWSER"
        return "SERVICE_SURFACE_BLOCKED"


class ChatGPTDesktopWorkflow(NativeDesktopWorkflow):
    service = "chatgpt"

    def __init__(self, registry: InstalledApplicationRegistry, computer_actions: Any) -> None:
        super().__init__(registry, computer_actions, application_alias="chatgpt")

    @staticmethod
    def choose_surface(*, official_desktop_available: bool, browser_available: bool) -> str:
        if official_desktop_available:
            return "DESKTOP"
        if browser_available:
            return "BROWSER"
        return "SERVICE_SURFACE_BLOCKED"


class GmailBrowserWorkflow:
    service = "gmail"

    @staticmethod
    def draft_target(recipient: str, subject: str) -> IntegrationReceipt:
        if not recipient.strip() or not subject.strip():
            return IntegrationReceipt("gmail", "draft", "NOT_FOUND", "exact_recipient_and_subject_required")
        return IntegrationReceipt("gmail", "draft", "READY", "draft_only_default", target_ref="configured_recipient")


class YouTubeWorkflow:
    service = "youtube"

    @staticmethod
    def resolve_video(query: str, candidates: Sequence[Mapping[str, object]]) -> TargetResolution:
        return NativeDesktopWorkflow.exact_target(query, candidates)
