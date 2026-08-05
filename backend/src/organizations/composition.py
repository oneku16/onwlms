"""Explicit organization module construction and route registration."""

from fastapi import FastAPI

from organizations.application.ports import OrganizationAuditSink
from organizations.application.service import OrganizationService
from organizations.infrastructure.repositories import SQLAlchemyCampusRepository
from organizations.infrastructure.repositories import SQLAlchemyOrganizationRepository
from organizations.presentation.router import router
from shared.database import Database


def create_organization_service(
    *,
    database: Database,
    audit: OrganizationAuditSink,
) -> OrganizationService:
    """Construct organization-owned PostgreSQL adapters and application service."""

    return OrganizationService(
        organizations=SQLAlchemyOrganizationRepository(database),
        campuses=SQLAlchemyCampusRepository(database),
        audit=audit,
    )


def install_organization_routes(
    *,
    app: FastAPI,
    service: OrganizationService,
) -> None:
    """Register the organization service and thin router on one application."""

    app.state.organization_service = service
    app.include_router(router)


__all__ = ["create_organization_service", "install_organization_routes"]
