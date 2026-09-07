"""Explicit official-grading construction and route registration."""

from datetime import datetime

from fastapi import FastAPI

from core.time import utc_now
from grading.application.ports import GradeTargetDirectory
from grading.application.ports import GradingAuditSink
from grading.application.ports import TermClosureDirectory
from grading.application.service import OfficialGradingService
from grading.infrastructure.sqlalchemy_repository import SQLAlchemyGradingRepository
from grading.infrastructure.term_guard import SQLAlchemyTermGradeWriteGuard
from grading.presentation.router import router
from shared.database import Database


class SystemGradingClock:
    """Supply timezone-aware UTC time to official grading use cases."""

    def now(self) -> datetime:
        """Return current UTC time."""

        return utc_now()


def create_official_grading_service(
    *,
    database: Database,
    targets: GradeTargetDirectory,
    terms: TermClosureDirectory,
    audit: GradingAuditSink,
) -> OfficialGradingService:
    """Construct PostgreSQL grading persistence and explicit collaborators."""

    return OfficialGradingService(
        repository=SQLAlchemyGradingRepository(database),
        targets=targets,
        terms=terms,
        term_writes=SQLAlchemyTermGradeWriteGuard(database),
        clock=SystemGradingClock(),
        audit=audit,
    )


def install_grading_routes(
    *,
    app: FastAPI,
    service: OfficialGradingService,
) -> None:
    """Register the explicitly composed grading service and thin router."""

    app.state.official_grading_service = service
    app.include_router(router)


__all__ = [
    "SystemGradingClock",
    "create_official_grading_service",
    "install_grading_routes",
]
