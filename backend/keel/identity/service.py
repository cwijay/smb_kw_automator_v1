"""Identity and tenancy use cases. Org membership, never a client header, decides the tenant."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, text, update

from keel.audit.service import audit
from keel.identity.models import ROLE_RANK, Invite, MagicLink, Membership, Org, Session, TenantProfile, User
from keel.identity.security import hash_password, new_token, token_hash, verify_password
from keel.platform.config import get_settings
from keel.platform.db import global_session, tenant_session
from keel.platform.errors import Conflict, Forbidden, NotFound, Unauthorized
from keel.platform.ids import uuid7


@dataclass(frozen=True)
class Ctx:
    """Who is calling and in which tenant. Built only from a verified session."""

    user_id: uuid.UUID
    email: str
    name: str
    org_id: uuid.UUID
    role: str
    session_id: uuid.UUID

    def at_least(self, role: str) -> bool:
        return ROLE_RANK[self.role] >= ROLE_RANK[role]


def _now() -> datetime:
    return datetime.now(UTC)


async def _create_session(user_id: uuid.UUID, org_id: uuid.UUID | None) -> str:
    token, digest = new_token()
    ttl = timedelta(days=get_settings().session_ttl_days)
    async with global_session() as db:
        db.add(Session(token_hash=digest, user_id=user_id, active_org_id=org_id, expires_at=_now() + ttl))
    return token


async def _memberships(user_id: uuid.UUID) -> list[tuple[Membership, Org]]:
    async with tenant_session(None, user_id) as db:
        rows = await db.execute(
            select(Membership, Org).join(Org, Org.id == Membership.org_id).where(Membership.user_id == user_id)
        )
        return [(m, o) for m, o in rows.all()]


async def signup(*, org_name: str, name: str, email: str, password: str, currency: str = "USD",
                 country: str = "US", timezone: str = "America/New_York") -> str:
    if len(password) < 10:
        raise Conflict("Use at least 10 characters for the password.", code="weak_password")
    # One transaction: user, org, owner membership and profile all land together or not at all.
    user = User(id=uuid7(), email=email, name=name, password_hash=hash_password(password))
    org_id = uuid7()
    async with tenant_session(org_id, user.id) as db:
        if await db.scalar(select(User.id).where(User.email == email)):
            raise Conflict("An account with this email already exists. Sign in instead.", code="email_taken")
        db.add(user)
        db.add(Org(id=org_id, name=org_name, currency=currency, country=country, timezone=timezone))
        await db.flush()
        db.add(Membership(org_id=org_id, user_id=user.id, role="owner"))
        db.add(TenantProfile(org_id=org_id, profile={}))
        await audit(db, org_id, user.id, "org.created", "org", org_id, name=org_name)
    return await _create_session(user.id, org_id)


async def login(email: str, password: str) -> str:
    async with global_session() as db:
        user = await db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(user.password_hash, password):
        raise Unauthorized("Email or password is not right.", code="bad_credentials")
    orgs = await _memberships(user.id)
    return await _create_session(user.id, orgs[0][1].id if orgs else None)


async def logout(token: str) -> None:
    async with global_session() as db:
        await db.execute(delete(Session).where(Session.token_hash == token_hash(token)))


async def request_magic_link(email: str) -> str | None:
    """Returns the link token (the caller emails it; dev mode shows it). None if no such user."""
    async with global_session() as db:
        if not await db.scalar(select(User.id).where(User.email == email)):
            return None
        token, digest = new_token()
        ttl = timedelta(minutes=get_settings().magic_link_ttl_minutes)
        db.add(MagicLink(token_hash=digest, email=email, expires_at=_now() + ttl))
    return token


async def verify_magic_link(token: str) -> str:
    async with global_session() as db:
        link = await db.scalar(select(MagicLink).where(MagicLink.token_hash == token_hash(token)))
        if link is None or link.used_at is not None or link.expires_at < _now():
            raise Unauthorized("This sign-in link has expired. Request a new one.", code="link_expired")
        link.used_at = _now()
        user = await db.scalar(select(User).where(User.email == link.email))
    assert user is not None
    orgs = await _memberships(user.id)
    return await _create_session(user.id, orgs[0][1].id if orgs else None)


async def resolve(token: str) -> Ctx:
    async with global_session() as db:
        row = await db.execute(
            select(Session, User).join(User, User.id == Session.user_id)
            .where(Session.token_hash == token_hash(token))
        )
        found = row.first()
        if found is None or found[0].expires_at < _now():
            raise Unauthorized("Your session has ended. Sign in again.")
        sess, user = found
        await db.execute(update(Session).where(Session.id == sess.id).values(last_seen_at=func.now()))
    memberships = await _memberships(user.id)
    if not memberships:
        raise Forbidden("You are not a member of any organisation yet.", code="no_org")
    chosen = next((m for m, _ in memberships if m.org_id == sess.active_org_id), memberships[0][0])
    return Ctx(user.id, user.email, user.name, chosen.org_id, chosen.role, sess.id)


async def switch_org(ctx: Ctx, org_id: uuid.UUID) -> None:
    if org_id not in {m.org_id for m, _ in await _memberships(ctx.user_id)}:
        raise Forbidden("You are not a member of that organisation.")
    async with global_session() as db:
        await db.execute(update(Session).where(Session.id == ctx.session_id).values(active_org_id=org_id))


async def my_orgs(ctx: Ctx) -> list[dict[str, str]]:
    return [{"id": str(o.id), "name": o.name, "role": m.role} for m, o in await _memberships(ctx.user_id)]


async def create_invite(ctx: Ctx, email: str, role: str) -> str:
    if role not in ("admin", "member", "viewer"):
        raise Conflict("Role must be admin, member or viewer.")
    if role == "admin" and not ctx.at_least("owner"):
        raise Forbidden("Only an owner can invite an admin.")
    token, digest = new_token()
    ttl = timedelta(days=get_settings().invite_ttl_days)
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        existing = await db.scalar(
            select(func.count()).select_from(Membership).join(User, User.id == Membership.user_id)
            .where(Membership.org_id == ctx.org_id, User.email == email)
        )
        if existing:
            raise Conflict("That person is already a member.")
        db.add(Invite(org_id=ctx.org_id, email=email, role=role, token_hash=digest, invited_by=ctx.user_id,
                      expires_at=_now() + ttl))
        await audit(db, ctx.org_id, ctx.user_id, "invite.created", "invite", None, email=email, role=role)
    return token


async def preview_invite(token: str) -> dict[str, str]:
    async with global_session() as db:
        row = (await db.execute(text("SELECT * FROM keel_find_invite(:h)"), {"h": token_hash(token)})).first()
    if row is None or row.accepted_at is not None or row.expires_at < _now():
        raise NotFound("This invite is no longer valid. Ask for a new one.", code="invite_invalid")
    async with tenant_session(row.org_id) as db:
        org_name = await db.scalar(select(Org.name).where(Org.id == row.org_id))
    return {"org_name": org_name or "", "email": row.email, "role": row.role}


async def accept_invite(token: str, *, name: str | None, password: str | None,
                        current: Ctx | None) -> str | None:
    """Joins the org. Returns a new session token when a new account was created."""
    async with global_session() as db:
        row = (await db.execute(text("SELECT * FROM keel_find_invite(:h)"), {"h": token_hash(token)})).first()
        if row is None or row.accepted_at is not None or row.expires_at < _now():
            raise NotFound("This invite is no longer valid. Ask for a new one.", code="invite_invalid")
        user = await db.scalar(select(User).where(User.email == row.email))
        if current is not None and current.email.lower() != str(row.email).lower():
            raise Forbidden("This invite was sent to a different email address.")
        new_session = False
        if user is None:
            if not name or not password or len(password) < 10:
                raise Conflict("Choose a name and a password of at least 10 characters.", code="weak_password")
            user = User(email=row.email, name=name, password_hash=hash_password(password))
            db.add(user)
            new_session = True
        elif current is None:
            raise Unauthorized("Sign in with this email to accept the invite.", code="sign_in_required")
    async with tenant_session(row.org_id, user.id) as db:
        db.add(Membership(org_id=row.org_id, user_id=user.id, role=row.role))
        await db.execute(update(Invite).where(Invite.id == row.id).values(accepted_at=_now()))
        await audit(db, row.org_id, user.id, "invite.accepted", "user", user.id, role=row.role)
    return await _create_session(user.id, row.org_id) if new_session else None


async def list_members(ctx: Ctx) -> list[dict[str, str]]:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        rows = await db.execute(
            select(Membership, User).join(User, User.id == Membership.user_id)
            .where(Membership.org_id == ctx.org_id).order_by(Membership.created_at)
        )
        members = [{"user_id": str(u.id), "name": u.name, "email": u.email, "role": m.role} for m, u in rows]
        invites = await db.execute(
            select(Invite).where(Invite.accepted_at.is_(None), Invite.expires_at > _now())
        )
        pending = [{"invite_id": str(i.id), "email": i.email, "role": i.role, "name": "", "user_id": ""}
                   for i in invites.scalars()]
    return members + [dict(p, role=f"invited:{p['role']}") for p in pending]


async def change_role(ctx: Ctx, user_id: uuid.UUID, role: str) -> None:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        m = await db.scalar(select(Membership).where(Membership.org_id == ctx.org_id,
                                                     Membership.user_id == user_id))
        if m is None:
            raise NotFound("Member not found.")
        if (m.role == "owner" or role == "owner") and not ctx.at_least("owner"):
            raise Forbidden("Only an owner can change owner roles.")
        if m.role == "owner" and role != "owner":
            owners = await db.scalar(select(func.count()).select_from(Membership)
                                     .where(Membership.org_id == ctx.org_id, Membership.role == "owner"))
            if owners == 1:
                raise Conflict("An organisation needs at least one owner.")
        m.role = role
        await audit(db, ctx.org_id, ctx.user_id, "member.role_changed", "user", user_id, role=role)


async def remove_member(ctx: Ctx, user_id: uuid.UUID) -> None:
    async with tenant_session(ctx.org_id, ctx.user_id) as db:
        m = await db.scalar(select(Membership).where(Membership.org_id == ctx.org_id,
                                                     Membership.user_id == user_id))
        if m is None:
            raise NotFound("Member not found.")
        if m.role == "owner":
            raise Conflict("Transfer ownership before removing an owner.")
        await db.delete(m)
        await audit(db, ctx.org_id, ctx.user_id, "member.removed", "user", user_id)
