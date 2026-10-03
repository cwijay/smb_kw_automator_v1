"""Batch sheet → signed-off batch record linking ingredient lots to the output lot.

Traceability rules: an output lot code is required. A blank ingredient lot code is recorded as
'missing' (never invented); approving with missing lot codes needs an explicit acknowledgement.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from keel.audit.models import Approval
from keel.audit.service import audit
from keel.documents.pipeline import latest_extraction
from keel.domain.matching import catalog, match_product
from keel.domain.models import Product
from keel.platform.errors import NotFound
from keel.production.models import Batch, BatchInput, Formula, Lot
from keel.workflows.engine import Flow, register

GATE = "sign_off_batch"
TOLERANCE = Decimal("0.02")  # 2% deviation from the scaled formula is flagged


def _v(field: dict[str, Any] | None) -> Any:
    return (field or {}).get("value")


async def _formula_warnings(
    db: AsyncSession, product_id: uuid.UUID, qty: Decimal | None, ingredients: list[dict[str, Any]]
) -> list[str]:
    formula = await db.scalar(select(Formula).where(Formula.product_id == product_id).order_by(Formula.version.desc()))
    if formula is None or qty is None or not formula.batch_size:
        return []
    scale = qty / formula.batch_size
    used = {(i["ingredient"] or "").lower(): i for i in ingredients}
    out = []
    for item in formula.items:
        expected = Decimal(str(item["quantity"])) * scale
        got = used.get(str(item["ingredient"]).lower())
        if got is None or got["quantity"] is None:
            out.append(f"Formula calls for {expected:.1f} {item['unit']} {item['ingredient']}; none recorded.")
        elif expected and abs(Decimal(got["quantity"]) - expected) / expected > TOLERANCE:
            out.append(
                f"{item['ingredient']}: {got['quantity']} recorded vs {expected:.1f} {item['unit']} expected "
                f"(formula × {scale:.2f})."
            )
    return out


async def build_proposal(
    db: AsyncSession, org_id: uuid.UUID, document_id: uuid.UUID, overrides: dict[str, Any]
) -> dict[str, Any]:
    extraction = await latest_extraction(db, document_id)
    if extraction is None:
        raise NotFound("No extraction for this document yet.")
    d = extraction.data
    blocks: list[str] = []
    written_product = _v(d.get("product_name"))
    product: Product | None = None
    if overrides.get("product_id"):
        product = await db.get(Product, uuid.UUID(overrides["product_id"]))
    else:
        options, products = await catalog(db)
        m = match_product(written_product, options, products)
        product = products.get(m.id) if m.id else None
    if product is None:
        blocks.append(f"Product '{written_product or 'unreadable'}' does not match a product. Pick one.")

    number = _v(d.get("batch_number"))
    output_lot = _v(d.get("output_lot"))
    if not output_lot:
        blocks.append("No output lot code. Correct the 'output lot' field so this batch can be traced.")
    elif await db.scalar(select(Lot.id).where(Lot.code == output_lot)):
        blocks.append(f"Lot {output_lot} is already recorded. A batch can't reuse a lot code.")
    if number and await db.scalar(select(Batch.id).where(Batch.number == number)):
        blocks.append(f"Batch {number} is already recorded.")

    ingredients = [
        {
            "path": f"ingredients[{i}]",
            "ingredient": _v(ing.get("ingredient")),
            "lot_code": _v(ing.get("lot_code")),
            "quantity": str(_v(ing.get("quantity"))) if _v(ing.get("quantity")) is not None else None,
            "unit": _v(ing.get("unit")),
        }
        for i, ing in enumerate(d.get("ingredients", []))
    ]
    missing = [i["ingredient"] for i in ingredients if not i["lot_code"]]
    if missing and not overrides.get("acknowledge_missing_lots"):
        blocks.append(
            f"{len(missing)} ingredient(s) have no lot code ({', '.join(str(m) for m in missing)}). "
            "Correct them, or acknowledge that this batch can't be fully traced."
        )
    qty = _v(d.get("quantity"))
    warnings = [c["message"] for c in extraction.checks if c["severity"] == "warn"]
    if product is not None:
        warnings += await _formula_warnings(db, product.id, Decimal(str(qty)) if qty is not None else None, ingredients)
    return {
        "document_id": str(document_id),
        "extraction_id": str(extraction.id),
        "product": {"id": str(product.id), "name": product.name, "sku": product.sku} if product else None,
        "product_as_written": written_product,
        "batch_number": number,
        "made_on": _v(d.get("made_on")),
        "output_lot": output_lot,
        "quantity": str(qty) if qty is not None else None,
        "unit": _v(d.get("unit")) or (product.unit if product else None),
        "prepared_by": _v(d.get("prepared_by")),
        "ingredients": ingredients,
        "missing_lots": missing,
        "acknowledged_missing_lots": bool(overrides.get("acknowledge_missing_lots")),
        "blocks": blocks,
        "warnings": warnings,
    }


def summary_of(p: dict[str, Any]) -> dict[str, Any]:
    what = p["product"]["name"] if p["product"] else "an unmatched product"
    qty = f"{Decimal(p['quantity']):g} {p['unit'] or ''} ".strip() + " " if p["quantity"] else ""
    text = f"Sign off batch {p['batch_number'] or '(new)'}: {qty}{what}, output lot {p['output_lot'] or '—'}"
    n = len(p["ingredients"])
    text += f", {n} ingredient(s)"
    if p["missing_lots"]:
        text += f", {len(p['missing_lots'])} without a lot code"
    return {
        "text": text + ". Batch records can't be edited afterwards, only superseded.",
        "blocks": p["blocks"],
        "can_approve": not p["blocks"],
    }


async def commit(
    db: AsyncSession, org_id: uuid.UUID, doc_id: uuid.UUID, p: dict[str, Any], approval: Approval
) -> dict[str, Any]:
    product_id = uuid.UUID(p["product"]["id"])
    out_lot = Lot(
        org_id=org_id,
        code=p["output_lot"],
        kind="product",
        product_id=product_id,
        quantity=Decimal(p["quantity"]) if p["quantity"] else None,
        unit=p["unit"],
    )
    db.add(out_lot)
    await db.flush()  # no ORM relationships: insert the lot before the batch that points at it
    batch = Batch(
        org_id=org_id,
        number=p["batch_number"] or f"B-{out_lot.code}",
        product_id=product_id,
        output_lot_id=out_lot.id,
        made_on=date.fromisoformat(p["made_on"]) if p["made_on"] else None,
        quantity=Decimal(p["quantity"]) if p["quantity"] else None,
        unit=p["unit"],
        prepared_by=p["prepared_by"],
        source_document_id=doc_id,
        approval_id=approval.id,
        signed_off_by=approval.decided_by,
    )
    db.add(batch)
    await db.flush()
    for ing in p["ingredients"]:
        lot_id = None
        if ing["lot_code"]:
            lot = await db.scalar(select(Lot).where(Lot.code == ing["lot_code"]))
            if lot is None:
                lot = Lot(org_id=org_id, code=ing["lot_code"], kind="ingredient", ingredient=ing["ingredient"])
                db.add(lot)
                await db.flush()
            lot_id = lot.id
        db.add(
            BatchInput(
                org_id=org_id,
                batch_id=batch.id,
                lot_id=lot_id,
                ingredient=ing["ingredient"] or "unreadable",
                quantity=Decimal(ing["quantity"]) if ing["quantity"] else None,
                unit=ing["unit"],
                status="read" if lot_id else "missing",
            )
        )
    await audit(
        db,
        org_id,
        approval.decided_by,
        "batch.signed_off",
        "batch",
        batch.id,
        number=batch.number,
        lot=out_lot.code,
        approval_id=str(approval.id),
    )
    return {"batch_id": str(batch.id)}


register(Flow(kind="batch_sheet", gate=GATE, build=build_proposal, summarize=summary_of, commit=commit))
