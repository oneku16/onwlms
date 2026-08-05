"""FastAPI composition root and process resource lifecycle."""

from collections.abc import AsyncIterator
from collections.abc import Awaitable
from collections.abc import Callable
from collections.abc import Iterable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.http import RequestContextMiddleware
from core.http import install_error_handlers
from core.logging import configure_logging
from core.settings import Settings
from shared.database import Database
from shared.database import DatabaseResource


def create_app(
    *,
    settings: Settings | None = None,
    database: DatabaseResource | None = None,
    shutdown_callbacks: Iterable[Callable[[], Awaitable[None]]] = (),
) -> FastAPI:
    """Create the OwnSIS API with owned or explicitly injected resources."""

    app_settings = settings or Settings()
    configure_logging()
    owned_database = database is None
    app_database: DatabaseResource = database or Database(app_settings)
    callbacks = tuple(shutdown_callbacks)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Close only resources created by this application factory."""

        try:
            yield
        finally:
            for callback in reversed(callbacks):
                await callback()
            if owned_database:
                await app_database.close()

    openapi_url = "/api/v1/openapi.json" if app_settings.openapi_enabled else None
    docs_url = "/api/docs" if app_settings.openapi_enabled else None
    app = FastAPI(
        title="OwnSIS API",
        version="0.1.0",
        lifespan=lifespan,
        openapi_url=openapi_url,
        docs_url=docs_url,
        redoc_url=None,
    )
    app.state.settings = app_settings
    app.state.database = app_database
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.cors_allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Idempotency-Key",
            "X-CSRF-Token",
            "X-Organization-ID",
            "X-Request-ID",
        ],
        expose_headers=["X-Request-ID"],
    )
    install_error_handlers(app)

    @app.get("/health", include_in_schema=False)
    async def health() -> JSONResponse:
        """Report process liveness without consulting dependencies."""

        return JSONResponse({"status": "ok"})

    @app.get("/ready", include_in_schema=False)
    async def ready(request: Request) -> JSONResponse:
        """Report whether required PostgreSQL infrastructure is available."""

        is_ready = await request.app.state.database.ready()
        status_code = 200 if is_ready else 503
        return JSONResponse(
            status_code=status_code,
            content={"status": "ready" if is_ready else "not_ready"},
        )

    return app


__all__ = ["create_app"]
