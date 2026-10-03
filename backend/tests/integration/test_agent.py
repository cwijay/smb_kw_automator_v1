import json
import uuid

import httpx

from tests.fixtures import order_sheet_pdf
from tests.integration.test_order_loop import _catalog, _upload


async def _ask(c: httpx.AsyncClient, message: str, conv: str | None = None) -> list[dict]:  # type: ignore[type-arg]
    r = await c.post("/api/agent/ask", json={"message": message, "conversation_id": conv or str(uuid.uuid4())})
    assert r.status_code == 200, r.text
    return [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]


async def test_ask_keel_uses_tenant_tools(owner: httpx.AsyncClient) -> None:
    await _catalog(owner)
    detail = await _upload(owner, order_sheet_pdf(["11 Malai Kulfi 4.50 49.50"], number="8008"))
    await owner.post(f"/api/workflows/{detail['document']['run_id']}/decide", json={"action": "approve"})
    events = await _ask(owner, "Which orders are not invoiced yet?")
    tools = [e for e in events if e["type"] == "tool"]
    assert tools and tools[0]["name"] == "find_orders" and tools[0]["args"] == {"status": "approved"}
    text = "".join(e["text"] for e in events if e["type"] == "token")
    assert "8008" in text and "Rasoi Kitchen" in text
    assert events[-1]["type"] == "done"


async def test_ask_keel_never_sees_other_tenant(owner: httpx.AsyncClient, other_tenant: httpx.AsyncClient) -> None:
    await _catalog(owner)
    detail = await _upload(owner, order_sheet_pdf(["2 Malai Kulfi 4.50 9.00"], number="9009"))
    await owner.post(f"/api/workflows/{detail['document']['run_id']}/decide", json={"action": "approve"})
    events = await _ask(other_tenant, "Show me orders")
    text = "".join(e["text"] for e in events if e["type"] == "token")
    assert "9009" not in text


async def test_ask_keel_traces_a_lot(owner: httpx.AsyncClient) -> None:
    from tests.fixtures import batch_sheet_pdf
    from tests.integration.test_production import _upload as upload_kind

    await _catalog(owner)
    doc = await upload_kind(
        owner, batch_sheet_pdf(["Whole Milk M-555 136 lbs"], batch="B-555", lot="L-555"), "batch_sheet", "b.pdf"
    )
    await owner.post(f"/api/workflows/{doc['document']['run_id']}/decide", json={"action": "approve"})
    events = await _ask(owner, "Trace lot L-555 please")
    assert next(e for e in events if e["type"] == "tool")["args"] == {"lot_code": "L-555"}
    assert "M-555" in "".join(e["text"] for e in events if e["type"] == "token")
