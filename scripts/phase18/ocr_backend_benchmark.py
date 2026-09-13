"""Phase 18 Workstream A Batch 04/05 - evidence-first OCR backend benchmark
(evaluation-only, never imported by production).

Generates a small set of JARVIS-owned synthetic fixture images (English,
Arabic, mixed) using an already-installed Windows system font (never a font
file copied into the repo), runs each candidate OCR backend against them,
and reports normalized recall, warm latency, and any errors - never
committing model weights, caches, or generated images.

Run inside an isolated evaluation venv (never the project's own `.venv`,
and never installed as a JARVIS dependency - see
`docs/audits/PHASE_18_WORKSTREAM_A_BATCH_04.md` Section 5 and
`docs/audits/PHASE_18_WORKSTREAM_A_BATCH_05.md` for the full evaluation
writeups and verdicts, including exact package versions):

    python ocr_backend_benchmark.py --backend paddleocr --out results.json
    python ocr_backend_benchmark.py --backend rapidocr --out results.json

R18B04-002 (Batch 05 Milestone 0): Batch 04's Arabic fixture images were
rendered with plain `ImageDraw.text()` and no complex-text/bidirectional
shaping engine. Pillow's native shaping (`PIL.features.check_feature
("raqm")`) is not available on this machine (Pillow 12.3.0, no bundled
libraqm), and without it, `ImageDraw.text()` draws each Arabic codepoint's
*isolated* presentation form in *logical* (not visual/RTL) order - not
correctly joined, connected Arabic script. This benchmark now explicitly
proves a valid shaping path before treating an Arabic/mixed fixture as
scorable evidence, or marks that fixture's rendering `FIXTURE_RENDERING_INVALID`
and refuses to generate an accuracy score for it, rather than silently
comparing an OCR engine's output against a garbled ground-truth image. The
shaping path actually used, and full rendering diagnostics, are recorded in
every benchmark result under `rendering_diagnostics`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, features as pil_features
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

SCORING_METHOD_DESCRIPTION = (
    "normalized_character_recall_v1: NFKC-normalize both expected and "
    "recognized text, collapse whitespace, strip; remove spaces; compute "
    "a multiset (order-insensitive) character-overlap recall of expected "
    "characters found in the recognized text. Never byte-perfect glyph "
    "comparison. The *expected* string used for scoring is always the "
    "original semantic Unicode text (e.g. base-form Arabic letters), never "
    "the reshaped/presentation-form glyphs used only for rendering the "
    "fixture image - scoring must reflect whether the OCR engine recovered "
    "real, readable text, not whether it reproduced rendering artifacts."
)


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


def _contains_arabic_script(text: str) -> bool:
    return any("\u0600" <= ch <= "\u06ff" or "\u0750" <= ch <= "\u077f" for ch in text)


@dataclass(slots=True)
class RenderedFixture:
    expected_text: str
    category: str
    path: Path | None
    layout_engine: str | None
    rendering_valid: bool
    rendering_error: str | None = None


@dataclass(slots=True)
class RenderingDiagnostics:
    pillow_version: str
    font_path: str
    raqm_feature_available: bool
    raqm_feature_version: str | None
    arabic_reshaper_available: bool
    python_bidi_available: bool
    per_fixture_layout_engine: dict[str, str | None] = field(default_factory=dict)


def _shape_arabic_for_render(text: str) -> tuple[str, str] | tuple[None, None]:
    """Best-effort non-raqm complex-text shaping path: `arabic_reshaper`
    (contextual letter-joining - each base Arabic letter mapped to its
    correct isolated/initial/medial/final presentation form) followed by
    `python-bidi`'s `get_display()` (Unicode Bidi Algorithm visual
    reordering - correctly handles mixed LTR+RTL runs, e.g. Latin text
    staying left-to-right alongside a reversed Arabic run). Returns
    (text_to_draw, layout_engine_name) on success, (None, None) if either
    dependency is unavailable - never silently draws unshaped text."""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
    except ImportError:
        return None, None
    reshaped = arabic_reshaper.reshape(text)
    display_text = get_display(reshaped)
    return display_text, "arabic_reshaper+python_bidi"


def render_fixture_images(out_dir: Path) -> tuple[list[RenderedFixture], RenderingDiagnostics]:
    out_dir.mkdir(parents=True, exist_ok=True)
    font_path = _pick_font()

    raqm_available = bool(pil_features.check_feature("raqm"))
    raqm_version = pil_features.version_feature("raqm") if raqm_available else None
    # `layout_engine` is a `ImageFont.truetype()` argument, not an
    # `ImageDraw.Draw()` one - a single RAQM-layout font instance is safe to
    # use for every fixture (English included) when raqm is available.
    font = ImageFont.truetype(font_path, 36, layout_engine=ImageFont.Layout.RAQM if raqm_available else ImageFont.Layout.BASIC)

    arabic_reshaper_available = False
    python_bidi_available = False
    try:
        import arabic_reshaper  # noqa: F401
        arabic_reshaper_available = True
    except ImportError:
        pass
    try:
        import bidi  # noqa: F401
        python_bidi_available = True
    except ImportError:
        pass

    diagnostics = RenderingDiagnostics(
        pillow_version=Image.__version__,
        font_path=font_path,
        raqm_feature_available=raqm_available,
        raqm_feature_version=raqm_version,
        arabic_reshaper_available=arabic_reshaper_available,
        python_bidi_available=python_bidi_available,
    )

    fixtures: list[RenderedFixture] = []
    for category, entries in FIXTURES.items():
        for text, filename in entries.items():
            needs_shaping = category in ("arabic", "mixed") and _contains_arabic_script(text)
            if not needs_shaping:
                image = Image.new("RGB", (500, 80), "white")
                draw = ImageDraw.Draw(image)
                draw.text((10, 15), text, font=font, fill="black")
                path = out_dir / filename
                image.save(path)
                diagnostics.per_fixture_layout_engine[text] = "plain_pil_no_shaping_needed"
                fixtures.append(RenderedFixture(text, category, path, "plain_pil_no_shaping_needed", True))
                continue

            layout_engine: str | None = None
            text_to_draw: str | None = None
            if raqm_available:
                # PIL's native raqm layout engine handles shaping/bidi
                # internally when drawing - draw the ORIGINAL logical text
                # directly with the raqm layout engine and RTL direction
                # hint for pure-Arabic fixtures; mixed fixtures let raqm's
                # own bidi handling place the Latin run correctly.
                text_to_draw = text
                layout_engine = "pil_raqm"
            else:
                shaped_text, engine_name = _shape_arabic_for_render(text)
                if shaped_text is not None:
                    text_to_draw = shaped_text
                    layout_engine = engine_name

            if text_to_draw is None:
                # No proven complex-text shaping path is available - refuse
                # to generate a silently-garbled fixture and refuse to
                # score it (R18B04-002).
                diagnostics.per_fixture_layout_engine[text] = None
                fixtures.append(RenderedFixture(
                    text, category, None, None, False,
                    rendering_error="FIXTURE_RENDERING_INVALID: no raqm and no arabic_reshaper+python-bidi available",
                ))
                continue

            image = Image.new("RGB", (500, 80), "white")
            draw = ImageDraw.Draw(image)
            try:
                if layout_engine == "pil_raqm":
                    draw.text((10, 15), text_to_draw, font=font, fill="black", direction="rtl" if category == "arabic" else None, language="ar")
                else:
                    draw.text((10, 15), text_to_draw, font=font, fill="black")
            except Exception as exc:
                diagnostics.per_fixture_layout_engine[text] = None
                fixtures.append(RenderedFixture(
                    text, category, None, None, False,
                    rendering_error=f"FIXTURE_RENDERING_INVALID: shaping draw failed - {exc.__class__.__name__}: {exc}",
                ))
                continue
            path = out_dir / filename
            image.save(path)
            diagnostics.per_fixture_layout_engine[text] = layout_engine
            fixtures.append(RenderedFixture(text, category, path, layout_engine, True))

    return fixtures, diagnostics


def _extract_text(predict_result) -> str:
    """PaddleOCR 3.x `.predict()` returns a list of pipeline result objects
    (dict-like, with `rec_texts`/`rec_scores` keys) - one per input image."""
    texts: list[str] = []
    for page in predict_result:
        rec_texts = page.get("rec_texts") if hasattr(page, "get") else None
        if rec_texts:
            texts.extend(rec_texts)
    return " ".join(texts)


def _run_cases(fixtures: list[RenderedFixture], predict_one) -> list[dict]:
    """Shared per-fixture loop for both backends: skips (and honestly
    records, without an accuracy score) any fixture whose rendering was
    invalid, and never silently substitutes a different string to score
    against."""
    cases: list[dict] = []
    for fixture in fixtures:
        if not fixture.rendering_valid or fixture.path is None:
            cases.append({
                "expected": fixture.expected_text, "category": fixture.category,
                "status": "FIXTURE_RENDERING_INVALID", "error": fixture.rendering_error,
            })
            continue
        started = time.perf_counter()
        try:
            recognized = predict_one(fixture.path)
            elapsed = time.perf_counter() - started
            cases.append({
                "expected": fixture.expected_text, "category": fixture.category,
                "recognized": recognized,
                "recall": round(_char_recall(fixture.expected_text, recognized), 3),
                "latency_seconds": round(elapsed, 3),
                "layout_engine": fixture.layout_engine,
            })
        except Exception as exc:
            cases.append({
                "expected": fixture.expected_text, "category": fixture.category,
                "error": f"{exc.__class__.__name__}: {exc}",
            })
    return cases


def run_paddleocr(fixtures: list[RenderedFixture]) -> dict:
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

        def predict_one(path: Path) -> str:
            predict_result = ocr.predict(str(path))
            return _extract_text(predict_result)

        engine_result["cases"] = _run_cases(fixtures, predict_one)
        result["engines"][engine_name] = engine_result
    return result


def run_rapidocr(fixtures: list[RenderedFixture]) -> dict:
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

        def predict_one(path: Path, _engine=engine) -> str:
            ocr_result = _engine(str(path))
            recognized_texts = ocr_result.txts if ocr_result and ocr_result.txts else []
            return " ".join(recognized_texts)

        engine_result["cases"] = _run_cases(fixtures, predict_one)
        result["engines"][engine_name] = engine_result
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", required=True, choices=["paddleocr", "rapidocr"])
    parser.add_argument("--out", required=True)
    parser.add_argument("--image-dir", default=None)
    args = parser.parse_args()

    image_dir = Path(args.image_dir) if args.image_dir else Path(__file__).parent / "_ocr_bench_images_tmp"
    fixtures, diagnostics = render_fixture_images(image_dir)

    if args.backend == "paddleocr":
        result = run_paddleocr(fixtures)
    elif args.backend == "rapidocr":
        result = run_rapidocr(fixtures)
    else:
        raise ValueError(args.backend)

    result["scoring_method"] = SCORING_METHOD_DESCRIPTION
    result["rendering_diagnostics"] = {
        "pillow_version": diagnostics.pillow_version,
        "font_path": diagnostics.font_path,
        "raqm_feature_available": diagnostics.raqm_feature_available,
        "raqm_feature_version": diagnostics.raqm_feature_version,
        "arabic_reshaper_available": diagnostics.arabic_reshaper_available,
        "python_bidi_available": diagnostics.python_bidi_available,
        "per_fixture_layout_engine": diagnostics.per_fixture_layout_engine,
    }

    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    # Delete generated fixture images after benchmarking - never persisted.
    for fixture in fixtures:
        if fixture.path is not None:
            fixture.path.unlink(missing_ok=True)
    try:
        image_dir.rmdir()
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
