from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from keel.platform import db
from keel.platform.config import get_settings
from keel.platform.errors import install_handlers
from keel.platform.logging import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    get_settings().storage_dir.mkdir(parents=True, exist_ok=True)
    yield
    from keel.workflows.runtime import close_checkpointer

    await close_checkpointer()
    await db.dispose()


def create_app() -> FastAPI:
    from keel.agents.routes import router as agent_router
    from keel.catalog.routes import router as catalog_router
    from keel.documents.routes import router as documents_router
    from keel.domain.routes import router as domain_router
    from keel.identity.routes import router as identity_router
    from keel.workflows.routes import router as workflow_router

    app = FastAPI(title="Keel API", version="0.1.0", lifespan=lifespan, generate_unique_id_function=lambda r: r.name)
    install_handlers(app)
    api = APIRouter(prefix="/api")

    @api.get("/healthz", tags=["ops"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "llm": "live" if get_settings().live_llm else "fake"}

    for r in (identity_router, catalog_router, documents_router, workflow_router, domain_router, agent_router):
        api.include_router(r)
    app.include_router(api)
    return app
