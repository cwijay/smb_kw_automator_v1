"""Production and food safety: batches, CCPs, HACCP readings and binder, lots, allocations, trace."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import aliased

from keel.api.deps import Admin, Member, Viewer
from keel.audit.service import audit
from keel.domain.models import Order, OrderLine, Product
from keel.identity.models import Org
from keel.identity.service import Ctx
from keel.platform.db import tenant_session
from keel.platform.errors import Conflict, NotFound
from keel.production.models import Allocation, Batch, BatchInput, CcpDefinition, CorrectiveAction, HaccpReading, Lot
from keel.production.trace import trace_lot
from keel.reports.haccp_pdf import render_binder

router = APIRouter(tags=["production"])


class BatchInputOut(BaseModel):
    ingredient: str
    lot_code: str | None
    quantity: Decimal | None
    unit: str | None
    status: str


class BatchOut(BaseModel):
    id: str
    number: str
    product: str | None
    output_lot: str | None
    made_on: date | None
    quantity: Decimal | None
    unit: str | None
    prepared_by: str | None
    version: int
    source_document_id: str | None
    inputs: list[BatchInputOut] = []
    supersedes: str | None = None
    superseded_by: str | None = None
    correction_reason: str | None = None


class CcpIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    min_value: Decimal | None = None
    max_value: Decimal | None = None
    unit: str = Field(min_length=1, max_length=20)
    aliases: list[str] = []


class CcpOut(CcpIn):
    id: str


class ReadingOut(BaseModel):
    id: str
    ccp: str
    batch_number: str | None
    value: Decimal | None
    unit: str | None
    status: str
    recorded_on: date | None
    time: str | None
    operator: str | None
    corrective_action: str | None
    source_document_id: str | None


class TraceOut(BaseModel):
    lot: dict[str, Any]
    backward: list[dict[str, Any]]
    batches: list[dict[str, Any]]
    forward_lots: int
    customers: list[dict[str, Any]]
    gaps: list[str]


class AllocateIn(BaseModel):
    lot_code: str = Field(min_length=1, max_length=60)
    quantity: Decimal | None = None


class LotOut(BaseModel):
    code: str
    kind: str
    name: str | None


@router.get("/batches", response_model=list[BatchOut])
async def list_batches(ctx: Ctx = Viewer) -> list[BatchOut]:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        rows = await db.execute(
            select(Batch, Product.name, Lot.code)
            .outerjoin(Product, Product.id == Batch.product_id)
            .outerjoin(Lot, Lot.id == Batch.output_lot_id)
            .where(~select(Successor.id).where(Successor.supersedes == Batch.id).exists())  # latest versions only
            .order_by(Batch.created_at.desc())
            .limit(200)
        )
        return [_batch_out(b, p, lot) for b, p, lot in rows]


Successor = aliased(Batch)


def _batch_out(
    b: Batch,
    product: str | None,
    lot: str | None,
    inputs: list[BatchInputOut] | None = None,
    successor: str | None = None,
) -> BatchOut:
    return BatchOut(
        id=str(b.id),
        number=b.number,
        product=product,
        output_lot=lot,
        made_on=b.made_on,
        quantity=b.quantity,
        unit=b.unit,
        prepared_by=b.prepared_by,
        version=b.version,
        source_document_id=str(b.source_document_id) if b.source_document_id else None,
        inputs=inputs or [],
        supersedes=str(b.supersedes) if b.supersedes else None,
        superseded_by=successor,
        correction_reason=b.correction_reason,
    )


@router.get("/batches/{batch_id}", response_model=BatchOut)
async def get_batch(batch_id: uuid.UUID, ctx: Ctx = Viewer) -> BatchOut:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        b = await db.get(Batch, batch_id)
        if b is None:
            raise NotFound("Batch not found.")
        product = await db.get(Product, b.product_id) if b.product_id else None
        out_lot = await db.get(Lot, b.output_lot_id) if b.output_lot_id else None
        rows = await db.execute(
            select(BatchInput, Lot.code).outerjoin(Lot, Lot.id == BatchInput.lot_id).where(BatchInput.batch_id == b.id)
        )
        inputs = [
            BatchInputOut(ingredient=i.ingredient, lot_code=code, quantity=i.quantity, unit=i.unit, status=i.status)
            for i, code in rows
        ]
        successor = await db.scalar(select(Batch.id).where(Batch.supersedes == b.id))
        return _batch_out(
            b,
            product.name if product else None,
            out_lot.code if out_lot else None,
            inputs,
            str(successor) if successor else None,
        )


@router.get("/ccps", response_model=list[CcpOut])
async def list_ccps(ctx: Ctx = Viewer) -> list[CcpOut]:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        rows = await db.scalars(
            select(CcpDefinition).where(CcpDefinition.active.is_(True)).order_by(CcpDefinition.name)
        )
        return [
            CcpOut(
                id=str(c.id), name=c.name, min_value=c.min_value, max_value=c.max_value, unit=c.unit, aliases=c.aliases
            )
            for c in rows
        ]


@router.post("/ccps", response_model=CcpOut)
async def create_ccp(body: CcpIn, ctx: Ctx = Admin) -> CcpOut:
    if body.min_value is None and body.max_value is None:
        raise Conflict("Give a minimum, a maximum, or both. A control point needs a critical limit.")
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        c = CcpDefinition(org_id=ctx.org_id, **body.model_dump())
        db.add(c)
        await audit(db, ctx.org_id, ctx.user_id, "ccp.created", "ccp", c.id, name=c.name)
    return CcpOut(id=str(c.id), **body.model_dump())


async def _readings(db: Any, since: date) -> list[ReadingOut]:
    rows = await db.execute(
        select(HaccpReading, CcpDefinition.name, CorrectiveAction.action)
        .outerjoin(CcpDefinition, CcpDefinition.id == HaccpReading.ccp_id)
        .outerjoin(CorrectiveAction, CorrectiveAction.reading_id == HaccpReading.id)
        .where((HaccpReading.recorded_on >= since) | HaccpReading.recorded_on.is_(None))
        .order_by(HaccpReading.recorded_on.desc().nulls_last(), HaccpReading.created_at)
    )
    return [
        ReadingOut(
            id=str(r.id),
            ccp=name or r.ccp_as_written,
            batch_number=r.batch_number,
            value=r.value,
            unit=r.unit,
            status=r.status,
            recorded_on=r.recorded_on,
            time=r.recorded_at_time,
            operator=r.operator,
            corrective_action=action,
            source_document_id=str(r.source_document_id) if r.source_document_id else None,
        )
        for r, name, action in rows
    ]


@router.get("/haccp/readings", response_model=list[ReadingOut])
async def list_readings(days: int = 90, ctx: Ctx = Viewer) -> list[ReadingOut]:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        return await _readings(db, date.today() - timedelta(days=days))


@router.get("/haccp/binder.pdf")
async def haccp_binder(days: int = 90, ctx: Ctx = Viewer) -> Response:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        org = await db.get(Org, ctx.org_id)
        readings = await _readings(db, date.today() - timedelta(days=days))
        ccps = await list_ccps(ctx)
    pdf = render_binder(
        org_name=org.name if org else "",
        days=days,
        ccps=[c.model_dump() for c in ccps],
        readings=[r.model_dump() for r in readings],
        generated=datetime.now(UTC),
    )
    return Response(
        pdf, media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="haccp-binder.pdf"'}
    )


@router.get("/lots", response_model=list[LotOut])
async def list_lots(q: str = "", ctx: Ctx = Viewer) -> list[LotOut]:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        rows = await db.execute(
            select(Lot, Product.name)
            .outerjoin(Product, Product.id == Lot.product_id)
            .where(Lot.code.ilike(f"%{q}%"))
            .order_by(Lot.created_at.desc())
            .limit(50)
        )
        return [LotOut(code=lot.code, kind=lot.kind, name=pname or lot.ingredient) for lot, pname in rows]


@router.get("/lots/{code}/trace", response_model=TraceOut)
async def trace(code: str, ctx: Ctx = Viewer) -> TraceOut:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        result = await trace_lot(db, code)
    if result is None:
        raise NotFound(f"No lot {code} on record.")
    return TraceOut(**result)


@router.post("/orders/{order_id}/lines/{line_id}/lots", response_model=dict[str, str])
async def allocate(order_id: uuid.UUID, line_id: uuid.UUID, body: AllocateIn, ctx: Ctx = Member) -> dict[str, str]:
    """Record which product lot went out on an order line (what makes a forward trace possible)."""
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        line = await db.get(OrderLine, line_id)
        if line is None or line.order_id != order_id or await db.get(Order, order_id) is None:
            raise NotFound("Order line not found.")
        lot = await db.scalar(select(Lot).where(Lot.code == body.lot_code, Lot.kind == "product"))
        if lot is None:
            raise NotFound(f"No product lot {body.lot_code}. Sign off its batch first.")
        if await db.scalar(
            select(Allocation.id).where(Allocation.order_line_id == line_id, Allocation.lot_id == lot.id)
        ):
            raise Conflict("That lot is already recorded on this line.")
        db.add(Allocation(org_id=ctx.org_id, order_line_id=line_id, lot_id=lot.id, quantity=body.quantity))
        await audit(db, ctx.org_id, ctx.user_id, "lot.allocated", "order", order_id, lot=lot.code)
    return {"status": "recorded"}
