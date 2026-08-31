"""Build the dependency-free local Command Center into package assets."""

from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ui" / "src"
TARGET = ROOT / "src" / "jarvis" / "ui_static"
ASSETS = ("index.html", "styles.css", "app.js")


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    for name in ASSETS:
        source = SOURCE / name
        if not source.is_file():
            raise SystemExit(f"missing frontend source: {source}")
        content = source.read_text(encoding="utf-8")
        if "http://" in content or "https://" in content:
            raise SystemExit(f"remote asset reference in {source}")
        shutil.copyfile(source, TARGET / name)
    print(f"built {len(ASSETS)} local JARVIS assets")


if __name__ == "__main__":
    main()
