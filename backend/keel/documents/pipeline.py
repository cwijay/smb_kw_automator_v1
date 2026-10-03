"""Document processing: render → OCR → extract (tiered) → validate → evidence → review.

Routing (tiers): text layer or CPU OCR first; then the default extractor (GPT-6 Luna, or the local
rules engine in fake mode); a Gemini re-read only when blocking checks fail or confidence is low and a
Google key is configured. Every model call is metered per tenant.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel
from sqlalchemy import delete, select

from keel.audit.service import audit, record_usage
from keel.documents import ocr
from keel.documents.align import find_box
from keel.documents.engines.base import EngineResult, Extractor, PageInput
from keel.documents.engines.fake import FakeExtractor
from keel.documents.models import Chunk, Document, Extraction, FieldCitation, FieldResult, Page
from keel.documents.render import page_text, render
from keel.documents.schemas import SCHEMAS, OrderPadX
from keel.documents.validators.order import Finding, check_order
from keel.files.storage import doc_key, storage
from keel.platform.config import get_settings
from keel.platform.db import tenant_session
from keel.platform.logging import log


def default_extractor() -> Extractor:
    s = get_settings()
    if not s.live_llm:
        return FakeExtractor()
    from keel.documents.engines.llm import LlmExtractor

    return LlmExtractor(s.model_default)


def escalation_extractor() -> Extractor | None:
    s = get_settings()
    if not s.live_llm or not s.google_api_key:
        return None
    from keel.documents.engines.llm import LlmExtractor

    return LlmExtractor(s.model_vision_handwriting)


def _needs_escalation(findings: list[Finding], data: OrderPadX, low: float) -> bool:
    if any(f.severity == "block" for f in findings):
        return True
    confs = [f.confidence for ln in data.lines for f in (ln.quantity, ln.line_total) if f.status == "read"]
    return bool(confs) and min(confs) < low


def flatten(model: BaseModel, prefix: str = "") -> list[tuple[str, dict[str, Any]]]:
    """(path, {value,status,confidence}) for every leaf field object in an extraction."""
    out: list[tuple[str, dict[str, Any]]] = []
    for name, val in model:
        path = f"{prefix}{name}"
        if isinstance(val, BaseModel) and {"value", "status", "confidence"} <= set(type(val).model_fields):
            out.append((path, val.model_dump(mode="json")))
        elif isinstance(val, BaseModel):
            out.extend(flatten(val, f"{path}."))
        elif isinstance(val, list):
            for i, item in enumerate(val):
                if isinstance(item, BaseModel):
                    out.extend(flatten(item, f"{path}[{i}]."))
    return out


async def process_document(org_id: uuid.UUID, document_id: uuid.UUID) -> uuid.UUID | None:
    """Returns the extraction id, or None when the document is not an order (stored for search only)."""
    s = get_settings()
    async with tenant_session(org_id) as db:
        doc = await db.get(Document, document_id)
        if doc is None:
            return None
        doc.status = "processing"
        key, mime, kind = doc.storage_key, doc.mime, doc.kind
    data = await storage().get(key)
    rendered = render(data, mime)
    inputs: list[PageInput] = []
    page_ids: list[uuid.UUID] = []
    async with tenant_session(org_id) as db:
        await db.execute(delete(Page).where(Page.document_id == document_id))
        await db.execute(delete(Chunk).where(Chunk.document_id == document_id))
        for n, rp in enumerate(rendered, 1):
            words = rp.words
            if not rp.has_text_layer and s.ocr_enabled:
                words = ocr.ocr_words(rp.png)
            image_key = doc_key(org_id, document_id, f"page-{n}.png")
            await storage().put(image_key, rp.png)
            page = Page(org_id=org_id, document_id=document_id, n=n, image_key=image_key, width=rp.width,
                        height=rp.height, has_text_layer=rp.has_text_layer, words=words)
            db.add(page)
            page_ids.append(page.id)
            text = page_text(words)
            inputs.append(PageInput(png=rp.png, text=text, words=words))
            if text.strip():
                db.add(Chunk(org_id=org_id, document_id=document_id, page_n=n, text=text))
        doc = await db.get(Document, document_id)
        assert doc is not None
        doc.page_count = len(rendered)
        if kind not in ("order_pad", "unknown"):
            doc.status = "processed"
            return None

    extractor = default_extractor()
    result: EngineResult = await extractor.extract(inputs, SCHEMAS["order_pad"])
    order = OrderPadX.model_validate(result.data.model_dump())
    findings = check_order(order, today=date.today(), low_confidence=s.low_confidence)
    results = [result]
    escalate = escalation_extractor()
    if escalate is not None and _needs_escalation(findings, order, s.low_confidence):
        second = await escalate.extract(inputs, SCHEMAS["order_pad"],
                                        hint="Second read: earlier checks failed. Read each digit carefully.")
        candidate = OrderPadX.model_validate(second.data.model_dump())
        cand_findings = check_order(candidate, today=date.today(), low_confidence=s.low_confidence)
        results.append(second)
        if sum(f.severity == "block" for f in cand_findings) <= sum(f.severity == "block" for f in findings):
            order, findings, result = candidate, cand_findings, second

    async with tenant_session(org_id) as db:
        for r in results:
            await record_usage(db, org_id, "extract", model=r.model, input_tokens=r.input_tokens,
                               output_tokens=r.output_tokens, pages=len(inputs), cost_usd=r.cost_usd,
                               document_id=str(document_id), engine=r.engine)
        extraction = Extraction(
            org_id=org_id, document_id=document_id, schema_name="order_pad", engine=result.engine,
            data=order.model_dump(mode="json"), checks=[f.dict() for f in findings],
            cost_usd=Decimal(str(sum(r.cost_usd for r in results))),
        )
        db.add(extraction)
        await db.flush()
        await _store_fields(db, org_id, document_id, extraction.id, order, inputs, page_ids, result.engine)
        doc = await db.get(Document, document_id)
        assert doc is not None
        doc.kind = "order_pad"
        doc.status = "needs_review"
        await audit(db, org_id, None, "document.extracted", "document", document_id, engine=result.engine,
                    findings=len(findings))
    log.info("document.processed", document_id=str(document_id), engine=result.engine, findings=len(findings))
    return extraction.id


async def _store_fields(db: Any, org_id: uuid.UUID, document_id: uuid.UUID, extraction_id: uuid.UUID,
                        order: OrderPadX, inputs: list[PageInput], page_ids: list[uuid.UUID], engine: str) -> None:
    for path, f in flatten(order):
        fr = FieldResult(org_id=org_id, document_id=document_id, extraction_id=extraction_id, path=path,
                         value=f["value"], status=f["status"], confidence=f["confidence"], engine=engine)
        for page_id, page in zip(page_ids, inputs, strict=True):
            raw = f["value"]
            if path.endswith(("quantity", "unit_price", "line_total", "total_written")) and raw is not None:
                raw = Decimal(str(raw))
            box = find_box(raw, page.words)
            if box is not None:
                fr.page_id = page_id
                db.add(fr)
                await db.flush()
                db.add(FieldCitation(org_id=org_id, field_result_id=fr.id, page_id=page_id, x=box["x"],
                                     y=box["y"], w=box["w"], h=box["h"], text=box["text"]))
                break
        else:
            fr.page_id = page_ids[0] if page_ids else None
            db.add(fr)


async def latest_extraction(db: Any, document_id: uuid.UUID) -> Extraction | None:
    return await db.scalar(  # type: ignore[no-any-return]
        select(Extraction).where(Extraction.document_id == document_id).order_by(Extraction.created_at.desc())
    )
