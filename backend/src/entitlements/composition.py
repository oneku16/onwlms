"""Explicit entitlement module construction and route registration."""

from fastapi import FastAPI

from entitlements.application.ports import EntitlementAuditSink
from entitlements.application.service import EntitlementService
from entitlements.infrastructure.repository import SQLAlchemyEntitlementRepository
from entitlements.presentation.router import router
from shared.database import Database


def create_entitlement_service(
    *,
    database: Database,
    audit: EntitlementAuditSink,
) -> EntitlementService:
    """Construct centralized PostgreSQL entitlement policy and adapters."""

    return EntitlementService(
        repository=SQLAlchemyEntitlementRepository(database),
        audit=audit,
    )


def install_entitlement_routes(
    *,
    app: FastAPI,
    service: EntitlementService,
) -> None:
    """Register the entitlement service and thin router on one application."""

    app.state.entitlement_service = service
    app.include_router(router)


__all__ = ["create_entitlement_service", "install_entitlement_routes"]
