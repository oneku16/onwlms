"""Explicit academic module construction and route registration."""

from dataclasses import dataclass
from datetime import datetime

from fastapi import FastAPI

from academics.application.admissions_enrollment_service import (
    AcceptedStudentAcademicEnrollmentService,
)
from academics.application.ports import AcademicAuditSink
from academics.application.ports import AcademicProfileDirectory
from academics.application.ports import CampusDirectory
from academics.application.ports import CourseSelectionStudentOwnership
from academics.application.reference_service import AcademicReferenceService
from academics.application.service import AcademicAdministrationService
from academics.application.service import AcademicEnrollmentTransitionService
from academics.application.service import CourseSelectionService
from academics.infrastructure.sqlalchemy_repository import SQLAlchemyAcademicRepository
from academics.presentation.router import router
from core.time import utc_now
from shared.database import Database


class SystemAcademicClock:
    """Supply timezone-aware UTC time to academic use cases."""

    def now(self) -> datetime:
        """Return current UTC time."""

        return utc_now()


@dataclass(frozen=True, slots=True)
class AcademicServices:
    """Expose the academic module's explicit application boundaries."""

    administration: AcademicAdministrationService
    course_selection: CourseSelectionService
    references: AcademicReferenceService
    admissions_enrollment: AcceptedStudentAcademicEnrollmentService
    enrollment_transitions: AcademicEnrollmentTransitionService


def create_academic_services(
    *,
    database: Database,
    campuses: CampusDirectory,
    profiles: AcademicProfileDirectory,
    audit: AcademicAuditSink,
    ownership: CourseSelectionStudentOwnership,
) -> AcademicServices:
    """Construct shared PostgreSQL academic persistence and application services."""

    repository = SQLAlchemyAcademicRepository(database)
    return AcademicServices(
        administration=AcademicAdministrationService(
            catalog=repository,
            campuses=campuses,
            profiles=profiles,
            audit=audit,
        ),
        course_selection=CourseSelectionService(
            catalog=repository,
            selections=repository,
            clock=SystemAcademicClock(),
            audit=audit,
            ownership=ownership,
        ),
        references=AcademicReferenceService(repository=repository),
        admissions_enrollment=AcceptedStudentAcademicEnrollmentService(
            catalog=repository,
            registrations=repository,
        ),
        enrollment_transitions=AcademicEnrollmentTransitionService(
            catalog=repository,
            audit=audit,
        ),
    )


def install_academic_routes(
    *,
    app: FastAPI,
    services: AcademicServices,
) -> None:
    """Register explicitly composed academic services and thin router."""

    app.state.academic_administration_service = services.administration
    app.state.academic_enrollment_transition_service = services.enrollment_transitions
    app.state.course_selection_service = services.course_selection
    app.include_router(router)


__all__ = [
    "AcademicServices",
    "SystemAcademicClock",
    "create_academic_services",
    "install_academic_routes",
]
