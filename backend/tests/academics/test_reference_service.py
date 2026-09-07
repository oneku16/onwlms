"""Academic cross-module reference boundary tests."""

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from uuid import UUID
from uuid import uuid4

import pytest

from academics.application.contracts import AcademicGradeTarget
from academics.application.reference_service import AcademicReferenceService
from academics.domain.exceptions import AcademicRuleError
from academics.domain.models import AcademicCalendarEvent
from academics.domain.models import AcademicEnrollmentStatus
from academics.domain.models import Course
from academics.domain.models import CourseEnrollment
from academics.domain.models import CourseEnrollmentStatus
from academics.domain.models import CourseOffering
from academics.domain.models import CourseSelectionRequest
from academics.domain.models import CourseSelectionStatus
from academics.domain.models import EducationMode
from academics.domain.models import Program
from academics.domain.models import Room
from academics.domain.models import StudentAcademicEnrollment
from academics.domain.models import Term
from academics.infrastructure.repository import InMemoryAcademicRepository
from core.errors import NotFoundError


@dataclass(frozen=True, slots=True)
class _ReferenceFixture:
    repository: InMemoryAcademicRepository
    organization_id: UUID
    other_organization_id: UUID
    program_id: UUID
    term_id: UUID
    student_enrollment_id: UUID
    course_enrollment_id: UUID
    offering_id: UUID
    course_id: UUID
    room_id: UUID
    horizon_start: datetime
    horizon_end: datetime


async def _reference_fixture() -> _ReferenceFixture:
    repository = InMemoryAcademicRepository()
    organization_id = uuid4()
    other_organization_id = uuid4()
    program_id = uuid4()
    term_id = uuid4()
    course_id = uuid4()
    offering_id = uuid4()
    student_enrollment_id = uuid4()
    course_enrollment_id = uuid4()
    room_id = uuid4()
    academic_year_id = uuid4()
    now = datetime(2026, 8, 5, 10, tzinfo=UTC)
    horizon_start = datetime(2026, 8, 10, 8, tzinfo=UTC)
    horizon_end = horizon_start + timedelta(hours=10)
    await repository.save_program(
        Program(
            id=program_id,
            organization_id=organization_id,
            department_id=uuid4(),
            code="BSC-CS",
            name="Computer Science",
            education_mode=EducationMode.FLEXIBLE_SELECTION,
            credit_unit_label="credits",
        )
    )
    await repository.save_term(
        Term(
            id=term_id,
            organization_id=organization_id,
            academic_year_id=academic_year_id,
            name="Fall",
            starts_on=horizon_start.date(),
            ends_on=(horizon_start + timedelta(days=120)).date(),
            enrollment_deadline=now,
            is_closed=True,
        )
    )
    await repository.save_course(
        Course(
            id=course_id,
            organization_id=organization_id,
            department_id=uuid4(),
            code="CS-101",
            title="Introduction to Computing",
            credits=Decimal("4"),
        )
    )
    await repository.save_course_offering(
        CourseOffering(
            id=offering_id,
            organization_id=organization_id,
            course_id=course_id,
            term_id=term_id,
            campus_id=uuid4(),
            section_code="A",
            capacity=30,
        )
    )
    await repository.save_student_enrollment(
        StudentAcademicEnrollment(
            id=student_enrollment_id,
            organization_id=organization_id,
            student_id=uuid4(),
            program_id=program_id,
            academic_year_id=academic_year_id,
            cohort_id=None,
            status=AcademicEnrollmentStatus.ACTIVE,
            enrolled_at=now,
        )
    )
    request_id = uuid4()
    request = CourseSelectionRequest(
        id=request_id,
        organization_id=organization_id,
        student_academic_enrollment_id=student_enrollment_id,
        term_id=term_id,
        offering_ids=(offering_id,),
        requested_credits=Decimal("4"),
        status=CourseSelectionStatus.APPROVED,
        submitted_at=now,
        submitted_by=uuid4(),
        decided_at=now,
        decided_by=uuid4(),
    )
    await repository.save_submission(
        request=request,
        enrollments=(
            CourseEnrollment(
                id=course_enrollment_id,
                organization_id=organization_id,
                student_academic_enrollment_id=student_enrollment_id,
                course_offering_id=offering_id,
                credits=Decimal("4"),
                status=CourseEnrollmentStatus.ENROLLED,
                enrolled_at=now,
                selection_request_id=request_id,
            ),
        ),
        offering_capacities={offering_id: 30},
    )
    await repository.save_room(
        Room(
            id=room_id,
            organization_id=organization_id,
            campus_id=uuid4(),
            code="R-101",
            room_type="lecture",
            capacity=40,
        )
    )
    await repository.save_room(
        Room(
            id=uuid4(),
            organization_id=other_organization_id,
            campus_id=uuid4(),
            code="OTHER",
            room_type="lecture",
            capacity=20,
        )
    )
    await repository.save_calendar_event(
        AcademicCalendarEvent(
            id=uuid4(),
            organization_id=organization_id,
            title="Instruction day",
            starts_at=horizon_start - timedelta(hours=1),
            ends_at=horizon_end + timedelta(hours=1),
            instruction_allowed=True,
        )
    )
    await repository.save_calendar_event(
        AcademicCalendarEvent(
            id=uuid4(),
            organization_id=organization_id,
            title="Closure",
            starts_at=horizon_start + timedelta(hours=2),
            ends_at=horizon_start + timedelta(hours=3),
            instruction_allowed=False,
        )
    )
    return _ReferenceFixture(
        repository=repository,
        organization_id=organization_id,
        other_organization_id=other_organization_id,
        program_id=program_id,
        term_id=term_id,
        student_enrollment_id=student_enrollment_id,
        course_enrollment_id=course_enrollment_id,
        offering_id=offering_id,
        course_id=course_id,
        room_id=room_id,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
    )


