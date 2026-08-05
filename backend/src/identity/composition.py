"""Explicit identity module construction and FastAPI registration helpers."""

from dataclasses import dataclass

import httpx
from fastapi import FastAPI

from core.settings import Settings
from identity.application.ports import IdentityAuditSink
from identity.application.ports import IdentityProvider
from identity.application.service import AuthenticationService
from identity.infrastructure.providers import DevelopmentIdentityProvider
from identity.infrastructure.providers import create_identity_provider
from identity.infrastructure.repositories import SQLAlchemySessionRepository
from identity.infrastructure.repositories import SQLAlchemySubjectRepository
from identity.presentation.router import router
from shared.database import Database


@dataclass(frozen=True, slots=True)
class IdentityResources:
    """Expose the composed service and any HTTP client owned by this module."""

    service: AuthenticationService
    owned_http_client: httpx.AsyncClient | None


def create_identity_resources(
    *,
    settings: Settings,
    database: Database,
    audit: IdentityAuditSink,
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
        owned_http_client=owned_http_client,
    )


def install_identity_routes(
    *,
    app: FastAPI,
    service: AuthenticationService,
) -> None:
    """Register the identity service and its thin router on one application."""

    app.state.identity_service = service
    app.include_router(router)


__all__ = [
    "IdentityResources",
    "create_identity_resources",
    "install_identity_routes",
]
