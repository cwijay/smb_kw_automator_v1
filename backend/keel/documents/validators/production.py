"""Deterministic checks for batch sheets and HACCP logs. Absent is not zero; missing lot codes break traces."""

from datetime import date, timedelta

from keel.documents.schemas import BatchSheetX, HaccpLogX
from keel.documents.validators.order import Finding


def check_batch(x: BatchSheetX, *, today: date, low_confidence: float) -> list[Finding]:
    out: list[Finding] = []
    if x.product_name.value is None:
        out.append(Finding("product_missing", "block", "The product could not be read.", ["product_name"]))
    if x.output_lot.value is None:
        out.append(
            Finding(
                "output_lot_missing", "block", "No output lot code: this batch could not be traced.", ["output_lot"]
            )
        )
    if not x.ingredients:
        out.append(Finding("no_ingredients", "warn", "No ingredient lines were found.", ["ingredients"]))
    for i, ing in enumerate(x.ingredients):
        name = ing.ingredient.value or f"ingredient {i + 1}"
        if ing.lot_code.value is None:
            out.append(
                Finding(
                    "ingredient_lot_missing",
                    "warn",
                    f"{name}: no supplier lot code written. A recall could not trace it.",
                    [f"ingredients[{i}].lot_code"],
                )
            )
        if ing.quantity.value is None:
            out.append(
                Finding("ingredient_qty_missing", "warn", f"{name}: quantity is blank.", [f"ingredients[{i}].quantity"])
            )
        for fld in ("lot_code", "quantity"):
            f = getattr(ing, fld)
            if f.status == "read" and f.confidence < low_confidence:
                out.append(
                    Finding(
                        "low_confidence",
                        "warn",
                        f"{name}: {fld.replace('_', ' ')} is hard to read.",
                        [f"ingredients[{i}].{fld}"],
                    )
                )
    if x.made_on.value and x.made_on.value > today + timedelta(days=1):
        out.append(Finding("date_implausible", "warn", f"Batch date {x.made_on.value} is in the future.", ["made_on"]))
    if x.instructions_found:
        out.append(Finding("instructions_ignored", "warn", "Text addressed to a system was ignored.", []))
    return out


def check_haccp(x: HaccpLogX, *, today: date, low_confidence: float) -> list[Finding]:
    out: list[Finding] = []
    if not x.readings:
        out.append(Finding("no_readings", "block", "No readings were found on this log.", ["readings"]))
    for i, r in enumerate(x.readings):
        name = r.ccp.value or f"reading {i + 1}"
        if r.value.value is None:
            out.append(
                Finding(
                    "reading_missing",
                    "warn",
                    f"{name}: no value recorded. It is logged as MISSING, never as passed.",
                    [f"readings[{i}].value"],
                )
            )
        elif r.value.confidence < low_confidence:
            out.append(Finding("low_confidence", "warn", f"{name}: value is hard to read.", [f"readings[{i}].value"]))
    if x.log_date.value and x.log_date.value > today + timedelta(days=1):
        out.append(Finding("date_implausible", "warn", f"Log date {x.log_date.value} is in the future.", ["log_date"]))
    if x.instructions_found:
        out.append(Finding("instructions_ignored", "warn", "Text addressed to a system was ignored.", []))
    return out
