from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "scripts" / "phase18"
RUNNER_SCRIPT = SCRIPT_DIR / "ocr_visual_acceptance.py"


def _load_runner():
    script_dir_text = str(SCRIPT_DIR)
    if script_dir_text not in sys.path:
        sys.path.insert(0, script_dir_text)
    spec = importlib.util.spec_from_file_location("phase18_batch07_ocr_runner_test_target", RUNNER_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Batch07OcrEvaluationScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = _load_runner()

    def test_character_recall_is_bounded_and_ignores_whitespace(self) -> None:
        self.assertEqual(self.runner._char_recall("JARVIS OCR", "JARMIS   OCR"), 0.889)
        self.assertEqual(self.runner._char_recall("", "anything"), 1.0)
        self.assertEqual(self.runner._char_recall("Arabic", ""), 0.0)

    def test_region_scoring_preserves_actual_text_and_best_recall(self) -> None:
        regions = [
            {"text": "JARMIS OCR fixture ready", "confidence": 0.46},
            {"text": "unrelated", "confidence": 0.99},
        ]

        scored = self.runner._score_expected_region(regions, "JARVIS OCR fixture ready")

        self.assertEqual(scored["expected"], "JARVIS OCR fixture ready")
        self.assertEqual(scored["actual_text"], "JARMIS OCR fixture ready")
        self.assertEqual(scored["confidence"], 0.46)
        self.assertEqual(scored["normalized_character_recall"], 0.952)
        self.assertFalse(scored["matched_exactly"])

    def test_candidate_names_are_explicit_and_bounded(self) -> None:
        self.assertEqual(self.runner.OCR_CANDIDATES, ("combined_ar_en", "english_only"))
        with self.assertRaises(ValueError):
            self.runner._validate_candidate("free_form_router")

    def test_candidate_model_files_are_explicit(self) -> None:
        self.assertEqual(
            self.runner._candidate_model_files("combined_ar_en"),
            ("craft_mlt_25k.pth", "arabic.pth"),
        )
        self.assertEqual(
            self.runner._candidate_model_files("english_only"),
            ("craft_mlt_25k.pth", "english_g2.pth"),
        )

    def test_candidate_model_error_fails_closed_for_missing_weight(self) -> None:
        with tempfile.TemporaryDirectory(prefix="jarvis_batch07_ocr_models_") as raw_root:
            root = Path(raw_root)
            model_dir = root / "model"
            (root / "user_network").mkdir()
            model_dir.mkdir()
            (model_dir / "craft_mlt_25k.pth").write_bytes(b"fixture")
            (model_dir / "arabic.pth").write_bytes(b"fixture")

            self.assertIsNone(self.runner._candidate_model_error(raw_root, "combined_ar_en"))
            self.assertEqual(
                self.runner._candidate_model_error(raw_root, "english_only"),
                "candidate_model_missing:english_g2.pth",
            )


if __name__ == "__main__":
    unittest.main()
