"""Request context. Identity comes only from the httpOnly session cookie verified here."""

from collections.abc import Awaitable, Callable

from fastapi import Depends, Request, Response

from keel.identity import service
from keel.identity.service import Ctx
from keel.platform.config import get_settings
from keel.platform.errors import Forbidden, Unauthorized


def session_token(request: Request) -> str | None:
    return request.cookies.get(get_settings().session_cookie)


async def current_ctx(request: Request) -> Ctx:
    token = session_token(request)
    if not token:
        raise Unauthorized("Sign in to continue.")
    return await service.resolve(token)


async def optional_ctx(request: Request) -> Ctx | None:
    token = session_token(request)
    if not token:
        return None
    try:
        return await service.resolve(token)
    except (Unauthorized, Forbidden):
        return None


def require_role(role: str) -> Callable[..., Awaitable[Ctx]]:
    async def dep(ctx: Ctx = Depends(current_ctx)) -> Ctx:
        if not ctx.at_least(role):
            raise Forbidden(f"This action needs the {role} role or higher.")
        return ctx

    return dep


def set_session_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        s.session_cookie,
        token,
        max_age=s.session_ttl_days * 86400,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(get_settings().session_cookie, path="/")


Member = Depends(require_role("member"))
Viewer = Depends(require_role("viewer"))
Admin = Depends(require_role("admin"))
