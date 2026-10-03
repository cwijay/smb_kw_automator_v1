"""Synthetic order sheets (no real customer documents are ever committed)."""

from fpdf import FPDF


def order_sheet_pdf(
    lines: list[str],
    *,
    customer: str = "Rasoi Kitchen",
    number: str = "1001",
    date: str = "2026-10-01",
    deliver: str = "2026-10-03",
    total: str | None = None,
    extra: list[str] | None = None,
) -> bytes:
    pdf = FPDF(format="A5")
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    rows = [
        f"Customer: {customer}",
        f"Order #: {number}",
        f"Date: {date}",
        f"Deliver: {deliver}",
        "Qty Item Price Amount",
        *lines,
    ]
    if total:
        rows.append(f"Total: {total}")
    rows += extra or []
    for row in rows:
        pdf.cell(0, 8, row, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def _sheet(rows: list[str]) -> bytes:
    pdf = FPDF(format="A5")
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for row in rows:
        pdf.cell(0, 8, row, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def batch_sheet_pdf(
    ingredients: list[str],
    *,
    product: str = "Malai Kulfi",
    batch: str = "B-001",
    lot: str | None = "L-1042",
    quantity: str = "120 tub",
    made_on: str = "2026-10-01",
) -> bytes:
    rows = ["Batch Sheet", f"Product: {product}", f"Batch: {batch}", f"Date: {made_on}"]
    if lot is not None:
        rows.append(f"Output lot: {lot}")
    rows += [f"Quantity: {quantity}", "Prepared by: RP", "Ingredient Lot Qty", *ingredients]
    return _sheet(rows)


def haccp_log_pdf(readings: list[str], *, batch: str = "B-001", day: str = "2026-10-01") -> bytes:
    return _sheet(
        ["HACCP Log", f"Batch: {batch}", f"Date: {day}", "Operator: RP", "CCP Value Time Initials", *readings]
    )
