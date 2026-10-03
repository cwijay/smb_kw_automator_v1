"""Synthetic gold set for the parser bake-off. Generated, deterministic, safe to commit.

Each document comes with the values a careful person would read off it. `null` means the paper is
empty there: an engine that puts a value in that spot has invented it. Real customer pages never go
in git; put them in a private directory with the same layout and pass it to `--gold`.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from keel.documents.render import render

FIXED = datetime(2026, 10, 1, tzinfo=UTC)


def _pdf(rows: list[str]) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(format="A5")
    pdf.set_creation_date(FIXED)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for row in rows:
        pdf.cell(0, 8, row, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def _order(
    customer: str, number: str, lines: list[tuple[str, str, str, str]], total: str
) -> tuple[list[str], dict[str, Any]]:
    rows = [
        f"Customer: {customer}",
        f"Order #: {number}",
        "Date: 2026-10-01",
        "Deliver: 2026-10-04",
        "Qty Item Price Amount",
    ]
    rows += [" ".join(line) for line in lines] + [f"Total: {total}"]
    expected: dict[str, Any] = {
        "customer_name": customer,
        "order_number": number,
        "order_date": "2026-10-01",
        "delivery_date": "2026-10-04",
        "total_written": total,
    }
    for i, (qty, desc, price, amount) in enumerate(lines):
        expected |= {
            f"lines[{i}].quantity": qty,
            f"lines[{i}].description": desc,
            f"lines[{i}].unit_price": price,
            f"lines[{i}].line_total": amount,
        }
    return rows, expected


def _batch(number: str, lot: str, ingredients: list[tuple[str, str | None, str]]) -> tuple[list[str], dict[str, Any]]:
    rows = ["Batch Sheet", "Product: Malai Kulfi", f"Batch: {number}", "Date: 2026-10-01", f"Output lot: {lot}"]
    rows += ["Quantity: 120 tub", "Prepared by: RP", "Ingredient Lot Qty"]
    rows += [f"{name} {code or '-'} {qty} lbs" for name, code, qty in ingredients]
    expected: dict[str, Any] = {"product_name": "Malai Kulfi", "batch_number": number, "made_on": "2026-10-01"}
    expected |= {"output_lot": lot, "quantity": "120", "prepared_by": "RP"}
    for i, (name, code, qty) in enumerate(ingredients):
        expected |= {f"ingredients[{i}].ingredient": name, f"ingredients[{i}].lot_code": code}
        expected[f"ingredients[{i}].quantity"] = qty
    return rows, expected


def _haccp(batch: str, readings: list[tuple[str, str | None, str, str]]) -> tuple[list[str], dict[str, Any]]:
    rows = ["HACCP Log", f"Batch: {batch}", "Date: 2026-10-01", "Operator: RP", "CCP Value Time Initials"]
    rows += [f"{ccp} {value if value is not None else '__'} {unit} {time} RP" for ccp, value, unit, time in readings]
    expected: dict[str, Any] = {"batch_number": batch, "log_date": "2026-10-01", "operator": "RP"}
    for i, (ccp, value, _unit, time) in enumerate(readings):
        expected |= {f"readings[{i}].ccp": ccp, f"readings[{i}].value": value, f"readings[{i}].time": time}
    return rows, expected


DOCS: list[tuple[str, str, str, tuple[list[str], dict[str, Any]]]] = [
    (
        "order-typed",
        "order_pad",
        "pdf",
        _order(
            "Rasoi Kitchen",
            "1001",
            [("11", "Malai Kulfi", "4.50", "49.50"), ("3", "Mango Kulfi", "5.50", "16.50")],
            "66.00",
        ),
    ),
    (
        "order-photo",
        "order_pad",
        "png",
        _order("Saffron Grill", "1002", [("6", "Pista Kulfi", "5.75", "34.50")], "34.50"),
    ),
    (
        "order-long",
        "order_pad",
        "pdf",
        _order(
            "Little Bombay Cafe",
            "1003",
            [
                ("2", "Paan Masala", "6.00", "12.00"),
                ("4", "Rose Petal Kulfi", "5.50", "22.00"),
                ("1", "Figs Walnut", "6.25", "6.25"),
            ],
            "40.25",
        ),
    ),
    (
        "batch-complete",
        "batch_sheet",
        "pdf",
        _batch(
            "B-100",
            "L-2001",
            [("Whole Milk", "M-0129", "136"), ("Cream", "C-0130", "280"), ("Sugar", "S-42702", "100")],
        ),
    ),
    (
        "batch-missing-lot",
        "batch_sheet",
        "pdf",
        _batch("B-101", "L-2002", [("Whole Milk", "M-0131", "136"), ("Rose Water", None, "140")]),
    ),
    (
        "batch-photo",
        "batch_sheet",
        "png",
        _batch("B-102", "L-2003", [("Whole Milk", "M-0133", "136"), ("Sugar", "S-42703", "100")]),
    ),
    (
        "haccp-clean",
        "haccp_log",
        "pdf",
        _haccp("B-100", [("Fill temperature", "168", "F", "09:10"), ("Pack weight", "6.2", "lb", "10:00")]),
    ),
    (
        "haccp-blank",
        "haccp_log",
        "pdf",
        _haccp(
            "B-101",
            [
                ("Fill temperature", "168", "F", "09:10"),
                ("Fill temperature", None, "F", "09:40"),
                ("Pack weight", "5.6", "lb", "10:00"),
            ],
        ),
    ),
]


def write(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    for name, kind, fmt, (rows, expected) in DOCS:
        pdf = _pdf(rows)
        data, mime = (pdf, "application/pdf") if fmt == "pdf" else (render(pdf, "application/pdf")[0].png, "image/png")
        file = f"{name}.{fmt}"
        (out / file).write_bytes(data)
        gold = {"file": file, "mime": mime, "kind": kind, "expected": expected}
        (out / f"{name}.json").write_text(json.dumps(gold, indent=2) + "\n")
    return len(DOCS)
