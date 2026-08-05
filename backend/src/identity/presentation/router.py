"""Thin FastAPI routes for browser OIDC and server-session handling."""

from typing import Annotated
from typing import cast
from urllib.parse import unquote
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

from fastapi import APIRouter
from fastapi import Header
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from pydantic import Field

from core.settings import AppEnvironment
from core.settings import Settings
from identity.application.service import AuthenticationService
from identity.domain.exceptions import InvalidAuthorizationFlowError
from identity.domain.models import CurrentSession
from identity.domain.models import EstablishedSession

router = APIRouter(prefix="/api/v1/auth", tags=["identity"])


class LoginRequest(BaseModel):
    """Validate the local path returned to after authentication."""

    return_path: str = Field(default="/", max_length=2048)


def _service(request: Request) -> AuthenticationService:
    """Return the explicitly composed identity application service."""

    return cast(AuthenticationService, request.app.state.identity_service)


def _settings(request: Request) -> Settings:
    """Return immutable process settings from the composition root."""

    return cast(Settings, request.app.state.settings)


def _correlation_id(request: Request) -> str:
    """Return the request correlation identifier without trusting input directly."""

    return str(getattr(request.state, "correlation_id", "unknown"))


def _safe_session_payload(current: CurrentSession) -> dict[str, object]:
    """Serialize only safe application identity fields and no provider claims."""

    return {
        "id": str(current.subject.id),
        "email": current.subject.email,
        "display_name": current.subject.display_name
        or current.subject.email
        or "OwnSIS user",
        "is_platform_admin": current.is_platform_admin,
        "expires_at": current.expires_at.isoformat(),
    }


def _set_no_store(response: JSONResponse | RedirectResponse) -> None:
    """Prevent browser or intermediary caching of authentication responses."""

    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def _set_session_cookies(
    *,
    response: JSONResponse | RedirectResponse,
    settings: Settings,
    established: EstablishedSession,
) -> None:
    """Set rotated HttpOnly session and readable CSRF cookies consistently."""

    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=established.session_token,
        max_age=settings.SESSION_TTL_SECONDS,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=established.csrf_token,
        max_age=settings.SESSION_TTL_SECONDS,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite="strict",
        path="/",
    )


def _absolute_frontend_return_url(
    *,
    settings: Settings,
    return_path: str,
) -> str:
    """Join a local return path to a validated absolute frontend base URL."""

    base = urlsplit(settings.APP_BASE_URL)
    local = urlsplit(return_path)
    decoded_base_path = unquote(base.path)
    base_segments = decoded_base_path.replace("\\", "/").split("/")
    try:
        base_port = base.port
    except ValueError as exc:
        raise InvalidAuthorizationFlowError from exc
    del base_port
    if (
        base.scheme not in {"http", "https"}
        or base.hostname is None
        or base.username is not None
        or base.password is not None
        or base.query
        or base.fragment
        or "\\" in decoded_base_path
        or ".." in base_segments
        or any(ord(character) < 32 for character in decoded_base_path)
        or local.scheme
        or local.netloc
        or not local.path.startswith("/")
    ):
        raise InvalidAuthorizationFlowError
    joined_path = f"{base.path.rstrip('/')}{local.path}"
    return urlunsplit(
        (
            base.scheme,
            base.netloc,
            joined_path,
            local.query,
            local.fragment,
        )
    )


@router.post("/login", status_code=status.HTTP_200_OK)
async def start_login(
    payload: LoginRequest,
    request: Request,
) -> JSONResponse:
    """Start a PKCE authorization flow and set its opaque pending cookie."""

    settings = _settings(request)
    started = await _service(request).start_login(return_path=payload.return_path)
    response = JSONResponse({"authorization_url": started.authorization_url})
    response.set_cookie(
        key=f"{settings.SESSION_COOKIE_NAME}_pending",
        value=started.pending_token,
        max_age=600,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/api/v1/auth/callback",
    )
    _set_no_store(response)
    return response


@router.get("/callback", status_code=status.HTTP_303_SEE_OTHER)
async def complete_login(
    request: Request,
    code: str,
    state: str,
) -> RedirectResponse:
    """Complete OwnID authorization, rotate the session, and redirect locally."""

    settings = _settings(request)
    pending_name = f"{settings.SESSION_COOKIE_NAME}_pending"
    established = await _service(request).complete_login(
        pending_token=request.cookies.get(pending_name, ""),
        state=state,
        code=code,
        existing_session_token=request.cookies.get(settings.SESSION_COOKIE_NAME),
        correlation_id=_correlation_id(request),
    )
    response = RedirectResponse(
        url=_absolute_frontend_return_url(
            settings=settings,
            return_path=established.return_path,
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )
    response.delete_cookie(key=pending_name, path="/api/v1/auth/callback")
    _set_session_cookies(
        response=response,
        settings=settings,
        established=established,
    )
    _set_no_store(response)
    return response


@router.post("/dev-login")
async def development_login(
    payload: LoginRequest,
    request: Request,
) -> JSONResponse:
    """Create a fake local/test session only when explicitly enabled."""

    settings = _settings(request)
    if settings.APP_ENV is AppEnvironment.PRODUCTION or not settings.DEV_AUTH_ENABLED:
        raise InvalidAuthorizationFlowError
    established = await _service(request).development_login(
        return_path=payload.return_path,
        existing_session_token=request.cookies.get(settings.SESSION_COOKIE_NAME),
        correlation_id=_correlation_id(request),
    )
    response = JSONResponse(
        {
            "user": _safe_session_payload(established.current),
            "return_path": established.return_path,
        }
    )
    _set_session_cookies(
        response=response,
        settings=settings,
        established=established,
    )
    _set_no_store(response)
    return response


@router.get("/me")
async def get_me(
    request: Request,
) -> JSONResponse:
    """Return the safe application identity for the active server session."""

    settings = _settings(request)
    current = await _service(request).get_current_session(
        session_token=request.cookies.get(settings.SESSION_COOKIE_NAME, ""),
    )
    response = JSONResponse(_safe_session_payload(current))
    _set_no_store(response)
    return response


@router.post("/refresh")
async def refresh_session(
    request: Request,
    csrf_token: Annotated[str, Header(alias="X-CSRF-Token")],
) -> JSONResponse:
    """Refresh encrypted provider tokens after session-bound CSRF validation."""

    settings = _settings(request)
    current = await _service(request).refresh_session(
        session_token=request.cookies.get(settings.SESSION_COOKIE_NAME, ""),
        csrf_token=csrf_token,
    )
    response = JSONResponse(_safe_session_payload(current))
    _set_no_store(response)
    return response


@router.post("/logout")
async def logout(
    request: Request,
    csrf_token: Annotated[str, Header(alias="X-CSRF-Token")],
) -> JSONResponse:
    """Clear the local session and report non-sensitive revocation status."""

    settings = _settings(request)
    result = await _service(request).logout(
        session_token=request.cookies.get(settings.SESSION_COOKIE_NAME, ""),
        csrf_token=csrf_token,
        correlation_id=_correlation_id(request),
    )
    response = JSONResponse(
        {
            "logged_out": True,
            "provider_revoked": result.provider_revoked,
        }
    )
    response.delete_cookie(key=settings.SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(key=settings.CSRF_COOKIE_NAME, path="/")
    _set_no_store(response)
    return response


__all__ = ["router"]
