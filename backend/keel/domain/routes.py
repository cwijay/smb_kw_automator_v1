import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select

from keel.api.deps import Member, Viewer
from keel.audit.models import Approval, AuditLog, UsageEvent
from keel.documents.models import Document
from keel.domain import invoicing
from keel.domain.models import Customer, Invoice, InvoiceLine, Order, OrderLine
from keel.identity.models import Org
from keel.identity.service import Ctx
from keel.platform.db import tenant_session
from keel.platform.errors import NotFound
from keel.reports.exports import qbo_invoices_csv, xero_invoices_csv
from keel.reports.invoice_pdf import render_invoice
from keel.workflows.approvals import decide

router = APIRouter(tags=["orders"])


class LineOut(BaseModel):
    description: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    line_total: Decimal


class OrderOut(BaseModel):
    id: str
    number: str | None
    customer: str | None
    customer_as_written: str | None
    order_date: date | None
    delivery_date: date | None
    status: str
    currency: str
    total: Decimal
    source_document_id: str | None
    lines: list[LineOut] = []


class InvoiceOut(BaseModel):
    id: str
    number: str
    order_id: str
    customer: str | None
    issue_date: date
    due_date: date
    status: str
    currency: str
    total: Decimal


class StageOut(BaseModel):
    approval_id: str
    summary: dict[str, Any]


class IssueIn(BaseModel):
    approval_id: uuid.UUID


class ApprovalDecisionIn(BaseModel):
    approve: bool


class Dashboard(BaseModel):
    currency: str
    to_review: int
    pending_approvals: int
    unbilled_orders: int
    unbilled_value: Decimal
    orders_7d: int
    invoiced_30d: Decimal
    ai_spend_month_usd: Decimal
    pages_month: int


class ActivityOut(BaseModel):
    at: datetime
    action: str
    target_type: str | None
    data: dict[str, Any]


async def _order_out(db: Any, o: Order, with_lines: bool = False) -> OrderOut:
    cust = await db.get(Customer, o.customer_id) if o.customer_id else None
    lines = []
    if with_lines:
        lines = [
            LineOut(
                description=ln.description,
                quantity=ln.quantity,
                unit=ln.unit,
                unit_price=ln.unit_price,
                line_total=ln.line_total,
            )
            for ln in await db.scalars(select(OrderLine).where(OrderLine.order_id == o.id))
        ]
    return OrderOut(
        id=str(o.id),
        number=o.number,
        customer=cust.name if cust else None,
        customer_as_written=o.customer_name_as_written,
        order_date=o.order_date,
        delivery_date=o.delivery_date,
        status=o.status,
        currency=o.currency,
        total=o.total,
        source_document_id=str(o.source_document_id) if o.source_document_id else None,
        lines=lines,
    )


@router.get("/orders", response_model=list[OrderOut])
async def list_orders(ctx: Ctx = Viewer) -> list[OrderOut]:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        orders = (await db.scalars(select(Order).order_by(Order.created_at.desc()).limit(200))).all()
        return [await _order_out(db, o) for o in orders]


@router.get("/orders/{order_id}", response_model=OrderOut)
async def get_order(order_id: uuid.UUID, ctx: Ctx = Viewer) -> OrderOut:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        o = await db.get(Order, order_id)
        if o is None:
            raise NotFound("Order not found.")
        return await _order_out(db, o, with_lines=True)


@router.post("/orders/{order_id}/invoice/stage", response_model=StageOut)
async def stage_invoice(order_id: uuid.UUID, ctx: Ctx = Member) -> StageOut:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        approval_id, summary = await invoicing.stage_invoice(db, ctx.org_id, ctx.user_id, order_id, date.today())
    return StageOut(approval_id=str(approval_id), summary=summary)


@router.post("/approvals/{approval_id}/decide", response_model=dict[str, str])
async def decide_approval(approval_id: uuid.UUID, body: ApprovalDecisionIn, ctx: Ctx = Member) -> dict[str, str]:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        a = await decide(db, approval_id, ctx.user_id, approve=body.approve)
        return {"status": a.status}


@router.post("/orders/{order_id}/invoice", response_model=InvoiceOut)
async def issue_invoice(order_id: uuid.UUID, body: IssueIn, ctx: Ctx = Member) -> InvoiceOut:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        inv = await invoicing.issue_invoice(db, ctx.org_id, order_id, body.approval_id, date.today())
        cust = await db.get(Customer, inv.customer_id) if inv.customer_id else None
        return InvoiceOut(
            id=str(inv.id),
            number=inv.number,
            order_id=str(inv.order_id),
            customer=cust.name if cust else None,
            issue_date=inv.issue_date,
            due_date=inv.due_date,
            status=inv.status,
            currency=inv.currency,
            total=inv.total,
        )


