from __future__ import annotations

import json
import unittest
from pathlib import Path

from jarvis.computer.applications import (
    ApplicationCandidate,
    ApplicationClass,
    ApplicationLaunchKind,
    AutomationTier,
    InstalledApplicationRegistry,
)
from jarvis.computer.controller import ComputerExecutionRouter
from jarvis.computer.service import WindowsNativeComputerController
from jarvis.contracts import ComputerAction, ToolContext, ToolResult, ToolResultStatus


def _exe(tmp_path: Path, name: str, content: bytes = b"MZ-JARVIS-TEST") -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_public_descriptor_is_opaque_and_reports_truthful_launch_capabilities(tmp_path: Path) -> None:
    target = _exe(tmp_path, "Spotify.exe")
    registry = InstalledApplicationRegistry()
    registry.refresh((ApplicationCandidate("Spotify", ApplicationLaunchKind.EXE, target),))

    match = registry.find("spotify")
    assert match.status == "matched"
    assert match.application is not None
    public = match.application.public_dict()

    assert public["app_ref"].startswith("app-")
    assert public["display_name"] == "Spotify"
    assert public["automation_tier"] == AutomationTier.TIER_C.value
    assert public["preferred_surface"] == "AUTO"
    assert public["resolved_surface"] == "DESKTOP"
    assert public["capabilities"] == {
        "launchable": True,
        "semantic_control": False,
        "visual_fallback": False,
    }
    assert str(target) not in json.dumps(public)
    assert "verified_launch_target" not in public
    assert "target_fingerprint" not in public


def test_alias_collision_fails_closed(tmp_path: Path) -> None:
    first = _exe(tmp_path, "first.exe")
    second = _exe(tmp_path, "second.exe")
    registry = InstalledApplicationRegistry()
    registry.refresh(
        (
            ApplicationCandidate("Study Tool", ApplicationLaunchKind.EXE, first, aliases=("notes",)),
            ApplicationCandidate("Other Tool", ApplicationLaunchKind.EXE, second, aliases=("notes",)),
        )
    )

    match = registry.find("notes")
    assert match.status == "ambiguous"
    assert match.application is None
    assert len(match.matches) == 2


def test_verified_alias_wins_over_a_stale_unresolved_duplicate(tmp_path: Path) -> None:
    target = _exe(tmp_path, "Notepad.exe")
    registry = InstalledApplicationRegistry()
    registry.refresh(
        (
            ApplicationCandidate("Notepad", ApplicationLaunchKind.EXE, None, source_id="stale:shortcut"),
            ApplicationCandidate("Notepad", ApplicationLaunchKind.EXE, target, source_id="verified:target"),
        )
    )

    match = registry.find("notepad")
    assert match.status == "matched"
    assert match.application is not None
    assert match.application.installed is True


def test_system_and_admin_targets_are_detected_but_not_generic_launchable(tmp_path: Path) -> None:
    target = _exe(tmp_path, "powershell.exe")
    registry = InstalledApplicationRegistry()
    registry.refresh((ApplicationCandidate("Windows PowerShell", ApplicationLaunchKind.EXE, target),))

    match = registry.find("powershell")
    assert match.status == "matched"
    assert match.application is not None
    assert match.application.application_class is ApplicationClass.ADMIN_TOOL
    assert match.application.enabled is False
    assert match.application.automation_tier is AutomationTier.TIER_D
    assert registry.prepare_launch(match.application.app_ref).status == "denied"


def test_admin_classification_is_conservative_for_descriptive_names(tmp_path: Path) -> None:
    target = _exe(tmp_path, "WindowsTerminal.exe")
    registry = InstalledApplicationRegistry()
    registry.refresh((ApplicationCandidate("Terminal Preview", ApplicationLaunchKind.EXE, target),))

    match = registry.find("terminal preview")
    assert match.application is not None
    assert match.application.application_class is ApplicationClass.ADMIN_TOOL
    assert match.application.enabled is False


def test_malicious_shortcut_target_is_never_launchable(tmp_path: Path) -> None:
    target = tmp_path / "payload.cmd"
    target.write_text("echo unsafe", encoding="utf-8")
    registry = InstalledApplicationRegistry()
    registry.refresh(
        (
            ApplicationCandidate(
                "Untrusted Shortcut",
                ApplicationLaunchKind.SHORTCUT,
                target,
                source_id="start-menu:untrusted.lnk",
            ),
        )
    )

    match = registry.find("untrusted shortcut")
    assert match.status == "matched"
    assert match.application is not None
    assert match.application.automation_tier is AutomationTier.TIER_D
    assert match.application.enabled is False
    assert match.application.reason == "unsafe_launch_target"
    assert registry.prepare_launch(match.application.app_ref).status == "denied"


