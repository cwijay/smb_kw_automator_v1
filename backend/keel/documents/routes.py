import copy
import hashlib
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Form, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from keel.api.deps import Member, Viewer
from keel.audit.models import Approval
from keel.audit.service import audit
from keel.documents.models import Document, Extraction, FieldCitation, FieldResult, Page
from keel.domain.models import WorkflowRun
from keel.files.storage import doc_key, storage
from keel.identity.service import Ctx
from keel.platform.config import get_settings
from keel.platform.db import tenant_session
from keel.platform.errors import Conflict, NotFound
from keel.platform.ids import uuid7
from keel.workers.runner import enqueue

router = APIRouter(tags=["documents"])

ALLOWED = {"application/pdf", "image/png", "image/jpeg", "image/webp"}


class DocumentOut(BaseModel):
    id: str
    filename: str
    kind: str
    status: str
    source: str
    page_count: int
    created_at: str
    error: str | None = None
    duplicate: bool = False
    run_id: str | None = None
    run_status: str | None = None


class Box(BaseModel):
    page_id: str
    x: float
    y: float
    w: float
    h: float
    text: str


class FieldOut(BaseModel):
    id: str
    path: str
    value: Any
    status: str
    confidence: float
    engine: str
    box: Box | None


class PageOut(BaseModel):
    id: str
    n: int
    width: int
    height: int
    has_text_layer: bool


class ApprovalOut(BaseModel):
    id: str
    gate: str
    status: str
    summary: dict[str, Any]
    proposal: dict[str, Any]


class DocumentDetail(BaseModel):
    document: DocumentOut
    pages: list[PageOut]
    fields: list[FieldOut]
    checks: list[dict[str, Any]]
    engine: str | None
    cost_usd: float
    approval: ApprovalOut | None


class CorrectionIn(BaseModel):
    value: Any


def _doc_out(d: Document, run: WorkflowRun | None = None, duplicate: bool = False) -> DocumentOut:
    return DocumentOut(
        id=str(d.id),
        filename=d.filename,
        kind=d.kind,
        status=d.status,
        source=d.source,
        page_count=d.page_count,
        created_at=d.created_at.isoformat(),
        error=d.error,
        duplicate=duplicate,
        run_id=str(run.id) if run else None,
        run_status=run.status if run else None,
    )


@router.post("/documents", response_model=DocumentOut)
async def upload(
    file: UploadFile,
    kind: Literal["order_pad", "other", "unknown"] = Form("order_pad"),
    source: Literal["upload", "camera", "email"] = Form("upload"),
    ctx: Ctx = Member,
) -> DocumentOut:
    data = await file.read()
    mime = file.content_type or ""
    if mime not in ALLOWED:
        raise Conflict("Upload a PDF or a photo (PNG, JPEG or WebP).", code="unsupported_type")
    if len(data) > get_settings().max_upload_mb * 1024 * 1024:
        raise Conflict(f"Files up to {get_settings().max_upload_mb} MB only.", code="too_large")
    digest = hashlib.sha256(data).hexdigest()
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        existing = await db.scalar(select(Document).where(Document.sha256 == digest))
        if existing:
            # The same photo twice is one set of orders: never process it again.
            return _doc_out(existing, duplicate=True)
        doc_id = uuid7()
        key = doc_key(ctx.org_id, doc_id, f"original-{(file.filename or 'upload').replace('/', '_')}")
        await storage().put(key, data)
        doc = Document(
            id=doc_id,
            org_id=ctx.org_id,
            kind=kind,
            filename=file.filename or "upload",
            mime=mime,
            size_bytes=len(data),
            sha256=digest,
            storage_key=key,
            source=source,
            created_by=ctx.user_id,
        )
        db.add(doc)
        await db.flush()
        await enqueue(db, ctx.org_id, "process_document", document_id=str(doc_id), user_id=str(ctx.user_id))
        await audit(db, ctx.org_id, ctx.user_id, "document.uploaded", "document", doc_id, filename=doc.filename)
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        fresh = await db.get(Document, doc_id)
        assert fresh is not None
        return _doc_out(fresh)


async def _run_for(db: Any, document_id: uuid.UUID) -> WorkflowRun | None:
    return await db.scalar(  # type: ignore[no-any-return]
        select(WorkflowRun).where(WorkflowRun.document_id == document_id).order_by(WorkflowRun.created_at.desc())
    )


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(ctx: Ctx = Viewer) -> list[DocumentOut]:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        docs = (await db.scalars(select(Document).order_by(Document.created_at.desc()).limit(200))).all()
        runs: dict[uuid.UUID, WorkflowRun] = {}
        for r in await db.scalars(select(WorkflowRun).order_by(WorkflowRun.created_at)):
            if r.document_id:
                runs[r.document_id] = r
        return [_doc_out(d, runs.get(d.id)) for d in docs]


