from fastapi import APIRouter, Query
from pydantic import BaseModel

from keel.api.deps import Viewer
from keel.identity.service import Ctx
from keel.platform.db import tenant_session
from keel.search.hybrid import search as hybrid_search

router = APIRouter(tags=["search"])


class SearchHit(BaseModel):
    document_id: str
    file: str
    kind: str
    page: int
    score: float
    matched: list[str]
    snippet: str


@router.get("/search", response_model=list[SearchHit])
async def search(
    q: str = Query(min_length=2, max_length=200), limit: int = Query(10, le=25), ctx: Ctx = Viewer
) -> list[SearchHit]:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        return [SearchHit(**h) for h in await hybrid_search(db, q, limit)]
