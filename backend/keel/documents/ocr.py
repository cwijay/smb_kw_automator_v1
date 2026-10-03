"""Tier 1 OCR on CPU: PP-OCR models through RapidOCR (ONNX). Gives text + boxes for evidence."""

import io
from functools import lru_cache
from typing import Any

from PIL import Image

from keel.platform.logging import log


@lru_cache(maxsize=1)
def _engine() -> Any:
    try:
        from rapidocr import RapidOCR
    except ImportError:  # optional extra: `uv sync --extra ocr`
        return None
    return RapidOCR()


def ocr_words(png: bytes) -> list[dict[str, Any]]:
    engine = _engine()
    if engine is None:
        log.warning("ocr.unavailable", hint="install the 'ocr' extra")
        return []
    width, height = Image.open(io.BytesIO(png)).size
    result = engine(png)
    words: list[dict[str, Any]] = []
    if result is None or result.boxes is None:
        return words
    for box, text, score in zip(result.boxes, result.txts, result.scores, strict=False):
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        words.append({
            "text": str(text), "x": min(xs) / width, "y": min(ys) / height,
            "w": (max(xs) - min(xs)) / width, "h": (max(ys) - min(ys)) / height,
            "conf": float(score), "source": "ocr",
        })
    return words