@router.get("/documents/{document_id}", response_model=DocumentDetail)
async def detail(document_id: uuid.UUID, ctx: Ctx = Viewer) -> DocumentDetail:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        doc = await db.get(Document, document_id)
        if doc is None:
            raise NotFound("Document not found.")
        pages = (await db.scalars(select(Page).where(Page.document_id == document_id).order_by(Page.n))).all()
        extraction = await db.scalar(
            select(Extraction).where(Extraction.document_id == document_id).order_by(Extraction.created_at.desc())
        )
        fields: list[FieldOut] = []
        if extraction:
            rows = await db.execute(
                select(FieldResult, FieldCitation)
                .outerjoin(FieldCitation, FieldCitation.field_result_id == FieldResult.id)
                .where(FieldResult.extraction_id == extraction.id)
            )
            for fr, cit in rows:
                box = Box(page_id=str(cit.page_id), x=cit.x, y=cit.y, w=cit.w, h=cit.h, text=cit.text) if cit else None
                fields.append(
                    FieldOut(
                        id=str(fr.id),
                        path=fr.path,
                        value=fr.value,
                        status=fr.status,
                        confidence=fr.confidence,
                        engine=fr.engine,
                        box=box,
                    )
                )
        run = await _run_for(db, document_id)
        approval = None
        if run and run.pending_approval_id:
            a = await db.get(Approval, run.pending_approval_id)
            if a:
                approval = ApprovalOut(
                    id=str(a.id), gate=a.gate, status=a.status, summary=a.summary, proposal=a.staged_payload
                )
        return DocumentDetail(
            document=_doc_out(doc, run),
            pages=[
                PageOut(id=str(p.id), n=p.n, width=p.width, height=p.height, has_text_layer=p.has_text_layer)
                for p in pages
            ],
            fields=sorted(fields, key=lambda f: _path_key(f.path)),
            checks=extraction.checks if extraction else [],
            engine=extraction.engine if extraction else None,
            cost_usd=float(extraction.cost_usd) if extraction else 0.0,
            approval=approval,
        )


def _path_key(path: str) -> tuple[Any, ...]:
    import re

    return tuple(int(p) if p.isdigit() else p for p in re.split(r"[\[\].]+", path) if p)


@router.get("/documents/{document_id}/pages/{n}/image")
async def page_image(document_id: uuid.UUID, n: int, ctx: Ctx = Viewer) -> Response:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        page = await db.scalar(select(Page).where(Page.document_id == document_id, Page.n == n))
        if page is None:
            raise NotFound("Page not found.")
        key = page.image_key
    return Response(
        await storage().get(key), media_type="image/png", headers={"Cache-Control": "private, max-age=3600"}
    )


def _set_path(data: dict[str, Any], path: str, value: Any) -> None:
    parts = [int(p) if p.isdigit() else p for p in path.replace("]", "").replace("[", ".").split(".")]
    node: Any = data
    for p in parts:
        node = node[p]
    node.update({"value": value, "status": "read" if value not in (None, "") else "blank", "confidence": 1.0})


@router.put("/documents/{document_id}/fields/{field_id}", response_model=FieldOut)
async def correct_field(document_id: uuid.UUID, field_id: uuid.UUID, body: CorrectionIn, ctx: Ctx = Member) -> FieldOut:
    """A human correction. It updates the evidence and supersedes any pending approval."""
    from datetime import UTC, datetime

    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        fr = await db.get(FieldResult, field_id)
        if fr is None or fr.document_id != document_id:
            raise NotFound("Field not found.")
        extraction = await db.get(Extraction, fr.extraction_id)
        assert extraction is not None
        data = copy.deepcopy(extraction.data)
        _set_path(data, fr.path, body.value)
        extraction.data = data
        flag_modified(extraction, "data")
        old = fr.value
        fr.value, fr.status, fr.confidence = body.value, "corrected", 1.0
        fr.corrected_by, fr.corrected_at = ctx.user_id, datetime.now(UTC)
        await audit(
            db, ctx.org_id, ctx.user_id, "field.corrected", "field", fr.id, path=fr.path, old=old, new=body.value
        )
        run = await _run_for(db, document_id)
        run_id = run.id if run and run.status == "waiting_approval" else None
        cit = await db.scalar(select(FieldCitation).where(FieldCitation.field_result_id == fr.id))
        out = FieldOut(
            id=str(fr.id),
            path=fr.path,
            value=fr.value,
            status=fr.status,
            confidence=fr.confidence,
            engine=fr.engine,
            box=Box(page_id=str(cit.page_id), x=cit.x, y=cit.y, w=cit.w, h=cit.h, text=cit.text) if cit else None,
        )
    if run_id:
        from keel.workflows.order_intake import resume

        await resume(ctx.org_id, ctx.user_id, run_id, "revise", {})
    return out
