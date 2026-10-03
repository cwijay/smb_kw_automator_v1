"""Shared LangGraph checkpointer (Postgres). Workflows pause at approval gates and resume later."""

from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from keel.platform.config import get_settings

_pool: AsyncConnectionPool | None = None
_saver: AsyncPostgresSaver | None = None


async def checkpointer() -> AsyncPostgresSaver:
    global _pool, _saver
    if _saver is None:
        dsn = get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")
        _pool = AsyncConnectionPool(
            dsn, max_size=5, open=False,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        )
        await _pool.open()
        _saver = AsyncPostgresSaver(_pool)  # type: ignore[arg-type]
    return _saver


async def close_checkpointer() -> None:
    global _pool, _saver
    if _pool is not None:
        await _pool.close()
    _pool, _saver = None, None


def thread_config(org_id: Any, run_id: Any) -> dict[str, Any]:
    # Thread ids are namespaced by tenant; ownership is checked through RLS on workflow_runs first.
    return {"configurable": {"thread_id": f"{org_id}:{run_id}"}}
