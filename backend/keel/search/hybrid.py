"""Hybrid document search: exact words (full-text), close spelling (pg_trgm) and, with an embedding
model configured, similar meaning (pgvector), fused with reciprocal rank fusion (RRF).

Runs inside the tenant's RLS session, so results can never include another business's documents.
"""

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from keel.audit.service import record_usage
from keel.documents.models import Chunk
from keel.platform.config import get_settings
from keel.platform.db import tenant_session
from keel.search.embed import embedder, literal

WORDS = """SELECT id, row_number() OVER (ORDER BY ts_rank_cd(tsv, q) DESC) AS r, 'words' AS src
  FROM chunks, websearch_to_tsquery('english', :q) q WHERE tsv @@ q ORDER BY r LIMIT :pool"""
SPELLING = """SELECT id, row_number() OVER (ORDER BY word_similarity(:q, text) DESC) AS r, 'spelling' AS src
  FROM chunks WHERE word_similarity(:q, text) >= :fuzzy ORDER BY r LIMIT :pool"""
MEANING = """SELECT id, row_number() OVER (ORDER BY emb <=> CAST(:e AS vector)) AS r, 'meaning' AS src
  FROM chunks WHERE emb_model = :model AND emb <=> CAST(:e AS vector) <= :max_dist
  ORDER BY r LIMIT :pool"""
FUSE = """
WITH hits AS ({signals}),
fused AS (SELECT id, sum(1.0 / (:k + r)) AS score, array_agg(DISTINCT src) AS matched FROM hits GROUP BY id)
SELECT c.document_id, d.filename, d.kind, c.page_n, c.text, f.score, f.matched,
       ts_headline('english', c.text, websearch_to_tsquery('english', :q), 'MaxWords=25, MinWords=8') AS snippet
FROM fused f JOIN chunks c ON c.id = f.id JOIN documents d ON d.id = c.document_id
ORDER BY f.score DESC, c.page_n LIMIT :limit
"""
SIGNALS = ("words", "spelling", "meaning")


def split(page_text: str, size: int) -> list[str]:
    """Line-aligned windows of about `size` characters, so a hit points at a small part of a page."""
    out: list[str] = []
    cur = ""
    for line in page_text.splitlines():
        if cur and len(cur) + len(line) > size:
            out.append(cur)
            cur = ""
        cur += line + "\n"
    if cur.strip():
        out.append(cur)
    return out


async def index_pages(org_id: uuid.UUID, document_id: uuid.UUID, pages: list[tuple[int, str]]) -> int:
    """Chunk and embed a document's page text. The embedding call happens outside any transaction."""
    s = get_settings()
    items = [(n, t) for n, page in pages for t in split(page, s.chunk_chars) if t.strip()]
    if not items:
        return 0
    e = embedder()
    emb = await e.embed([t for _, t in items]) if e else None
    async with tenant_session(org_id) as db:
        for i, (n, t) in enumerate(items):
            chunk = Chunk(org_id=org_id, document_id=document_id, page_n=n, text=t)
            db.add(chunk)
            if emb:
                await db.flush()
                await db.execute(
                    text("UPDATE chunks SET emb = CAST(:e AS vector), emb_model = :m WHERE id = :id"),
                    {"e": literal(emb.vectors[i]), "m": emb.model, "id": chunk.id},
                )
        if emb and emb.tokens:
            await record_usage(
                db,
                org_id,
                "embed",
                model=emb.model,
                input_tokens=emb.tokens,
                output_tokens=0,
                pages=len(pages),
                cost_usd=emb.cost_usd,
                document_id=str(document_id),
                engine=emb.model,
            )
    return len(items)


async def search(db: AsyncSession, query: str, limit: int = 8) -> list[dict[str, Any]]:
    s = get_settings()
    params: dict[str, Any] = {"q": query, "k": s.rrf_k, "pool": s.search_pool, "limit": limit, "fuzzy": s.search_fuzzy}
    signals = [WORDS, SPELLING]
    e = embedder()
    if e is not None:
        q = await e.embed([query])
        params |= {"e": literal(q.vectors[0]), "model": q.model, "max_dist": 1 - s.search_min_similarity}
        signals.append(MEANING)
    sql = FUSE.format(signals=" UNION ALL ".join(f"({x})" for x in signals))
    rows = await db.execute(text(sql), params)
    return [
        {
            "document_id": str(r.document_id),
            "file": r.filename,
            "kind": r.kind,
            "page": r.page_n,
            "score": round(float(r.score), 4),
            "matched": [m for m in SIGNALS if m in r.matched],
            "snippet": r.snippet if "words" in r.matched else near_miss(query, r.text),
        }
        for r in rows
    ]


def near_miss(query: str, chunk: str) -> str:
    """For spelling or meaning hits full-text can't highlight: the closest line, closest word in <b>."""
    from rapidfuzz import fuzz

    lines = [ln.strip() for ln in chunk.splitlines() if ln.strip()] or [""]
    line = max(lines, key=lambda ln: fuzz.partial_ratio(query.lower(), ln.lower()))
    words = line.split()
    if not words:
        return ""
    best = max(range(len(words)), key=lambda i: max(fuzz.ratio(q, words[i].lower()) for q in query.lower().split()))
    words[best] = f"<b>{words[best]}</b>"
    return " ".join(words)


async def reindex(everything: bool = False) -> int:
    """Re-embed documents whose chunks were made by another embedding model (or never indexed).
    `everything` re-chunks and re-embeds all documents, e.g. after changing the chunk size."""
    from sqlalchemy import create_engine, delete, select

    from keel.documents.models import Document, Page
    from keel.documents.render import page_text

    e = embedder()
    if e is None:
        return 0  # nothing to embed offline; words and spelling search read the text directly
    model = e.name
    # Operator command (like `keel migrate`): only the list of orgs comes from the owner role.
    owner = create_engine(get_settings().database_owner_url)
    with owner.connect() as conn:
        org_ids = list(conn.execute(text("SELECT id FROM orgs")).scalars())
    owner.dispose()
    total = 0
    for org_id in org_ids:
        async with tenant_session(org_id) as db:
            current = select(Chunk.document_id).where(text("chunks.emb_model = :m")).params(m=model)
            docs = select(Document.id) if everything else select(Document.id).where(Document.id.not_in(current))
            stale = list((await db.scalars(docs)).all())
        for doc_id in stale:
            async with tenant_session(org_id) as db:
                pages = (await db.scalars(select(Page).where(Page.document_id == doc_id).order_by(Page.n))).all()
                texts = [(p.n, page_text(p.words)) for p in pages]
                await db.execute(delete(Chunk).where(Chunk.document_id == doc_id))
            total += await index_pages(org_id, doc_id, texts)
    return total
