import uuid
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from keel.api.deps import Member, Viewer
from keel.audit.models import Approval
from keel.identity.service import Ctx
from keel.platform.db import tenant_session
from keel.workflows import engine

router = APIRouter(tags=["workflows"])


class DecisionIn(BaseModel):
    """`revise` carries the owner's picks; Keel never guesses them."""

    action: Literal["approve", "revise", "reject"]
    customer_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    line_products: dict[str, uuid.UUID] = {}
    line_ccps: dict[str, uuid.UUID] = {}
    corrective_actions: dict[str, str] = {}
    acknowledge_missing_lots: bool | None = None


class DecisionOut(BaseModel):
    order_id: str | None = None
    batch_id: str | None = None
    reading_ids: list[str] = []
    approval_id: str | None = None


class PendingApproval(BaseModel):
    id: str
    gate: str
    summary: dict[str, Any]
    document_id: str | None
    created_at: str


@router.post("/workflows/{run_id}/decide", response_model=DecisionOut)
async def decide(run_id: uuid.UUID, body: DecisionIn, ctx: Ctx = Member) -> DecisionOut:
    overrides: dict[str, Any] = {}
    if body.customer_id:
        overrides["customer_id"] = str(body.customer_id)
    if body.product_id:
        overrides["product_id"] = str(body.product_id)
    if body.line_products:
        overrides["line_products"] = {k: str(v) for k, v in body.line_products.items()}
    if body.line_ccps:
        overrides["line_ccps"] = {k: str(v) for k, v in body.line_ccps.items()}
    if body.corrective_actions:
        overrides["corrective_actions"] = {k: v.strip() for k, v in body.corrective_actions.items() if v.strip()}
    if body.acknowledge_missing_lots is not None:
        overrides["acknowledge_missing_lots"] = body.acknowledge_missing_lots
    out = await engine.resume(ctx.org_id, ctx.user_id, run_id, body.action, overrides)
    return DecisionOut(approval_id=out["approval_id"], **out["result"])


@router.get("/approvals", response_model=list[PendingApproval])
async def pending(ctx: Ctx = Viewer) -> list[PendingApproval]:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        rows = await db.scalars(
            select(Approval).where(Approval.status == "pending").order_by(Approval.created_at.desc()).limit(50)
        )
        return [
            PendingApproval(
                id=str(a.id),
                gate=a.gate,
                summary=a.summary,
                document_id=a.staged_payload.get("document_id"),
                created_at=a.created_at.isoformat(),
            )
            for a in rows
        ]
