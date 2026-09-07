"""Thin FastAPI routes for browser OIDC and server-session handling."""

from datetime import datetime
from typing import Annotated
from typing import cast
from urllib.parse import unquote
from urllib.parse import urlsplit
from urllib.parse import urlunsplit
from uuid import UUID

from fastapi import APIRouter
from fastapi import Header
from fastapi import Query
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from pydantic import Field
from pydantic import SecretStr

from core.context import PlatformActorContext
from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.settings import AppEnvironment
from core.settings import Settings
from identity.application.platform_administration import PlatformAdministrationService
from identity.application.service import AuthenticationService
from identity.domain.exceptions import InvalidAuthorizationFlowError
from identity.domain.models import CurrentSession
from identity.domain.models import EstablishedSession
from identity.domain.models import PlatformAdministrator
from identity.presentation.dependencies import PLATFORM_ADMIN_PERMISSIONS
from identity.presentation.dependencies import ActorDep
from identity.presentation.dependencies import CSRFDep
from identity.presentation.dependencies import CurrentSessionDep

router = APIRouter(prefix="/api/v1/auth", tags=["identity"])
platform_router = APIRouter(
    prefix="/api/v1/platform/administrators",
    tags=["platform-administration"],
)


class LoginRequest(BaseModel):
    """Validate the local path returned to after authentication."""

    return_path: str = Field(default="/", max_length=2048)


class PlatformAdministratorBootstrapRequest(BaseModel):
    """Protect the one-time first-administrator bootstrap operation."""

    bootstrap_secret: SecretStr


class PlatformAdministratorResponse(BaseModel):
    """Expose safe global privilege assignment state."""

    subject_id: UUID
    active: bool


class AuthorizationStartResponse(BaseModel):
    """Describe the safe browser authorization handoff."""

    authorization_url: str


class CurrentSessionResponse(BaseModel):
    """Expose the supported session view without provider token material."""

    id: UUID
    email: str | None
    display_name: str
    is_platform_admin: bool
    permissions: list[str]
    expires_at: datetime


class DevelopmentLoginResponse(BaseModel):
    """Describe the explicit local-only login result."""

    user: CurrentSessionResponse
    return_path: str


class LogoutResponse(BaseModel):
    """Report local logout and optional provider propagation safely."""

    logged_out: bool
    provider_revoked: bool
    provider_logout_url: str | None


def _service(request: Request) -> AuthenticationService:
    """Return the explicitly composed identity application service."""

    return cast(AuthenticationService, request.app.state.identity_service)


def _platform_administration(request: Request) -> PlatformAdministrationService:
    """Return the explicitly composed platform-administration service."""

    return cast(
        PlatformAdministrationService,
        request.app.state.platform_administration_service,
    )


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
        "permissions": (
            sorted(PLATFORM_ADMIN_PERMISSIONS) if current.is_platform_admin else []
        ),
        "expires_at": current.expires_at.isoformat(),
    }


def _safe_platform_administrator_payload(
    administrator: PlatformAdministrator,
) -> dict[str, object]:
    """Serialize global privilege state without OwnID claims or tenant data."""

    return {
        "subject_id": str(administrator.subject_id),
        "active": administrator.active,
    }


def _platform_actor(
    actor: PlatformActorContext | TenantActorContext,
) -> PlatformActorContext:
    """Require a separately established global platform actor."""

    if not isinstance(actor, PlatformActorContext):
        raise AuthorizationError
    return actor


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


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    response_model=AuthorizationStartResponse,
)
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


@router.post("/dev-login", response_model=DevelopmentLoginResponse)
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


@router.get("/me", response_model=CurrentSessionResponse)
async def get_me(
    request: Request,
) -> JSONResponse:
    """Return the safe application identity for the active server session."""

    settings = _settings(request)
    current = await _service(request).get_current_session(
        session_token=request.cookies.get(settings.SESSION_COOKIE_NAME, ""),
        correlation_id=_correlation_id(request),
    )
    response = JSONResponse(_safe_session_payload(current))
    _set_no_store(response)
    return response


@router.post("/refresh", response_model=CurrentSessionResponse)
async def refresh_session(
    request: Request,
    csrf_token: Annotated[str, Header(alias="X-CSRF-Token")],
) -> JSONResponse:
    """Refresh encrypted provider tokens after session-bound CSRF validation."""

    settings = _settings(request)
    current = await _service(request).refresh_session(
        session_token=request.cookies.get(settings.SESSION_COOKIE_NAME, ""),
        csrf_token=csrf_token,
        correlation_id=_correlation_id(request),
    )
    response = JSONResponse(_safe_session_payload(current))
    _set_no_store(response)
    return response


@router.post("/logout", response_model=LogoutResponse)
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
            "provider_logout_url": result.provider_logout_url,
        }
    )
    response.delete_cookie(key=settings.SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(key=settings.CSRF_COOKIE_NAME, path="/")
    _set_no_store(response)
    return response


@platform_router.post(
    "/bootstrap",
    status_code=status.HTTP_201_CREATED,
    response_model=PlatformAdministratorResponse,
)
async def bootstrap_platform_administrator(
    payload: PlatformAdministratorBootstrapRequest,
    request: Request,
    current: CurrentSessionDep,
    _csrf: CSRFDep,
) -> JSONResponse:
    """Assign the signed-in OwnID subject as the first platform admin once."""

    administrator = await _platform_administration(request).bootstrap(
        subject_id=current.subject.id,
        supplied_secret=payload.bootstrap_secret.get_secret_value(),
        correlation_id=_correlation_id(request),
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=_safe_platform_administrator_payload(administrator),
    )


@platform_router.get("", response_model=list[PlatformAdministratorResponse])
async def list_platform_administrators(
    request: Request,
    actor: ActorDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    """List bounded platform-administrator assignment state."""

    administrators = await _platform_administration(request).list_administrators(
        actor=_platform_actor(actor),
        limit=limit,
        offset=offset,
    )
    return JSONResponse(
        [_safe_platform_administrator_payload(value) for value in administrators]
    )


@platform_router.post(
    "/{subject_id}/assign",
    response_model=PlatformAdministratorResponse,
)
async def assign_platform_administrator(
    subject_id: UUID,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> JSONResponse:
    """Assign or reactivate one existing OwnID subject."""

    administrator = await _platform_administration(request).assign(
        actor=_platform_actor(actor),
        subject_id=subject_id,
    )
    return JSONResponse(_safe_platform_administrator_payload(administrator))


@platform_router.post(
    "/{subject_id}/revoke",
    response_model=PlatformAdministratorResponse,
)
async def revoke_platform_administrator(
    subject_id: UUID,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> JSONResponse:
    """Revoke one assignment while preserving a final active administrator."""

    administrator = await _platform_administration(request).revoke(
        actor=_platform_actor(actor),
        subject_id=subject_id,
    )
    return JSONResponse(_safe_platform_administrator_payload(administrator))


__all__ = ["platform_router", "router"]
