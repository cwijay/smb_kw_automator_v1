"""Inspection binder: every HACCP reading with its status, limit, corrective action and source."""

from datetime import datetime
from typing import Any

from fpdf import FPDF

STATUS = {"read": "OK", "missing": "MISSING", "out_of_range": "OUT OF RANGE"}


def render_binder(
    *, org_name: str, days: int, ccps: list[dict[str, Any]], readings: list[dict[str, Any]], generated: datetime
) -> bytes:
    pdf = FPDF(format="A4", orientation="L")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 9, f"{org_name}: HACCP monitoring records", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(90, 90, 90)
    total = len(readings)
    missing = sum(r["status"] == "missing" for r in readings)
    out = sum(r["status"] == "out_of_range" for r in readings)
    pdf.cell(
        0,
        5,
        f"Last {days} days. {total} readings: {total - missing - out} OK, {missing} missing, {out} out of "
        f"range. Generated {generated:%Y-%m-%d %H:%M} UTC by Keel.",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(3)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Critical limits", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    for c in ccps:
        lim = " and ".join(
            x
            for x in (
                f">= {c['min_value']}" if c["min_value"] is not None else "",
                f"<= {c['max_value']}" if c["max_value"] is not None else "",
            )
            if x
        )
        pdf.cell(0, 5, f"{c['name']}: {lim} {c['unit']}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    cols = (
        ("Date", 24),
        ("Time", 16),
        ("Batch", 28),
        ("Control point", 48),
        ("Value", 24),
        ("Status", 28),
        ("By", 14),
        ("Corrective action", 95),
    )
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(238, 242, 239)
    for title, w in cols:
        pdf.cell(w, 7, title, border="B", fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    for r in readings:
        flagged = r["status"] != "read"
        pdf.set_text_color(170, 40, 30) if flagged else pdf.set_text_color(0, 0, 0)
        value = "" if r["value"] is None else f"{r['value']} {r['unit'] or ''}"
        cells = [
            str(r["recorded_on"] or ""),
            r["time"] or "",
            r["batch_number"] or "",
            r["ccp"],
            value,
            STATUS.get(r["status"], r["status"]),
            r["operator"] or "",
            (r["corrective_action"] or "")[:70],
        ]
        for (_, w), val in zip(cols, cells, strict=True):
            pdf.cell(w, 6, str(val)[:60])
        pdf.ln()
    pdf.set_text_color(110, 110, 110)
    pdf.ln(4)
    pdf.multi_cell(
        0,
        4,
        "Readings were transcribed from photographed or scanned logs and verified by a named "
        "reviewer in Keel. Blank readings are recorded as MISSING, never as passed. Records are "
        "append-only; corrections are new versions.",
    )
    return bytes(pdf.output())
