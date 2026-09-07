"""Tenant and profile-kind validation for academic administration writes."""

from dataclasses import dataclass
from datetime import UTC
from datetime import date
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from uuid import uuid4

import pytest

from academics.application.service import ACADEMICS_ENROLLMENT_MANAGE
from academics.application.service import ACADEMICS_STRUCTURE_MANAGE
from academics.application.service import AcademicAdministrationService
from academics.domain.models import AcademicEnrollmentStatus
from academics.domain.models import AcademicYear
from academics.domain.models import Course
from academics.domain.models import CourseOffering
from academics.domain.models import EducationMode
from academics.domain.models import Program
from academics.domain.models import StudentAcademicEnrollment
from academics.domain.models import TeacherAssignment
from academics.domain.models import Term
from academics.infrastructure.repository import InMemoryAcademicRepository
from core.context import TenantActorContext
from core.errors import NotFoundError


@dataclass(frozen=True, slots=True)
class ExactAcademicProfileDirectory:
    """Expose only explicitly registered tenant and profile-kind pairs."""

    teachers: frozenset[tuple[UUID, UUID]]
    students: frozenset[tuple[UUID, UUID]]

    async def teacher_profile_exists(
        self,
        *,
        organization_id: UUID,
        teacher_profile_id: UUID,
    ) -> bool:
        return (organization_id, teacher_profile_id) in self.teachers

    async def student_profile_exists(
        self,
        *,
        organization_id: UUID,
        student_profile_id: UUID,
    ) -> bool:
        return (organization_id, student_profile_id) in self.students


class UnusedCampusDirectory:
    """Fail if the focused assignment/enrollment paths resolve a campus."""

    async def campus_exists(
        self,
        *,
        organization_id: UUID,
        campus_id: UUID,
    ) -> bool:
        del organization_id, campus_id
        raise AssertionError("Profile reference validation must not resolve a campus.")


class UnusedTermClosureAudit:
    """Fail if profile reference validation emits a term-closure audit event."""

    async def record_term_closure_intent(
        self,
        *,
        organization_id: UUID,
        actor_subject_id: UUID,
        term_id: UUID,
        correlation_id: str,
        reason: str,
    ) -> None:
        del organization_id, actor_subject_id, term_id, correlation_id, reason
        raise AssertionError("Profile reference validation must not close a term.")


@dataclass(frozen=True, slots=True)
class AcademicReferenceFixture:
    organization_id: UUID
    other_organization_id: UUID
    repository: InMemoryAcademicRepository
    service: AcademicAdministrationService
    actor: TenantActorContext
    offering_id: UUID
    program_id: UUID
    academic_year_id: UUID
    teacher_profile_id: UUID
    student_profile_id: UUID
    foreign_teacher_profile_id: UUID
    foreign_student_profile_id: UUID


