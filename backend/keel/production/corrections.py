"""Batch corrections. Signed batch records are append-only: a correction is a new version that supersedes
the old one, behind its own hash-bound approval. The old version stays readable; trace uses the latest.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keel.api.deps import Member
from keel.audit.service import audit
from keel.identity.service import Ctx
from keel.platform.db import tenant_session
from keel.platform.errors import Conflict, NotFound
from keel.production.models import Batch, BatchInput, Lot
from keel.workflows.approvals import consume, request_approval

GATE = "correct_batch"
router = APIRouter(tags=["production"])


class InputIn(BaseModel):
    ingredient: str = Field(min_length=1, max_length=120)
    lot_code: str | None = Field(default=None, max_length=60)
    quantity: Decimal | None = None
    unit: str | None = Field(default=None, max_length=20)


class CorrectionIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)
    made_on: date | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    prepared_by: str | None = None
    inputs: list[InputIn]


class CorrectionStageOut(BaseModel):
    approval_id: str
    summary: dict[str, Any]


class CorrectionDoneIn(CorrectionIn):
    approval_id: uuid.UUID


class CorrectionDoneOut(BaseModel):
    batch_id: str
    version: int


def _num(v: Decimal | None) -> str | None:
    return None if v is None else format(v.normalize(), "f")


async def _current(db: AsyncSession, batch_id: uuid.UUID) -> tuple[Batch, list[dict[str, Any]]]:
    b = await db.get(Batch, batch_id)
    if b is None:
        raise NotFound("Batch not found.")
    if await db.scalar(select(Batch.id).where(Batch.supersedes == b.id)):
        raise Conflict("This version has already been corrected. Correct the latest version instead.")
    rows = await db.execute(
        select(BatchInput, Lot.code).outerjoin(Lot, Lot.id == BatchInput.lot_id).where(BatchInput.batch_id == b.id)
    )
    inputs = [
        {"ingredient": i.ingredient, "lot_code": code, "quantity": _num(i.quantity), "unit": i.unit} for i, code in rows
    ]
    return b, inputs


async def proposal(db: AsyncSession, batch_id: uuid.UUID, change: CorrectionIn) -> dict[str, Any]:
    b, before_inputs = await _current(db, batch_id)
    before: dict[str, Any] = {
        "made_on": b.made_on.isoformat() if b.made_on else None,
        "quantity": _num(b.quantity),
        "unit": b.unit,
        "prepared_by": b.prepared_by,
        "inputs": before_inputs,
    }
    after: dict[str, Any] = {
        "made_on": change.made_on.isoformat() if change.made_on else None,
        "quantity": _num(change.quantity),
        "unit": change.unit,
        "prepared_by": change.prepared_by,
        "inputs": [
            {
                "ingredient": i.ingredient.strip(),
                "lot_code": (i.lot_code or "").strip() or None,
                "quantity": _num(i.quantity),
                "unit": i.unit,
            }
            for i in change.inputs
        ],
    }
    fields = ("made_on", "quantity", "unit", "prepared_by")
    changes = [
        f"{k.replace('_', ' ')}: {before[k] or '—'} → {after[k] or '—'}" for k in fields if before[k] != after[k]
    ]
    old = {i["ingredient"]: i for i in before["inputs"]}
    new = {i["ingredient"]: i for i in after["inputs"]}
    for name in sorted(old.keys() | new.keys()):
        if name not in new:
            changes.append(f"{name}: removed")
        elif name not in old:
            changes.append(f"{name}: added (lot {new[name]['lot_code'] or 'not written down'})")
        elif old[name] != new[name]:
            o, n = old[name], new[name]
            lot = f"lot {o['lot_code'] or '—'} → {n['lot_code'] or '—'}"
            changes.append(f"{name}: {lot}, qty {o['quantity'] or '—'} → {n['quantity'] or '—'}")
    return {
        "batch_id": str(b.id),
        "number": b.number,
        "from_version": b.version,
        "to_version": b.version + 1,
        "reason": change.reason.strip(),
        "after": after,
        "changes": changes,
    }


def _summary(p: dict[str, Any]) -> dict[str, Any]:
    blocks = [] if p["changes"] else ["Nothing changed. Edit a value before asking for approval."]
    missing = [i["ingredient"] for i in p["after"]["inputs"] if not i["lot_code"]]
    text = (
        f"Correct batch {p['number']}: version {p['from_version']} → {p['to_version']}, {len(p['changes'])} change(s)."
    )
    if missing:
        text += f" {len(missing)} ingredient(s) still without a lot code."
    return {"text": text + " The old version stays on record.", "blocks": blocks, "can_approve": not blocks}


@router.post("/batches/{batch_id}/corrections/stage", response_model=CorrectionStageOut)
async def stage_correction(batch_id: uuid.UUID, body: CorrectionIn, ctx: Ctx = Member) -> CorrectionStageOut:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        p = await proposal(db, batch_id, body)
        summary = _summary(p) | {"changes": p["changes"]}
        if summary["blocks"]:
            raise Conflict(summary["blocks"][0])
        approval = await request_approval(db, ctx.org_id, GATE, p, summary, ctx.user_id)
        return CorrectionStageOut(approval_id=str(approval.id), summary=summary)


@router.post("/batches/{batch_id}/corrections", response_model=CorrectionDoneOut)
async def commit_correction(batch_id: uuid.UUID, body: CorrectionDoneIn, ctx: Ctx = Member) -> CorrectionDoneOut:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        p = await proposal(db, batch_id, body)
        approval = await consume(db, body.approval_id, GATE, p)  # refuses if anything differs from what was approved
        old = await db.get(Batch, batch_id)
        assert old is not None
        a = p["after"]
        new = Batch(
            org_id=ctx.org_id,
            number=old.number,
            product_id=old.product_id,
            output_lot_id=old.output_lot_id,
            made_on=date.fromisoformat(a["made_on"]) if a["made_on"] else None,
            quantity=Decimal(a["quantity"]) if a["quantity"] else None,
            unit=a["unit"],
            prepared_by=a["prepared_by"],
            source_document_id=old.source_document_id,
            approval_id=approval.id,
            signed_off_by=approval.decided_by,
            version=old.version + 1,
            supersedes=old.id,
            correction_reason=p["reason"],
        )
        db.add(new)
        await db.flush()
        for i in a["inputs"]:
            lot_id = None
            if i["lot_code"]:
                lot = await db.scalar(select(Lot).where(Lot.code == i["lot_code"]))
                if lot is None:
                    lot = Lot(org_id=ctx.org_id, code=i["lot_code"], kind="ingredient", ingredient=i["ingredient"])
                    db.add(lot)
                    await db.flush()
                lot_id = lot.id
            db.add(
                BatchInput(
                    org_id=ctx.org_id,
                    batch_id=new.id,
                    lot_id=lot_id,
                    ingredient=i["ingredient"],
                    quantity=Decimal(i["quantity"]) if i["quantity"] else None,
                    unit=i["unit"],
                    status="read" if lot_id else "missing",
                )
            )
        await audit(
            db,
            ctx.org_id,
            ctx.user_id,
            "batch.corrected",
            "batch",
            new.id,
            number=old.number,
            version=new.version,
            reason=p["reason"],
            approval_id=str(approval.id),
        )
        return CorrectionDoneOut(batch_id=str(new.id), version=new.version)
