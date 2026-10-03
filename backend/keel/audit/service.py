"""Append-only audit log, usage metering and per-tenant counters."""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from keel.audit.models import AuditLog, UsageEvent


async def audit(
    db: AsyncSession,
    org_id: uuid.UUID,
    actor: uuid.UUID | None,
    action: str,
    target_type: str | None = None,
    target_id: str | uuid.UUID | None = None,
    **data: Any,
) -> None:
    db.add(
        AuditLog(
            org_id=org_id,
            actor_user_id=actor,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id else None,
            data=data,
        )
    )


async def record_usage(
    db: AsyncSession,
    org_id: uuid.UUID,
    kind: str,
    *,
    model: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    pages: int = 0,
    cost_usd: float | Decimal = 0,
    **ref: Any,
) -> None:
    db.add(
        UsageEvent(
            org_id=org_id,
            kind=kind,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            pages=pages,
            cost_usd=Decimal(str(cost_usd)),
            ref=ref,
        )
    )


async def next_number(db: AsyncSession, org_id: uuid.UUID, name: str) -> int:
    row = await db.execute(
        text(
            "INSERT INTO counters (org_id, name, value) VALUES (:o, :n, 1) "
            "ON CONFLICT (org_id, name) DO UPDATE SET value = counters.value + 1 RETURNING value"
        ),
        {"o": org_id, "n": name},
    )
    return int(row.scalar_one())