def test_replaced_executable_invalidates_the_opaque_reference(tmp_path: Path) -> None:
    target = _exe(tmp_path, "Editor.exe", b"original")
    registry = InstalledApplicationRegistry()
    registry.refresh((ApplicationCandidate("Editor", ApplicationLaunchKind.EXE, target),))
    match = registry.find("editor")
    assert match.application is not None

    target.write_bytes(b"replaced")
    launch = registry.prepare_launch(match.application.app_ref)

    assert launch.status == "stale"
    assert launch.application is None
    assert launch.reason == "launch_target_changed"


def test_generic_calculator_host_requires_the_exact_window_identity(tmp_path: Path) -> None:
    target = _exe(tmp_path, "calc.exe")
    registry = InstalledApplicationRegistry()
    registry.refresh((ApplicationCandidate("Calculator", ApplicationLaunchKind.EXE, target),))
    app = registry.find("calculator").application
    assert app is not None

    assert WindowsNativeComputerController._window_matches_application(app, "ApplicationFrameHost.exe", "Calculator")
    assert not WindowsNativeComputerController._window_matches_application(app, "ApplicationFrameHost.exe", "Settings")


def test_safe_msix_identity_is_internal_and_not_exposed(tmp_path: Path) -> None:
    explorer = _exe(tmp_path, "explorer.exe")
    registry = InstalledApplicationRegistry()
    registry.refresh(
        (
            ApplicationCandidate(
                "Store Notes",
                ApplicationLaunchKind.MSIX,
                explorer,
                arguments=("shell:AppsFolder\u005cContoso.Notes_123!App",),
                aumid="Contoso.Notes_123!App",
            ),
        )
    )

    match = registry.find("store notes")
    assert match.status == "matched"
    assert match.application is not None
    assert match.application.launch_kind is ApplicationLaunchKind.MSIX
    assert "Contoso.Notes_123!App" not in json.dumps(match.application.public_dict())
    prepared = registry.prepare_launch(match.application.app_ref)
    assert prepared.status == "ready"
    assert prepared.target == explorer
    assert prepared.arguments == ("shell:AppsFolder\\Contoso.Notes_123!App",)


def test_disable_and_surface_preference_persist_only_safe_refs(tmp_path: Path) -> None:
    target = _exe(tmp_path, "Calculator.exe")
    settings = tmp_path / "installed-apps.json"
    registry = InstalledApplicationRegistry(settings_path=settings)
    registry.refresh((ApplicationCandidate("Calculator", ApplicationLaunchKind.EXE, target),))
    match = registry.find("calculator")
    assert match.application is not None

    registry.set_enabled(match.application.app_ref, False)
    registry.set_surface_preference(match.application.app_ref, "DESKTOP")
    saved = json.loads(settings.read_text(encoding="utf-8"))
    assert saved == {"disabled_app_refs": [match.application.app_ref], "surface_preferences": {match.application.app_ref: "DESKTOP"}}

    second = InstalledApplicationRegistry(settings_path=settings)
    second.refresh((ApplicationCandidate("Calculator", ApplicationLaunchKind.EXE, target),))
    restored = second.find("calculator")
    assert restored.application is not None
    assert restored.application.enabled is False
    assert restored.application.preferred_surface.value == "DESKTOP"


def test_legacy_discovery_ignores_path_executables_and_uses_standard_locations(tmp_path: Path, monkeypatch) -> None:
    path_brave = tmp_path / "brave.exe"
    path_brave.write_bytes(b"PATH-PAYLOAD")
    standard = tmp_path / "local" / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe"
    standard.parent.mkdir(parents=True)
    standard.write_bytes(b"STANDARD-BRAVE")
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "program-files"))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "program-files-x86"))
    monkeypatch.setenv("WINDIR", str(tmp_path / "windows"))

    candidates = tuple(InstalledApplicationRegistry()._legacy_candidates())
    brave = [item for item in candidates if item.display_name == "Brave"]

    assert len(brave) == 1
    assert brave[0].target == standard
    assert brave[0].target != path_brave


class _RecordingComputerAdapter:
    def __init__(self) -> None:
        self.actions: list[ComputerAction] = []

    async def execute(self, action: ComputerAction, context: ToolContext) -> ToolResult:
        del context
        self.actions.append(action)
        return ToolResult(ToolResultStatus.SUCCEEDED, {"accepted": True}, verified=True)


class NativeApplicationRouterBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_remote_alias_is_preserved_but_native_app_ref_stays_local(self) -> None:
        local = _RecordingComputerAdapter()
        satellite = _RecordingComputerAdapter()
        router = ComputerExecutionRouter(local, satellite)  # type: ignore[arg-type]
        context = ToolContext(None, None, "session", "correlation", metadata={"execution_adapter": "satellite"})

        legacy = await router.execute(
            ComputerAction("open_application", {"application": "notepad"}, dry_run=True),
            context,
        )
        native = await router.execute(
            ComputerAction("open_application", {"app_ref": "app-opaque"}, dry_run=True),
            context,
        )

        assert legacy.status is ToolResultStatus.SUCCEEDED
        assert [item.parameters for item in satellite.actions] == [{"application": "notepad"}]
        assert native.status is ToolResultStatus.DENIED
        assert native.error_code == "native_application_control_local_only"
        assert local.actions == []
