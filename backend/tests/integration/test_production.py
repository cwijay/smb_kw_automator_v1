import uuid

import httpx
import pytest
from sqlalchemy import text

from keel.platform.db import tenant_session
from keel.workers.runner import drain
from tests.fixtures import batch_sheet_pdf, haccp_log_pdf, order_sheet_pdf
from tests.integration.test_order_loop import _catalog

INGREDIENTS = ["Whole Milk M-0129 136 lbs", "Cream C-0130 280 lbs", "Sugar S-42702 100 lbs", "Rose Water - 140 ml"]


async def _upload(c: httpx.AsyncClient, pdf: bytes, kind: str, name: str) -> dict:  # type: ignore[type-arg]
    r = await c.post("/api/documents", files={"file": (name, pdf, "application/pdf")}, data={"kind": kind})
    assert r.status_code == 200, r.text
    await drain()
    return (await c.get(f"/api/documents/{r.json()['id']}")).json()  # type: ignore[no-any-return]


async def _decide(c: httpx.AsyncClient, run_id: str, **body: object) -> httpx.Response:
    return await c.post(f"/api/workflows/{run_id}/decide", json=body)


async def test_batch_sign_off_then_trace_both_ways(owner: httpx.AsyncClient) -> None:
    await _catalog(owner)
    doc = await _upload(owner, batch_sheet_pdf(INGREDIENTS), "batch_sheet", "batch.pdf")
    assert doc["document"]["kind"] == "batch_sheet"
    proposal, summary = doc["approval"]["proposal"], doc["approval"]["summary"]
    assert proposal["product"]["name"] == "Malai Kulfi" and proposal["output_lot"] == "L-1042"
    # a blank lot code is recorded as missing, and blocks approval until acknowledged
    assert proposal["missing_lots"] == ["Rose Water"] and summary["can_approve"] is False
    run_id = doc["document"]["run_id"]
    assert (await _decide(owner, run_id, action="approve")).status_code == 409
    await _decide(owner, run_id, action="revise", acknowledge_missing_lots=True)
    out = (await _decide(owner, run_id, action="approve")).json()
    batch = (await owner.get(f"/api/batches/{out['batch_id']}")).json()
    assert batch["output_lot"] == "L-1042" and len(batch["inputs"]) == 4
    assert {i["status"] for i in batch["inputs"]} == {"read", "missing"}

    # ship that lot on an order, then trace
    order_doc = await _upload(owner, order_sheet_pdf(["11 Malai Kulfi 4.50 49.50"], number="T-1"), "order_pad", "o.pdf")
    order_id = (await _decide(owner, order_doc["document"]["run_id"], action="approve")).json()["order_id"]
    line = (await owner.get(f"/api/orders/{order_id}")).json()["lines"][0]
    r = await owner.post(f"/api/orders/{order_id}/lines/{line['id']}/lots", json={"lot_code": "L-1042"})
    assert r.status_code == 200, r.text
    assert (await owner.get(f"/api/orders/{order_id}")).json()["lines"][0]["lots"] == ["L-1042"]

    forward = (await owner.get("/api/lots/M-0129/trace")).json()
    assert [c["customer"] for c in forward["customers"]] == ["Rasoi Kitchen"]
    assert forward["batches"][0]["number"] == "B-001"
    backward = (await owner.get("/api/lots/L-1042/trace")).json()
    assert {b["code"] for b in backward["backward"]} == {"M-0129", "C-0130", "S-42702"}
    assert any("Rose Water" in g for g in backward["gaps"])

    # the same lot code can't be produced twice
    again = await _upload(owner, batch_sheet_pdf(INGREDIENTS[:1], batch="B-002"), "batch_sheet", "b2.pdf")
    assert any("L-1042 is already recorded" in b for b in again["approval"]["summary"]["blocks"])


async def test_batch_records_are_append_only(owner: httpx.AsyncClient) -> None:
    await _catalog(owner)
    doc = await _upload(owner, batch_sheet_pdf(INGREDIENTS[:2], batch="B-777", lot="L-777"), "batch_sheet", "b.pdf")
    await _decide(owner, doc["document"]["run_id"], action="approve")
    me = (await owner.get("/api/me")).json()
    with pytest.raises(Exception, match="permission denied"):
        async with tenant_session(uuid.UUID(me["org_id"])) as db:
            await db.execute(text("UPDATE batches SET number = 'tampered'"))


async def _ccps(c: httpx.AsyncClient) -> None:
    for body in (
        {"name": "Fill temperature", "min_value": "165", "unit": "F", "aliases": ["fill temp"]},
        {"name": "Pack weight", "min_value": "6.0", "unit": "lb"},
    ):
        assert (await c.post("/api/ccps", json=body)).status_code == 200


async def test_haccp_missing_and_out_of_range_need_corrective_action(owner: httpx.AsyncClient) -> None:
    await _ccps(owner)
    log = haccp_log_pdf(
        ["Fill temperature 168 F 09:10 RP", "Fill temperature __ F 09:40 RP", "Pack weight 5.6 lb 10:00 RP"]
    )
    doc = await _upload(owner, log, "haccp_log", "haccp.pdf")
    proposal, summary = doc["approval"]["proposal"], doc["approval"]["summary"]
    assert [r["status"] for r in proposal["readings"]] == ["read", "missing", "out_of_range"]
    assert summary["missing"] == 1 and summary["out_of_range"] == 1 and summary["can_approve"] is False
    run_id = doc["document"]["run_id"]
    assert (await _decide(owner, run_id, action="approve")).status_code == 409
    await _decide(
        owner,
        run_id,
        action="revise",
        corrective_actions={
            "1": "Probe not used; batch held and re-checked at 169F",
            "2": "Underweight pouch topped up to 6.1 lb",
        },
    )
    out = (await _decide(owner, run_id, action="approve")).json()
    assert len(out["reading_ids"]) == 3
    readings = (await owner.get("/api/haccp/readings")).json()
    by_status = {r["status"]: r for r in readings}
    assert by_status["missing"]["value"] is None  # a blank is never stored as 0 or as passed
    assert "re-checked" in by_status["missing"]["corrective_action"]
    pdf = await owner.get("/api/haccp/binder.pdf")
    assert pdf.content.startswith(b"%PDF")


async def test_haccp_without_control_points_is_blocked(owner: httpx.AsyncClient) -> None:
    doc = await _upload(owner, haccp_log_pdf(["Fill temperature 168 F 09:10 RP"]), "haccp_log", "h.pdf")
    assert any("No critical control points" in b for b in doc["approval"]["summary"]["blocks"])


async def test_trace_is_tenant_scoped(owner: httpx.AsyncClient, other_tenant: httpx.AsyncClient) -> None:
    await _catalog(owner)
    doc = await _upload(owner, batch_sheet_pdf(INGREDIENTS[:2], batch="B-900", lot="L-900"), "batch_sheet", "b.pdf")
    await _decide(owner, doc["document"]["run_id"], action="approve")
    assert (await owner.get("/api/lots/L-900/trace")).status_code == 200
    assert (await other_tenant.get("/api/lots/L-900/trace")).status_code == 404
    assert (await other_tenant.get("/api/lots")).json() == []
