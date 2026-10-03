import httpx
from sqlalchemy import select

from keel.domain.models import Customer
from keel.platform.db import tenant_session
from tests.conftest import _client


async def test_signup_me_and_logout(owner: httpx.AsyncClient) -> None:
    me = (await owner.get("/api/me")).json()
    assert me["role"] == "owner"
    assert me["org_name"] == "Acme Kulfi"
    assert len(me["orgs"]) == 1
    assert (await owner.post("/api/auth/logout")).status_code == 200
    assert (await owner.get("/api/me")).status_code == 401


async def test_login_wrong_password(app: object, owner: httpx.AsyncClient) -> None:
    async with _client(app) as c:
        r = await c.post("/api/auth/login", json={"email": owner.email, "password": "nope-nope-nope"})  # type: ignore[attr-defined]
        assert r.status_code == 401
        r = await c.post("/api/auth/login", json={"email": owner.email, "password": "correct-horse-battery"})  # type: ignore[attr-defined]
        assert r.status_code == 200
        assert (await c.get("/api/me")).status_code == 200


async def test_client_headers_cannot_choose_tenant(owner: httpx.AsyncClient, other_tenant: httpx.AsyncClient) -> None:
    other_me = (await other_tenant.get("/api/me")).json()
    await other_tenant.post("/api/customers", json={"name": "Secret Café"})
    r = await owner.get("/api/customers", headers={"X-Organization-ID": other_me["org_id"]})
    assert all(c["name"] != "Secret Café" for c in r.json())


async def test_rls_canary_blocks_cross_tenant_reads(owner: httpx.AsyncClient, other_tenant: httpx.AsyncClient) -> None:
    await other_tenant.post("/api/customers", json={"name": "Canary Diner"})
    mine = (await owner.get("/api/me")).json()
    theirs = (await other_tenant.get("/api/me")).json()
    # Even a query with NO tenant filter, run as the app role inside tenant A, cannot see tenant B rows.
    async with tenant_session(mine["org_id"]) as db:
        names = (await db.scalars(select(Customer.name))).all()
    assert "Canary Diner" not in names
    async with tenant_session(theirs["org_id"]) as db:
        assert "Canary Diner" in (await db.scalars(select(Customer.name))).all()
    async with tenant_session(None) as db:
        assert (await db.scalars(select(Customer.name))).all() == []


async def test_invite_flow_and_roles(app: object, owner: httpx.AsyncClient) -> None:
    r = await owner.post("/api/orgs/current/invites", json={"email": "staff@example.com", "role": "member"})
    link = r.json()["dev_link"]
    token = link.rsplit("/", 1)[1]
    async with _client(app) as staff:
        preview = (await staff.get(f"/api/invites/{token}")).json()
        assert preview["org_name"] == "Acme Kulfi"
        r = await staff.post(f"/api/invites/{token}/accept", json={"name": "Sam", "password": "another-long-pass"})
        assert r.status_code == 200, r.text
        me = (await staff.get("/api/me")).json()
        assert me["role"] == "member"
        # members cannot invite or change roles
        assert (
            await staff.post("/api/orgs/current/invites", json={"email": "x@example.com", "role": "viewer"})
        ).status_code == 403
        # invite tokens are single use
        assert (await staff.get(f"/api/invites/{token}")).status_code == 404
    members = (await owner.get("/api/orgs/current/members")).json()
    assert {m["role"] for m in members} >= {"owner", "member"}


async def test_last_owner_cannot_be_demoted(owner: httpx.AsyncClient) -> None:
    me = (await owner.get("/api/me")).json()
    r = await owner.patch(f"/api/orgs/current/members/{me['user_id']}", json={"role": "member"})
    assert r.status_code == 409


async def test_magic_link(app: object, owner: httpx.AsyncClient) -> None:
    async with _client(app) as c:
        r = await c.post("/api/auth/magic-link", json={"email": owner.email})  # type: ignore[attr-defined]
        token = r.json()["dev_link"].split("token=")[1]
        assert (await c.post("/api/auth/magic-link/verify", json={"token": token})).status_code == 200
        assert (await c.get("/api/me")).status_code == 200
        assert (await c.post("/api/auth/magic-link/verify", json={"token": token})).status_code == 401
