"""Keel CLI: one codebase, several run modes.

keel api      HTTP API (uvicorn)
keel worker   background job runner (parsing, extraction, workflows)
keel migrate  database migrations + LangGraph checkpoint tables (as the owner role)
keel seed     demo tenant with users, catalog and sample documents
keel openapi  print the OpenAPI document (used to generate the frontend client)
"""

import argparse
import asyncio
import json
import sys


def _migrate() -> None:
    from alembic import command
    from alembic.config import Config

    from keel.platform.config import get_settings

    settings = get_settings()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", settings.database_owner_url)
    command.upgrade(cfg, "head")
    asyncio.run(_setup_checkpointer(settings.database_owner_url))
    print("migrations applied")


async def _setup_checkpointer(owner_url: str) -> None:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg import AsyncConnection

    dsn = owner_url.replace("postgresql+psycopg://", "postgresql://")
    async with await AsyncConnection.connect(dsn, autocommit=True) as conn:
        await AsyncPostgresSaver(conn).setup()  # type: ignore[arg-type]
        await conn.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON checkpoints, checkpoint_blobs, checkpoint_writes, "
            "checkpoint_migrations TO keel_app"
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="keel")
    sub = parser.add_subparsers(dest="cmd", required=True)
    api = sub.add_parser("api")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8000)
    api.add_argument("--reload", action="store_true")
    sub.add_parser("worker")
    sub.add_parser("migrate")
    sub.add_parser("seed")
    sub.add_parser("openapi")
    args = parser.parse_args(argv)

    if args.cmd == "api":
        import uvicorn

        uvicorn.run("keel.api.app:create_app", factory=True, host=args.host, port=args.port, reload=args.reload)
    elif args.cmd == "worker":
        from keel.workers.runner import run_forever

        asyncio.run(run_forever())
    elif args.cmd == "migrate":
        _migrate()
    elif args.cmd == "seed":
        from keel.seed import seed

        asyncio.run(seed())
    elif args.cmd == "openapi":
        from keel.api.app import create_app

        json.dump(create_app().openapi(), sys.stdout, indent=2)


if __name__ == "__main__":
    main()
