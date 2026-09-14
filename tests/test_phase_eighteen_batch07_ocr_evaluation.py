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

    def test_character_recall_is_sequence_aware_and_normalizes_unicode_whitespace(self) -> None:
        cases = (
            ("JARVIS OCR", "JARVIS OCR", 1.0),
            ("JARVIS OCR", "  JARVIS\tOCR\n", 1.0),
            ("abc", "abxc", 0.75),
            ("abc", "ac", 0.667),
            ("abc", "axc", 0.667),
        )
        for expected, actual, similarity in cases:
            with self.subTest(expected=expected, actual=actual):
                self.assertEqual(self.runner._char_recall(expected, actual), similarity)

        self.assertLess(self.runner._char_recall("abc", "acb"), 1.0)
        self.assertLess(self.runner._char_recall("abc", "cba"), 1.0)
        self.assertEqual(self.runner._char_recall("", ""), 1.0)
        self.assertEqual(self.runner._char_recall("", "anything"), 0.0)
        self.assertEqual(self.runner._char_recall("Arabic", ""), 0.0)
        self.assertEqual(
            self.runner._char_recall(
                self.runner.LABEL_ARABIC_GREETING,
                f"\t{self.runner.LABEL_ARABIC_GREETING}\n",
            ),
            1.0,
        )

    def test_region_scoring_preserves_actual_text_and_best_recall(self) -> None:
        regions = [
            {"text": "JARMIS OCR fixture ready", "confidence": 0.46},
            {"text": "unrelated", "confidence": 0.99},
        ]

        scored = self.runner._score_expected_region(regions, "JARVIS OCR fixture ready")

        self.assertEqual(scored["expected"], "JARVIS OCR fixture ready")
        self.assertEqual(scored["actual_text"], "JARMIS OCR fixture ready")
        self.assertEqual(scored["confidence"], 0.46)
        self.assertEqual(scored["normalized_character_recall"], 0.958)
        self.assertFalse(scored["matched_exactly"])

    def test_candidate_names_are_explicit_and_bounded(self) -> None:
        self.assertEqual(
            self.runner.OCR_CANDIDATES,
            ("combined_ar_en", "english_only", "combined_then_english"),
        )
        with self.assertRaises(ValueError):
            self.runner._validate_candidate("free_form_router")

    def test_visual_target_matching_returns_only_opaque_refs(self) -> None:
        regions = [
            {"visual_ref": "visual-first", "text": "VISUAL APPLY", "confidence": 0.98},
            {"visual_ref": "visual-other", "text": "other", "confidence": 0.99},
        ]
        self.assertEqual(
            self.runner._visual_ref_matches(regions, " visual\tapply "),
            ["visual-first"],
        )

    def test_visual_actuation_main_is_explicitly_three_run_gated(self) -> None:
        source = RUNNER_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("_visual_actuation_main", source)
        self.assertIn('"three_clean_physical_iterations"', source)
        self.assertIn('"visual_target_ambiguous"', source)
        self.assertIn('"native_input_injection_failed"', source)

    def test_candidate_model_files_are_explicit(self) -> None:
        self.assertEqual(
            self.runner._candidate_model_files("combined_ar_en"),
            ("craft_mlt_25k.pth", "arabic.pth"),
        )
        self.assertEqual(
            self.runner._candidate_model_files("english_only"),
            ("craft_mlt_25k.pth", "english_g2.pth"),
        )
        self.assertEqual(
            self.runner._candidate_model_files("combined_then_english"),
            ("craft_mlt_25k.pth", "arabic.pth", "english_g2.pth"),
        )

    def test_combined_then_english_merge_preserves_arabic_and_chooses_better_latin(self) -> None:
        def region(x: int, text: str, confidence: float) -> tuple[list[list[int]], str, float]:
            return ([[x, 0], [x + 20, 0], [x + 20, 10], [x, 10]], text, confidence)

        merged = self.runner._merge_combined_then_english_regions(
            [
                region(0, "\u0645\u0631\u062d\u0628\u0627", 0.96),
                region(50, "JARV1S", 0.40),
            ],
            [
                region(0, "MARHABA", 0.99),
                region(50, "JARVIS", 0.85),
                region(100, "EXTRA", 0.70),
            ],
        )

        self.assertEqual([item[1] for item in merged], ["\u0645\u0631\u062d\u0628\u0627", "JARVIS", "EXTRA"])

    def test_combined_then_english_reader_runs_exactly_two_passes(self) -> None:
        class Reader:
            def __init__(self, text: str, confidence: float) -> None:
                self.text = text
                self.confidence = confidence
                self.calls = 0

            def readtext(self, _image: object, *, detail: int) -> list[tuple[list[list[int]], str, float]]:
                self.calls += 1
                return [([[0, 0], [20, 0], [20, 10], [0, 10]], self.text, self.confidence)]

        combined = Reader("JARV1S", 0.4)
        english = Reader("JARVIS", 0.9)
        timing: dict[str, object] = {}
        wrapper = self.runner._CombinedThenEnglishReader(combined, lambda: english, timing)

        result = wrapper.readtext(object())

        self.assertEqual(combined.calls, 1)
        self.assertEqual(english.calls, 1)
        self.assertEqual(result[0][1], "JARVIS")
        self.assertEqual(timing["candidate_pass_records"][0]["pass_count"], 2)

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

    def test_candidate_model_metadata_reports_explicit_disk_footprint(self) -> None:
        with tempfile.TemporaryDirectory(prefix="jarvis_batch07_ocr_models_") as raw_root:
            root = Path(raw_root)
            model_dir = root / "model"
            (root / "user_network").mkdir()
            model_dir.mkdir()
            (model_dir / "craft_mlt_25k.pth").write_bytes(b"craft")
            (model_dir / "arabic.pth").write_bytes(b"arabic-weight")

            metadata = self.runner._candidate_model_metadata(raw_root, "combined_ar_en")

            self.assertEqual(
                metadata,
                [
                    {"name": "craft_mlt_25k.pth", "size_bytes": 5},
                    {"name": "arabic.pth", "size_bytes": 13},
                ],
            )

    def test_memory_delta_is_explicit_and_handles_unavailable_snapshots(self) -> None:
        self.assertEqual(
            self.runner._memory_delta(
                {"working_set_bytes": 100},
                {"working_set_bytes": 175},
            ),
            75,
        )
        self.assertIsNone(self.runner._memory_delta(None, {"working_set_bytes": 175}))


if __name__ == "__main__":
    unittest.main()
