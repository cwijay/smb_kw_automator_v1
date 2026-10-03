"""Lot trace: backward to supplier lots, forward to batches, product lots, orders and customers.

Runs as recursive SQL over batch inputs/outputs inside the tenant's RLS session, so a trace can never
cross into another business. Superseded batch versions are ignored.
"""

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

LIVE_BATCH = "NOT EXISTS (SELECT 1 FROM batches n WHERE n.supersedes = b.id)"

BACKWARD = f"""
WITH RECURSIVE up(lot_id, depth) AS (
  SELECT CAST(:lot AS uuid), 0
  UNION
  SELECT bi.lot_id, up.depth + 1 FROM up
  JOIN batches b ON b.output_lot_id = up.lot_id AND {LIVE_BATCH}
  JOIN batch_inputs bi ON bi.batch_id = b.id
  WHERE bi.lot_id IS NOT NULL AND up.depth < 8
)
SELECT l.code, l.kind, l.ingredient, l.supplier, up.depth FROM up JOIN lots l ON l.id = up.lot_id
WHERE up.depth > 0 ORDER BY up.depth, l.code
"""

FORWARD_LOTS = f"""
WITH RECURSIVE down(lot_id, depth) AS (
  SELECT CAST(:lot AS uuid), 0
  UNION
  SELECT b.output_lot_id, down.depth + 1 FROM down
  JOIN batch_inputs bi ON bi.lot_id = down.lot_id
  JOIN batches b ON b.id = bi.batch_id AND {LIVE_BATCH}
  WHERE b.output_lot_id IS NOT NULL AND down.depth < 8
)
SELECT lot_id, depth FROM down
"""

BATCHES_FOR = f"""
SELECT DISTINCT b.number, b.made_on, l.code AS output_lot, p.name AS product
FROM batches b JOIN lots l ON l.id = b.output_lot_id LEFT JOIN products p ON p.id = b.product_id
WHERE {LIVE_BATCH} AND (b.output_lot_id = ANY(:lots) OR b.id IN (
  SELECT batch_id FROM batch_inputs WHERE lot_id = ANY(:lots)))
ORDER BY b.made_on NULLS LAST, b.number
"""

CUSTOMERS_FOR = """
SELECT o.number AS order_number, o.delivery_date, c.name AS customer, c.email, l.code AS lot,
       ol.description AS product, a.quantity
FROM allocations a
JOIN lots l ON l.id = a.lot_id
JOIN order_lines ol ON ol.id = a.order_line_id
JOIN orders o ON o.id = ol.order_id
LEFT JOIN customers c ON c.id = o.customer_id
WHERE a.lot_id = ANY(:lots)
ORDER BY o.delivery_date NULLS LAST, o.number
"""

MISSING_INPUTS = f"""
SELECT b.number, bi.ingredient FROM batch_inputs bi JOIN batches b ON b.id = bi.batch_id
WHERE bi.status = 'missing' AND b.output_lot_id = ANY(:lots) AND {LIVE_BATCH}
"""


async def trace_lot(db: AsyncSession, code: str) -> dict[str, Any] | None:
    lot = (
        await db.execute(text("SELECT id, code, kind, ingredient, supplier FROM lots WHERE code = :c"), {"c": code})
    ).first()
    if lot is None:
        return None
    lot_id: uuid.UUID = lot.id
    backward = [dict(r._mapping) for r in (await db.execute(text(BACKWARD), {"lot": lot_id})).all()]
    lots = [r.lot_id for r in (await db.execute(text(FORWARD_LOTS), {"lot": lot_id})).all()]
    up_ids = [lot_id] + [
        r.id
        for r in (
            await db.execute(text("SELECT id FROM lots WHERE code = ANY(:c)"), {"c": [b["code"] for b in backward]})
        ).all()
    ]
    batches = [dict(r._mapping) for r in (await db.execute(text(BATCHES_FOR), {"lots": lots})).all()]
    customers = [dict(r._mapping) for r in (await db.execute(text(CUSTOMERS_FOR), {"lots": lots})).all()]
    gaps = [dict(r._mapping) for r in (await db.execute(text(MISSING_INPUTS), {"lots": up_ids})).all()]
    return {
        "lot": {"code": lot.code, "kind": lot.kind, "ingredient": lot.ingredient, "supplier": lot.supplier},
        "backward": backward,
        "batches": batches,
        "forward_lots": len(lots) - 1,
        "customers": customers,
        "gaps": [f"Batch {g['number']}: {g['ingredient']} has no lot code" for g in gaps],
    }
