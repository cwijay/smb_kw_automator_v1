"""Offline parsing for batch sheets and HACCP logs (same honesty rules as the order parser)."""

import re
from decimal import Decimal, InvalidOperation

from keel.documents.engines.fake import _date
from keel.documents.schemas import (
    BatchSheetX,
    DateField,
    HaccpLogX,
    IngredientX,
    NumberField,
    ReadingX,
    TextField,
)

BLANK = {"", "-", "—", "?", "__", "___", "blank", "n/a"}
INGREDIENT = re.compile(
    r"^(?P<ing>[A-Za-z][A-Za-z &'/-]*?)\s+(?P<lot>[A-Z0-9][A-Z0-9/-]*\d[A-Z0-9/-]*|-|—|\?|__)\s+"
    r"(?P<qty>\d+(?:[.,]\d+)?|-|__)\s*(?P<unit>[A-Za-z]+)?$"
)
READING = re.compile(
    r"^(?P<ccp>[A-Za-z][A-Za-z ]*?)\s+(?P<val>-?\d+(?:[.,]\d+)?|blank|-|—|__|\?)\s*"
    r"(?P<unit>F|C|°F|°C|lb|lbs|kg|g|pH|%)?"
    r"(?:\s+(?P<time>\d{1,2}:\d{2}))?(?:\s+(?P<ini>[A-Z]{1,3}))?$"
)
SUSPICIOUS = re.compile(r"\b(ignore|assistant|system prompt|instructions?)\b", re.I)


def _num(raw: str | None, conf: float) -> NumberField:
    if raw is None or raw.strip().lower() in BLANK:
        return NumberField(status="blank")
    try:
        return NumberField(value=Decimal(raw.replace(",", ".")), status="read", confidence=conf)
    except InvalidOperation:
        return NumberField(status="unreadable")


def _text(raw: str | None, conf: float) -> TextField:
    if raw is None or raw.strip().lower() in BLANK:
        return TextField(status="blank")
    return TextField(value=raw.strip(), status="read", confidence=conf)


def _header(line: str, *names: str) -> str | None:
    m = re.match(rf"^(?:{'|'.join(names)})\s*[:#-]?\s*(.*)$", line, re.I)
    return m.group(1).strip() if m else None


def parse_batch(text: str, conf: float) -> BatchSheetX:
    x = BatchSheetX(product_name=TextField(status="unreadable"))
    in_table = False
    for line in (ln.strip() for ln in text.splitlines()):
        if not line:
            continue
        if (v := _header(line, "product")) is not None:
            x.product_name = _text(v, conf)
        elif (v := _header(line, "batch", "batch no", "batch #")) is not None and not in_table:
            x.batch_number = _text(v, conf)
        elif (v := _header(line, "date", "made on")) is not None:
            d = _date(v)
            x.made_on = DateField(value=d, status="read", confidence=conf) if d else DateField(status="unreadable")
        elif (v := _header(line, "output lot", "lot", "lot #")) is not None and not in_table:
            x.output_lot = _text(v, conf)
        elif (v := _header(line, "quantity", "yield")) is not None and not in_table:
            parts = v.split()
            x.quantity = _num(parts[0] if parts else None, conf)
            x.unit = _text(parts[1] if len(parts) > 1 else None, conf)
        elif (v := _header(line, "prepared by", "operator")) is not None:
            x.prepared_by = _text(v, conf)
        elif re.match(r"^ingredient\b", line, re.I):
            in_table = True
        elif SUSPICIOUS.search(line):
            x.instructions_found.append(line)
        elif in_table and (m := INGREDIENT.match(line)):
            x.ingredients.append(
                IngredientX(
                    ingredient=_text(m.group("ing"), conf),
                    lot_code=_text(m.group("lot"), conf),
                    quantity=_num(m.group("qty"), conf),
                    unit=_text(m.group("unit"), conf),
                )
            )
    return x


def parse_haccp(text: str, conf: float) -> HaccpLogX:
    x = HaccpLogX()
    in_table = False
    for line in (ln.strip() for ln in text.splitlines()):
        if not line:
            continue
        if not in_table and (v := _header(line, "batch", "batch no", "batch #")) is not None:
            x.batch_number = _text(v, conf)
        elif not in_table and (v := _header(line, "date")) is not None:
            d = _date(v)
            x.log_date = DateField(value=d, status="read", confidence=conf) if d else DateField(status="unreadable")
        elif not in_table and (v := _header(line, "operator", "checked by")) is not None:
            x.operator = _text(v, conf)
        elif re.match(r"^(ccp|check)\b", line, re.I):
            in_table = True
        elif SUSPICIOUS.search(line):
            x.instructions_found.append(line)
        elif in_table and (m := READING.match(line)):
            x.readings.append(
                ReadingX(
                    ccp=_text(m.group("ccp"), conf),
                    value=_num(m.group("val"), conf),
                    unit=_text((m.group("unit") or "").replace("°", ""), conf),
                    time=_text(m.group("time"), conf),
                    initials=_text(m.group("ini"), conf),
                )
            )
    return x
