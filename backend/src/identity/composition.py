"""Explicit identity module construction and FastAPI registration helpers."""

from dataclasses import dataclass

import httpx
from fastapi import FastAPI

from core.settings import Settings
from identity.application.platform_administration import PlatformAdministrationService
from identity.application.ports import IdentityAuditSink
from identity.application.ports import IdentityProvider
from identity.application.ports import PlatformAdministrationAuditSink
from identity.application.service import AuthenticationService
from identity.infrastructure.providers import DevelopmentIdentityProvider
from identity.infrastructure.providers import create_identity_provider
from identity.infrastructure.repositories import (
    SQLAlchemyPlatformAdministratorRepository,
)
from identity.infrastructure.repositories import SQLAlchemySessionRepository
from identity.infrastructure.repositories import SQLAlchemySubjectRepository
from identity.presentation.router import platform_router
from identity.presentation.router import router
from shared.database import Database


@dataclass(frozen=True, slots=True)
class IdentityResources:
    """Expose the composed service and any HTTP client owned by this module."""

    service: AuthenticationService
    platform_administration: PlatformAdministrationService
    owned_http_client: httpx.AsyncClient | None


def create_identity_resources(
    *,
    settings: Settings,
    database: Database,
    audit: IdentityAuditSink,
    platform_audit: PlatformAdministrationAuditSink,
    provider: IdentityProvider | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> IdentityResources:
    """Construct PostgreSQL identity adapters with an explicit provider seam."""

    if not settings.SESSION_ENCRYPTION_KEY:
        message = "SESSION_ENCRYPTION_KEY is required for server-side sessions"
        raise ValueError(message)
    owned_http_client: httpx.AsyncClient | None = None
    selected_provider = provider
    if selected_provider is None:
        selected_provider, owned_http_client = create_identity_provider(
            settings=settings,
            http_client=http_client,
        )
    service = AuthenticationService(
        provider=selected_provider,
        subjects=SQLAlchemySubjectRepository(database),
        sessions=SQLAlchemySessionRepository(
            database=database,
            encryption_key=settings.SESSION_ENCRYPTION_KEY,
        ),
        audit=audit,
        session_ttl_seconds=settings.SESSION_TTL_SECONDS,
        development_identity=(
            selected_provider
            if isinstance(selected_provider, DevelopmentIdentityProvider)
            else None
        ),
    )
    return IdentityResources(
        service=service,
        platform_administration=PlatformAdministrationService(
            administrators=SQLAlchemyPlatformAdministratorRepository(database),
            audit=platform_audit,
            bootstrap_secret=(
                settings.PLATFORM_ADMIN_BOOTSTRAP_SECRET.get_secret_value()
            ),
        ),
        owned_http_client=owned_http_client,
    )


def install_identity_routes(
    *,
    app: FastAPI,
    service: AuthenticationService,
    platform_administration: PlatformAdministrationService,
) -> None:
    """Register the identity service and its thin router on one application."""

    app.state.identity_service = service
    app.state.platform_administration_service = platform_administration
    app.include_router(router)
    app.include_router(platform_router)


__all__ = [
    "IdentityResources",
    "create_identity_resources",
    "install_identity_routes",
]
