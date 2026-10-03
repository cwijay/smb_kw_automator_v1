import httpx

from tests.conftest import _client
from tests.fixtures import order_sheet_pdf
from tests.integration.test_agent import _ask
from tests.integration.test_order_loop import _catalog, _upload

CHANGE = {"fiscal_year_end": "03-31", "books_export": "xero", "allergens": ["Milk", "Pistachio", "milk"]}


async def test_profile_changes_need_an_approved_diff(owner: httpx.AsyncClient) -> None:
    staged = await owner.post("/api/profile/stage", json=CHANGE)
    assert staged.status_code == 200, staged.text
    assert "Fiscal year ends: — → 03-31" in staged.json()["changes"]
    assert "Allergens handled: — → milk, pistachio" in staged.json()["changes"]  # normalised, de-duplicated
    approval_id = staged.json()["approval_id"]

    # not approved yet → refused; approved but a different change → refused
    assert (await owner.post("/api/profile", json=CHANGE | {"approval_id": approval_id})).status_code in (403, 409)
    await owner.post(f"/api/approvals/{approval_id}/decide", json={"approve": True})
    swapped = CHANGE | {"books_export": "qbo", "approval_id": approval_id}
    assert (await owner.post("/api/profile", json=swapped)).status_code in (403, 409)

    done = await owner.post("/api/profile", json=CHANGE | {"approval_id": approval_id})
    assert done.status_code == 200, done.text
    assert done.json()["profile"] == {
        "fiscal_year_end": "03-31",
        "books_export": "xero",
        "allergens": ["milk", "pistachio"],
    }
    assert (await owner.post("/api/profile/stage", json=CHANGE)).status_code == 409  # nothing changed
    assert (await owner.post("/api/profile/stage", json={"fiscal_year_end": "13-40"})).status_code == 422


async def test_onboarding_is_computed_from_records(owner: httpx.AsyncClient) -> None:
    steps = {s["key"]: s["done"] for s in (await owner.get("/api/profile")).json()["onboarding"]}
    assert not any(steps.values())
    events = await _ask(owner, "What's next to get set up?")
    assert any(e["type"] == "tool" and e["name"] == "onboarding_status" for e in events)
    answer = "".join(e["text"] for e in events if e["type"] == "token")
    assert "Photograph one real order pad" in answer  # prove value first

    await _catalog(owner)
    await _upload(owner, order_sheet_pdf(["11 Malai Kulfi 4.50 49.50"]))
    steps = {s["key"]: s["done"] for s in (await owner.get("/api/profile")).json()["onboarding"]}
    assert steps == {"first_paper": True, "products": True, "customers": True, "ccps": False, "profile": False}


async def test_profile_is_admin_only_and_tenant_scoped(
    app: object, owner: httpx.AsyncClient, other_tenant: httpx.AsyncClient
) -> None:
    staged = (await owner.post("/api/profile/stage", json={"notes": "We close on Mondays"})).json()
    await owner.post(f"/api/approvals/{staged['approval_id']}/decide", json={"approve": True})
    await owner.post("/api/profile", json={"notes": "We close on Mondays", "approval_id": staged["approval_id"]})
    assert (await other_tenant.get("/api/profile")).json()["profile"] == {}

    link = (await owner.post("/api/orgs/current/invites", json={"email": "m@example.com", "role": "member"})).json()
    token = link["dev_link"].rsplit("/", 1)[1]
    async with _client(app) as member:
        await member.post(f"/api/invites/{token}/accept", json={"name": "Mo", "password": "another-long-pass"})
        assert (await member.get("/api/profile")).json()["profile"]["notes"] == "We close on Mondays"
        assert (await member.post("/api/profile/stage", json={"notes": "x"})).status_code == 403
