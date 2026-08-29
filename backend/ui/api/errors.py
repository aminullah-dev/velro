"""The HTTP error envelope.

Every non-2xx response has the same shape, without exception, including
FastAPI's own validation failures -- a client that has to parse two error
formats will eventually mishandle one of them.

The envelope carries a stable code and a structured context, never a rendered
sentence. The apps and the admin panel each resolve the code to a translated
message using that same context, so one raise site serves three locales and
three surfaces with no duplicated strings.
"""

from __future__ import annotations

import traceback
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from shared import error_codes
from shared.errors import AppError
from shared.logging import get_logger, redact

log = get_logger(__name__)

# Contexts are returned to clients. These keys never leave the server.
_NEVER_RETURN = frozenset({"code_hash", "token_hash", "password", "otp", "verification_code"})


def message_key_for(code: str) -> str:
    """`TRIP_SEATS_UNAVAILABLE` -> `error.trip_seats_unavailable`.

    Derived rather than mapped, so adding a code cannot leave a client with no
    key to translate.
    """
    return f"error.{code.lower()}"


def envelope(
    code: str, *, context: dict[str, Any] | None = None, request_id: str | None = None
) -> dict[str, Any]:
    safe = {k: v for k, v in (context or {}).items() if k not in _NEVER_RETURN}
    return {
        "success": False,
        "error": {
            "code": code,
            "message_key": message_key_for(code),
            "context": redact(safe),
            "request_id": request_id,
        },
    }


def ok(data: Any = None, *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """The success envelope of section 65."""
    return {"success": True, "data": data, "message": None, "meta": meta or {}}


def install(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        level = log.warning if exc.http_status < 500 else log.error
        # The context is nested rather than splatted: a context carrying
        # `status`, `code` or `path` would otherwise collide with the logger's
        # own fields and raise from inside the error handler.
        level(
            "request.failed",
            code=exc.code,
            status=exc.http_status,
            path=request.url.path,
            request_id=request_id,
            context=exc.context,
        )
        return JSONResponse(
            status_code=exc.http_status,
            content=envelope(exc.code, context=exc.context, request_id=request_id),
            headers={"X-Request-ID": request_id or ""},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        fields = [
            {
                "field": ".".join(str(part) for part in err.get("loc", ())[1:]),
                "rule": err.get("type"),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=envelope(
                error_codes.VALIDATION_FAILED,
                context={"fields": fields},
                request_id=request_id,
            ),
            headers={"X-Request-ID": request_id or ""},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        code = {
            401: error_codes.TOKEN_INVALID,
            403: error_codes.PERMISSION_DENIED,
            404: error_codes.VALIDATION_FAILED,
            429: error_codes.RATE_LIMITED,
        }.get(exc.status_code, error_codes.INTERNAL_ERROR)
        return JSONResponse(
            status_code=exc.status_code,
            content=envelope(code, context={"detail": str(exc.detail)}, request_id=request_id),
            headers={"X-Request-ID": request_id or ""},
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        """The last resort.

        A traceback never reaches a user, and an English exception string never
        reaches a Dari-speaking one. The request id is what support asks for.
        """
        request_id = getattr(request.state, "request_id", None)
        # The traceback goes to the log -- never to the response. Without it
        # here, a 500 in production is unactionable.
        log.error(
            "request.unhandled",
            path=request.url.path,
            request_id=request_id,
            error=type(exc).__name__,
            detail=str(exc),
            traceback="".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ),
        )
        return JSONResponse(
            status_code=500,
            content=envelope(error_codes.INTERNAL_ERROR, request_id=request_id),
            headers={"X-Request-ID": request_id or ""},
        )
