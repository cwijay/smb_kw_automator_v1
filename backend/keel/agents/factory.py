"""Ask Keel: a deepagents analyst with skills, tenant memory and read-only, tenant-bound tools.

- Skills (`/skills/`) and shared rules (`/shared/`) are mounted read-only from the repo.
- The tenant profile is rendered into `/tenant/AGENTS.md` and loaded as memory.
- Writes are denied on every path: Ask Keel explains and finds; it never changes records.
- Conversation state lives in the Postgres checkpointer under a thread id the server builds.
"""

import uuid
from pathlib import Path
from typing import Any, cast

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend
from deepagents.backends.utils import create_file_data
from deepagents.middleware.filesystem import FilesystemPermission
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware
from langchain.chat_models import init_chat_model
from sqlalchemy import select

from keel.agents.offline import OfflineModel
from keel.agents.tools import build_tools
from keel.domain.models import Customer, Product
from keel.identity.models import Org, TenantProfile
from keel.platform.config import get_settings
from keel.platform.db import tenant_session
from keel.workflows.runtime import checkpointer

ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT / "skills"
SHARED_DIR = ROOT / "shared"

SYSTEM = (
    "You are Keel, the back-office assistant for a small food producer. You answer the owner's questions "
    "from Keel's records using your tools. Read /shared/rules.md once if you are unsure about a rule.\n\n"
    + (SHARED_DIR / "rules.md").read_text()
)


def chat_model() -> Any:
    s = get_settings()
    if not s.live_llm:
        return OfflineModel()
    provider, _, name = s.model_default.partition(":")
    kwargs: dict[str, Any] = {"use_responses_api": True, "reasoning": {"effort": "low"}} if provider == "openai" else {}
    return init_chat_model(name, model_provider=provider, **kwargs)


async def tenant_memory(org_id: uuid.UUID, user_id: uuid.UUID) -> str:
    async with tenant_session(org_id, user_id) as db:
        org = await db.get(Org, org_id)
        profile = await db.get(TenantProfile, org_id)
        customers = (await db.scalars(select(Customer.name).order_by(Customer.name).limit(40))).all()
        products = (
            await db.scalars(select(Product).where(Product.active.is_(True)).order_by(Product.name).limit(60))
        ).all()
    assert org is not None
    lines = [
        "## Business context",
        f"- Business: {org.name}",
        f"- Country: {org.country}; currency: {org.currency}; timezone: {org.timezone}",
        f"- Customers: {', '.join(customers) or 'none yet'}",
        f"- Products: {', '.join(f'{p.name} ({p.sku}, {p.unit})' for p in products) or 'none yet'}",
    ]
    for k, v in (profile.profile if profile else {}).items():
        lines.append(f"- {k}: {v}")
    return "\n".join(lines) + "\n"


async def build_agent(org_id: uuid.UUID, user_id: uuid.UUID) -> Any:
    backend = CompositeBackend(
        default=StateBackend(),
        routes={
            "/skills/": FilesystemBackend(root_dir=SKILLS_DIR, virtual_mode=True),
            "/shared/": FilesystemBackend(root_dir=SHARED_DIR, virtual_mode=True),
        },
    )
    return create_deep_agent(
        model=chat_model(),
        tools=build_tools(org_id, user_id),
        system_prompt=SYSTEM,
        skills=["/skills/"],
        memory=["/tenant/AGENTS.md"],
        permissions=[FilesystemPermission(operations=["write"], paths=["/**"], mode="deny")],
        backend=backend,
        middleware=cast(Any, [ModelCallLimitMiddleware(run_limit=8), ToolCallLimitMiddleware(run_limit=10)]),
        checkpointer=await checkpointer(),
        name="ask-keel",
    )


async def agent_input(org_id: uuid.UUID, user_id: uuid.UUID, message: str) -> dict[str, Any]:
    memory = await tenant_memory(org_id, user_id)
    return {
        "messages": [{"role": "user", "content": message}],
        "files": {"/tenant/AGENTS.md": create_file_data(memory)},
    }


def thread(org_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID) -> dict[str, Any]:
    # The server builds the thread id from the verified session, so a client can't open someone else's thread.
    return {"configurable": {"thread_id": f"ask:{org_id}:{user_id}:{conversation_id}"}, "recursion_limit": 40}
