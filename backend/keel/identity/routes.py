import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from keel.api.deps import Admin, Viewer, clear_session_cookie, optional_ctx, session_token, set_session_cookie
from keel.audit.service import audit
from keel.identity import service
from keel.identity.models import Org
from keel.identity.service import Ctx
from keel.platform.config import get_settings
from keel.platform.db import tenant_session
from keel.platform.errors import NotFound

router = APIRouter(tags=["identity"])


class SignupIn(BaseModel):
    org_name: str = Field(min_length=2, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    currency: str = Field(default="USD", pattern="^[A-Z]{3}$")
    country: str = Field(default="US", pattern="^[A-Z]{2}$")
    timezone: str = "America/New_York"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class EmailIn(BaseModel):
    email: EmailStr


class TokenIn(BaseModel):
    token: str


class OkOut(BaseModel):
    ok: bool = True
    dev_link: str | None = Field(default=None, description="Only in dev: the link that would be emailed.")


class OrgRef(BaseModel):
    id: str
    name: str
    role: str


class MeOut(BaseModel):
    user_id: str
    name: str
    email: str
    org_id: str
    org_name: str
    role: str
    currency: str
    timezone: str
    orgs: list[OrgRef]


class OrgPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    currency: str | None = Field(default=None, pattern="^[A-Z]{3}$")
    country: str | None = Field(default=None, pattern="^[A-Z]{2}$")
    timezone: str | None = None


class InviteIn(BaseModel):
    email: EmailStr
    role: Literal["admin", "member", "viewer"] = "member"


class InvitePreview(BaseModel):
    org_name: str
    email: str
    role: str


class AcceptIn(BaseModel):
    name: str | None = None
    password: str | None = None


class MemberOut(BaseModel):
    user_id: str
    invite_id: str | None = None
    name: str
    email: str
    role: str


class RoleIn(BaseModel):
    role: Literal["owner", "admin", "member", "viewer"]


def _dev_link(path: str) -> str | None:
    s = get_settings()
    return f"{s.frontend_url}{path}" if s.env != "prod" else None


@router.post("/auth/signup", response_model=OkOut)
async def signup(body: SignupIn, response: Response) -> OkOut:
    token = await service.signup(**body.model_dump())
    set_session_cookie(response, token)
    return OkOut()


@router.post("/auth/login", response_model=OkOut)
async def login(body: LoginIn, response: Response) -> OkOut:
    set_session_cookie(response, await service.login(body.email, body.password))
    return OkOut()


@router.post("/auth/logout", response_model=OkOut)
async def logout(request: Request, response: Response) -> OkOut:
    token = session_token(request)
    if token:
        await service.logout(token)
    clear_session_cookie(response)
    return OkOut()


@router.post("/auth/magic-link", response_model=OkOut)
async def magic_link(body: EmailIn) -> OkOut:
    token = await service.request_magic_link(body.email)
    # Same answer whether or not the email exists, so the endpoint can't be used to probe accounts.
    return OkOut(dev_link=_dev_link(f"/auth/magic?token={token}") if token else None)


@router.post("/auth/magic-link/verify", response_model=OkOut)
async def magic_verify(body: TokenIn, response: Response) -> OkOut:
    set_session_cookie(response, await service.verify_magic_link(body.token))
    return OkOut()


@router.get("/me", response_model=MeOut)
async def me(ctx: Ctx = Viewer) -> MeOut:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        org = await db.scalar(select(Org).where(Org.id == ctx.org_id))
    assert org is not None
    return MeOut(
        user_id=str(ctx.user_id), name=ctx.name, email=ctx.email, org_id=str(ctx.org_id), org_name=org.name,
        role=ctx.role, currency=org.currency, timezone=org.timezone,
        orgs=[OrgRef(**o) for o in await service.my_orgs(ctx)],
    )


@router.post("/me/active-org/{org_id}", response_model=OkOut)
async def switch_org(org_id: uuid.UUID, ctx: Ctx = Viewer) -> OkOut:
    await service.switch_org(ctx, org_id)
    return OkOut()


@router.patch("/orgs/current", response_model=OkOut)
async def update_org(body: OrgPatch, ctx: Ctx = Admin) -> OkOut:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        org = await db.scalar(select(Org).where(Org.id == ctx.org_id))
        if org is None:
            raise NotFound("Organisation not found.")
        changes = body.model_dump(exclude_none=True)
        for k, v in changes.items():
            setattr(org, k, v)
        await audit(db, ctx.org_id, ctx.user_id, "org.updated", "org", ctx.org_id, **changes)
    return OkOut()


@router.get("/orgs/current/members", response_model=list[MemberOut])
async def members(ctx: Ctx = Viewer) -> list[MemberOut]:
    return [MemberOut(**m) for m in await service.list_members(ctx)]


@router.post("/orgs/current/invites", response_model=OkOut)
async def invite(body: InviteIn, ctx: Ctx = Admin) -> OkOut:
    token = await service.create_invite(ctx, body.email, body.role)
    return OkOut(dev_link=_dev_link(f"/invite/{token}"))


@router.patch("/orgs/current/members/{user_id}", response_model=OkOut)
async def set_role(user_id: uuid.UUID, body: RoleIn, ctx: Ctx = Admin) -> OkOut:
    await service.change_role(ctx, user_id, body.role)
    return OkOut()


@router.delete("/orgs/current/members/{user_id}", response_model=OkOut)
async def remove(user_id: uuid.UUID, ctx: Ctx = Admin) -> OkOut:
    await service.remove_member(ctx, user_id)
    return OkOut()


@router.get("/invites/{token}", response_model=InvitePreview)
async def invite_preview(token: str) -> InvitePreview:
    return InvitePreview(**await service.preview_invite(token))


@router.post("/invites/{token}/accept", response_model=OkOut)
async def invite_accept(token: str, body: AcceptIn, response: Response,
                        current: Ctx | None = Depends(optional_ctx)) -> OkOut:
    new_token = await service.accept_invite(token, name=body.name, password=body.password, current=current)
    if new_token:
        set_session_cookie(response, new_token)
    return OkOut()
