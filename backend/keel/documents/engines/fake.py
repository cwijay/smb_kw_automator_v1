"""Deterministic local extractor for order sheets. No API keys; used for tests, demos and offline dev.

It reads the OCR/text-layer text with simple patterns. It is honest by construction: anything it
cannot parse is left null with status "unreadable", and OCR confidence flows into field confidence.
"""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel

from keel.documents.engines.base import EngineResult, PageInput
from keel.documents.schemas import DateField, NumberField, OrderLineX, OrderPadX, TextField

LINE = re.compile(
    r"^(?P<qty>\d+(?:[.,]\d+)?)\s*(?P<unit>kg|tubs?|cases?|ea|each|pcs|trays?)?\s+(?P<desc>.+?)"
    r"(?:\s+\$?(?P<price>\d+[.,]\d{2}))?(?:\s+\$?(?P<amount>\d+[.,]\d{2}))?$",
    re.IGNORECASE,
)
HEADER = {
    "customer_name": re.compile(r"^(?:customer|name|sold to|bill to)\s*[:#-]?\s*(.+)$", re.I),
    "order_number": re.compile(r"^(?:order|order no|order #|order number)\s*[:#-]?\s*(\S+)$", re.I),
    "order_date": re.compile(r"^(?:date|order date)\s*[:#-]?\s*(.+)$", re.I),
    "delivery_date": re.compile(r"^(?:deliver(?:y)?(?: date)?|due)\s*[:#-]?\s*(.+)$", re.I),
    "total_written": re.compile(r"^(?:total|grand total)\s*[:#-]?\s*\$?\s*(\d+[.,]?\d*)$", re.I),
}


def _num(s: str | None) -> Decimal | None:
    if not s:
        return None
    try:
        return Decimal(s.replace(",", "."))
    except InvalidOperation:
        return None


def _date(s: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d %b %Y", "%b %d %Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


class FakeExtractor:
    name = "local-rules"

    async def extract(self, pages: list[PageInput], schema: type[BaseModel], hint: str = "") -> EngineResult:
        conf_by_text = {w["text"].strip().lower(): float(w.get("conf", 0.9)) for p in pages for w in p.words}
        base_conf = 0.97 if any(w.get("source") == "text_layer" for p in pages for w in p.words) else 0.85
        result = OrderPadX(customer_name=TextField(status="unreadable"))
        in_lines = False
        for raw in "\n".join(p.text for p in pages).splitlines():
            line = raw.strip()
            if not line:
                continue
            conf = min(base_conf, conf_by_text.get(line.lower(), base_conf))
            matched_header = False
            for key, rx in HEADER.items():
                m = rx.match(line)
                if not m:
                    continue
                matched_header = True
                val = m.group(1).strip()
                if key in ("order_date", "delivery_date"):
                    d = _date(val)
                    setattr(result, key, DateField(value=d, status="read" if d else "unreadable",
                                                   confidence=conf if d else 0.0))
                elif key == "total_written":
                    n = _num(val)
                    result.total_written = NumberField(value=n, status="read" if n is not None else "unreadable",
                                                       confidence=conf)
                else:
                    setattr(result, key, TextField(value=val, status="read", confidence=conf))
                break
            if matched_header:
                continue
            if re.match(r"^(qty|quantity)\b", line, re.I):
                in_lines = True
                continue
            crossed = line.startswith("~") or "(crossed out)" in line.lower()
            m = LINE.match(line.lstrip("~ ").replace("(crossed out)", "").strip())
            if in_lines and m:
                desc = m.group("desc").replace("(crossed out)", "").strip(" ~")
                price, amount = _num(m.group("price")), _num(m.group("amount"))
                result.lines.append(OrderLineX(
                    description=TextField(value=desc, status="read", confidence=conf),
                    quantity=NumberField(value=_num(m.group("qty")), status="read", confidence=conf),
                    unit=TextField(value=(m.group("unit") or "each").lower(), status="read", confidence=conf),
                    unit_price=NumberField(value=price, status="read" if price is not None else "blank",
                                           confidence=conf if price is not None else 0.0),
                    line_total=NumberField(value=amount, status="read" if amount is not None else "blank",
                                           confidence=conf if amount is not None else 0.0),
                    crossed_out=crossed,
                ))
            elif re.search(r"\b(ignore|assistant|system prompt|instructions?)\b", line, re.I):
                result.instructions_found.append(line)
        return EngineResult(data=result, engine=self.name)
