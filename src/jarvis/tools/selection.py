"""Deterministic model-facing tool selection without authority decisions."""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable

from .registry import ToolRegistry, ToolSpec


_ARABIC_NORMALIZATION = str.maketrans({
    "أ": "ا",
    "إ": "ا",
    "آ": "ا",
    "ى": "ي",
})
_LATIN_WORD = re.compile(r"(?<![A-Za-z0-9_]){term}(?![A-Za-z0-9_])")


def normalize_intent(intent: str) -> str:
    """Normalize only the selector's matching view; preserve the user text."""

    normalized = intent.translate(_ARABIC_NORMALIZATION).replace("ـ", "")
    normalized = unicodedata.normalize("NFD", normalized)
    normalized = "".join(character for character in normalized if unicodedata.category(character) != "Mn")
    normalized = unicodedata.normalize("NFC", normalized).casefold()
    return " ".join(normalized.split())


class ToolSchemaSelector:
    """Select a bounded view of registered tools from trusted user intent only."""

    MAX_MODEL_TOOLS = 8
    VISUAL_TOOLS = ("desktop.context.read", "screen.observe", "screen.latest")
    ARABIC_METADATA_TOOLS = ("desktop.context.read",)
    COMPUTER_TOOLS = (
        "desktop.context.read",
        "computer.window.control",
        "computer.keyboard.type",
        "computer.clipboard.read",
        "computer.clipboard.write",
        "computer.audio.adjust",
    )
    STATUS_TOOLS = ("status.read",)
    ENGINEERING_TOOLS = ("project.tests.run",)
    VISUAL_MARKERS = (
        "screen", "desktop", "active application", "active window", "current window",
        "what is on", "look at", "see what", "which application is active",
        "شوف الشاشة", "بص على الشاشة", "بص للشاشة", "ايه اللي على الشاشة", "ايه اللي قدامي",
        "شوف اللي قدامي", "بص على الويندو", "بص على النافذة", "السكرين", "شوف الscreen",
        "بص على الwindow",
    )
    COMPUTER_MARKERS = (
        "keyboard", "typing", "clipboard", "window", "minimize", "maximize", "restore",
        "volume", "mute", "audio", "اكتب", "اكتبلي", "اكتب لي", "اكتب الكلام ده", "اكتب ده",
        "تايب", "كيبورد", "كليب بورد", "الكليب بورد", "انسخ", "حط في الكليب بورد",
        "حطه في الclipboard", "صغر الويندو", "صغر النافذة", "كبر الويندو", "كبر النافذة",
        "رجع الويندو", "وطي الصوت", "علي الصوت", "ارفع الصوت", "اخفض الصوت", "اقفل الصوت",
        "اكتم الصوت", "فك الميوت", "علي الvolume", "ميوت",
    )
    STATUS_MARKERS = ("status", "health", "ready", "state", "الحالة", "حالتك", "السيستم شغال", "النظام شغال", "جاهز", "انت جاهز")
    ENGINEERING_MARKERS = (
        "run the tests", "run tests", "test the project", "execute tests", "unit tests",
        "شغل التستات", "رن التستات", "شغل tests", "اعمل test للمشروع", "اختبر المشروع",
        "شغل الunit tests",
    )

    def __init__(self, registry: ToolRegistry, *, max_model_tools: int = MAX_MODEL_TOOLS) -> None:
        if not 1 <= max_model_tools <= self.MAX_MODEL_TOOLS:
            raise ValueError("max_model_tools_out_of_bounds")
        self.registry = registry
        self.max_model_tools = max_model_tools

    def select(self, intent: str) -> tuple[dict[str, object], ...]:
        lowered = normalize_intent(intent)
        available = {spec.name: spec for spec in self.registry.list() if spec.enabled}
        names: list[str] = []

        for name in sorted(available):
            if name.casefold() in lowered:
                names.append(name)
        if self._matches_any(lowered, self.VISUAL_MARKERS):
            names.extend(self.ARABIC_METADATA_TOOLS if self._has_arabic_script(lowered) else self.VISUAL_TOOLS)
        if self._matches_computer(lowered):
            names.extend(self.COMPUTER_TOOLS)
        if self._matches_any(lowered, self.STATUS_MARKERS):
            names.extend(self.STATUS_TOOLS)
        if self._matches_any(lowered, self.ENGINEERING_MARKERS):
            names.extend(self.ENGINEERING_TOOLS)

        selected: list[ToolSpec] = []
        seen: set[str] = set()
        for name in names:
            spec = available.get(name)
            if spec is None or name in seen:
                continue
            seen.add(name)
            selected.append(spec)
            if len(selected) >= self.max_model_tools:
                break
        return tuple(self._schema(spec) for spec in selected)

    @staticmethod
    def _matches_any(intent: str, markers: Iterable[str]) -> bool:
        return any(ToolSchemaSelector._matches(intent, marker) for marker in markers)

    @staticmethod
    def _matches(intent: str, marker: str) -> bool:
        marker = normalize_intent(marker)
        if any("\u0600" <= character <= "\u06ff" for character in marker):
            return marker in intent
        return bool(re.search(_LATIN_WORD.pattern.replace("{term}", re.escape(marker)), intent))

    @classmethod
    def _matches_computer(cls, intent: str) -> bool:
        if cls._matches_any(intent, cls.COMPUTER_MARKERS):
            return True
        if not cls._matches(intent, "type"):
            return False
        return not cls._matches(intent, "what type")

    @staticmethod
    def _has_arabic_script(intent: str) -> bool:
        return any("\u0600" <= character <= "\u06ff" for character in intent)

    @staticmethod
    def _schema(spec: ToolSpec) -> dict[str, object]:
        description = spec.description
        if spec.name == "desktop.context.read":
            description = (
                f"{description} Read the current screen's active application or window metadata. "
                "Use this tool first for identifying what is open; do not call screen.observe or "
                "screen.latest unless pixels, a region, or a cached screen observation is requested. "
                "For Arabic or mixed requests such as 'شوف الشاشة', 'إيه اللي قدامي؟', or "
                "'شوف الscreen', call this tool first."
            )
        elif spec.name == "screen.observe":
            description = (
                f"{description} Use only when the user explicitly requests screen pixels or a region. "
                "Do not call this for identifying the active application or window; use "
                "desktop.context.read instead, including Arabic requests such as 'شوف الشاشة'."
            )
        elif spec.name == "screen.latest":
            description = (
                f"{description} Use only for an explicitly requested cached screen observation. "
                "Do not call this for identifying the active application or window; use "
                "desktop.context.read instead, including Arabic requests such as 'شوف الشاشة'."
            )
        return {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": description,
                "parameters": spec.json_schema(),
            },
        }

    @classmethod
    def schema_bytes(cls, schemas: Iterable[dict[str, object]]) -> int:
        return len(json.dumps(tuple(schemas), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
