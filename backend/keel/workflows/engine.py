"""Document workflows (LangGraph): stage → [gate] → commit, one graph for every document kind.

Each kind plugs in a `Flow`: how to build a deterministic proposal from the extraction (+ owner
overrides), how to summarise it for the gate, and how to commit it. The gate is a real `interrupt()`;
`commit` re-stages from the data as it is now and `consume()` refuses if the hash no longer matches.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy.ext.asyncio import AsyncSession

from keel.audit.models import Approval
from keel.documents.models import Document
from keel.domain.models import WorkflowRun
from keel.platform.db import tenant_session
from keel.platform.errors import ApprovalRequired, Conflict, NotFound
from keel.workflows.approvals import consume, decide, request_approval
from keel.workflows.runtime import checkpointer, thread_config

Builder = Callable[[AsyncSession, uuid.UUID, uuid.UUID, dict[str, Any]], Awaitable[dict[str, Any]]]
Committer = Callable[[AsyncSession, uuid.UUID, uuid.UUID, dict[str, Any], Approval], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class Flow:
    kind: str
    gate: str
    build: Builder
    summarize: Callable[[dict[str, Any]], dict[str, Any]]
    commit: Committer


FLOWS: dict[str, Flow] = {}
ALIASES = {"order_intake": "order_pad", "unknown": "order_pad"}
MERGED_OVERRIDES = {"line_products", "line_ccps", "corrective_actions"}


def register(flow: Flow) -> Flow:
    FLOWS[flow.kind] = flow
    return flow


def flow_for(kind: str) -> Flow:
    from keel.workflows.flows import batch, haccp, order  # noqa: F401  (registers the flows)

    return FLOWS[ALIASES.get(kind, kind)]


class State(TypedDict, total=False):
    org_id: str
    user_id: str | None
    document_id: str
    run_id: str
    kind: str
    approval_id: str | None
    decision: dict[str, Any]
    result: dict[str, Any]


def _ids(state: State) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    return uuid.UUID(state["org_id"]), uuid.UUID(state["document_id"]), uuid.UUID(state["run_id"])


async def _stage(state: State) -> State:
    org_id, doc_id, run_id = _ids(state)
    flow = flow_for(state["kind"])
    async with tenant_session(org_id) as db:
        run = await db.get(WorkflowRun, run_id)
        assert run is not None
        proposal = await flow.build(db, org_id, doc_id, run.state.get("overrides", {}))
        user = uuid.UUID(state["user_id"]) if state.get("user_id") else None
        approval = await request_approval(db, org_id, flow.gate, proposal, flow.summarize(proposal), user)
        run.status, run.pending_approval_id = "waiting_approval", approval.id
    return {"approval_id": str(approval.id)}


async def _gate(state: State) -> State:
    return {"decision": interrupt({"approval_id": state["approval_id"]})}


def _after_gate(state: State) -> Literal["commit", "stage", "reject"]:
    action = state["decision"]["action"]
    return "commit" if action == "approve" else "stage" if action == "revise" else "reject"


async def _commit(state: State) -> State:
    org_id, doc_id, run_id = _ids(state)
    flow = flow_for(state["kind"])
    async with tenant_session(org_id) as db:
        run = await db.get(WorkflowRun, run_id)
        assert run is not None
        proposal = await flow.build(db, org_id, doc_id, run.state.get("overrides", {}))
        approval = await consume(db, uuid.UUID(state["approval_id"]), flow.gate, proposal)
        result = await flow.commit(db, org_id, doc_id, proposal, approval)
        run.status, run.pending_approval_id = "done", None
        run.state = {**run.state, "result": result}
        doc = await db.get(Document, doc_id)
        if doc:
            doc.status = "processed"
    return {"result": result}


async def _reject(state: State) -> State:
    org_id, doc_id, run_id = _ids(state)
    async with tenant_session(org_id) as db:
        run = await db.get(WorkflowRun, run_id)
        assert run is not None
        run.status, run.pending_approval_id = "cancelled", None
        doc = await db.get(Document, doc_id)
        if doc:
            doc.status = "processed"
    return {}


_graph: Any = None


async def graph() -> Any:
    global _graph
    if _graph is None:
        g = StateGraph(State)
        g.add_node("stage", _stage)
        g.add_node("gate", _gate)
        g.add_node("commit", _commit)
        g.add_node("reject", _reject)
        g.add_edge(START, "stage")
        g.add_edge("stage", "gate")
        g.add_conditional_edges("gate", _after_gate)
        g.add_edge("commit", END)
        g.add_edge("reject", END)
        _graph = g.compile(checkpointer=await checkpointer())
    return _graph


async def start(org_id: uuid.UUID, document_id: uuid.UUID, kind: str, user_id: uuid.UUID | None) -> uuid.UUID:
    kind = flow_for(kind).kind
    async with tenant_session(org_id) as db:
        run = WorkflowRun(org_id=org_id, kind=kind, document_id=document_id, state={})
        db.add(run)
    await (await graph()).ainvoke(
        {
            "org_id": str(org_id),
            "user_id": str(user_id) if user_id else None,
            "document_id": str(document_id),
            "run_id": str(run.id),
            "kind": kind,
        },
        thread_config(org_id, run.id),
    )
    return run.id


async def resume(
    org_id: uuid.UUID, user_id: uuid.UUID, run_id: uuid.UUID, action: str, overrides: dict[str, Any] | None = None
) -> dict[str, Any]:
    async with tenant_session(org_id, user_id) as db:
        run = await db.get(WorkflowRun, run_id)  # RLS: another tenant's run is simply not found
        if run is None:
            raise NotFound("Workflow not found.")
        if run.status != "waiting_approval" or run.pending_approval_id is None:
            raise Conflict("This workflow is not waiting for a decision.")
        approval = await db.get(Approval, run.pending_approval_id)
        assert approval is not None
        if action == "approve":
            if approval.summary.get("blocks"):
                raise ApprovalRequired("Resolve the highlighted problems before approving.")
            await decide(db, approval.id, user_id, approve=True)
        else:
            if action == "revise":
                merged = dict(run.state.get("overrides", {}))
                for key, val in (overrides or {}).items():
                    merged[key] = {**merged.get(key, {}), **val} if key in MERGED_OVERRIDES else val
                run.state = {**run.state, "overrides": merged}
            await decide(db, approval.id, user_id, approve=False)
    out = await (await graph()).ainvoke(Command(resume={"action": action}), thread_config(org_id, run_id))
    return {"result": out.get("result") or {}, "approval_id": out.get("approval_id")}


async def latest_run(db: AsyncSession, document_id: uuid.UUID) -> WorkflowRun | None:
    from sqlalchemy import select

    return await db.scalar(
        select(WorkflowRun).where(WorkflowRun.document_id == document_id).order_by(WorkflowRun.created_at.desc())
    )
