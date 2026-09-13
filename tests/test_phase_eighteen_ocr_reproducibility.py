"""Batch 06 (R18B05-002): reproducible offline EasyOCR CPU runtime.

DEC-048 accepted EasyOCR 1.7.2 on a CPU-only PyTorch/torchvision runtime as
the physically-evaluated NIGHTFURY configuration. Upstream EasyOCR 1.7.2
leaves `torch` unpinned and `torchvision` broadly constrained, so without a
project-owned pin, a later `pip install .[computer-ocr]` could silently
resolve a different (or, on some platforms/indexes, CUDA-heavy) PyTorch
runtime than the one the accepted evidence was produced on.

This is the project's own deterministic guard against that drift:

- `test_pinned_versions_match_pyproject_extra` always runs, needs no
  optional dependency installed, and simply proves `pyproject.toml`'s
  `computer-ocr` extra still pins the exact recorded versions.
- The remaining tests skip cleanly when the optional `computer-ocr` extra
  is not installed in the running interpreter (the normal case for this
  repository's own `.venv`, matching every other OCR test in this suite),
  and assert the pinned exact versions plus a genuinely CPU-only build
  whenever it *is* installed (e.g. inside an isolated evaluation venv, or a
  future CI lane carrying the extra) - see
  `scripts/setup/provision_easyocr_models.py` for the matching one-time
  setup-side version/CPU-only check.
"""

from __future__ import annotations

import unittest
from pathlib import Path

PINNED_VERSIONS = {"easyocr": "1.7.2", "torch": "2.14.0", "torchvision": "0.29.0"}


class ReproducibleOcrRuntimeTests(unittest.TestCase):
    def test_pinned_versions_match_pyproject_extra(self) -> None:
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        text = pyproject.read_text(encoding="utf-8")
        start = text.index("computer-ocr = [")
        end = text.index("]", start)
        block = text[start:end]
        for package, version in PINNED_VERSIONS.items():
            self.assertIn(
                f'"{package}=={version}"', block,
                f"{package} must stay pinned to exactly {version} in pyproject.toml's computer-ocr extra (DEC-048)",
            )

    def test_installed_easyocr_matches_pinned_version(self) -> None:
        try:
            import easyocr
        except ImportError:
            self.skipTest("easyocr is not installed in this interpreter")
        self.assertEqual(getattr(easyocr, "__version__", None), PINNED_VERSIONS["easyocr"])

    def test_installed_torch_is_the_pinned_cpu_only_build(self) -> None:
        try:
            import torch
        except ImportError:
            self.skipTest("torch is not installed in this interpreter")
        self.assertTrue(
            torch.__version__.startswith(PINNED_VERSIONS["torch"]),
            f"torch {torch.__version__} does not match the pinned {PINNED_VERSIONS['torch']}",
        )
        self.assertIsNone(
            torch.version.cuda,
            "torch resolved a CUDA build - the accepted DEC-048 runtime is CPU-only",
        )

    def test_installed_torchvision_matches_pinned_version(self) -> None:
        try:
            import torchvision
        except ImportError:
            self.skipTest("torchvision is not installed in this interpreter")
        self.assertTrue(
            torchvision.__version__.startswith(PINNED_VERSIONS["torchvision"]),
            f"torchvision {torchvision.__version__} does not match the pinned {PINNED_VERSIONS['torchvision']}",
        )


if __name__ == "__main__":
    unittest.main()
