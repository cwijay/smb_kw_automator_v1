"""Evidence: link each extracted value back to boxes on the page (OCR or text-layer words)."""

from decimal import Decimal
from typing import Any

from rapidfuzz import fuzz


def _norm(v: Any) -> str:
    if isinstance(v, Decimal):
        s = format(v.normalize(), "f")
        return s
    return str(v).strip().lower()


def find_box(value: Any, words: list[dict[str, Any]], min_score: float = 80) -> dict[str, Any] | None:
    """Best matching word or line box for a value. Numbers must match exactly as tokens."""
    if value is None or not words:
        return None
    target = _norm(value)
    if not target:
        return None
    best, best_score = None, 0.0
    numeric = isinstance(value, (int, float, Decimal))
    for w in words:
        text = w["text"].strip().lower()
        if numeric:
            tokens = [t.strip("$,") for t in text.split()]
            candidates = {t for t in tokens} | {t.rstrip("0").rstrip(".") for t in tokens if "." in t}
            score = 100.0 if target in candidates or target.rstrip("0").rstrip(".") in candidates else 0.0
        else:
            score = fuzz.partial_ratio(target, text) if len(text) >= 2 else 0.0
        if score > best_score:
            best, best_score = w, score
    return best if best_score >= min_score else None
