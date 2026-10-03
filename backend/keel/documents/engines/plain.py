"""Bridge to extraction services that take a plain JSON schema and return plain values (Reducto, ADE).

Our schemas carry {value, status, confidence} per field; those services return bare values. Going out,
each field becomes a nullable JSON type. Coming back, a value becomes status "read" and a null becomes
"unreadable": we can't tell "empty on the paper" from "not found", so a person decides. Never "blank",
never 0. A value that doesn't parse as its type is also "unreadable".
"""

import io
import typing
from datetime import date
from decimal import Decimal, InvalidOperation
from types import UnionType
from typing import Any

from pydantic import BaseModel

from keel.documents.engines.base import PageInput
from keel.documents.schemas import DateField, NumberField, TextField

FIELD_TYPES: dict[type[BaseModel], dict[str, Any]] = {
    TextField: {"type": ["string", "null"]},
    NumberField: {"type": ["number", "null"]},
    DateField: {"type": ["string", "null"], "description": "ISO date, YYYY-MM-DD"},
}


def _inner(annotation: Any) -> Any:
    """list[X] -> X; X | None -> X."""
    args = [a for a in typing.get_args(annotation) if a is not type(None)]
    return args[0] if args else annotation


def plain_schema(model: type[BaseModel]) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for name, f in model.model_fields.items():
        ann = f.annotation
        origin = typing.get_origin(ann)
        if ann in FIELD_TYPES:
            prop = dict(FIELD_TYPES[ann])
        elif origin is list and isinstance(_inner(ann), type) and issubclass(_inner(ann), BaseModel):
            prop = {"type": "array", "items": plain_schema(_inner(ann))}
        elif origin is list:
            prop = {"type": "array", "items": {"type": "string"}}
        elif ann is bool:
            prop = {"type": "boolean"}
        elif origin in (typing.Union, UnionType) and _inner(ann) is int:
            prop = {"type": ["integer", "null"]}
        else:
            prop = {"type": ["string", "null"]}
        if f.description:
            prop["description"] = f.description
        props[name] = prop
    out: dict[str, Any] = {"type": "object", "properties": props}
    if model.__doc__ and model.__doc__.strip():
        out["description"] = model.__doc__.strip()
    return out


def _field(kind: type[BaseModel], raw: Any, confidence: float) -> BaseModel:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return kind(value=None, status="unreadable", confidence=0.0)
    try:
        if kind is NumberField:
            value: Any = Decimal(str(raw).replace(",", "").replace("$", "").strip())
        elif kind is DateField:
            value = date.fromisoformat(str(raw).strip()[:10])
        else:
            value = str(raw).strip()
    except (InvalidOperation, ValueError):
        return kind(value=None, status="unreadable", confidence=0.0)
    return kind(value=value, status="read", confidence=confidence)


def typed(model: type[BaseModel], data: dict[str, Any] | None, confidence: float) -> BaseModel:
    data = data or {}
    values: dict[str, Any] = {}
    for name, f in model.model_fields.items():
        ann, raw = f.annotation, data.get(name)
        origin = typing.get_origin(ann)
        if ann in FIELD_TYPES:
            values[name] = _field(ann, raw, confidence)
        elif origin is list and isinstance(_inner(ann), type) and issubclass(_inner(ann), BaseModel):
            values[name] = [typed(_inner(ann), item, confidence) for item in (raw or []) if isinstance(item, dict)]
        elif origin is list:
            values[name] = [str(x) for x in (raw or [])]
        elif ann is bool:
            values[name] = bool(raw)
        elif raw is not None:
            values[name] = raw
    return model.model_validate(values)


def pages_pdf(pages: list[PageInput]) -> bytes:
    """One PDF from the page images, so a service sees the whole document in one request."""
    from fpdf import FPDF
    from PIL import Image

    pdf = FPDF(unit="pt")
    for p in pages:
        with Image.open(io.BytesIO(p.png)) as im:
            w, h = im.size
        pdf.add_page(format=(w, h))
        pdf.image(io.BytesIO(p.png), x=0, y=0, w=w, h=h)
    return bytes(pdf.output())
