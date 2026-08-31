"""Verify that the committed/staged tree imports without ignored source files."""

from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD", help="git ref or tree to archive")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "src/jarvis/desktop/secret_store.py"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if tracked.returncode != 0:
        print("secure-store source is not tracked", file=sys.stderr)
        return 1
    archive = subprocess.run(
        ["git", "archive", "--format=tar", args.ref],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if archive.returncode != 0:
        print(archive.stderr.decode(errors="replace"), file=sys.stderr)
        return archive.returncode
    with tempfile.TemporaryDirectory(prefix="jarvis-clean-tree-") as temporary:
        extracted = Path(temporary)
        with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as handle:
            for member in handle.getmembers():
                target = (extracted / member.name).resolve()
                if member.issym() or member.islnk() or (target != extracted and extracted not in target.parents):
                    print("archive member escapes extraction root", file=sys.stderr)
                    return 1
                handle.extract(member, extracted)
        environment = dict(os.environ)
        for key in tuple(environment):
            if key.casefold() == "pythonpath" or key.casefold().startswith("jarvis_voice_"):
                environment.pop(key, None)
        environment["PYTHONPATH"] = str(extracted / "src")
        check = subprocess.run(
            [
                sys.executable,
                "-c",
                "import jarvis.desktop; from jarvis.desktop.lifecycle import JarvisDesktopLifecycle; from jarvis.desktop.secret_store import platform_secret_store; print('OK')",
            ],
            cwd=extracted,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        sys.stdout.write(check.stdout)
        sys.stderr.write(check.stderr)
        return check.returncode if check.returncode else (0 if check.stdout.strip().endswith("OK") else 1)


if __name__ == "__main__":
    raise SystemExit(main())
