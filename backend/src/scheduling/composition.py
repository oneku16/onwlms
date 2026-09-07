"""Explicit construction and route registration for scheduling."""

from fastapi import FastAPI

from scheduling.application.availability_service import TeacherAvailabilityService
from scheduling.application.generator import DeterministicHeuristicSchedulingGenerator
from scheduling.application.ports import SchedulingGenerator
from scheduling.application.ports import SchedulingResourceDirectory
from scheduling.application.ports import TeacherReferenceDirectory
from scheduling.application.ports import TimetableGenerationEntitlement
from scheduling.application.service import TimetableService
from scheduling.infrastructure.sqlalchemy_repository import (
    SQLAlchemySchedulingRepository,
)
from scheduling.infrastructure.sqlalchemy_repository import (
    SQLAlchemyTeacherAvailabilityRepository,
)
from scheduling.presentation.router import router
from shared.database import Database


def create_timetable_service(
    *,
    database: Database,
    resources: SchedulingResourceDirectory,
    entitlements: TimetableGenerationEntitlement,
    generator: SchedulingGenerator | None = None,
) -> TimetableService:
    """Construct the PostgreSQL adapter and replaceable scheduling generator."""

    return TimetableService(
        repository=SQLAlchemySchedulingRepository(database),
        resources=resources,
        generator=generator or DeterministicHeuristicSchedulingGenerator(),
        entitlements=entitlements,
    )


def create_teacher_availability_service(
    *,
    database: Database,
    teachers: TeacherReferenceDirectory,
) -> TeacherAvailabilityService:
    """Construct tenant-scoped teacher availability persistence."""

    return TeacherAvailabilityService(
        SQLAlchemyTeacherAvailabilityRepository(database),
        teachers,
    )


def install_scheduling_routes(
    *,
    app: FastAPI,
    service: TimetableService,
    teacher_availability: TeacherAvailabilityService,
) -> None:
    """Register the explicitly composed service and thin scheduling router."""

    app.state.timetable_service = service
    app.state.teacher_availability_service = teacher_availability
    app.include_router(router)


__all__ = [
    "create_teacher_availability_service",
    "create_timetable_service",
    "install_scheduling_routes",
]
