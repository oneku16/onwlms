"""HTTP middleware and stable public error translation."""

import re
from collections.abc import Awaitable
from collections.abc import Callable
from typing import cast
from uuid import uuid4

import structlog
from fastapi import FastAPI
from fastapi import Request
from fastapi import status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from core.errors import AppError
from core.errors import AuthenticationError
from core.errors import AuthorizationError
from core.errors import ConflictError
from core.errors import NotFoundError
from core.errors import ValidationError


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind a correlation ID and baseline security headers to every request."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Process one request without logging query strings or payloads."""

        supplied = request.headers.get("x-request-id", "")
        correlation_id = (
            supplied
            if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", supplied)
            else str(uuid4())
        )
        request.state.correlation_id = correlation_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        logger = structlog.get_logger("http")
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_failed",
                method=request.method,
                path=request.url.path,
            )
            raise
        response.headers["X-Request-ID"] = correlation_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        )
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
        )
        return response


def _problem(
    *,
    status_code: int,
    title: str,
    detail: str,
    request: Request,
    errors: list[dict[str, object]] | None = None,
) -> JSONResponse:
    """Build a stable RFC 9457-style error response."""

    content: dict[str, object] = {
        "type": "about:blank",
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": request.url.path,
        "correlation_id": getattr(request.state, "correlation_id", "unknown"),
    }
    if errors is not None:
        content["errors"] = errors
    return JSONResponse(
        status_code=status_code,
        content=content,
        media_type="application/problem+json",
    )


def install_error_handlers(app: FastAPI) -> None:
    """Translate validation and expected application failures safely."""

    @app.exception_handler(RequestValidationError)
    async def validation_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        errors: list[dict[str, object]] = []
        for error in exc.errors():
            errors.append(
                {
                    "location": [str(part) for part in error["loc"]],
                    "message": str(error["msg"]),
                    "code": str(error["type"]),
                }
            )
        return _problem(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            title="Validation failed",
            detail="The request contains invalid values.",
            request=request,
            errors=errors,
        )

    @app.exception_handler(AppError)
    async def application_handler(
        request: Request,
        exc: AppError,
    ) -> JSONResponse:
        mapping: list[tuple[type[AppError], int, str, str]] = [
            (
                AuthenticationError,
                status.HTTP_401_UNAUTHORIZED,
                "Not authenticated",
                "A valid application session is required.",
            ),
            (
                AuthorizationError,
                status.HTTP_403_FORBIDDEN,
                "Forbidden",
                "You are not allowed to perform this action.",
            ),
            (
                NotFoundError,
                status.HTTP_404_NOT_FOUND,
                "Not found",
                "The requested resource was not found.",
            ),
            (
                ConflictError,
                status.HTTP_409_CONFLICT,
                "Conflict",
                str(exc),
            ),
            (
                ValidationError,
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Invalid operation",
                str(exc),
            ),
        ]
        for error_type, status_code, title, detail in mapping:
            if isinstance(exc, error_type):
                return _problem(
                    status_code=status_code,
                    title=title,
                    detail=detail,
                    request=request,
                )
        return _problem(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            title="Operation unavailable",
            detail="The operation could not be completed safely.",
            request=request,
        )

    cast(object, validation_handler)
    cast(object, application_handler)


__all__ = ["RequestContextMiddleware", "install_error_handlers"]
