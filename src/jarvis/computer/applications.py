"""Bounded installed-application identity for the canonical computer boundary.

The registry is deliberately a catalog, not an execution authority.  It only
discovers launch identity from bounded Windows sources and returns opaque
application references to callers.  Launch/focus still happens in
``ComputerActionService`` and ``WindowsNativeComputerController``.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shutil
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from ctypes import wintypes
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import UUID


_NORMALIZE_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)


class ApplicationLaunchKind(StrEnum):
    EXE = "exe"
    SHORTCUT = "shortcut"
    MSIX = "msix"


class ApplicationClass(StrEnum):
    USER_APP = "USER_APP"
    SYSTEM_APP = "SYSTEM_APP"
    ADMIN_TOOL = "ADMIN_TOOL"
    INSTALLER = "INSTALLER"
    UNINSTALLER = "UNINSTALLER"
    BACKGROUND_COMPONENT = "BACKGROUND_COMPONENT"
    UNSUPPORTED = "UNSUPPORTED"


class AutomationTier(StrEnum):
    TIER_A = "TIER_A"
    TIER_B = "TIER_B"
    TIER_C = "TIER_C"
    TIER_D = "TIER_D"


class SurfacePreference(StrEnum):
    AUTO = "AUTO"
    DESKTOP = "DESKTOP"
    BROWSER = "BROWSER"
    API = "API"


class ApplicationLoginStatus(StrEnum):
    READY = "READY"
    OWNER_LOGIN_REQUIRED = "OWNER_LOGIN_REQUIRED"
    NOT_INSTALLED = "NOT_INSTALLED"
    IDENTITY_UNVERIFIED = "IDENTITY_UNVERIFIED"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class ApplicationCandidate:
    """A discovery-source record.

    ``target`` and ``arguments`` are internal discovery data.  They are never
    included in :meth:`InstalledApplication.public_dict`.
    """

    display_name: str
    launch_kind: ApplicationLaunchKind
    target: Path | None
    aliases: tuple[str, ...] = ()
    source_id: str = ""
    arguments: tuple[str, ...] = ()
    publisher: str | None = None
    version: str | None = None
    aumid: str | None = None


@dataclass(frozen=True, slots=True)
class ShortcutTarget:
    target: Path | None
    arguments: tuple[str, ...] = ()
    aumid: str | None = None


@dataclass(frozen=True, slots=True)
class ApplicationLookup:
    status: str
    application: "InstalledApplication | None" = None
    matches: tuple["InstalledApplication", ...] = ()
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class PreparedApplicationLaunch:
    status: str
    application: "InstalledApplication | None" = None
    target: Path | None = None
    arguments: tuple[str, ...] = ()
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class InstalledApplication:
    """Internal descriptor with a model-safe public projection."""

    app_ref: str
    display_name: str
    canonical_name: str
    aliases: tuple[str, ...]
    launch_kind: ApplicationLaunchKind
    verified_launch_target: Path | None
    launch_arguments: tuple[str, ...]
    aumid: str | None
    publisher: str | None
    version: str | None
    process_identity: tuple[str, ...]
    window_identity_rules: tuple[str, ...]
    automation_tier: AutomationTier
    application_class: ApplicationClass
    risk_class: str
    installed: bool
    enabled: bool
    reason: str
    preferred_surface: SurfacePreference
    semantic_control: bool
    visual_fallback: bool
    login_status: ApplicationLoginStatus
    last_verified: str | None
    target_fingerprint: tuple[int, int, str] | None
    owner_disabled: bool = False

    def public_dict(self) -> dict[str, object]:
        """Return the only descriptor shape allowed outside the registry."""

        reason = "owner_disabled" if self.owner_disabled else self.reason
        launchable = bool(
            self.installed
            and self.enabled
            and not self.owner_disabled
            and self.automation_tier is not AutomationTier.TIER_D
        )
        resolved_surface = (
            self.preferred_surface.value
            if self.preferred_surface is not SurfacePreference.AUTO
            else "DESKTOP" if launchable else "UNSUPPORTED"
        )
        return {
            "app_ref": self.app_ref,
            "display_name": self.display_name,
            "canonical_name": self.canonical_name,
            "aliases": list(self.aliases),
            "launch_kind": self.launch_kind.value,
            "publisher": self.publisher,
            "version": self.version,
            "automation_tier": self.automation_tier.value,
            "application_class": self.application_class.value,
            "risk_class": self.risk_class,
            "installed": self.installed,
            "enabled": self.enabled and not self.owner_disabled,
            "reason": reason,
            "resolved_surface": resolved_surface,
            "preferred_surface": self.preferred_surface.value,
            "capabilities": {
                "launchable": launchable,
                "semantic_control": self.semantic_control,
                "visual_fallback": self.visual_fallback,
            },
            "login_status": self.login_status.value,
            "last_verified": self.last_verified,
        }


@dataclass(frozen=True, slots=True)
class _TargetIdentity:
    path: Path
    fingerprint: tuple[int, int, str]


class InstalledApplicationRegistry:
    """Discover and resolve installed Windows applications within fixed bounds."""

    MAX_CANDIDATES = 512
    MAX_FILES_PER_ROOT = 256
    MAX_ROOT_DEPTH = 4
    MAX_HASH_BYTES = 512 * 1024 * 1024
    _SAFE_EXECUTABLE_SUFFIXES = frozenset({".exe"})
    _REJECTED_TARGET_SUFFIXES = frozenset({
        ".bat", ".cmd", ".com", ".js", ".jse", ".msc", ".ps1", ".vbe", ".vbs", ".wsf",
    })
    _MSIX_AUMID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}![A-Za-z0-9][A-Za-z0-9._-]{0,120}$")
    _NORMALIZE_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)
    _KNOWN_ALIASES: Mapping[str, tuple[str, ...]] = {
        "spotify": ("spotify",),
        "discord": ("discord",),
        "whatsapp": ("whatsapp",),
        "onenote": ("onenote", "one note"),
        "notion": ("notion",),
        "chatgpt": ("chatgpt", "chat gpt"),
        "brave": ("brave", "brave browser"),
        "visual studio code": ("vs code", "vscode", "code"),
        "calculator": ("calculator", "calc"),
        "file explorer": ("file explorer", "explorer"),
    }
    _ADMIN_TERMS = frozenset({
        "cmd", "command prompt", "powershell", "pwsh", "windows terminal", "terminal",
        "regedit", "registry editor", "services", "services.msc", "task scheduler", "taskschd",
    })
    _SYSTEM_TERMS = frozenset({"file explorer", "explorer", "control panel", "settings"})
    _INSTALLER_TERMS = ("setup", "installer", "install", "msiexec")
    _UNINSTALLER_TERMS = ("uninstall", "uninstaller", "remove")
    _BACKGROUND_TERMS = ("updater", "update service", "daemon", "background", "helper service")
    _LEGACY_EXECUTABLES: Mapping[str, tuple[str, ...]] = {
        "code": ("code", "vscode"),
        "notepad": ("notepad",),
        "calculator": ("calculator", "calc"),
        "brave": ("brave",),
        "explorer": ("explorer", "file explorer"),
    }
    _KNOWN_PROCESS_ALIASES: Mapping[str, tuple[str, ...]] = {
        # Modern Windows Calculator can present its visible window through a
        # generic host even though the verified launch identity is calc.exe.
        "calc.exe": ("applicationframehost.exe", "calculatorapp.exe"),
    }
    _GENERIC_WINDOW_HOSTS = frozenset({"applicationframehost.exe", "calculatorapp.exe"})

    def __init__(
        self,
        *,
        start_menu_roots: tuple[Path, ...] | None = None,
        app_paths_reader: Callable[[], Iterable[ApplicationCandidate]] | None = None,
        shortcut_resolver: Callable[[Path], ShortcutTarget | None] | None = None,
        settings_path: Path | None = None,
    ) -> None:
        self.start_menu_roots = start_menu_roots or self._default_start_menu_roots()
        self._app_paths_reader = app_paths_reader or self._read_app_paths
        self._shortcut_resolver = shortcut_resolver or _resolve_windows_shortcut
        self.settings_path = settings_path
        self._apps: dict[str, InstalledApplication] = {}
        self._loaded = False
        self._disabled_refs: set[str] = set()
        self._surface_preferences: dict[str, SurfacePreference] = {}
        self._load_settings()

    @property
    def loaded(self) -> bool:
        return self._loaded

    def refresh(self, candidates: Iterable[ApplicationCandidate] | None = None) -> tuple[InstalledApplication, ...]:
        """Refresh once from bounded sources; never scans arbitrary disks."""

        source_candidates = tuple(candidates) if candidates is not None else tuple(self._discover_candidates())
        source_candidates = source_candidates[: self.MAX_CANDIDATES]
        by_identity: dict[str, InstalledApplication] = {}
        for candidate in source_candidates:
            app = self._build_application(candidate)
            identity = self._dedupe_identity(candidate, app)
            current = by_identity.get(identity)
            if current is None:
                by_identity[identity] = app
            else:
                by_identity[identity] = self._merge_duplicate(current, app)
        self._apps = {item.app_ref: item for item in by_identity.values()}
        self._loaded = True
        return self.applications()

    def applications(self, *, refresh: bool = False) -> tuple[InstalledApplication, ...]:
        if refresh or not self._loaded:
            self.refresh()
        return tuple(sorted(self._apps.values(), key=lambda item: (item.display_name.casefold(), item.app_ref)))

    def public_list(self, *, refresh: bool = False) -> tuple[dict[str, object], ...]:
        return tuple(item.public_dict() for item in self.applications(refresh=refresh))

    def find(self, query: str, *, refresh: bool = False) -> ApplicationLookup:
        if refresh or not self._loaded:
            self.refresh()
        normalized = _normalize_name(query)
        if not normalized:
            return ApplicationLookup("not_found", reason="application_query_required")
        exact_ref = self._apps.get(query.strip())
        if exact_ref is not None:
            return ApplicationLookup("matched", exact_ref, (exact_ref,))
        matches = tuple(
            item for item in self.applications()
            if normalized in {_normalize_name(item.display_name), _normalize_name(item.canonical_name), *(_normalize_name(alias) for alias in item.aliases)}
        )
        # A stale/unresolved shortcut with the same friendly name must not
        # shadow one verified installed target. Multiple verified targets
        # still remain ambiguous and fail closed; an owner-disabled target is
        # retained only when it is the sole match so the denial is explicit.
        usable_matches = tuple(
            item for item in matches
            if item.installed and item.enabled and item.automation_tier is not AutomationTier.TIER_D
        )
        if usable_matches:
            matches = usable_matches
        if not matches:
            return ApplicationLookup("not_found", reason="application_not_found")
        if len(matches) > 1:
            return ApplicationLookup("ambiguous", matches=matches, reason="application_identity_ambiguous")
        return ApplicationLookup("matched", matches[0], matches)

    def get(self, app_ref: str, *, refresh: bool = False) -> InstalledApplication | None:
        if refresh or not self._loaded:
            self.refresh()
        return self._apps.get(app_ref)

    def prepare_launch(self, app_ref: str) -> PreparedApplicationLaunch:
        app = self.get(app_ref)
        if app is None:
            return PreparedApplicationLaunch("not_found", reason="application_ref_not_found")
        if app.owner_disabled:
            return PreparedApplicationLaunch("denied", app, reason="application_disabled")
        if not app.enabled:
            return PreparedApplicationLaunch("denied", app, reason=app.reason)
        if app.application_class in {
            ApplicationClass.ADMIN_TOOL,
            ApplicationClass.INSTALLER,
            ApplicationClass.UNINSTALLER,
            ApplicationClass.BACKGROUND_COMPONENT,
            ApplicationClass.UNSUPPORTED,
        }:
            return PreparedApplicationLaunch("denied", app, reason="application_class_denied")
        identity = self._revalidate_target(app)
        if identity is None:
            return PreparedApplicationLaunch("stale", reason="launch_target_changed")
        return PreparedApplicationLaunch("ready", app, identity.path, app.launch_arguments)

    def set_enabled(self, app_ref: str, enabled: bool) -> InstalledApplication:
        app = self.get(app_ref)
        if app is None:
            raise KeyError("application_ref_not_found")
        updated = replace(app, owner_disabled=not enabled)
        self._apps[app_ref] = updated
        self._disabled_refs.discard(app_ref)
        if not enabled:
            self._disabled_refs.add(app_ref)
        self._save_settings()
        return updated

    def set_surface_preference(self, app_ref: str, preference: str | SurfacePreference) -> InstalledApplication:
        app = self.get(app_ref)
        if app is None:
            raise KeyError("application_ref_not_found")
        try:
            value = preference if isinstance(preference, SurfacePreference) else SurfacePreference(str(preference).upper())
        except ValueError as exc:
            raise ValueError("surface_preference_invalid") from exc
        self._surface_preferences[app_ref] = value
        updated = replace(app, preferred_surface=value)
        self._apps[app_ref] = updated
        self._save_settings()
        return updated

    def _build_application(self, candidate: ApplicationCandidate) -> InstalledApplication:
        display_name = _bounded_name(candidate.display_name) or "Unknown application"
        canonical_name = _canonical_name(display_name)
        target_alias = candidate.target.stem if candidate.target is not None else ""
        aliases = _aliases_for(display_name, (*candidate.aliases, target_alias))
        application_class = self._classify(display_name, candidate.target)
        target, target_fingerprint, target_reason = self._validate_candidate_target(candidate)
        if application_class in {
            ApplicationClass.ADMIN_TOOL,
            ApplicationClass.INSTALLER,
            ApplicationClass.UNINSTALLER,
            ApplicationClass.BACKGROUND_COMPONENT,
        }:
            tier = AutomationTier.TIER_D
            enabled = False
            reason = "application_class_denied"
        elif target_reason is not None:
            tier = AutomationTier.TIER_D
            enabled = False
            reason = target_reason
            application_class = ApplicationClass.UNSUPPORTED if application_class is ApplicationClass.USER_APP else application_class
        else:
            tier = AutomationTier.TIER_C
            enabled = True
            reason = "discovered_target_verified"
        if candidate.launch_kind is ApplicationLaunchKind.MSIX and not candidate.aumid:
            tier, enabled, reason = AutomationTier.TIER_D, False, "msix_identity_missing"
        owner_disabled = self._disabled_refs.__contains__(self._stable_ref(display_name, candidate, target))
        preference = self._surface_preferences.get(self._stable_ref(display_name, candidate, target), SurfacePreference.AUTO)
        if owner_disabled:
            enabled = False
        login_status = ApplicationLoginStatus.UNSUPPORTED if tier is AutomationTier.TIER_D else ApplicationLoginStatus.IDENTITY_UNVERIFIED
        app_ref = self._stable_ref(display_name, candidate, target)
        process_name = target.name.casefold() if target is not None else ""
        process_identity = (process_name, *self._KNOWN_PROCESS_ALIASES.get(process_name, ())) if process_name else ()
        window_rules = tuple(dict.fromkeys((display_name, canonical_name, *aliases)))
        return InstalledApplication(
            app_ref=app_ref,
            display_name=display_name,
            canonical_name=canonical_name,
            aliases=aliases,
            launch_kind=candidate.launch_kind,
            verified_launch_target=target,
            launch_arguments=tuple(candidate.arguments),
            aumid=candidate.aumid,
            publisher=_bounded_optional(candidate.publisher, 200),
            version=_bounded_optional(candidate.version, 100),
            process_identity=process_identity,
            window_identity_rules=window_rules,
            automation_tier=tier,
            application_class=application_class,
            risk_class="system" if application_class is ApplicationClass.SYSTEM_APP else "user",
            installed=target is not None and target_fingerprint is not None,
            enabled=enabled,
            reason=reason,
            preferred_surface=preference,
            semantic_control=False,
            visual_fallback=False,
            login_status=login_status,
            last_verified=datetime.now(UTC).isoformat() if target_reason is None else None,
            target_fingerprint=target_fingerprint,
            owner_disabled=owner_disabled,
        )

    def _validate_candidate_target(
        self,
        candidate: ApplicationCandidate,
    ) -> tuple[Path | None, tuple[int, int, str] | None, str | None]:
        target = candidate.target
        if target is None:
            return None, None, "launch_target_unresolved"
        try:
            path = target.expanduser().resolve(strict=True)
        except (OSError, RuntimeError):
            return None, None, "stale_launch_target"
        if path.is_symlink():
            return None, None, "untrusted_launch_target"
        if path.suffix.casefold() in self._REJECTED_TARGET_SUFFIXES:
            return None, None, "unsafe_launch_target"
        if path.suffix.casefold() not in self._SAFE_EXECUTABLE_SUFFIXES:
            return None, None, "unsupported_launch_target"
        args = tuple(candidate.arguments)
        if candidate.launch_kind is ApplicationLaunchKind.MSIX:
            if path.name.casefold() != "explorer.exe" or not _valid_msix_aumid(candidate.aumid) or not _valid_msix_arguments(args, candidate.aumid or ""):
                return None, None, "msix_identity_invalid"
        elif args and not (candidate.source_id.startswith("legacy:") and candidate.launch_kind is ApplicationLaunchKind.EXE):
            return None, None, "shortcut_arguments_not_allowed"
        try:
            fingerprint = _file_fingerprint(path, self.MAX_HASH_BYTES)
        except OSError:
            return None, None, "launch_target_unreadable"
        return path, fingerprint, None

    def _revalidate_target(self, app: InstalledApplication) -> _TargetIdentity | None:
        target = app.verified_launch_target
        if target is None or app.target_fingerprint is None:
            return None
        try:
            current = _file_fingerprint(target, self.MAX_HASH_BYTES)
        except OSError:
            return None
        if current != app.target_fingerprint:
            return None
        return _TargetIdentity(target, current)

    def _classify(self, display_name: str, target: Path | None) -> ApplicationClass:
        material = _normalize_name(display_name)
        target_name = _normalize_name(target.stem if target else "")
        material_blob = f"{material} {target_name}"
        if any(term in material_blob for term in self._ADMIN_TERMS):
            return ApplicationClass.ADMIN_TOOL
        if any(term in material_blob for term in self._UNINSTALLER_TERMS):
            return ApplicationClass.UNINSTALLER
        if any(term in material_blob for term in self._INSTALLER_TERMS):
            return ApplicationClass.INSTALLER
        if any(term in material_blob for term in self._BACKGROUND_TERMS):
            return ApplicationClass.BACKGROUND_COMPONENT
        if any(term in material_blob for term in self._SYSTEM_TERMS):
            return ApplicationClass.SYSTEM_APP
        return ApplicationClass.USER_APP

    def _dedupe_identity(self, candidate: ApplicationCandidate, app: InstalledApplication) -> str:
        if app.verified_launch_target is not None:
            return f"target:{str(app.verified_launch_target).casefold()}"
        return f"source:{candidate.source_id or app.app_ref}"

    def _merge_duplicate(self, first: InstalledApplication, second: InstalledApplication) -> InstalledApplication:
        aliases = tuple(dict.fromkeys((*first.aliases, *second.aliases)))
        process_identity = tuple(dict.fromkeys((*first.process_identity, *second.process_identity)))
        window_identity_rules = tuple(dict.fromkeys((*first.window_identity_rules, *second.window_identity_rules)))
        preferred = first if first.automation_tier.value <= second.automation_tier.value else second
        return replace(
            preferred,
            aliases=aliases,
            process_identity=process_identity,
            window_identity_rules=window_identity_rules,
            app_ref=first.app_ref,
            owner_disabled=first.owner_disabled or second.owner_disabled,
            preferred_surface=first.preferred_surface if first.preferred_surface is not SurfacePreference.AUTO else second.preferred_surface,
        )

    def _stable_ref(self, display_name: str, candidate: ApplicationCandidate, target: Path | None) -> str:
        material = candidate.aumid if candidate.launch_kind is ApplicationLaunchKind.MSIX and candidate.aumid else str(target).casefold() if target else candidate.source_id or display_name
        digest = hashlib.sha256(f"{_normalize_name(display_name)}|{material}".encode("utf-8")).hexdigest()[:24]
        return f"app-{digest}"

    def _discover_candidates(self) -> Iterable[ApplicationCandidate]:
        count = 0
        for root in self.start_menu_roots:
            for path in _bounded_files(root, self.MAX_FILES_PER_ROOT, self.MAX_ROOT_DEPTH):
                if count >= self.MAX_CANDIDATES:
                    return
                suffix = path.suffix.casefold()
                if suffix == ".lnk":
                    resolved = self._shortcut_resolver(path)
                    source_id = _start_menu_source_id(root, path)
                    if resolved is None:
                        yield ApplicationCandidate(path.stem, ApplicationLaunchKind.SHORTCUT, None, source_id=source_id)
                    else:
                        kind = ApplicationLaunchKind.MSIX if resolved.aumid else ApplicationLaunchKind.SHORTCUT
                        yield ApplicationCandidate(
                            path.stem,
                            kind,
                            resolved.target,
                            source_id=source_id,
                            arguments=resolved.arguments,
                            aumid=resolved.aumid,
                        )
                    count += 1
                elif suffix == ".exe":
                    yield ApplicationCandidate(path.stem, ApplicationLaunchKind.EXE, path, source_id=_start_menu_source_id(root, path))
                    count += 1
        for candidate in self._app_paths_reader():
            if count >= self.MAX_CANDIDATES:
                return
            yield candidate
            count += 1
        for candidate in self._legacy_candidates():
            if count >= self.MAX_CANDIDATES:
                return
            yield candidate
            count += 1

    def _legacy_candidates(self) -> Iterable[ApplicationCandidate]:
        executable_names = {
            "code": "code.exe",
            "notepad": "notepad.exe",
            "calculator": "calc.exe",
            "brave": "brave.exe",
            "explorer": "explorer.exe",
        }
        for display_name, executable in executable_names.items():
            target = shutil.which(executable)
            if target is None and display_name in {"notepad", "calculator", "explorer"}:
                windows_dir = os.getenv("WINDIR")
                if windows_dir:
                    system_target = Path(windows_dir) / "System32" / executable
                    if system_target.is_file():
                        target = str(system_target)
            if target is None:
                continue
            args = ("--new-window",) if display_name == "brave" else ()
            yield ApplicationCandidate(
                display_name.title() if display_name != "brave" else "Brave",
                ApplicationLaunchKind.EXE,
                Path(target),
                aliases=self._LEGACY_EXECUTABLES.get(display_name, (display_name,)),
                source_id=f"legacy:{display_name}",
                arguments=args,
            )

    @staticmethod
    def _default_start_menu_roots() -> tuple[Path, ...]:
        roots: list[Path] = []
        appdata = os.getenv("APPDATA")
        programdata = os.getenv("PROGRAMDATA")
        if appdata:
            roots.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
        if programdata:
            roots.append(Path(programdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
        return tuple(dict.fromkeys(roots))

    def _read_app_paths(self) -> Iterable[ApplicationCandidate]:
        if os.name != "nt":
            return ()
        try:
            import winreg
        except ImportError:
            return ()
        output: list[ApplicationCandidate] = []
        root_spec = (
            (winreg.HKEY_CURRENT_USER, "hkcu"),
            (winreg.HKEY_LOCAL_MACHINE, "hklm"),
        )
        base = r"Software\Microsoft\Windows\CurrentVersion\App Paths"
        for hive, hive_name in root_spec:
            try:
                with winreg.OpenKey(hive, base, 0, winreg.KEY_READ) as parent:
                    subkey_count = min(int(winreg.QueryInfoKey(parent)[0]), self.MAX_FILES_PER_ROOT)
                    for index in range(subkey_count):
                        try:
                            key_name = str(winreg.EnumKey(parent, index))
                            with winreg.OpenKey(parent, key_name, 0, winreg.KEY_READ) as child:
                                raw_target = winreg.QueryValueEx(child, "")[0]
                        except (OSError, TypeError):
                            continue
                        target = _parse_exact_executable_value(raw_target)
                        output.append(ApplicationCandidate(Path(key_name).stem, ApplicationLaunchKind.EXE, target, source_id=f"{hive_name}:{key_name}"))
            except OSError:
                continue
        return tuple(output)

    def _load_settings(self) -> None:
        if self.settings_path is None or not self.settings_path.is_file():
            return
        try:
            raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
            disabled = raw.get("disabled_app_refs", []) if isinstance(raw, dict) else []
            preferences = raw.get("surface_preferences", {}) if isinstance(raw, dict) else {}
            if isinstance(disabled, list):
                self._disabled_refs = {item for item in disabled if isinstance(item, str) and item.startswith("app-") and len(item) <= 40}
            if isinstance(preferences, dict):
                for app_ref, value in preferences.items():
                    if isinstance(app_ref, str) and app_ref.startswith("app-") and isinstance(value, str):
                        try:
                            self._surface_preferences[app_ref] = SurfacePreference(value)
                        except ValueError:
                            continue
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self._disabled_refs.clear()
            self._surface_preferences.clear()

    def _save_settings(self) -> None:
        if self.settings_path is None:
            return
        payload = {
            "disabled_app_refs": sorted(self._disabled_refs),
            "surface_preferences": {key: value.value for key, value in sorted(self._surface_preferences.items())},
        }
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.settings_path.with_name(f".{self.settings_path.name}.tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        temporary.replace(self.settings_path)


def _bounded_files(root: Path, maximum: int, max_depth: int) -> Iterable[Path]:
    if not root.is_dir():
        return ()
    output: list[Path] = []
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack and len(output) < maximum:
        current, depth = stack.pop()
        try:
            entries = sorted(os.scandir(current), key=lambda entry: entry.name.casefold())
        except OSError:
            continue
        for entry in entries:
            if len(output) >= maximum:
                break
            try:
                if entry.is_dir(follow_symlinks=False) and depth < max_depth:
                    stack.append((Path(entry.path), depth + 1))
                elif entry.is_file(follow_symlinks=False) and Path(entry.name).suffix.casefold() in {".lnk", ".exe"}:
                    output.append(Path(entry.path))
            except OSError:
                continue
    return tuple(output)


def _start_menu_source_id(root: Path, path: Path) -> str:
    """Return a stable internal source identity without exposing filesystem paths."""

    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = Path(path.name)
    return f"start-menu:{str(relative).replace(chr(92), '/')}"


def _normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value)).casefold().strip()
    return " ".join(_NORMALIZE_NON_WORD.sub(" ", normalized).split())


def _canonical_name(value: str) -> str:
    return _normalize_name(value)


def _bounded_name(value: str) -> str:
    return " ".join(str(value).replace(" - Shortcut", "").split())[:120].strip()


def _bounded_optional(value: str | None, maximum: int) -> str | None:
    if value is None:
        return None
    clean = " ".join(str(value).split())
    return clean[:maximum] or None


def _aliases_for(display_name: str, aliases: Iterable[str]) -> tuple[str, ...]:
    values = [display_name, *aliases]
    normalized_display = _normalize_name(display_name)
    values.extend(InstalledApplicationRegistry._KNOWN_ALIASES.get(normalized_display, ()))
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = " ".join(str(value).split())[:100].strip()
        normalized = _normalize_name(clean)
        if clean and normalized and normalized not in seen:
            result.append(clean)
            seen.add(normalized)
    return tuple(result)


def _file_fingerprint(path: Path, max_bytes: int) -> tuple[int, int, str]:
    stat = path.stat()
    if not path.is_file() or stat.st_size > max_bytes:
        raise OSError("launch_target_too_large_or_not_file")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return int(stat.st_size), int(stat.st_mtime_ns), digest.hexdigest()


def _parse_exact_executable_value(raw: object) -> Path | None:
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value:
        return None
    if value.startswith('"'):
        closing = value.find('"', 1)
        if closing < 0 or value[closing + 1 :].strip():
            return None
        value = value[1:closing]
    elif any(char.isspace() for char in value):
        return None
    return Path(value)


def _valid_msix_aumid(value: str | None) -> bool:
    return isinstance(value, str) and bool(InstalledApplicationRegistry._MSIX_AUMID.fullmatch(value))


def _valid_msix_arguments(arguments: tuple[str, ...], aumid: str) -> bool:
    return arguments == (f"shell:AppsFolder\\{aumid}",)


def _resolve_windows_shortcut(path: Path) -> ShortcutTarget | None:
    """Resolve a .lnk through IShellLink without invoking a shell command."""

    if os.name != "nt":
        return None
    try:
        ole32 = ctypes.WinDLL("ole32.dll")
        shell32 = ctypes.WinDLL("shell32.dll")
    except (AttributeError, OSError):
        return None
    shell_link = ctypes.c_void_p()
    persist_file = ctypes.c_void_p()
    initialized = False
    try:
        ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        ole32.CoInitializeEx.restype = ctypes.c_long
        ole32.CoUninitialize.argtypes = []
        ole32.CoUninitialize.restype = None
        hr = ole32.CoInitializeEx(None, 0x2)
        initialized = hr in (0, 1, 0x00000001)
        if not initialized:
            return None
        clsid = _guid("00021401-0000-0000-C000-000000000046")
        iid_shell_link = _guid("000214F9-0000-0000-C000-000000000046")
        iid_persist_file = _guid("0000010b-0000-0000-C000-000000000046")
        ole32.CoCreateInstance.argtypes = [ctypes.POINTER(_GUID), ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
        ole32.CoCreateInstance.restype = ctypes.c_long
        if ole32.CoCreateInstance(ctypes.byref(clsid), None, 0x1, ctypes.byref(iid_shell_link), ctypes.byref(shell_link)) != 0:
            return None
        query_interface = _com_method(shell_link, 0, ctypes.c_long, [ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)])
        if query_interface(shell_link, ctypes.byref(iid_persist_file), ctypes.byref(persist_file)) != 0:
            return None
        load = _com_method(persist_file, 5, ctypes.c_long, [wintypes.LPCWSTR, wintypes.DWORD])
        if load(persist_file, str(path), 0) != 0:
            return None
        target_buffer = ctypes.create_unicode_buffer(32_768)
        get_path = _com_method(shell_link, 3, ctypes.c_long, [wintypes.LPWSTR, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD])
        if get_path(shell_link, target_buffer, len(target_buffer), None, 0) != 0 or not target_buffer.value:
            return None
        arguments_buffer = ctypes.create_unicode_buffer(8_192)
        get_arguments = _com_method(shell_link, 10, ctypes.c_long, [wintypes.LPWSTR, ctypes.c_int])
        if get_arguments(shell_link, arguments_buffer, len(arguments_buffer)) != 0:
            return None
        arguments = arguments_buffer.value.strip()
        if not arguments:
            return ShortcutTarget(Path(target_buffer.value))
        if target_buffer.value.casefold().endswith("explorer.exe") and arguments.startswith("shell:AppsFolder\\"):
            aumid = arguments.removeprefix("shell:AppsFolder\\")
            if _valid_msix_aumid(aumid):
                return ShortcutTarget(Path(target_buffer.value), (f"shell:AppsFolder\\{aumid}",), aumid)
        return ShortcutTarget(Path(target_buffer.value), (arguments,))
    except (OSError, ValueError, TypeError):
        return None
    finally:
        for pointer in (persist_file, shell_link):
            if not pointer or not pointer.value:
                continue
            try:
                _com_method(pointer, 2, ctypes.c_ulong, [])(pointer)
            except (AttributeError, OSError, TypeError, ValueError):
                pass
        if initialized:
            try:
                ole32.CoUninitialize()
            except (AttributeError, OSError):
                pass


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid(value: str) -> _GUID:
    parsed = UUID(value)
    data4 = (ctypes.c_ubyte * 8).from_buffer_copy(parsed.bytes[8:])
    return _GUID(parsed.time_low, parsed.time_mid, parsed.time_hi_version, data4)


def _com_method(pointer: ctypes.c_void_p, index: int, restype: object, arguments: list[object]):
    vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    address = vtable[index]
    function = ctypes.CFUNCTYPE(restype, ctypes.c_void_p, *arguments)(address)
    return function
