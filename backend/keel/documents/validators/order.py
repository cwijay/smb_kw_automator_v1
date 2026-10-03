"""Deterministic checks on an extracted order. Code decides; the model only proposes.

Each check returns findings with a stable code, severity and the field paths involved, so the review
UI can highlight them and tests can assert on them.
"""

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from keel.documents.schemas import OrderPadX

TOLERANCE = Decimal("0.01")


@dataclass
class Finding:
    code: str
    severity: str  # "block" (cannot approve until resolved) | "warn"
    message: str
    paths: list[str] = field(default_factory=list)

    def dict(self) -> dict[str, Any]:
        return asdict(self)


def check_order(x: OrderPadX, *, today: date, low_confidence: float) -> list[Finding]:
    out: list[Finding] = []
    if x.customer_name.value is None:
        out.append(Finding("customer_missing", "block", "The customer name could not be read.", ["customer_name"]))
    live = [(i, ln) for i, ln in enumerate(x.lines) if not ln.crossed_out]
    if not live:
        out.append(Finding("no_lines", "block", "No order lines were found.", ["lines"]))

    for i, ln in live:
        p = f"lines[{i}]"
        if ln.quantity.value is None:
            out.append(
                Finding(
                    "quantity_unreadable",
                    "block",
                    f"Line {i + 1}: the quantity could not be read. It will not be guessed.",
                    [f"{p}.quantity"],
                )
            )
        elif ln.quantity.value <= 0:
            out.append(
                Finding(
                    "quantity_not_positive", "block", f"Line {i + 1}: quantity must be above zero.", [f"{p}.quantity"]
                )
            )
        for name in ("description", "quantity", "unit_price", "line_total"):
            fld = getattr(ln, name)
            if fld.status == "read" and fld.confidence < low_confidence:
                out.append(
                    Finding(
                        "low_confidence",
                        "warn",
                        f"Line {i + 1}: {name.replace('_', ' ')} is hard to read; please confirm.",
                        [f"{p}.{name}"],
                    )
                )
        q, up, lt = ln.quantity.value, ln.unit_price.value, ln.line_total.value
        has_all = q is not None and up is not None and lt is not None
        if ln.price_group is None and has_all and abs(q * up - lt) > TOLERANCE:  # type: ignore[operator]
            out.append(
                Finding(
                    "line_math",
                    "warn",
                    f"Line {i + 1}: {q} × {up} = {q * up}, but the paper says {lt}.",  # type: ignore[operator]
                    [f"{p}.quantity", f"{p}.unit_price", f"{p}.line_total"],
                )
            )

    # Grouped pricing: bracketed lines share one amount, checked against the summed quantity.
    groups: dict[int, list[int]] = {}
    for i, ln in live:
        if ln.price_group is not None:
            groups.setdefault(ln.price_group, []).append(i)
    for idx in groups.values():
        qty = sum((x.lines[i].quantity.value or Decimal(0)) for i in idx)
        price = next((x.lines[i].unit_price.value for i in idx if x.lines[i].unit_price.value is not None), None)
        amount = next((x.lines[i].line_total.value for i in idx if x.lines[i].line_total.value is not None), None)
        if price is not None and amount is not None and abs(qty * price - amount) > TOLERANCE:
            out.append(
                Finding(
                    "group_math",
                    "warn",
                    f"Grouped lines {[i + 1 for i in idx]}: {qty} × {price} ≠ {amount}.",
                    [f"lines[{i}].line_total" for i in idx],
                )
            )

    written = x.total_written.value
    amounts = [ln.line_total.value for _, ln in live if ln.line_total.value is not None]
    if written is not None and amounts and abs(sum(amounts) - written) > TOLERANCE:
        out.append(
            Finding(
                "total_mismatch",
                "warn",
                f"Lines add up to {sum(amounts)}, but the written total is {written}. "
                "A line may be cropped or misread.",
                ["total_written"],
            )
        )

    for name in ("order_date", "delivery_date"):
        d = getattr(x, name).value
        if d is not None and d > today + timedelta(days=120):
            out.append(
                Finding("date_implausible", "warn", f"{name.replace('_', ' ')} {d} is far in the future.", [name])
            )
    if x.delivery_date.value and x.order_date.value and x.delivery_date.value < x.order_date.value:
        out.append(
            Finding("delivery_before_order", "warn", "Delivery date is before the order date.", ["delivery_date"])
        )
    if x.instructions_found:
        out.append(
            Finding(
                "instructions_ignored",
                "warn",
                "The paper contains text addressed to a system. It was recorded and ignored.",
                ["instructions_found"],
            )
        )
    return out
