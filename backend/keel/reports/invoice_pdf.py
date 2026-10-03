"""Invoice PDF (fpdf2, pure Python). Ledger look: tabular numbers, ISO currency codes."""

from decimal import Decimal
from typing import Any

from fpdf import FPDF


def _money(v: Decimal, cur: str) -> str:
    return f"{cur} {v:,.2f}"


def render_invoice(
    *, org: dict[str, Any], customer: dict[str, Any], invoice: dict[str, Any], lines: list[dict[str, Any]]
) -> bytes:
    cur = invoice["currency"]
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, org["name"], new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(0, 6, "INVOICE", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 10)
    meta = [
        ("Invoice", invoice["number"]),
        ("Issued", str(invoice["issue_date"])),
        ("Due", str(invoice["due_date"])),
        ("Order", invoice.get("order_number") or ""),
    ]
    for k, v in meta:
        pdf.cell(28, 6, k)
        pdf.cell(0, 6, v, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Bill to", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for part in [customer["name"], customer.get("address") or "", customer.get("email") or ""]:
        if part:
            pdf.cell(0, 5, part, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    widths = (90, 25, 35, 35)
    pdf.set_fill_color(238, 242, 239)
    pdf.set_font("Helvetica", "B", 9)
    for title, w, align in zip(("Item", "Qty", "Unit price", "Amount"), widths, "LRRR", strict=True):
        pdf.cell(w, 8, title, border="B", align=align, fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 10)
    for ln in lines:
        pdf.cell(widths[0], 7, str(ln["description"])[:60])
        pdf.cell(widths[1], 7, f"{Decimal(ln['quantity']).normalize():f}", align="R")
        pdf.cell(widths[2], 7, _money(Decimal(ln["unit_price"]), cur), align="R")
        pdf.cell(widths[3], 7, _money(Decimal(ln["line_total"]), cur), align="R")
        pdf.ln()
    pdf.ln(2)
    for label, value, bold in (
        ("Subtotal", invoice["subtotal"], False),
        ("Tax", invoice["tax"], False),
        ("Total due", invoice["total"], True),
    ):
        pdf.set_font("Helvetica", "B" if bold else "", 10)
        pdf.cell(sum(widths[:3]), 7, label, align="R")
        pdf.cell(widths[3], 7, _money(Decimal(value), cur), align="R")
        pdf.ln()
    pdf.ln(8)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(110, 110, 110)
    pdf.multi_cell(0, 4, "Prepared by Keel from the approved order. Each line traces back to the source document.")
    return bytes(pdf.output())
