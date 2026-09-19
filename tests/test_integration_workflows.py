from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from jarvis.computer.applications import ApplicationCandidate, ApplicationLaunchKind, InstalledApplicationRegistry
from jarvis.contracts import ComputerAction, DeviceIdentity, Identity, ToolResultStatus
from jarvis.integrations.workflows import (
    ChatGPTDesktopWorkflow,
    DiscordDesktopWorkflow,
    GmailBrowserWorkflow,
    NativeDesktopWorkflow,
    NotionDesktopWorkflow,
    OneNoteDesktopWorkflow,
    SpotifyDesktopWorkflow,
    WhatsAppDesktopWorkflow,
)


def test_service_target_helpers_fail_closed_on_ambiguity_and_unsafe_destinations() -> None:
    candidates = (
        {"target_ref": "media-a", "title": "Study Track"},
        {"target_ref": "media-b", "title": "Study Track"},
    )
    assert SpotifyDesktopWorkflow.resolve_media("Study Track", candidates).status == "AMBIGUOUS"
    assert not DiscordDesktopWorkflow.validate_destination("recent DM")
    assert DiscordDesktopWorkflow.validate_destination("channel:jarvis-test")
    assert WhatsAppDesktopWorkflow.validate_self_chat("myself")
    assert not WhatsAppDesktopWorkflow.validate_self_chat("recent contact")
    assert OneNoteDesktopWorkflow.exact_page("JARVIS", "Study", "Computer Vision") == ("JARVIS", "Study", "Computer Vision")
    assert OneNoteDesktopWorkflow.exact_page("", "Study", "Computer Vision") is None


def test_surface_selection_never_confuses_blocked_web_with_ready() -> None:
    assert NotionDesktopWorkflow.choose_surface(native_available=True, browser_available=True) == "DESKTOP"
    assert NotionDesktopWorkflow.choose_surface(native_available=False, browser_available=True) == "BROWSER"
    assert NotionDesktopWorkflow.choose_surface(native_available=False, browser_available=False) == "SERVICE_SURFACE_BLOCKED"
    assert ChatGPTDesktopWorkflow.choose_surface(official_desktop_available=False, browser_available=False) == "SERVICE_SURFACE_BLOCKED"
    assert GmailBrowserWorkflow.draft_target("owner-test@example.invalid", "JARVIS test").status == "READY"
    assert GmailBrowserWorkflow.draft_target("", "JARVIS test").status == "NOT_FOUND"


def test_native_workflow_uses_opaque_app_ref_and_fresh_status_readback(tmp_path: Path) -> None:
    asyncio.run(_test_native_workflow_uses_opaque_app_ref_and_fresh_status_readback(tmp_path))


async def _test_native_workflow_uses_opaque_app_ref_and_fresh_status_readback(tmp_path: Path) -> None:
    target = tmp_path / "Spotify.exe"
    target.write_bytes(b"MZ-JARVIS")
    registry = InstalledApplicationRegistry()
    registry.refresh((ApplicationCandidate("Spotify", ApplicationLaunchKind.EXE, target),))
    lookup = registry.find("spotify")
    assert lookup.application is not None
    actions: list[ComputerAction] = []

    class Computer:
        async def execute(self, action, _identity, _device):
            actions.append(action)
            if action.action == "open_application":
                return SimpleNamespace(status=ToolResultStatus.SUCCEEDED, verified=True, error_code=None, output={})
            return SimpleNamespace(
                status=ToolResultStatus.SUCCEEDED,
                verified=True,
                error_code=None,
                output={"running": True, "focused": True},
            )

    workflow = SpotifyDesktopWorkflow(registry, Computer())
    receipt = await workflow.open_and_focus(
        Identity("identity", "Owner", "owner"),
        DeviceIdentity("device", "owner", "desktop", "windows", frozenset(), frozenset()),
    )

    assert receipt.status == "READY"
    assert receipt.verified is True
    assert [action.action for action in actions] == ["open_application", "application_status"]
    assert all(action.parameters.get("app_ref") == lookup.application.app_ref for action in actions)
