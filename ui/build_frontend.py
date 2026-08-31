"""Build the local React Command Center into deterministic package assets."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "ui"
SOURCE = FRONTEND / "dist"
TARGET = ROOT / "src" / "jarvis" / "ui_static"
ASSETS = ("index.html", "styles.css", "app.js")


def main() -> None:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        raise SystemExit("npm is required to build the local React frontend")
    if not (FRONTEND / "node_modules" / "vite" / "package.json").is_file():
        install = subprocess.run([npm, "ci", "--ignore-scripts"], cwd=FRONTEND, check=False)
        if install.returncode:
            raise SystemExit(install.returncode)
    result = subprocess.run([npm, "run", "build"], cwd=FRONTEND, check=False)
    if result.returncode:
        raise SystemExit(result.returncode)
    TARGET.mkdir(parents=True, exist_ok=True)
    for path in TARGET.iterdir():
        if path.is_file():
            path.unlink()
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
