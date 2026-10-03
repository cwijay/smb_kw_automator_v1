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
    worker = sub.add_parser("worker")
    worker.add_argument("--drain", action="store_true", help="process queued jobs, then exit (Cloud Run Job)")
    sub.add_parser("migrate")
    sub.add_parser("seed")
    sub.add_parser("openapi")
    reindex_cmd = sub.add_parser("reindex", help="re-embed documents for the current embedding model")
    reindex_cmd.add_argument("--all", action="store_true", help="re-chunk and re-embed every document")
    evals = sub.add_parser("evals", help="parser bake-off").add_subparsers(dest="evals_cmd", required=True)
    synth = evals.add_parser("synthetic", help="write the synthetic gold set")
    synth.add_argument("--out", default="evals/gold/synthetic")
    bake = evals.add_parser("parsers", help="compare extraction engines on a gold set")
    bake.add_argument(
        "--engines", default="local-rules", help="comma separated: local-rules,luna,gemini,sol,reducto,ade"
    )
    bake.add_argument("--gold", default="evals/gold/synthetic")
    bake.add_argument("--out", default="evals/reports")
    bake.add_argument("--min-accuracy", type=float, default=None, help="fail if any engine scores below this")
    bake.add_argument("--max-invented", type=int, default=None, help="fail if any engine invents more values")
    args = parser.parse_args(argv)

    if args.cmd == "api":
        import uvicorn

        uvicorn.run("keel.api.app:create_app", factory=True, host=args.host, port=args.port, reload=args.reload)
    elif args.cmd == "worker":
        from keel.workers.runner import drain_and_exit, run_forever

        asyncio.run(drain_and_exit() if args.drain else run_forever())
    elif args.cmd == "migrate":
        _migrate()
    elif args.cmd == "seed":
        from keel.seed import seed

        asyncio.run(seed())
    elif args.cmd == "reindex":
        from keel.search.hybrid import reindex

        print(f"indexed {asyncio.run(reindex(args.all))} chunk(s)")
    elif args.cmd == "evals":
        _evals(args)
    elif args.cmd == "openapi":
        from keel.api.app import create_app

        json.dump(create_app().openapi(), sys.stdout, indent=2)


def _evals(args: argparse.Namespace) -> None:
    from pathlib import Path

    if args.evals_cmd == "synthetic":
        from keel.evals.synthetic import write

        print(f"wrote {write(Path(args.out))} gold document(s) to {args.out}")
        return
    from keel.evals.parsers import bakeoff

    totals = bakeoff([e.strip() for e in args.engines.split(",") if e.strip()], Path(args.gold), Path(args.out))
    print((Path(args.out) / "report.md").read_text())
    failed = [
        n
        for n, t in totals.items()
        if (args.min_accuracy is not None and t.accuracy < args.min_accuracy)
        or (args.max_invented is not None and t.invented > args.max_invented)
    ]
    if failed:
        raise SystemExit(f"Below the bar: {', '.join(failed)}")


if __name__ == "__main__":
    main()
