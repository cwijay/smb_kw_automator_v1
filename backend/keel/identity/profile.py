"""Tenant profile and onboarding.

The profile holds the business facts Keel relies on (fiscal year end, where the books live, how exports
are formatted, allergens). It is rendered into Ask Keel's memory, so a change is shown as a diff and
written only with a hash-bound approval. Onboarding status is computed from real records, never a flag:
prove value first (read one real paper), then catalog, customers, control points, profile.
"""

import copy
import uuid
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from keel.api.deps import Admin, Viewer
from keel.audit.service import audit
from keel.identity.models import TenantProfile
from keel.identity.service import Ctx
from keel.platform.db import tenant_session
from keel.platform.errors import Conflict
from keel.workflows.approvals import consume, request_approval

GATE = "update_profile"
router = APIRouter(tags=["settings"])

LABELS = {
    "fiscal_year_end": "Fiscal year ends",
    "books_export": "Books export format",
    "ledger": "Books are kept in",
    "allergens": "Allergens handled",
    "notes": "Notes for Keel",
}


class ProfileIn(BaseModel):
    """Only the fields given are changed."""

    fiscal_year_end: str | None = Field(default=None, pattern=r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")
    books_export: Literal["qbo", "xero", "none"] | None = None
    ledger: Literal["quickbooks", "xero", "spreadsheet", "none"] | None = None
    allergens: list[str] | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=500)


class ProfileStageOut(BaseModel):
    approval_id: str
    changes: list[str]


class ProfileApplyIn(ProfileIn):
    approval_id: uuid.UUID


class Step(BaseModel):
    key: str
    title: str
    done: bool
    href: str


class ProfileOut(BaseModel):
    profile: dict[str, Any]
    onboarding: list[Step]


def _clean(body: ProfileIn) -> dict[str, Any]:
    out = body.model_dump(exclude_none=True, exclude={"approval_id"})
    if "allergens" in out:
        out["allergens"] = sorted({a.strip().lower() for a in out["allergens"] if a.strip()})
    if "notes" in out:
        out["notes"] = out["notes"].strip()
    return out


def _show(v: Any) -> str:
    return ", ".join(v) if isinstance(v, list) else (str(v) if v not in (None, "") else "—")


async def _current(db: AsyncSession, org_id: uuid.UUID) -> TenantProfile:
    p = await db.get(TenantProfile, org_id)
    if p is None:
        p = TenantProfile(org_id=org_id, profile={})
        db.add(p)
        await db.flush()
    return p


def _proposal(current: dict[str, Any], change: dict[str, Any]) -> dict[str, Any]:
    diff = {k: {"from": current.get(k), "to": v} for k, v in change.items() if current.get(k) != v}
    lines = [f"{LABELS[k]}: {_show(d['from'])} → {_show(d['to'])}" for k, d in diff.items()]
    return {"diff": diff, "changes": lines}


async def onboarding(db: AsyncSession, profile: dict[str, Any]) -> list[Step]:
    from keel.documents.models import Document
    from keel.domain.models import Customer, Product
    from keel.production.models import CcpDefinition

    async def count(model: Any) -> int:
        return int(await db.scalar(select(func.count()).select_from(model)) or 0)

    read = await db.scalar(select(func.count()).select_from(Document).where(Document.status != "uploaded"))
    return [
        Step(key="first_paper", title="Photograph one real order pad", done=bool(read), href="/"),
        Step(
            key="products",
            title="Add your products and how people write them",
            done=await count(Product) > 0,
            href="/catalog",
        ),
        Step(
            key="customers",
            title="Add your customers and their shorthand",
            done=await count(Customer) > 0,
            href="/catalog",
        ),
        Step(
            key="ccps",
            title="Set your critical control points",
            done=await count(CcpDefinition) > 0,
            href="/food-safety",
        ),
        Step(
            key="profile",
            title="Tell Keel your fiscal year and where your books live",
            done=bool(profile.get("fiscal_year_end") and profile.get("books_export")),
            href="/settings",
        ),
    ]


@router.get("/profile", response_model=ProfileOut)
async def get_profile(ctx: Ctx = Viewer) -> ProfileOut:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        p = await _current(db, ctx.org_id)
        return ProfileOut(profile=p.profile, onboarding=await onboarding(db, p.profile))


@router.post("/profile/stage", response_model=ProfileStageOut)
async def stage_profile(body: ProfileIn, ctx: Ctx = Admin) -> ProfileStageOut:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        p = await _current(db, ctx.org_id)
        proposal = _proposal(p.profile, _clean(body))
        if not proposal["diff"]:
            raise Conflict("Nothing changed.")
        text = "Update the business profile Keel works from: " + "; ".join(proposal["changes"]) + "."
        summary = {"text": text, "changes": proposal["changes"], "blocks": [], "can_approve": True}
        approval = await request_approval(db, ctx.org_id, GATE, proposal, summary, ctx.user_id)
        return ProfileStageOut(approval_id=str(approval.id), changes=proposal["changes"])


@router.post("/profile", response_model=ProfileOut)
async def apply_profile(body: ProfileApplyIn, ctx: Ctx = Admin) -> ProfileOut:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        p = await _current(db, ctx.org_id)
        proposal = _proposal(p.profile, _clean(body))
        approval = await consume(db, body.approval_id, GATE, proposal)  # refuses if the change differs
        updated = copy.deepcopy(p.profile)
        updated.update({k: d["to"] for k, d in proposal["diff"].items()})
        p.profile = updated
        flag_modified(p, "profile")
        await audit(
            db,
            ctx.org_id,
            ctx.user_id,
            "profile.updated",
            "org",
            ctx.org_id,
            changes=proposal["changes"],
            approval_id=str(approval.id),
        )
        return ProfileOut(profile=p.profile, onboarding=await onboarding(db, p.profile))