@router.get("/invoices", response_model=list[InvoiceOut])
async def list_invoices(ctx: Ctx = Viewer) -> list[InvoiceOut]:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        out = []
        for inv in await db.scalars(select(Invoice).order_by(Invoice.created_at.desc()).limit(200)):
            cust = await db.get(Customer, inv.customer_id) if inv.customer_id else None
            out.append(
                InvoiceOut(
                    id=str(inv.id),
                    number=inv.number,
                    order_id=str(inv.order_id),
                    customer=cust.name if cust else None,
                    issue_date=inv.issue_date,
                    due_date=inv.due_date,
                    status=inv.status,
                    currency=inv.currency,
                    total=inv.total,
                )
            )
        return out


@router.get("/invoices/{invoice_id}/pdf")
async def invoice_pdf(invoice_id: uuid.UUID, ctx: Ctx = Viewer) -> Response:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        inv = await db.get(Invoice, invoice_id)
        if inv is None:
            raise NotFound("Invoice not found.")
        org = await db.get(Org, ctx.org_id)
        cust = await db.get(Customer, inv.customer_id) if inv.customer_id else None
        order = await db.get(Order, inv.order_id)
        lines = (await db.scalars(select(InvoiceLine).where(InvoiceLine.invoice_id == inv.id))).all()
        pdf = render_invoice(
            org={"name": org.name if org else ""},
            customer={
                "name": cust.name if cust else "",
                "address": cust.address if cust else None,
                "email": cust.email if cust else None,
            },
            invoice={
                "number": inv.number,
                "issue_date": inv.issue_date,
                "due_date": inv.due_date,
                "currency": inv.currency,
                "subtotal": inv.subtotal,
                "tax": inv.tax,
                "total": inv.total,
                "order_number": order.number if order else None,
            },
            lines=[
                {
                    "description": ln.description,
                    "quantity": ln.quantity,
                    "unit_price": ln.unit_price,
                    "line_total": ln.line_total,
                }
                for ln in lines
            ],
        )
    return Response(
        pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{inv.number}.pdf"'}
    )


@router.get("/invoices/export.csv")
async def export_invoices(format: Literal["qbo", "xero"] = "qbo", ctx: Ctx = Viewer) -> Response:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        invoices = list(
            (await db.scalars(select(Invoice).where(Invoice.status != "void").order_by(Invoice.number))).all()
        )
        rows = await invoicing.invoice_export_rows(db, invoices)
    body = qbo_invoices_csv(rows) if format == "qbo" else xero_invoices_csv(rows)
    return Response(
        body, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="invoices-{format}.csv"'}
    )


@router.get("/dashboard", response_model=Dashboard)
async def dashboard(ctx: Ctx = Viewer) -> Dashboard:
    now = datetime.now(UTC)
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        org = await db.get(Org, ctx.org_id)

        async def count(q: Any) -> int:
            return int(await db.scalar(select(func.count()).select_from(q.subquery())) or 0)

        unbilled = await db.execute(
            select(func.count(), func.coalesce(func.sum(Order.total), 0)).where(Order.status == "approved")
        )
        n_unbilled, v_unbilled = unbilled.one()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        usage = (
            await db.execute(
                select(
                    func.coalesce(func.sum(UsageEvent.cost_usd), 0), func.coalesce(func.sum(UsageEvent.pages), 0)
                ).where(UsageEvent.at >= month_start)
            )
        ).one()
        return Dashboard(
            currency=org.currency if org else "USD",
            to_review=await count(select(Document.id).where(Document.status == "needs_review")) or 0,
            pending_approvals=await count(select(Approval.id).where(Approval.status == "pending")) or 0,
            unbilled_orders=n_unbilled,
            unbilled_value=Decimal(v_unbilled),
            orders_7d=await count(select(Order.id).where(Order.created_at >= now - timedelta(days=7))) or 0,
            invoiced_30d=Decimal(
                await db.scalar(
                    select(func.coalesce(func.sum(Invoice.total), 0)).where(
                        Invoice.created_at >= now - timedelta(days=30)
                    )
                )
                or 0
            ),
            ai_spend_month_usd=Decimal(usage[0]),
            pages_month=int(usage[1]),
        )


@router.get("/activity", response_model=list[ActivityOut])
async def activity(ctx: Ctx = Viewer) -> list[ActivityOut]:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        rows = await db.scalars(select(AuditLog).order_by(AuditLog.at.desc()).limit(30))
        return [ActivityOut(at=a.at, action=a.action, target_type=a.target_type, data=a.data) for a in rows]
