"""Domain errors mapped to HTTP responses in one place."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class KeelError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class NotFound(KeelError):
    status = 404
    code = "not_found"


class Unauthorized(KeelError):
    status = 401
    code = "unauthorized"


class Forbidden(KeelError):
    status = 403
    code = "forbidden"


class Conflict(KeelError):
    status = 409
    code = "conflict"


class ApprovalRequired(KeelError):
    """Raised by write tools when no valid approval matches the exact staged payload."""

    status = 409
    code = "approval_required"


class QuotaExceeded(KeelError):
    status = 429
    code = "quota_exceeded"


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(KeelError)
    async def _handle(_: Request, exc: KeelError) -> JSONResponse:
        return JSONResponse({"error": exc.code, "message": exc.message}, status_code=exc.status)
