"""Development/setup-only EasyOCR model provisioning (Batch 06, R18B05-001).

This script is NOT a production tool. It is never imported by, registered
as, or automatically triggered from `computer.visual.read`, any other
Computer Use capability, or core JARVIS startup - production OCR
initialization (`src/jarvis/computer/visual_ocr.py`) always passes
`download_enabled=False` and fails closed (`visual_ocr_models_unavailable`)
rather than ever reaching a code path that could download anything.

Its only job is to download and checksum-verify the exact two EasyOCR
1.7.2 model weight files JARVIS's production visual-OCR adapter needs for
`Reader(["ar", "en"], detect_network="craft")`, into a directory the owner
explicitly configures - and nothing else. Run it once, by hand, as a
developer/setup step:

    python scripts/setup/provision_easyocr_models.py --model-dir <path>

Then point the running JARVIS instance at that directory:

    JARVIS_OCR_MODEL_DIR=<path>   (or JarvisConfig.ocr_model_dir)

Model weights are never committed to Git - the target directory must live
outside the repository. Re-running this script is safe and idempotent: an
already-present, checksum-valid file is left untouched; a missing or
checksum-invalid one is (re-)downloaded.

Model/checksum evidence (recorded here, not re-derived at runtime) was
read directly from `easyocr.config.detection_models["craft"]` and
`easyocr.config.recognition_models["gen1"]["arabic_g1"]` at EasyOCR 1.7.2 -
this is the exact same source EasyOCR's own (disabled-in-production)
downloader would use.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

# (kind, filename, download URL, expected MD5) - the only two files
# production `EasyOcrVisualAdapter._models_ready()` checks for.
_REQUIRED_MODELS = (
    {
        "kind": "detection (craft)",
        "filename": "craft_mlt_25k.pth",
        "url": "https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/craft_mlt_25k.zip",
        "md5": "2f8227d2def4037cdb3b34389dcf9ec1",
    },
    {
        "kind": "recognition (arabic_g1 - auto-selected for lang_list=['ar','en'])",
        "filename": "arabic.pth",
        "url": "https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/arabic.zip",
        "md5": "993074555550e4e06a6077d55ff0449a",
    },
)

# Must match `pyproject.toml`'s `computer-ocr` extra exactly (R18B05-002) -
# kept here too so this script can warn about drift without importing
# anything from the `jarvis` package itself.
_PINNED_VERSIONS = {"easyocr": "1.7.2", "torch": "2.14.0", "torchvision": "0.29.0"}


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_and_extract(url: str, expected_filename: str, dest_dir: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="jarvis_ocr_provision_") as tmp_text:
        tmp = Path(tmp_text)
        archive_path = tmp / "model.zip"
        print(f"  downloading {url}")
        urllib.request.urlretrieve(url, archive_path)  # noqa: S310 - explicit one-time setup action, never called from any runtime path
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(tmp)
        extracted = tmp / expected_filename
        if not extracted.is_file():
            raise RuntimeError(f"expected '{expected_filename}' was not present in the downloaded archive from {url}")
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(extracted), str(dest_dir / expected_filename))


def _check_runtime_versions() -> list[str]:
    problems: list[str] = []
    try:
        import easyocr
        version = getattr(easyocr, "__version__", "unknown")
        if version != _PINNED_VERSIONS["easyocr"]:
            problems.append(f"easyocr {version} != pinned {_PINNED_VERSIONS['easyocr']}")
    except ImportError:
        problems.append("easyocr is not installed (install the 'computer-ocr' extra first)")
    try:
        import torch
        version = torch.__version__
        if not version.startswith(_PINNED_VERSIONS["torch"]):
            problems.append(f"torch {version} != pinned {_PINNED_VERSIONS['torch']}")
        if torch.version.cuda is not None:
            problems.append(f"torch resolved a CUDA build (torch.version.cuda={torch.version.cuda}) - a CPU-only build is required")
    except ImportError:
        problems.append("torch is not installed (install the 'computer-ocr' extra first)")
    try:
        import torchvision
        version = torchvision.__version__
        if not version.startswith(_PINNED_VERSIONS["torchvision"]):
            problems.append(f"torchvision {version} != pinned {_PINNED_VERSIONS['torchvision']}")
    except ImportError:
        problems.append("torchvision is not installed (install the 'computer-ocr' extra first)")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--model-dir",
        default=os.getenv("JARVIS_OCR_MODEL_DIR", "").strip() or None,
        help="Target directory (defaults to $JARVIS_OCR_MODEL_DIR) - must be set explicitly; there is no implicit home-directory location.",
    )
    parser.add_argument("--verify-only", action="store_true", help="Only verify existing files/runtime versions; never download.")
    parser.add_argument("--skip-runtime-check", action="store_true", help="Skip the torch/torchvision/easyocr pinned-version check.")
    args = parser.parse_args(argv)

    if not args.model_dir:
        print("error: --model-dir (or $JARVIS_OCR_MODEL_DIR) must be set explicitly - no implicit home-directory location is used.", file=sys.stderr)
        return 2

    model_root = Path(args.model_dir)
    model_storage_directory = model_root / "model"
    user_network_directory = model_root / "user_network"
    if not args.verify_only:
        user_network_directory.mkdir(parents=True, exist_ok=True)

    ok = True
    for entry in _REQUIRED_MODELS:
        target = model_storage_directory / entry["filename"]
        if target.is_file() and _md5(target) == entry["md5"]:
            print(f"  OK       {entry['filename']} ({entry['kind']}) already present, checksum verified")
            continue
        if args.verify_only:
            print(f"  MISSING  {entry['filename']} ({entry['kind']})")
            ok = False
            continue
        if target.is_file():
            print(f"  existing {entry['filename']} failed checksum verification - re-provisioning")
            target.unlink()
        _download_and_extract(entry["url"], entry["filename"], model_storage_directory)
        actual_md5 = _md5(target)
        if actual_md5 != entry["md5"]:
            print(f"  ERROR    {entry['filename']} checksum mismatch after download (got {actual_md5}, expected {entry['md5']})", file=sys.stderr)
            ok = False
            continue
        print(f"  OK       {entry['filename']} ({entry['kind']}) provisioned, checksum verified")

    if not args.skip_runtime_check:
        for problem in _check_runtime_versions():
            print(f"  WARNING  {problem}", file=sys.stderr)
            ok = False

    print()
    if ok:
        print(f"Provisioning complete. Set JARVIS_OCR_MODEL_DIR={model_root} for the JARVIS runtime to use these models offline.")
        return 0
    print("Provisioning incomplete - see warnings/errors above.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