async def _fixture() -> AcademicReferenceFixture:
    organization_id = uuid4()
    other_organization_id = uuid4()
    teacher_profile_id = uuid4()
    student_profile_id = uuid4()
    foreign_teacher_profile_id = uuid4()
    foreign_student_profile_id = uuid4()
    academic_year_id = uuid4()
    program_id = uuid4()
    term_id = uuid4()
    course_id = uuid4()
    offering_id = uuid4()
    repository = InMemoryAcademicRepository()
    profiles = ExactAcademicProfileDirectory(
        teachers=frozenset(
            {
                (organization_id, teacher_profile_id),
                (other_organization_id, foreign_teacher_profile_id),
            }
        ),
        students=frozenset(
            {
                (organization_id, student_profile_id),
                (other_organization_id, foreign_student_profile_id),
            }
        ),
    )
    await repository.save_program(
        Program(
            id=program_id,
            organization_id=organization_id,
            department_id=uuid4(),
            code="CS",
            name="Computer Science",
            education_mode=EducationMode.FLEXIBLE_SELECTION,
            credit_unit_label="credits",
        )
    )
    await repository.save_academic_year(
        AcademicYear(
            id=academic_year_id,
            organization_id=organization_id,
            name="2026-2027",
            starts_on=date(2026, 8, 1),
            ends_on=date(2027, 7, 31),
        )
    )
    await repository.save_term(
        Term(
            id=term_id,
            organization_id=organization_id,
            academic_year_id=academic_year_id,
            name="Fall",
            starts_on=date(2026, 8, 10),
            ends_on=date(2026, 12, 20),
            enrollment_deadline=datetime(2026, 8, 20, tzinfo=UTC),
        )
    )
    await repository.save_course(
        Course(
            id=course_id,
            organization_id=organization_id,
            department_id=uuid4(),
            code="CS-101",
            title="Foundations",
            credits=Decimal("3"),
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
    return AcademicReferenceFixture(
        organization_id=organization_id,
        other_organization_id=other_organization_id,
        repository=repository,
        service=AcademicAdministrationService(
            catalog=repository,
            campuses=UnusedCampusDirectory(),
            profiles=profiles,
            audit=UnusedTermClosureAudit(),
        ),
        actor=TenantActorContext(
            subject_id=uuid4(),
            organization_id=organization_id,
            membership_id=uuid4(),
            correlation_id="academic-reference-integrity",
            permissions=frozenset(
                {ACADEMICS_STRUCTURE_MANAGE, ACADEMICS_ENROLLMENT_MANAGE}
            ),
        ),
        offering_id=offering_id,
        program_id=program_id,
        academic_year_id=academic_year_id,
        teacher_profile_id=teacher_profile_id,
        student_profile_id=student_profile_id,
        foreign_teacher_profile_id=foreign_teacher_profile_id,
        foreign_student_profile_id=foreign_student_profile_id,
    )


async def test_teacher_assignment_requires_same_tenant_teacher_profile() -> None:
    fixture = await _fixture()

    await fixture.service.assign_teacher(
        context=fixture.actor,
        assignment=TeacherAssignment(
            id=uuid4(),
            organization_id=fixture.organization_id,
            course_offering_id=fixture.offering_id,
            teacher_id=fixture.teacher_profile_id,
            role="lead",
        ),
    )

    for invalid_teacher_id in (
        fixture.student_profile_id,
        fixture.foreign_teacher_profile_id,
    ):
        with pytest.raises(NotFoundError, match="assignment reference"):
            await fixture.service.assign_teacher(
                context=fixture.actor,
                assignment=TeacherAssignment(
                    id=uuid4(),
                    organization_id=fixture.organization_id,
                    course_offering_id=fixture.offering_id,
                    teacher_id=invalid_teacher_id,
                    role="assistant",
                ),
            )

    stored = await fixture.repository.list_teacher_assignments(
        organization_id=fixture.organization_id,
        course_offering_id=fixture.offering_id,
        limit=10,
        offset=0,
    )
    assert tuple(value.teacher_id for value in stored) == (fixture.teacher_profile_id,)


async def test_student_enrollment_requires_same_tenant_student_profile() -> None:
    fixture = await _fixture()
    now = datetime(2026, 8, 5, 10, tzinfo=UTC)

    await fixture.service.enroll_student(
        context=fixture.actor,
        enrollment=StudentAcademicEnrollment(
            id=uuid4(),
            organization_id=fixture.organization_id,
            student_id=fixture.student_profile_id,
            program_id=fixture.program_id,
            academic_year_id=fixture.academic_year_id,
            cohort_id=None,
            status=AcademicEnrollmentStatus.ACTIVE,
            enrolled_at=now,
        ),
    )

    for invalid_student_id in (
        fixture.teacher_profile_id,
        fixture.foreign_student_profile_id,
    ):
        with pytest.raises(NotFoundError, match="enrollment reference"):
            await fixture.service.enroll_student(
                context=fixture.actor,
                enrollment=StudentAcademicEnrollment(
                    id=uuid4(),
                    organization_id=fixture.organization_id,
                    student_id=invalid_student_id,
                    program_id=fixture.program_id,
                    academic_year_id=fixture.academic_year_id,
                    cohort_id=None,
                    status=AcademicEnrollmentStatus.ACTIVE,
                    enrolled_at=now,
                ),
            )

    stored = await fixture.repository.list_student_enrollments(
        organization_id=fixture.organization_id,
        student_id=None,
        program_id=fixture.program_id,
        academic_year_id=fixture.academic_year_id,
        limit=10,
        offset=0,
    )
    assert tuple(value.student_id for value in stored) == (fixture.student_profile_id,)
