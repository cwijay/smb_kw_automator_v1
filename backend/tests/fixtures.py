"""Synthetic order sheets (no real customer documents are ever committed)."""

from fpdf import FPDF


def order_sheet_pdf(lines: list[str], *, customer: str = "Rasoi Kitchen", number: str = "1001",
                    date: str = "2026-10-01", deliver: str = "2026-10-03", total: str | None = None,
                    extra: list[str] | None = None) -> bytes:
    pdf = FPDF(format="A5")
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    rows = [f"Customer: {customer}", f"Order #: {number}", f"Date: {date}", f"Deliver: {deliver}",
            "Qty Item Price Amount", *lines]
    if total:
        rows.append(f"Total: {total}")
    rows += extra or []
    for row in rows:
        pdf.cell(0, 8, row, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
