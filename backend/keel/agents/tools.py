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
from sqlalchemy import func, select

from keel.audit.models import Approval, UsageEvent
from keel.documents.models import Document
from keel.domain.models import Customer, Invoice, Order, OrderLine, Product
from keel.identity.models import Org
from keel.platform.db import tenant_session
from keel.search.hybrid import search as hybrid_search


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
        """Search the text of uploaded documents by words and by similarity (tolerates misspellings and shorthand).
        Returns file, page, a snippet and whether it matched on words, similarity or both."""
        async with session() as db:
            return _j({"matches": await hybrid_search(db, query)})

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

    @tool
    async def trace_lot(lot_code: str) -> str:
        """Recall trace for one lot code: supplier lots it came from, batches it went into, and which
        customers received it (order, delivery date). Also lists gaps such as ingredients with no lot code."""
        from keel.production.trace import trace_lot as run_trace

        async with session() as db:
            result = await run_trace(db, lot_code.strip().upper())
        return _j(result or {"error": f"No lot {lot_code} on record."})

    @tool
    async def onboarding_status() -> str:
        """Setup progress: which onboarding steps are done, which is next, and the business profile."""
        from keel.identity.models import TenantProfile
        from keel.identity.profile import onboarding

        async with session() as db:
            p = await db.get(TenantProfile, org_id)
            profile = p.profile if p else {}
            steps = await onboarding(db, profile)
        nxt = next((s for s in steps if not s.done), None)
        return _j(
            {
                "steps": [{"title": s.title, "done": s.done, "where": s.href} for s in steps],
                "next": {"title": nxt.title, "where": nxt.href} if nxt else None,
                "profile": profile,
            }
        )

    @tool
    async def food_safety_status(days: int = 30) -> str:
        """HACCP readings in the last `days` days: counts within limits, missing and out of range, with the
        flagged readings and their corrective actions."""
        from keel.production.models import CcpDefinition, CorrectiveAction, HaccpReading

        since = datetime.now(UTC).date() - timedelta(days=days)
        async with session() as db:
            rows = (
                await db.execute(
                    select(HaccpReading, CcpDefinition.name, CorrectiveAction.action)
                    .outerjoin(CcpDefinition, CcpDefinition.id == HaccpReading.ccp_id)
                    .outerjoin(CorrectiveAction, CorrectiveAction.reading_id == HaccpReading.id)
                    .where(HaccpReading.recorded_on >= since)
                )
            ).all()
        flagged = [
            {
                "ccp": n or r.ccp_as_written,
                "status": r.status,
                "value": r.value,
                "date": r.recorded_on,
                "batch": r.batch_number,
                "corrective_action": a,
            }
            for r, n, a in rows
            if r.status != "read"
        ]
        return _j(
            {
                "days": days,
                "readings": len(rows),
                "within_limits": sum(r.status == "read" for r, _, _ in rows),
                "missing": sum(r.status == "missing" for r, _, _ in rows),
                "out_of_range": sum(r.status == "out_of_range" for r, _, _ in rows),
                "flagged": flagged,
            }
        )

    return [
        business_snapshot,
        find_orders,
        order_details,
        sales_by_product,
        list_invoices,
        search_documents,
        catalog,
        trace_lot,
        food_safety_status,
        onboarding_status,
    ]
