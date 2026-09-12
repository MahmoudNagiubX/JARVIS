"""Product-owned, fail-closed approved-root file access policy (GAP-0503).

Subordinate to `PolicyPermissionEngine` - this is not a second permission
authority. It answers exactly one question for every concrete path a
computer file action (`inspect_file`/`search_files`/`open_file`/
`open_folder`) is about to touch:

    is this path within an owner-approved root, not a sensitive path,
    and not an escape (symlink/junction/`..`) outside that root?

With no configured roots, every path-requiring operation is denied
(`file_root_not_configured`) - an intentional security tightening, never a
silent fallback to unrestricted access.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

MAX_ROOTS = 20
MAX_SEARCH_MATCHES = 100
MAX_SEARCH_CANDIDATES_SCANNED = 5_000

# Credential/key-store directory names, denied wherever they appear as a
# path component - defense in depth even nested under an approved root.
_SENSITIVE_DIR_NAMES = frozenset({".ssh", ".gnupg", ".aws", ".azure", ".kube"})

# Exact (casefolded) filenames that are always sensitive. ".env.example" is
# deliberately absent - it is a safe template, not a secret.
_SENSITIVE_FILE_NAMES = frozenset({
    ".env", ".env.local", ".env.development", ".env.production", ".env.test",
    "login data", "cookies", "web data",
})
_SENSITIVE_FILE_SUFFIXES = (".pem", ".key", ".pfx", ".p12", ".ppk")
_SENSITIVE_FILE_STEMS = frozenset({"id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"})
# Path substrings (already casefolded, backslash-normalized) recognizable as
# OS credential/security stores.
_SENSITIVE_PATH_SUBSTRINGS = (
    "\\windows\\system32\\config\\",
    "\\microsoft\\credentials\\",
    "\\microsoft\\protect\\",
    "\\microsoft\\crypto\\",
)

# Root-level environment variables that must never themselves be *approved
# as a root* - each names a location broad enough that approving it defeats
# confinement entirely (Section 8.2 of the Batch 03 task).
_FORBIDDEN_ROOT_ENV_VARS = ("APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "WINDIR", "SYSTEMROOT", "PROGRAMFILES", "PROGRAMFILES(X86)")
_FORBIDDEN_ROOT_DIRECT_CHILD_NAMES = frozenset({"windows", "programdata", "program files", "program files (x86)", "users"})


@dataclass(frozen=True, slots=True)
class FileAccessDecision:
    allowed: bool
    reason_code: str | None = None
    resolved_path: Path | None = None


def _is_forbidden_root(path: Path) -> bool:
    """A configured root may not itself be an entire drive, the user's home
    directory, or one of the other classic overly-broad system locations -
    approving any of these would defeat root confinement (Section 8.2)."""
    if path.parent == path:  # a bare drive root, e.g. C:\
        return True
    try:
        if path == Path.home().resolve():
            return True
    except OSError:
        pass
    if len(path.parts) == 2 and path.parts[-1].casefold() in _FORBIDDEN_ROOT_DIRECT_CHILD_NAMES:
        return True
    for env_var in _FORBIDDEN_ROOT_ENV_VARS:
        value = os.environ.get(env_var)
        if not value:
            continue
        try:
            if path == Path(value).resolve():
                return True
        except OSError:
            continue
    return False


def _is_sensitive(path: Path) -> bool:
    parts_casefold = {part.casefold() for part in path.parts}
    if parts_casefold & _SENSITIVE_DIR_NAMES:
        return True
    name_casefold = path.name.casefold()
    if name_casefold in _SENSITIVE_FILE_NAMES:
        return True
    if name_casefold.endswith(_SENSITIVE_FILE_SUFFIXES):
        return True
    if path.stem.casefold() in _SENSITIVE_FILE_STEMS:
        return True
    path_casefold = str(path).casefold()
    return any(substring in path_casefold for substring in _SENSITIVE_PATH_SUBSTRINGS)


@dataclass(slots=True)
class FileAccessPolicy:
    roots: tuple[Path, ...] = field(default_factory=tuple)

    @classmethod
    def from_config_roots(cls, raw_roots: tuple[str, ...]) -> "FileAccessPolicy":
        normalized: list[Path] = []
        seen: set[str] = set()
        for raw in raw_roots:
            if not isinstance(raw, str) or not raw.strip():
                continue
            try:
                resolved = Path(raw).expanduser().resolve()
            except OSError:
                continue
            key = str(resolved).casefold()
            if key in seen:
                continue
            if _is_forbidden_root(resolved):
                continue
            if not resolved.is_dir():
                continue
            seen.add(key)
            normalized.append(resolved)
            if len(normalized) >= MAX_ROOTS:
                break
        return cls(tuple(normalized))

    def configured(self) -> bool:
        return bool(self.roots)

    def status(self) -> dict[str, object]:
        """Bounded, model-safe status - never the actual root strings."""
        return {"configured": self.configured(), "root_count": len(self.roots)}

    def _containing_root(self, resolved: Path) -> Path | None:
        for root in self.roots:
            try:
                resolved.relative_to(root)
                return root
            except ValueError:
                continue
        return None

    def evaluate(self, raw_path: str) -> FileAccessDecision:
        if not self.roots:
            return FileAccessDecision(False, "file_root_not_configured")
        if not isinstance(raw_path, str) or not raw_path.strip():
            return FileAccessDecision(False, "file_path_escape_denied")
        try:
            # Path.resolve() on Windows follows symlinks/junctions to their
            # real target (via GetFinalPathNameByHandleW when the path
            # exists) - a path that physically resolves outside an approved
            # root is denied below regardless of how it was reached.
            resolved = Path(raw_path).expanduser().resolve()
        except OSError:
            return FileAccessDecision(False, "file_path_escape_denied")
        if self._containing_root(resolved) is None:
            return FileAccessDecision(False, "file_path_outside_allowed_root")
        if _is_sensitive(resolved):
            return FileAccessDecision(False, "file_sensitive_path_denied")
        return FileAccessDecision(True, None, resolved)

    def evaluate_search_root(self, raw_root: str) -> FileAccessDecision:
        decision = self.evaluate(raw_root)
        if not decision.allowed:
            return decision
        assert decision.resolved_path is not None
        if not decision.resolved_path.is_dir():
            return FileAccessDecision(False, "file_path_outside_allowed_root")
        return decision

    def filter_search_results(self, root: Path, candidates) -> tuple[list[str], int]:
        """Re-checks every candidate individually (never trusts bulk
        traversal alone) - a symlink/junction that walks outside the
        approved root is excluded, and sensitive children are silently
        skipped (never named in the returned/filtered-count output)."""
        matches: list[str] = []
        filtered = 0
        scanned = 0
        for candidate in candidates:
            scanned += 1
            if scanned > MAX_SEARCH_CANDIDATES_SCANNED or len(matches) >= MAX_SEARCH_MATCHES:
                break
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            try:
                resolved.relative_to(root)
            except ValueError:
                continue
            if not resolved.is_file():
                continue
            if _is_sensitive(resolved):
                filtered += 1
                continue
            matches.append(str(resolved))
        return matches, filtered
