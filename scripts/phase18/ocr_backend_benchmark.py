"""Phase 18 Workstream A Batch 04 Milestone 2 - evidence-first OCR backend
benchmark (evaluation-only, never imported by production).

Generates a small set of JARVIS-owned synthetic fixture images (English,
Arabic, mixed) using an already-installed Windows system font (never a font
file copied into the repo), runs each candidate OCR backend against them,
and reports normalized recall, warm latency, and any errors - never
committing model weights, caches, or generated images.

Run inside an isolated evaluation venv (never the project's own `.venv`,
and never installed as a JARVIS dependency - see
`docs/audits/PHASE_18_WORKSTREAM_A_BATCH_04.md` Section 5 for the full
evaluation writeup and verdict, including exact package versions):

    python ocr_backend_benchmark.py --backend paddleocr --out results.json
    python ocr_backend_benchmark.py --backend rapidocr --out results.json

Result (Batch 04, Python 3.12.10, NIGHTFURY): PaddleOCR 3.7.0 +
paddlepaddle 3.3.1 crashes on every prediction with a reproducible
`NotImplementedError` deep inside PaddlePaddle's CPU oneDNN executor
(unrelated to this script or JARVIS), unfixed by disabling oneDNN via flag
or downgrading paddlepaddle (which then breaks API compatibility with
paddleocr 3.7.0 instead). RapidOCR 3.9.2 runs, but its only available
Arabic recognition tier ("mobile", the same tier for both PP-OCRv4 and
PP-OCRv5 - RapidOCR offers no larger Arabic model) scores well under the
required 0.85 recall gate on the fixture corpus below; RapidOCR's own
Arabic path also reproducibly fails outright without an undeclared
`python-bidi` dependency, exactly matching the concern this batch's task
raised in advance. See the audit for the full per-case evidence.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("ERROR: Pillow not installed in this evaluation venv", file=sys.stderr)
    raise

FIXTURES: dict[str, dict[str, str]] = {
    "english": {
        "JARVIS COMPUTER USE": "jarvis_computer_use.png",
        "Open Settings": "open_settings.png",
        "Save Draft": "save_draft.png",
    },
    "arabic": {
        "مرحبا يا جارفيس": "marhaba_jarvis.png",
        "الإعدادات": "settings_ar.png",
        "حفظ": "save_ar.png",
    },
    "mixed": {
        "JARVIS الإعدادات": "jarvis_mixed.png",
    },
}

# Windows-system fonts already present on the machine - never copied into
# the repo. Segoe UI has broad Arabic + Latin coverage on modern Windows.
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\tahoma.ttf",
]


def _normalize(text: str) -> str:
    """Conservative whitespace/Unicode normalization for accuracy scoring -
    never byte-perfect glyph comparison."""
    normalized = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", normalized).strip()


def _char_recall(expected: str, actual: str) -> float:
    expected_norm = _normalize(expected)
    actual_norm = _normalize(actual)
    if not expected_norm:
        return 1.0
    expected_chars = list(expected_norm.replace(" ", ""))
    actual_chars = list(actual_norm.replace(" ", ""))
    matched = 0
    remaining = list(actual_chars)
    for ch in expected_chars:
        if ch in remaining:
            remaining.remove(ch)
            matched += 1
    return matched / len(expected_chars)


def _pick_font() -> str:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    raise RuntimeError("no known Windows system font found")


def render_fixture_images(out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    font_path = _pick_font()
    font = ImageFont.truetype(font_path, 36)
    paths: dict[str, Path] = {}
    for category, entries in FIXTURES.items():
        for text, filename in entries.items():
            image = Image.new("RGB", (500, 80), "white")
            draw = ImageDraw.Draw(image)
            draw.text((10, 15), text, font=font, fill="black")
            path = out_dir / filename
            image.save(path)
            paths[text] = path
    return paths


def _extract_text(predict_result) -> str:
    """PaddleOCR 3.x `.predict()` returns a list of pipeline result objects
    (dict-like, with `rec_texts`/`rec_scores` keys) - one per input image."""
    texts: list[str] = []
    for page in predict_result:
        rec_texts = page.get("rec_texts") if hasattr(page, "get") else None
        if rec_texts:
            texts.extend(rec_texts)
    return " ".join(texts)


def run_paddleocr(image_paths: dict[str, Path]) -> dict:
    import platform

    result: dict = {"backend": "paddleocr", "python_version": platform.python_version()}
    import paddleocr
    import paddle

    result["paddleocr_version"] = getattr(paddleocr, "__version__", "unknown")
    result["paddle_version"] = getattr(paddle, "__version__", "unknown")
    result["engines"] = {}

    # Two separate engines: English (Latin script) and Arabic (the task's
    # named Arabic PP-OCRv5 mobile recognizer, documented as supporting
    # Arabic+English). No GPU - CPU-only, matching JARVIS's local-only
    # requirement.
    for engine_name, lang in (("english", "en"), ("arabic", "ar")):
        engine_result: dict = {}
        cold_start = time.perf_counter()
        try:
            ocr = paddleocr.PaddleOCR(
                lang=lang, ocr_version="PP-OCRv5",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False, use_textline_orientation=False,
            )
        except Exception as exc:
            engine_result["init_error"] = f"{exc.__class__.__name__}: {exc}"
            result["engines"][engine_name] = engine_result
            continue
        engine_result["cold_init_seconds"] = round(time.perf_counter() - cold_start, 3)

        cases = []
        for text, path in image_paths.items():
            started = time.perf_counter()
            try:
                predict_result = ocr.predict(str(path))
                recognized = _extract_text(predict_result)
                elapsed = time.perf_counter() - started
                cases.append({
                    "expected": text, "recognized": recognized,
                    "recall": round(_char_recall(text, recognized), 3),
                    "latency_seconds": round(elapsed, 3),
                })
            except Exception as exc:
                cases.append({"expected": text, "error": f"{exc.__class__.__name__}: {exc}"})
        engine_result["cases"] = cases
        result["engines"][engine_name] = engine_result
    return result


def run_rapidocr(image_paths: dict[str, Path]) -> dict:
    import platform

    result: dict = {"backend": "rapidocr", "python_version": platform.python_version()}
    import rapidocr

    result["rapidocr_version"] = getattr(rapidocr, "__version__", "unknown")
    try:
        import bidi
        result["python_bidi_version"] = getattr(bidi, "__version__", "present_unknown_version")
    except ImportError:
        result["python_bidi_version"] = None

    result["engines"] = {}
    for engine_name, lang in (("english", rapidocr.LangRec.EN), ("arabic", rapidocr.LangRec.ARABIC)):
        engine_result: dict = {}
        cold_start = time.perf_counter()
        try:
            engine = rapidocr.RapidOCR(params={
                "Rec.lang_type": lang,
                "Rec.ocr_version": rapidocr.OCRVersion.PPOCRV5,
                "Rec.model_type": rapidocr.ModelType.MOBILE,
                "Det.ocr_version": rapidocr.OCRVersion.PPOCRV5,
                "Det.model_type": rapidocr.ModelType.MOBILE,
            })
        except Exception as exc:
            engine_result["init_error"] = f"{exc.__class__.__name__}: {exc}"
            result["engines"][engine_name] = engine_result
            continue
        engine_result["cold_init_seconds"] = round(time.perf_counter() - cold_start, 3)

        cases = []
        for text, path in image_paths.items():
            started = time.perf_counter()
            try:
                ocr_result = engine(str(path))
                recognized_texts = ocr_result.txts if ocr_result and ocr_result.txts else []
                recognized = " ".join(recognized_texts)
                elapsed = time.perf_counter() - started
                cases.append({
                    "expected": text, "recognized": recognized,
                    "recall": round(_char_recall(text, recognized), 3),
                    "latency_seconds": round(elapsed, 3),
                })
            except Exception as exc:
                cases.append({"expected": text, "error": f"{exc.__class__.__name__}: {exc}"})
        engine_result["cases"] = cases
        result["engines"][engine_name] = engine_result
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", required=True, choices=["paddleocr", "rapidocr"])
    parser.add_argument("--out", required=True)
    parser.add_argument("--image-dir", default=None)
    args = parser.parse_args()

    image_dir = Path(args.image_dir) if args.image_dir else Path(__file__).parent / "_ocr_bench_images_tmp"
    image_paths = render_fixture_images(image_dir)

    if args.backend == "paddleocr":
        result = run_paddleocr(image_paths)
    elif args.backend == "rapidocr":
        result = run_rapidocr(image_paths)
    else:
        raise ValueError(args.backend)

    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    # Delete generated fixture images after benchmarking - never persisted.
    for path in image_paths.values():
        path.unlink(missing_ok=True)
    try:
        image_dir.rmdir()
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
