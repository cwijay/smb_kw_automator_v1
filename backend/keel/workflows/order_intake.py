"""Order intake workflow (LangGraph): stage → [gate: create order] → create.

The gate is a real `interrupt()`. Nothing is written until the owner approves the exact summary they
saw; `create` re-stages from the current data and refuses if the hash no longer matches.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy.ext.asyncio import AsyncSession

from keel.audit.models import Approval
from keel.audit.service import audit, next_number
from keel.documents.models import Document
from keel.documents.pipeline import latest_extraction
from keel.domain.matching import catalog, match_customer, match_product, price_for
from keel.domain.models import Customer, Order, OrderLine, WorkflowRun
from keel.identity.models import Org
from keel.platform.db import tenant_session
from keel.platform.errors import ApprovalRequired, Conflict, NotFound
from keel.workflows.approvals import consume, decide, request_approval
from keel.workflows.runtime import checkpointer, thread_config

GATE = "create_order"


class State(TypedDict, total=False):
    org_id: str
    user_id: str | None
    document_id: str
    run_id: str
    approval_id: str | None
    decision: dict[str, Any]
    order_id: str | None


async def build_proposal(
    db: AsyncSession, org_id: uuid.UUID, document_id: uuid.UUID, overrides: dict[str, Any]
) -> dict[str, Any]:
    """Deterministic: same extraction + same overrides → same payload (and hash)."""
    extraction = await latest_extraction(db, document_id)
    if extraction is None:
        raise NotFound("No extraction for this document yet.")
    data = extraction.data
    org = await db.get(Org, org_id)
    assert org is not None

    written_customer = (data.get("customer_name") or {}).get("value")
    customer: dict[str, Any] | None
    if overrides.get("customer_id"):
        cust = await db.get(Customer, uuid.UUID(overrides["customer_id"]))
        customer = {"id": str(cust.id), "name": cust.name, "matched_by": "owner"} if cust else None
    else:
        m = await match_customer(db, written_customer)
        customer = {"id": str(m.id), "name": m.name, "matched_by": f"fuzzy {m.score:.0f}"} if m.id else None

    options, products = await catalog(db)
    line_products: dict[str, str] = overrides.get("line_products", {})
    lines: list[dict[str, Any]] = []
    held: list[dict[str, Any]] = []
    blocks: list[str] = []
    for i, ln in enumerate(data.get("lines", [])):
        desc = (ln.get("description") or {}).get("value")
        qty = (ln.get("quantity") or {}).get("value")
        path = f"lines[{i}]"
        if ln.get("crossed_out"):
            held.append({"path": path, "description": desc, "reason": "crossed out on the paper"})
            continue
        if qty is None:
            held.append({"path": path, "description": desc, "reason": "quantity unreadable; not guessed"})
            continue
        pid = line_products.get(str(i))
        product = products.get(uuid.UUID(pid)) if pid else None
        if product is None:
            pm = match_product(desc, options, products)
            product = products.get(pm.id) if pm.id else None
        if product is None:
            blocks.append(f"Line {i + 1} ('{desc}') does not match a product. Pick one.")
            lines.append({"path": path, "description": desc, "product_id": None, "quantity": str(qty)})
            continue
        unit_price, price_source = await price_for(db, uuid.UUID(customer["id"]) if customer else None, product)
        q = Decimal(str(qty))
        lines.append(
            {
                "path": path,
                "description": desc,
                "product_id": str(product.id),
                "product_name": product.name,
                "sku": product.sku,
                "quantity": str(q),
                "unit": product.unit,
                "unit_price": str(unit_price),
                "price_source": price_source,
                "line_total": str((q * unit_price).quantize(Decimal("0.01"))),
            }
        )
    if customer is None:
        blocks.append(f"Customer '{written_customer or 'unreadable'}' does not match a customer. Pick one.")
    if not any(ln.get("product_id") for ln in lines):
        blocks.append("There are no lines to order.")
    blocks += [
        c["message"]
        for c in extraction.checks
        if c["severity"] == "block" and c["code"] not in ("customer_missing", "quantity_unreadable", "no_lines")
    ]
    total = sum((Decimal(ln["line_total"]) for ln in lines if ln.get("line_total")), Decimal(0))
    paper_total = (data.get("total_written") or {}).get("value")
    return {
        "document_id": str(document_id),
        "extraction_id": str(extraction.id),
        "currency": org.currency,
        "customer": customer,
        "customer_as_written": written_customer,
        "order_number": (data.get("order_number") or {}).get("value"),
        "order_date": (data.get("order_date") or {}).get("value"),
        "delivery_date": (data.get("delivery_date") or {}).get("value"),
        "lines": lines,
        "held": held,
        "blocks": blocks,
        "total": str(total),
        "paper_total": paper_total,
        "warnings": [c["message"] for c in extraction.checks if c["severity"] == "warn"],
    }


def summary_of(p: dict[str, Any]) -> dict[str, Any]:
    n = sum(1 for ln in p["lines"] if ln.get("product_id"))
    who = p["customer"]["name"] if p["customer"] else "an unmatched customer"
    text = f"Create 1 order for {who}: {n} line{'s' if n != 1 else ''}, {p['currency']} {Decimal(p['total']):,.2f}"
    if p["delivery_date"]:
        text += f", delivery {p['delivery_date']}"
    if p["held"]:
        text += f". {len(p['held'])} line(s) held back and not ordered"
    return {
        "text": text + ".",
        "lines": n,
        "total": p["total"],
        "currency": p["currency"],
        "held": len(p["held"]),
        "blocks": p["blocks"],
        "can_approve": not p["blocks"],
    }


async def _stage(state: State) -> State:
    org_id, doc_id, run_id = uuid.UUID(state["org_id"]), uuid.UUID(state["document_id"]), uuid.UUID(state["run_id"])
    async with tenant_session(org_id) as db:
        run = await db.get(WorkflowRun, run_id)
        assert run is not None
        proposal = await build_proposal(db, org_id, doc_id, run.state.get("overrides", {}))
        user = uuid.UUID(state["user_id"]) if state.get("user_id") else None
        approval = await request_approval(db, org_id, GATE, proposal, summary_of(proposal), user)
        run.status, run.pending_approval_id = "waiting_approval", approval.id
    return {"approval_id": str(approval.id)}


async def _gate(state: State) -> State:
    decision = interrupt({"gate": GATE, "approval_id": state["approval_id"]})
    return {"decision": decision}


def _after_gate(state: State) -> Literal["create", "stage", "reject"]:
    action = state["decision"]["action"]
    return "create" if action == "approve" else "stage" if action == "revise" else "reject"


async def _create(state: State) -> State:
    org_id, doc_id, run_id = uuid.UUID(state["org_id"]), uuid.UUID(state["document_id"]), uuid.UUID(state["run_id"])
    async with tenant_session(org_id) as db:
        run = await db.get(WorkflowRun, run_id)
        assert run is not None
        # Re-stage from the data as it is NOW. If anything changed since approval, the hash differs.
        proposal = await build_proposal(db, org_id, doc_id, run.state.get("overrides", {}))
        approval = await consume(db, uuid.UUID(state["approval_id"]), GATE, proposal)
        number = proposal["order_number"] or f"K-{await next_number(db, org_id, 'order'):05d}"
        order = Order(
            org_id=org_id,
            number=number,
            customer_id=uuid.UUID(proposal["customer"]["id"]),
            customer_name_as_written=proposal["customer_as_written"],
            order_date=date.fromisoformat(proposal["order_date"]) if proposal["order_date"] else date.today(),
            delivery_date=date.fromisoformat(proposal["delivery_date"]) if proposal["delivery_date"] else None,
            currency=proposal["currency"],
            total=Decimal(proposal["total"]),
            source_document_id=doc_id,
            approval_id=approval.id,
            created_by=approval.decided_by,
        )
        db.add(order)
        await db.flush()
        for ln in proposal["lines"]:
            db.add(
                OrderLine(
                    org_id=org_id,
                    order_id=order.id,
                    product_id=uuid.UUID(ln["product_id"]),
                    description=ln["product_name"],
                    quantity=Decimal(ln["quantity"]),
                    unit=ln["unit"],
                    unit_price=Decimal(ln["unit_price"]),
                    line_total=Decimal(ln["line_total"]),
                )
            )
        run.status, run.pending_approval_id = "done", None
        doc = await db.get(Document, doc_id)
        if doc:
            doc.status = "processed"
        await audit(
            db,
            org_id,
            approval.decided_by,
            "order.created",
            "order",
            order.id,
            number=number,
            total=proposal["total"],
            approval_id=str(approval.id),
        )
    return {"order_id": str(order.id)}


async def _reject(state: State) -> State:
    org_id = uuid.UUID(state["org_id"])
    async with tenant_session(org_id) as db:
        run = await db.get(WorkflowRun, uuid.UUID(state["run_id"]))
        assert run is not None
        run.status, run.pending_approval_id = "cancelled", None
        doc = await db.get(Document, uuid.UUID(state["document_id"]))
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
        g.add_node("create", _create)
        g.add_node("reject", _reject)
        g.add_edge(START, "stage")
        g.add_edge("stage", "gate")
        g.add_conditional_edges("gate", _after_gate)
        g.add_edge("create", END)
        g.add_edge("reject", END)
        _graph = g.compile(checkpointer=await checkpointer())
    return _graph


async def start_order_intake(org_id: uuid.UUID, document_id: uuid.UUID, user_id: uuid.UUID | None) -> uuid.UUID:
    async with tenant_session(org_id) as db:
        run = WorkflowRun(org_id=org_id, kind="order_intake", document_id=document_id, state={})
        db.add(run)
    await (await graph()).ainvoke(
        {
            "org_id": str(org_id),
            "user_id": str(user_id) if user_id else None,
            "document_id": str(document_id),
            "run_id": str(run.id),
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
        elif action == "revise":
            merged = dict(run.state.get("overrides", {}))
            for key, val in (overrides or {}).items():
                if key == "line_products":
                    merged["line_products"] = {**merged.get("line_products", {}), **val}
                else:
                    merged[key] = val
            run.state = {**run.state, "overrides": merged}
            await decide(db, approval.id, user_id, approve=False)
        else:
            await decide(db, approval.id, user_id, approve=False)
    result = await (await graph()).ainvoke(Command(resume={"action": action}), thread_config(org_id, run_id))
    return {"order_id": result.get("order_id"), "approval_id": result.get("approval_id")}
