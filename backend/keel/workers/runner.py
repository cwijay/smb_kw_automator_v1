"""Postgres-backed job queue (no in-process state). Safe with many workers via SKIP LOCKED."""

import asyncio
import traceback
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import text

from keel.audit.models import Job
from keel.platform.config import get_settings
from keel.platform.db import global_session, tenant_session
from keel.platform.logging import configure_logging, log

Handler = Callable[[uuid.UUID, dict[str, Any]], Awaitable[None]]
MAX_ATTEMPTS = 3


async def enqueue(db: Any, org_id: uuid.UUID, kind: str, **payload: Any) -> None:
    db.add(Job(org_id=org_id, kind=kind, payload=payload))


async def _process_document(org_id: uuid.UUID, payload: dict[str, Any]) -> None:
    from keel.documents.models import Document
    from keel.documents.pipeline import process_document
    from keel.workflows.order_intake import start_order_intake

    doc_id = uuid.UUID(payload["document_id"])
    try:
        extraction_id = await process_document(org_id, doc_id)
    except Exception as exc:
        async with tenant_session(org_id) as db:
            doc = await db.get(Document, doc_id)
            if doc:
                doc.status, doc.error = "failed", f"{type(exc).__name__}: {exc}"[:500]
        raise
    if extraction_id is not None:
        requested_by = payload.get("user_id")
        await start_order_intake(org_id, doc_id, uuid.UUID(requested_by) if requested_by else None)


HANDLERS: dict[str, Handler] = {"process_document": _process_document}


async def run_once() -> bool:
    """Claim and run one job. Returns False when the queue is empty."""
    async with global_session() as db:
        row = (
            await db.execute(
                text(
                    "UPDATE jobs SET status='running', locked_at=now(), attempts=attempts+1 WHERE id = ("
                    " SELECT id FROM jobs WHERE status='queued' AND run_after <= now()"
                    " ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING id, org_id, kind, payload, attempts"
                )
            )
        ).first()
    if row is None:
        return False
    try:
        await HANDLERS[row.kind](row.org_id, row.payload)
        status, error = "done", None
    except Exception:
        error = traceback.format_exc()[-2000:]
        status = "failed" if row.attempts >= MAX_ATTEMPTS else "queued"
        log.error("job.failed", job=str(row.id), kind=row.kind, attempts=row.attempts)
    async with global_session() as db:
        await db.execute(
            text(
                "UPDATE jobs SET status=:s, last_error=:e, locked_at=NULL, "
                "run_after = now() + make_interval(secs => 5 * attempts) WHERE id=:id"
            ),
            {"s": status, "e": error, "id": row.id},
        )
    return True


async def drain() -> None:
    while await run_once():
        pass


async def run_forever() -> None:
    configure_logging()
    log.info("worker.started")
    while True:
        if not await run_once():
            await asyncio.sleep(get_settings().worker_poll_seconds)
