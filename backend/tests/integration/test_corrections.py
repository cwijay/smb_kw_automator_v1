import httpx

from tests.fixtures import batch_sheet_pdf
from tests.integration.test_order_loop import _catalog
from tests.integration.test_production import INGREDIENTS, _decide, _upload


async def _signed_batch(c: httpx.AsyncClient) -> dict:  # type: ignore[type-arg]
    await _catalog(c)
    doc = await _upload(c, batch_sheet_pdf(INGREDIENTS), "batch_sheet", "b.pdf")
    run = doc["document"]["run_id"]
    await _decide(c, run, action="revise", acknowledge_missing_lots=True)
    batch_id = (await _decide(c, run, action="approve")).json()["batch_id"]
    return (await c.get(f"/api/batches/{batch_id}")).json()  # type: ignore[no-any-return]


def _fixed(batch: dict, **extra: object) -> dict:  # type: ignore[type-arg]
    inputs = [{**i, "lot_code": "RW-77" if i["ingredient"] == "Rose Water" else i["lot_code"]} for i in batch["inputs"]]
    return {
        "reason": "Rose water lot was on the jar label",
        "made_on": batch["made_on"],
        "quantity": batch["quantity"],
        "unit": batch["unit"],
        "prepared_by": batch["prepared_by"],
        "inputs": inputs,
    } | extra


async def test_correction_supersedes_and_trace_follows_latest(owner: httpx.AsyncClient) -> None:
    batch = await _signed_batch(owner)
    body = _fixed(batch)
    staged = await owner.post(f"/api/batches/{batch['id']}/corrections/stage", json=body)
    assert staged.status_code == 200, staged.text
    assert any("Rose Water: lot — → RW-77" in c for c in staged.json()["summary"]["changes"])
    approval_id = staged.json()["approval_id"]

    # the approval is bound to exactly this change: a different body is refused
    await owner.post(f"/api/approvals/{approval_id}/decide", json={"approve": True})
    tampered = await owner.post(
        f"/api/batches/{batch['id']}/corrections", json=_fixed(batch, quantity="999") | {"approval_id": approval_id}
    )
    assert tampered.status_code in (403, 409), tampered.text
    done = await owner.post(f"/api/batches/{batch['id']}/corrections", json=body | {"approval_id": approval_id})
    assert done.status_code == 200, done.text
    assert done.json()["version"] == 2

    old = (await owner.get(f"/api/batches/{batch['id']}")).json()
    new = (await owner.get(f"/api/batches/{done.json()['batch_id']}")).json()
    assert old["superseded_by"] == new["id"] and new["supersedes"] == old["id"]
    assert new["correction_reason"] == "Rose water lot was on the jar label"
    assert [b["version"] for b in (await owner.get("/api/batches")).json()] == [2]  # list shows the latest only

    trace = (await owner.get("/api/lots/L-1042/trace")).json()
    assert trace["gaps"] == [] and "RW-77" in {b["code"] for b in trace["backward"]}

    # a version can only be corrected once; the old one is closed
    again = await owner.post(f"/api/batches/{batch['id']}/corrections/stage", json=body)
    assert again.status_code == 409


async def test_correction_without_changes_is_refused(owner: httpx.AsyncClient) -> None:
    batch = await _signed_batch(owner)
    same = _fixed(batch, inputs=batch["inputs"])
    r = await owner.post(f"/api/batches/{batch['id']}/corrections/stage", json=same)
    assert r.status_code == 409 and "Nothing changed" in r.text


async def test_correction_is_tenant_scoped(owner: httpx.AsyncClient, other_tenant: httpx.AsyncClient) -> None:
    batch = await _signed_batch(owner)
    r = await other_tenant.post(f"/api/batches/{batch['id']}/corrections/stage", json=_fixed(batch))
    assert r.status_code == 404
