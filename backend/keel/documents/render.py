"""Turn an upload into page images plus any embedded text layer (with word boxes, normalised 0-1)."""

import io
from dataclasses import dataclass, field
from typing import Any

import pypdfium2 as pdfium
from PIL import Image, ImageOps

MAX_SIDE = 2000


@dataclass
class RenderedPage:
    png: bytes
    width: int
    height: int
    words: list[dict[str, Any]] = field(default_factory=list)  # {text, x, y, w, h, conf, source}

    @property
    def has_text_layer(self) -> bool:
        return any(w.get("source") == "text_layer" for w in self.words)


def _to_png(img: Image.Image) -> tuple[bytes, int, int]:
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), img.width, img.height


def _pdf_words(page: pdfium.PdfPage) -> list[dict[str, Any]]:
    textpage = page.get_textpage()
    width, height = page.get_size()
    words: list[dict[str, Any]] = []
    current: list[tuple[str, tuple[float, float, float, float]]] = []

    def flush() -> None:
        if not current:
            return
        text = "".join(c for c, _ in current).strip()
        if text:
            left = min(b[0] for _, b in current)
            bottom = min(b[1] for _, b in current)
            right = max(b[2] for _, b in current)
            top = max(b[3] for _, b in current)
            words.append(
                {
                    "text": text,
                    "x": left / width,
                    "y": 1 - top / height,
                    "w": (right - left) / width,
                    "h": (top - bottom) / height,
                    "conf": 1.0,
                    "source": "text_layer",
                }
            )
        current.clear()

    for i in range(textpage.count_chars()):
        ch = textpage.get_text_range(i, 1)
        if ch.isspace() or ch == "":
            flush()
            continue
        current.append((ch, textpage.get_charbox(i)))
    flush()
    return words


def render(data: bytes, mime: str) -> list[RenderedPage]:
    if mime == "application/pdf":
        pdf = pdfium.PdfDocument(data)
        pages = []
        for page in pdf:
            png, w, h = _to_png(page.render(scale=2).to_pil())
            pages.append(RenderedPage(png, w, h, _pdf_words(page)))
        return pages
    png, w, h = _to_png(Image.open(io.BytesIO(data)))
    return [RenderedPage(png, w, h)]


def page_text(words: list[dict[str, Any]]) -> str:
    """Reading-order text: words whose boxes overlap vertically belong to the same line.

    Overlap (not just midpoints) keeps low glyphs such as underscores or commas on their line.
    """
    lines: list[dict[str, Any]] = []  # {top, bottom, words}
    for word in sorted(words, key=lambda w: (w["y"] + w["h"] / 2, w["x"])):
        top, bottom = word["y"], word["y"] + word["h"]
        for line in lines:
            overlap = min(bottom, line["bottom"]) - max(top, line["top"])
            if overlap > 0 and overlap >= 0.3 * min(word["h"] or 1e-6, line["bottom"] - line["top"]):
                line["words"].append(word)
                line["top"], line["bottom"] = min(line["top"], top), max(line["bottom"], bottom)
                break
        else:
            lines.append({"top": top, "bottom": bottom, "words": [word]})
    lines.sort(key=lambda ln: ln["top"])
    return "\n".join(" ".join(w["text"] for w in sorted(ln["words"], key=lambda w: w["x"])) for ln in lines)
