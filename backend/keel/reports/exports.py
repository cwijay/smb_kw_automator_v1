"""Ledger hand-off files. When there is no ledger write access, an import file is a complete outcome."""

import csv
import io
from typing import Any

QBO_COLUMNS = [
    "*InvoiceNo",
    "*Customer",
    "*InvoiceDate",
    "*DueDate",
    "Terms",
    "Memo",
    "Item(Product/Service)",
    "ItemDescription",
    "ItemQuantity",
    "ItemRate",
    "*ItemAmount",
    "Taxable",
    "TaxRate",
]


def qbo_invoices_csv(invoices: list[dict[str, Any]]) -> str:
    """QuickBooks Online invoice import layout, one row per invoice line."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(QBO_COLUMNS)
    for inv in invoices:
        for ln in inv["lines"]:
            w.writerow(
                [
                    inv["number"],
                    inv["customer"],
                    inv["issue_date"].strftime("%m/%d/%Y"),
                    inv["due_date"].strftime("%m/%d/%Y"),
                    f"Net {inv['terms_days']}",
                    f"Order {inv['order_number']}",
                    ln["sku"] or ln["description"],
                    ln["description"],
                    f"{ln['quantity']:f}",
                    f"{ln['unit_price']:.2f}",
                    f"{ln['line_total']:.2f}",
                    "N",
                    "",
                ]
            )
    return buf.getvalue()


def xero_invoices_csv(invoices: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "*ContactName",
            "*InvoiceNumber",
            "*InvoiceDate",
            "*DueDate",
            "Description",
            "*Quantity",
            "*UnitAmount",
            "*AccountCode",
            "*TaxType",
            "Currency",
        ]
    )
    for inv in invoices:
        for ln in inv["lines"]:
            w.writerow(
                [
                    inv["customer"],
                    inv["number"],
                    inv["issue_date"].isoformat(),
                    inv["due_date"].isoformat(),
                    ln["description"],
                    f"{ln['quantity']:f}",
                    f"{ln['unit_price']:.2f}",
                    "200",
                    "Tax Exempt",
                    inv["currency"],
                ]
            )
    return buf.getvalue()
