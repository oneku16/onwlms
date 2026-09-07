"""Explicit admissions construction and route registration."""

from datetime import datetime

from fastapi import FastAPI

from admissions.application.ports import AcceptedApplicantEnrollmentRegistrar
from admissions.application.ports import AdmissionsAuditSink
from admissions.application.ports import AdmissionsTargetDirectory
from admissions.application.ports import DepositVerifier
from admissions.application.service import AdmissionsService
from admissions.infrastructure.repository import UnconfiguredDepositVerifier
from admissions.infrastructure.sqlalchemy_repository import (
    SQLAlchemyAdmissionsRepository,
)
from admissions.presentation.router import router
from core.time import utc_now
from shared.database import Database


class SystemAdmissionsClock:
    """Supply timezone-aware UTC time to admissions use cases."""

    def now(self) -> datetime:
        """Return current UTC time."""

        return utc_now()


def create_admissions_service(
    *,
    database: Database,
    pii_encryption_key: str,
    targets: AdmissionsTargetDirectory,
    registrar: AcceptedApplicantEnrollmentRegistrar,
    audit: AdmissionsAuditSink,
    deposits: DepositVerifier | None = None,
) -> AdmissionsService:
    """Construct PostgreSQL admissions persistence and explicit collaborators."""

    return AdmissionsService(
        repository=SQLAlchemyAdmissionsRepository(
            database=database,
            pii_encryption_key=pii_encryption_key,
        ),
        targets=targets,
        registrar=registrar,
        deposits=deposits or UnconfiguredDepositVerifier(),
        clock=SystemAdmissionsClock(),
        audit=audit,
    )


def install_admissions_routes(
    *,
    app: FastAPI,
    service: AdmissionsService,
) -> None:
    """Register the explicitly composed admissions service and thin router."""

    app.state.admissions_service = service
    app.include_router(router)


__all__ = [
    "SystemAdmissionsClock",
    "create_admissions_service",
    "install_admissions_routes",
]
