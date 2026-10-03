"""Database access.

Tenant isolation is enforced by Postgres row-level security. Every tenant-scoped unit of work runs
inside `tenant_session(org_id, user_id)`, which sets `app.org_id` / `app.user_id` with SET LOCAL
semantics (transaction scoped). The runtime role has no BYPASSRLS, so a forgotten filter cannot leak
another tenant's rows.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm.decl_base import _declarative_constructor

from keel.platform.config import get_settings


class Base(DeclarativeBase):
    def __init__(self, **kwargs: object) -> None:
        # Assign UUIDv7 ids at construction (not at flush) so related rows and audit entries can use them.
        if "id" in self.__mapper__.columns and kwargs.get("id") is None:
            from keel.platform.ids import uuid7

            kwargs["id"] = uuid7()
        _declarative_constructor(self, **kwargs)


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url, pool_pre_ping=True, pool_size=10)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def sessionmaker() -> async_sessionmaker[AsyncSession]:
    engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def dispose() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine, _sessionmaker = None, None


async def _set_context(session: AsyncSession, org_id: uuid.UUID | None, user_id: uuid.UUID | None) -> None:
    await session.execute(
        text("SELECT set_config('app.org_id', :org, true), set_config('app.user_id', :usr, true)"),
        {"org": str(org_id) if org_id else "", "usr": str(user_id) if user_id else ""},
    )


@asynccontextmanager
async def tenant_session(org_id: uuid.UUID | None, user_id: uuid.UUID | None = None) -> AsyncIterator[AsyncSession]:
    """One transaction with the tenant context applied. Commits on success, rolls back on error."""
    async with sessionmaker()() as session, session.begin():
        await _set_context(session, org_id, user_id)
        yield session


@asynccontextmanager
async def global_session() -> AsyncIterator[AsyncSession]:
    """Transaction with no tenant context: only global identity tables are visible."""
    async with tenant_session(None, None) as session:
        yield session
