"""Invoicing with its own approval gate. Issuing an invoice is a separate decision from creating an order."""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keel.audit.service import audit, next_number
from keel.domain.models import Customer, Invoice, InvoiceLine, Order, OrderLine, Product
from keel.platform.errors import Conflict, NotFound
from keel.workflows.approvals import consume, request_approval

GATE = "issue_invoice"


async def invoice_proposal(db: AsyncSession, order_id: uuid.UUID, issue_date: date) -> dict[str, Any]:
    order = await db.get(Order, order_id)
    if order is None:
        raise NotFound("Order not found.")
    if order.status != "approved":
        raise Conflict(f"Order {order.number} is already {order.status}.")
    customer = await db.get(Customer, order.customer_id) if order.customer_id else None
    if customer is None:
        raise Conflict("The order has no customer.")
    lines = (await db.scalars(select(OrderLine).where(OrderLine.order_id == order_id))).all()
    subtotal = sum((ln.line_total for ln in lines), Decimal(0))
    return {
        "order_id": str(order.id), "order_number": order.number, "customer_id": str(customer.id),
        "customer": customer.name, "currency": order.currency, "issue_date": issue_date.isoformat(),
        "due_date": (issue_date + timedelta(days=customer.payment_terms_days)).isoformat(),
        "lines": [{"product_id": str(ln.product_id) if ln.product_id else None, "description": ln.description,
                   "quantity": str(ln.quantity), "unit_price": str(ln.unit_price), "line_total": str(ln.line_total)}
                  for ln in lines],
        "subtotal": str(subtotal), "tax": "0.00", "total": str(subtotal),
    }


async def stage_invoice(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, order_id: uuid.UUID,
                        issue_date: date) -> tuple[uuid.UUID, dict[str, Any]]:
    p = await invoice_proposal(db, order_id, issue_date)
    summary = {
        "text": f"Issue invoice for order {p['order_number']} to {p['customer']}: {len(p['lines'])} lines, "
                f"{p['currency']} {Decimal(p['total']):,.2f}, due {p['due_date']}. It will not be emailed.",
        "total": p["total"], "currency": p["currency"], "can_approve": True, "blocks": [],
    }
    approval = await request_approval(db, org_id, GATE, p, summary, user_id)
    return approval.id, summary


async def issue_invoice(db: AsyncSession, org_id: uuid.UUID, order_id: uuid.UUID, approval_id: uuid.UUID,
                        issue_date: date) -> Invoice:
    p = await invoice_proposal(db, order_id, issue_date)
    approval = await consume(db, approval_id, GATE, p)
    number = f"INV-{await next_number(db, org_id, 'invoice'):05d}"
    inv = Invoice(org_id=org_id, number=number, order_id=order_id, customer_id=uuid.UUID(p["customer_id"]),
                  issue_date=date.fromisoformat(p["issue_date"]), due_date=date.fromisoformat(p["due_date"]),
                  currency=p["currency"], subtotal=Decimal(p["subtotal"]), tax=Decimal(p["tax"]),
                  total=Decimal(p["total"]), approval_id=approval.id)
    db.add(inv)
    await db.flush()
    for ln in p["lines"]:
        db.add(InvoiceLine(org_id=org_id, invoice_id=inv.id,
                           product_id=uuid.UUID(ln["product_id"]) if ln["product_id"] else None,
                           description=ln["description"], quantity=Decimal(ln["quantity"]),
                           unit_price=Decimal(ln["unit_price"]), line_total=Decimal(ln["line_total"])))
    order = await db.get(Order, order_id)
    assert order is not None
    order.status = "invoiced"
    await audit(db, org_id, approval.decided_by, "invoice.issued", "invoice", inv.id, number=number,
                total=p["total"], approval_id=str(approval.id))
    return inv


async def invoice_export_rows(db: AsyncSession, invoices: list[Invoice]) -> list[dict[str, Any]]:
    out = []
    for inv in invoices:
        customer = await db.get(Customer, inv.customer_id) if inv.customer_id else None
        order = await db.get(Order, inv.order_id)
        lines = []
        for ln in await db.scalars(select(InvoiceLine).where(InvoiceLine.invoice_id == inv.id)):
            product = await db.get(Product, ln.product_id) if ln.product_id else None
            lines.append({"sku": product.sku if product else None, "description": ln.description,
                          "quantity": ln.quantity, "unit_price": ln.unit_price, "line_total": ln.line_total})
        out.append({"number": inv.number, "customer": customer.name if customer else "",
                    "issue_date": inv.issue_date, "due_date": inv.due_date, "currency": inv.currency,
                    "terms_days": customer.payment_terms_days if customer else 30,
                    "order_number": order.number if order else "", "lines": lines})
    return out