async def test_admissions_target_requires_program_and_term_in_same_tenant() -> None:
    fixture = await _reference_fixture()
    service = AcademicReferenceService(repository=fixture.repository)

    assert await service.admissions_target_exists(
        organization_id=fixture.organization_id,
        program_id=fixture.program_id,
        intake_id=fixture.term_id,
    )
    assert not await service.admissions_target_exists(
        organization_id=fixture.other_organization_id,
        program_id=fixture.program_id,
        intake_id=fixture.term_id,
    )


async def test_grade_target_and_term_closure_use_official_joined_facts() -> None:
    fixture = await _reference_fixture()
    service = AcademicReferenceService(repository=fixture.repository)

    target = await service.get_grade_target(
        organization_id=fixture.organization_id,
        course_enrollment_id=fixture.course_enrollment_id,
    )

    assert target == AcademicGradeTarget(
        organization_id=fixture.organization_id,
        student_academic_enrollment_id=fixture.student_enrollment_id,
        course_enrollment_id=fixture.course_enrollment_id,
        course_offering_id=fixture.offering_id,
        course_id=fixture.course_id,
        term_id=fixture.term_id,
        credits=Decimal("4"),
    )
    assert await service.is_term_closed(
        organization_id=fixture.organization_id,
        term_id=fixture.term_id,
    )
    with pytest.raises(NotFoundError):
        await service.is_term_closed(
            organization_id=fixture.other_organization_id,
            term_id=fixture.term_id,
        )


async def test_scheduling_references_are_tenant_scoped_and_horizon_bounded() -> None:
    fixture = await _reference_fixture()
    service = AcademicReferenceService(repository=fixture.repository)

    references = await service.scheduling_references(
        organization_id=fixture.organization_id,
        starts_at=fixture.horizon_start,
        ends_at=fixture.horizon_end,
    )

    assert tuple(room.room_id for room in references.rooms) == (fixture.room_id,)
    assert len(references.instruction_windows) == 2
    assert references.instruction_windows[0].starts_at == fixture.horizon_start
    assert references.instruction_windows[0].ends_at == (
        fixture.horizon_start + timedelta(hours=2)
    )
    assert references.instruction_windows[1].starts_at == (
        fixture.horizon_start + timedelta(hours=3)
    )
    assert references.instruction_windows[1].ends_at == fixture.horizon_end
    with pytest.raises(AcademicRuleError):
        await service.scheduling_references(
            organization_id=fixture.organization_id,
            starts_at=fixture.horizon_end,
            ends_at=fixture.horizon_start,
        )
    with pytest.raises(AcademicRuleError, match="52 weeks"):
        await service.scheduling_references(
            organization_id=fixture.organization_id,
            starts_at=fixture.horizon_start,
            ends_at=fixture.horizon_start + timedelta(weeks=53),
        )
