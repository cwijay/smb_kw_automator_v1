"""Read-only tools for Ask Keel. Each tool is bound to one tenant at construction time.

Tools never take an org id from the model; the closure carries it, and RLS enforces it again.
They return compact JSON, not raw rows.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from langchain_core.tools import BaseTool, tool
from sqlalchemy import func, select, text

from keel.audit.models import Approval, UsageEvent
from keel.documents.models import Document
from keel.domain.models import Customer, Invoice, Order, OrderLine, Product
from keel.identity.models import Org
from keel.platform.db import tenant_session


def _j(obj: Any) -> str:
    return json.dumps(obj, default=lambda o: str(o) if isinstance(o, (Decimal, uuid.UUID, datetime)) else o.isoformat())


def build_tools(org_id: uuid.UUID, user_id: uuid.UUID) -> list[BaseTool]:
    def session() -> Any:
        return tenant_session(org_id, user_id)

    @tool
    async def business_snapshot() -> str:
        """Today's picture: documents waiting for review, approvals pending, orders not yet invoiced
        (count and value), invoiced in the last 30 days, and AI spend this month."""
        now = datetime.now(UTC)
        async with session() as db:
            org = await db.get(Org, org_id)
            unbilled = (
                await db.execute(
                    select(func.count(), func.coalesce(func.sum(Order.total), 0)).where(Order.status == "approved")
                )
            ).one()
            return _j(
                {
                    "currency": org.currency if org else None,
                    "documents_to_review": await db.scalar(
                        select(func.count()).where(Document.status == "needs_review")
                    ),
                    "approvals_pending": await db.scalar(select(func.count()).where(Approval.status == "pending")),
                    "orders_not_invoiced": unbilled[0],
                    "value_not_invoiced": unbilled[1],
                    "invoiced_last_30_days": await db.scalar(
                        select(func.coalesce(func.sum(Invoice.total), 0)).where(
                            Invoice.created_at >= now - timedelta(days=30)
                        )
                    ),
                    "ai_spend_this_month_usd": await db.scalar(
                        select(func.coalesce(func.sum(UsageEvent.cost_usd), 0)).where(
                            UsageEvent.at >= now.replace(day=1, hour=0, minute=0, second=0)
                        )
                    ),
                }
            )

    @tool
    async def find_orders(customer: str | None = None, status: str | None = None, days: int = 30) -> str:
        """Orders from the last `days` days. Optional filters: customer (name, fuzzy) and status
        (approved = not yet invoiced, invoiced, cancelled)."""
        since = datetime.now(UTC) - timedelta(days=days)
        async with session() as db:
            q = (
                select(Order, Customer.name)
                .outerjoin(Customer, Customer.id == Order.customer_id)
                .where(Order.created_at >= since)
                .order_by(Order.created_at.desc())
                .limit(50)
            )
            if status:
                q = q.where(Order.status == status)
            if customer:
                q = q.where(Customer.name.ilike(f"%{customer}%"))
            rows = (await db.execute(q)).all()
            return _j(
                {
                    "count": len(rows),
                    "orders": [
                        {
                            "number": o.number,
                            "customer": name,
                            "status": o.status,
                            "total": o.total,
                            "currency": o.currency,
                            "delivery_date": o.delivery_date,
                            "created": o.created_at.date(),
                        }
                        for o, name in rows
                    ],
                }
            )

    @tool
    async def order_details(number: str) -> str:
        """Lines, prices and source document of one order, by its order number."""
        async with session() as db:
            o = await db.scalar(select(Order).where(Order.number == number))
            if o is None:
                return _j({"error": f"No order numbered {number}."})
            cust = await db.get(Customer, o.customer_id) if o.customer_id else None
            lines = (await db.scalars(select(OrderLine).where(OrderLine.order_id == o.id))).all()
            return _j(
                {
                    "number": o.number,
                    "customer": cust.name if cust else None,
                    "written_on_paper_as": o.customer_name_as_written,
                    "status": o.status,
                    "total": o.total,
                    "currency": o.currency,
                    "source_document_id": o.source_document_id,
                    "lines": [
                        {
                            "item": ln.description,
                            "qty": ln.quantity,
                            "unit": ln.unit,
                            "unit_price": ln.unit_price,
                            "line_total": ln.line_total,
                        }
                        for ln in lines
                    ],
                }
            )

    @tool
    async def sales_by_product(days: int = 30) -> str:
        """Quantity and revenue per product from orders in the last `days` days."""
        since = datetime.now(UTC) - timedelta(days=days)
        async with session() as db:
            rows = (
                await db.execute(
                    select(OrderLine.description, func.sum(OrderLine.quantity), func.sum(OrderLine.line_total))
                    .join(Order, Order.id == OrderLine.order_id)
                    .where(Order.created_at >= since, Order.status != "cancelled")
                    .group_by(OrderLine.description)
                    .order_by(func.sum(OrderLine.line_total).desc())
                )
            ).all()
            return _j({"days": days, "products": [{"product": d, "quantity": q, "revenue": r} for d, q, r in rows]})

    @tool
    async def list_invoices(days: int = 60) -> str:
        """Invoices issued in the last `days` days with customer, total and due date."""
        since = datetime.now(UTC) - timedelta(days=days)
        async with session() as db:
            rows = (
                await db.execute(
                    select(Invoice, Customer.name)
                    .outerjoin(Customer, Customer.id == Invoice.customer_id)
                    .where(Invoice.created_at >= since)
                    .order_by(Invoice.number)
                )
            ).all()
            return _j(
                {
                    "count": len(rows),
                    "invoices": [
                        {
                            "number": i.number,
                            "customer": n,
                            "total": i.total,
                            "currency": i.currency,
                            "due_date": i.due_date,
                            "status": i.status,
                        }
                        for i, n in rows
                    ],
                }
            )

    @tool
    async def search_documents(query: str) -> str:
        """Full-text search over the text of uploaded documents. Returns document, page and a snippet."""
        async with session() as db:
            rows = (
                await db.execute(
                    text(
                        "SELECT c.document_id, d.filename, c.page_n, "
                        "ts_headline('english', c.text, plainto_tsquery('english', :q), 'MaxWords=25') AS snippet "
                        "FROM chunks c JOIN documents d ON d.id = c.document_id "
                        "WHERE c.tsv @@ plainto_tsquery('english', :q) "
                        "ORDER BY ts_rank_cd(c.tsv, plainto_tsquery('english', :q)) DESC LIMIT 8"
                    ),
                    {"q": query},
                )
            ).all()
            return _j(
                {
                    "matches": [
                        {"document_id": r.document_id, "file": r.filename, "page": r.page_n, "snippet": r.snippet}
                        for r in rows
                    ]
                }
            )

    @tool
    async def catalog() -> str:
        """Products (SKU, name, unit, list price) and customers known to Keel."""
        async with session() as db:
            products = (await db.scalars(select(Product).order_by(Product.name))).all()
            customers = (await db.scalars(select(Customer).order_by(Customer.name))).all()
            return _j(
                {
                    "products": [
                        {"sku": p.sku, "name": p.name, "unit": p.unit, "price": p.unit_price} for p in products
                    ],
                    "customers": [{"name": c.name, "terms_days": c.payment_terms_days} for c in customers],
                }
            )

    return [business_snapshot, find_orders, order_details, sales_by_product, list_invoices, search_documents, catalog]
