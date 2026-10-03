"""HACCP log → verified readings. A blank critical reading is MISSING, never passed.

Every reading is matched to a critical control point (CCP) with its limits. Missing and out-of-range
readings need a corrective action written by a person before the log can be approved.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keel.audit.models import Approval
from keel.audit.service import audit
from keel.documents.pipeline import latest_extraction
from keel.platform.errors import NotFound
from keel.production.models import CcpDefinition, CorrectiveAction, HaccpReading
from keel.workflows.engine import Flow, register

GATE = "record_haccp"
MATCH_THRESHOLD = 80


def _v(field: dict[str, Any] | None) -> Any:
    return (field or {}).get("value")


def _status(value: Decimal | None, ccp: CcpDefinition | None) -> str:
    if value is None:
        return "missing"
    if ccp is None:
        return "read"
    if ccp.min_value is not None and value < ccp.min_value:
        return "out_of_range"
    if ccp.max_value is not None and value > ccp.max_value:
        return "out_of_range"
    return "read"


def _limit(ccp: CcpDefinition) -> str:
    lo = f"≥ {ccp.min_value:g}" if ccp.min_value is not None else ""
    hi = f"≤ {ccp.max_value:g}" if ccp.max_value is not None else ""
    return " and ".join(x for x in (lo, hi) if x) + f" {ccp.unit}"


async def build_proposal(
    db: AsyncSession, org_id: uuid.UUID, document_id: uuid.UUID, overrides: dict[str, Any]
) -> dict[str, Any]:
    extraction = await latest_extraction(db, document_id)
    if extraction is None:
        raise NotFound("No extraction for this document yet.")
    d = extraction.data
    ccps = list((await db.scalars(select(CcpDefinition).where(CcpDefinition.active.is_(True)))).all())
    by_id = {c.id: c for c in ccps}
    names = {n.lower(): c.id for c in ccps for n in [c.name, *c.aliases]}
    picks: dict[str, str] = overrides.get("line_ccps", {})
    actions: dict[str, str] = overrides.get("corrective_actions", {})
    blocks: list[str] = []
    if not ccps:
        blocks.append("No critical control points are set up yet. Add them under Food safety first.")
    readings = []
    for i, r in enumerate(d.get("readings", [])):
        written = _v(r.get("ccp"))
        ccp: CcpDefinition | None = None
        if picks.get(str(i)):
            ccp = by_id.get(uuid.UUID(picks[str(i)]))
        elif written and names:
            hit = process.extractOne(written.lower(), list(names), scorer=fuzz.WRatio)
            if hit and hit[1] >= MATCH_THRESHOLD:
                ccp = by_id[names[hit[0]]]
        raw = _v(r.get("value"))
        value = Decimal(str(raw)) if raw is not None else None
        status = _status(value, ccp)
        action = actions.get(str(i))
        label = f"Reading {i + 1} ({written or 'unreadable'})"
        if ccp is None and ccps:
            blocks.append(f"{label} does not match a critical control point. Pick one.")
        if status in ("missing", "out_of_range") and not action:
            what = "has no value" if status == "missing" else f"is outside the limit ({_limit(ccp) if ccp else ''})"
            blocks.append(f"{label} {what}. Record the corrective action that was taken.")
        readings.append(
            {
                "path": f"readings[{i}]",
                "ccp_as_written": written,
                "ccp_id": str(ccp.id) if ccp else None,
                "ccp_name": ccp.name if ccp else None,
                "limit": _limit(ccp) if ccp else None,
                "value": str(value) if value is not None else None,
                "unit": _v(r.get("unit")) or (ccp.unit if ccp else None),
                "time": _v(r.get("time")),
                "initials": _v(r.get("initials")),
                "status": status,
                "corrective_action": action,
            }
        )
    return {
        "document_id": str(document_id),
        "extraction_id": str(extraction.id),
        "batch_number": _v(d.get("batch_number")),
        "log_date": _v(d.get("log_date")),
        "operator": _v(d.get("operator")),
        "readings": readings,
        "blocks": blocks,
        "warnings": [c["message"] for c in extraction.checks if c["severity"] == "warn"],
    }


def summary_of(p: dict[str, Any]) -> dict[str, Any]:
    rs = p["readings"]
    ok = sum(r["status"] == "read" for r in rs)
    missing = sum(r["status"] == "missing" for r in rs)
    out = sum(r["status"] == "out_of_range" for r in rs)
    text = f"Record {len(rs)} HACCP reading(s)"
    if p["batch_number"]:
        text += f" for batch {p['batch_number']}"
    if p["log_date"]:
        text += f" on {p['log_date']}"
    text += f": {ok} within limits"
    if missing:
        text += f", {missing} missing"
    if out:
        text += f", {out} out of range"
    return {
        "text": text + ". You are verifying them as the reviewer.",
        "blocks": p["blocks"],
        "can_approve": not p["blocks"],
        "missing": missing,
        "out_of_range": out,
    }


async def commit(
    db: AsyncSession, org_id: uuid.UUID, doc_id: uuid.UUID, p: dict[str, Any], approval: Approval
) -> dict[str, Any]:
    ids = []
    for r in p["readings"]:
        reading = HaccpReading(
            org_id=org_id,
            ccp_id=uuid.UUID(r["ccp_id"]) if r["ccp_id"] else None,
            ccp_as_written=r["ccp_as_written"] or "unreadable",
            batch_number=p["batch_number"],
            value=Decimal(r["value"]) if r["value"] is not None else None,
            unit=r["unit"],
            status=r["status"],
            recorded_on=date.fromisoformat(p["log_date"]) if p["log_date"] else None,
            recorded_at_time=r["time"],
            operator=r["initials"] or p["operator"],
            source_document_id=doc_id,
            approval_id=approval.id,
            verified_by=approval.decided_by,
        )
        db.add(reading)
        await db.flush()
        if r["corrective_action"]:
            db.add(
                CorrectiveAction(
                    org_id=org_id, reading_id=reading.id, action=r["corrective_action"], recorded_by=approval.decided_by
                )
            )
        ids.append(str(reading.id))
    await audit(
        db,
        org_id,
        approval.decided_by,
        "haccp.recorded",
        "document",
        doc_id,
        readings=len(ids),
        approval_id=str(approval.id),
    )
    return {"reading_ids": ids}


register(Flow(kind="haccp_log", gate=GATE, build=build_proposal, summarize=summary_of, commit=commit))
