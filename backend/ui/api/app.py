"""The FastAPI application.

Versioned prefix ``/v1``: a breaking change means ``/v2``, not a flag. Every
response, success or failure, carries the same envelope, and every request
carries an id that appears in the body, the header and every log line for that
request -- because the first thing support has is "it failed", and the second
thing they need is which request it was.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from shared import config
from shared import logging as app_logging
from shared.ids import new_id
from ui.api import errors
from ui.api.errors import ok
from ui.api.routers import auth, bookings, driver, geography
from ui.api.session_scope import DatabaseSessionMiddleware

API_PREFIX = "/api/v1"


def create_app(settings: config.Settings | None = None) -> FastAPI:
    cfg = settings or config.load()
    app_logging.configure(level=cfg.log_level, json_output=cfg.log_json)

    app = FastAPI(
        title="VELRO",
        version="0.1.0",
        description="Station-based transportation platform",
        docs_url=None if cfg.is_production else "/docs",
        openapi_url=None if cfg.is_production else "/openapi.json",
    )

    if cfg.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(cfg.cors_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID", "ETag"],
        )

    from ui.api.deps import _session_factory

    # Ordering matters: the session middleware is added first, so it sits
    # *inside* the request-context middleware and can see the request id.
    app.add_middleware(DatabaseSessionMiddleware, session_factory=_session_factory())

    log = app_logging.get_logger("velro.request")

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or new_id()
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        log.info(
            "request.completed",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            request_id=request_id,
            actor_id=getattr(request.state, "actor_id", None),
            # Bodies are never logged.
        )
        return response

    errors.install(app)

    for router in (auth.router, geography.router, bookings.router, driver.router):
        app.include_router(router, prefix=API_PREFIX)

    @app.get("/healthz", tags=["ops"])
    def liveness() -> dict:
        """Is the process up. Never touches the database."""
        return ok({"status": "alive"})

    @app.get("/readyz", tags=["ops"])
    def readiness() -> dict:
        """Are dependencies reachable. Separate from liveness deliberately: a
        database blip must not cause an orchestrator to kill a healthy process."""
        from sqlalchemy import text

        from ui.api.deps import _engine

        with _engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return ok({"status": "ready", "database": "ok"})

    return app


# The ASGI application uvicorn serves. Built once, at import.
asgi = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("ui.api.app:asgi", host="0.0.0.0", port=8000)
