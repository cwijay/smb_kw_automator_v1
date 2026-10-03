"""Approval gates enforced in code.

A write that sends, spends, publishes or commits needs an approval whose hash matches the exact staged
payload. Approving one batch never covers another, and editing after approval forces a new approval.
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from keel.audit.models import Approval
from keel.audit.service import audit
from keel.platform.errors import ApprovalRequired, NotFound


def _default(o: Any) -> str:
    if isinstance(o, (Decimal, uuid.UUID, datetime)):
        return str(o)
    raise TypeError(type(o))


def payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_default)
    return hashlib.sha256(canonical.encode()).hexdigest()


async def request_approval(
    db: AsyncSession,
    org_id: uuid.UUID,
    gate: str,
    payload: dict[str, Any],
    summary: dict[str, Any],
    requested_by: uuid.UUID | None,
) -> Approval:
    clean = json.loads(json.dumps(payload, default=_default))
    approval = Approval(
        org_id=org_id,
        gate=gate,
        payload_hash=payload_hash(clean),
        summary=summary,
        staged_payload=clean,
        requested_by=requested_by,
    )
    db.add(approval)
    await db.flush()
    return approval


async def decide(db: AsyncSession, approval_id: uuid.UUID, user_id: uuid.UUID, approve: bool) -> Approval:
    approval = await db.get(Approval, approval_id)
    if approval is None:
        raise NotFound("Approval not found.")
    if approval.status != "pending":
        raise ApprovalRequired("This approval was already decided. Review the latest version.")
    approval.status = "approved" if approve else "rejected"
    approval.decided_by, approval.decided_at = user_id, datetime.now(UTC)
    await audit(
        db,
        approval.org_id,
        user_id,
        f"approval.{approval.status}",
        "approval",
        approval.id,
        gate=approval.gate,
        summary=approval.summary,
    )
    return approval


async def consume(db: AsyncSession, approval_id: uuid.UUID | None, gate: str, payload: dict[str, Any]) -> Approval:
    """Called by every write tool. Refuses unless an approved, unused approval matches this payload."""
    if approval_id is None:
        raise ApprovalRequired(f"'{gate}' needs an explicit approval first.")
    approval = await db.get(Approval, approval_id, with_for_update=True)
    if approval is None or approval.gate != gate:
        raise ApprovalRequired(f"No approval for '{gate}'.")
    if approval.status != "approved":
        raise ApprovalRequired(f"Approval for '{gate}' is {approval.status}, not approved.")
    if approval.payload_hash != payload_hash(json.loads(json.dumps(payload, default=_default))):
        raise ApprovalRequired("What is being written differs from what was approved. Approve again.")
    await db.execute(
        update(Approval).where(Approval.id == approval_id).values(status="used", used_at=datetime.now(UTC))
    )
    return approval
