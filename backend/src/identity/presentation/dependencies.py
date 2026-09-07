"""Reusable identity, tenant-membership, and CSRF FastAPI dependencies."""

from typing import Annotated
from typing import cast
from uuid import UUID

from fastapi import Depends
from fastapi import Header
from fastapi import Request

from core.context import ActorContext
from core.context import PlatformActorContext
from core.errors import AuthenticationError
from core.settings import Settings
from identity.application.platform_administration import (
    MANAGE_PLATFORM_ADMINISTRATORS_PERMISSION,
)
from identity.application.ports import TenantContextResolver
from identity.application.service import AuthenticationService
from identity.domain.models import CurrentSession

PLATFORM_ADMIN_PERMISSIONS = frozenset(
    {
        "organizations.platform.create",
        "organizations.platform.lifecycle",
        "people.platform.appoint_owner",
        "people.platform.manage_owner_lifecycle",
        "entitlements.platform.manage",
        "audit.platform.read",
        MANAGE_PLATFORM_ADMINISTRATORS_PERMISSION,
    }
)


def _authentication(request: Request) -> AuthenticationService:
    """Return the explicitly composed authentication service."""

    return cast(AuthenticationService, request.app.state.identity_service)


def _memberships(request: Request) -> TenantContextResolver:
    """Return the explicitly composed tenant membership resolver."""

    return cast(TenantContextResolver, request.app.state.membership_service)


def _settings(request: Request) -> Settings:
    """Return immutable process settings from application state."""

    return cast(Settings, request.app.state.settings)


def _correlation_id(request: Request) -> str:
    """Return the middleware-established correlation identifier."""

    return str(getattr(request.state, "correlation_id", "unknown"))


async def require_actor(
    request: Request,
    organization_header: Annotated[
        str | None,
        Header(alias="X-Organization-ID"),
    ] = None,
) -> ActorContext:
    """Resolve platform context or validate a requested tenant against membership."""

    current = await require_current_session(request)
    if organization_header is None:
        if not current.is_platform_admin:
            raise AuthenticationError
        return PlatformActorContext(
            subject_id=current.subject.id,
            correlation_id=_correlation_id(request),
            permissions=PLATFORM_ADMIN_PERMISSIONS,
        )
    try:
        organization_id = UUID(organization_header)
    except ValueError as exc:
        raise AuthenticationError from exc
    return await _memberships(request).resolve_tenant_context(
        identity_subject_id=current.subject.id,
        organization_id=organization_id,
        correlation_id=_correlation_id(request),
    )


async def require_current_session(request: Request) -> CurrentSession:
    """Return the safe current session for routes that do not need tenant context."""

    settings = _settings(request)
    return await _authentication(request).get_current_session(
        session_token=request.cookies.get(settings.SESSION_COOKIE_NAME, ""),
        correlation_id=_correlation_id(request),
    )


async def require_csrf(
    request: Request,
    csrf_token: Annotated[str, Header(alias="X-CSRF-Token")],
) -> None:
    """Validate the double-submit header against the server-side session binding."""

    settings = _settings(request)
    await _authentication(request).validate_csrf(
        session_token=request.cookies.get(settings.SESSION_COOKIE_NAME, ""),
        csrf_token=csrf_token,
    )


ActorDep = Annotated[ActorContext, Depends(require_actor)]
CSRFDep = Annotated[None, Depends(require_csrf)]
CurrentSessionDep = Annotated[CurrentSession, Depends(require_current_session)]

__all__ = [
    "PLATFORM_ADMIN_PERMISSIONS",
    "ActorDep",
    "CSRFDep",
    "CurrentSessionDep",
    "require_actor",
    "require_csrf",
    "require_current_session",
]
