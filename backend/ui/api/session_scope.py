"""Per-request database session, committed before the response is returned.

FastAPI runs the teardown of a ``yield`` dependency *after* the response has
been sent. Committing there is a trap: a commit that fails leaves the client
holding a 200 for work that rolled back -- a passenger told their seat is booked
when it is not.

So the session lives in a middleware instead. The commit happens while the
response can still be replaced, and a failure becomes a real error response.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from fastapi.responses import JSONResponse
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from shared import error_codes
from shared.logging import get_logger

log = get_logger(__name__)

_session: ContextVar[Session | None] = ContextVar("velro_session", default=None)

#: Where on_rollback keeps its undo actions, in the session's own info dict.
_UNDO = "velro.undo_on_rollback"


def current_session() -> Session:
    session = _session.get()
    if session is None:
        raise RuntimeError("no database session bound to this request")
    return session


def on_rollback(session: Session, undo: Callable[[], None]) -> None:
    """Run ``undo`` if this request's transaction is rolled back.

    For side effects outside the database that a rollback cannot reach -- a
    file written to storage before the row that names it. Without this a
    failed upload left a photograph of somebody's identity card on disk with
    no row pointing at it: never shown, never deleted, invisible to account
    deletion.

    Forgotten on commit, however the commit happens (the middleware's, or a
    handler's own), so nothing that was committed is ever undone.
    """
    undo_list = session.info.get(_UNDO)
    if undo_list is None:
        undo_list = session.info[_UNDO] = []
        event.listen(session, "after_commit", _forget_undo)
    undo_list.append(undo)


def _forget_undo(session: Session) -> None:
    session.info.pop(_UNDO, None)


def _rollback(session: Session) -> None:
    """Roll back, then undo what the database could not take back with it.

    Each undo is best effort and logged on failure: the response is already
    decided, and one stuck file must not stop the next from being removed.
    """
    session.rollback()
    for undo in session.info.pop(_UNDO, ()):
        try:
            undo()
        except Exception as exc:
            log.error("request.undo_failed", error=type(exc).__name__, detail=str(exc))


class DatabaseSessionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, session_factory: sessionmaker[Session]) -> None:
        super().__init__(app)
        self._session_factory = session_factory

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        session = self._session_factory()
        token = _session.set(session)
        try:
            response = await call_next(request)

            if response.status_code < 400:
                try:
                    session.commit()
                except Exception as exc:
                    _rollback(session)
                    request_id = getattr(request.state, "request_id", None)
                    log.error(
                        "request.commit_failed",
                        path=request.url.path,
                        request_id=request_id,
                        error=type(exc).__name__,
                        detail=str(exc),
                    )
                    # The handler thought it succeeded. It did not, and the
                    # client must be told so rather than shown a false 200.
                    from ui.api.errors import envelope

                    return JSONResponse(
                        status_code=500,
                        content=envelope(
                            error_codes.INTERNAL_ERROR, request_id=request_id
                        ),
                        headers={"X-Request-ID": request_id or ""},
                    )
            else:
                _rollback(session)
            return response
        except Exception:
            _rollback(session)
            raise
        finally:
            session.close()
            _session.reset(token)
