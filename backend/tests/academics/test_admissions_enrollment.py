"""Module-owned academic enrollment conversion tests."""

from dataclasses import replace
from datetime import UTC
from datetime import date
from datetime import datetime
from uuid import uuid4

import pytest

from academics.application.admissions_enrollment_service import (
    AcceptedStudentAcademicEnrollmentService,
)
from academics.application.contracts import AcceptedStudentAcademicEnrollmentCommand
from academics.domain.exceptions import AcademicRuleError
from academics.domain.models import AcademicYear
from academics.domain.models import EducationMode
from academics.domain.models import Program
from academics.domain.models import Term
from academics.infrastructure.repository import InMemoryAcademicRepository
from core.errors import ConflictError
from core.errors import NotFoundError


async def test_admissions_enrollment_uses_exact_ids_intake_year_and_no_cohort() -> None:
    repository = InMemoryAcademicRepository()
    organization_id = uuid4()
    program = Program(
        id=uuid4(),
        organization_id=organization_id,
        department_id=uuid4(),
        code="BSCS",
        name="Computer Science",
        education_mode=EducationMode.FLEXIBLE_SELECTION,
        credit_unit_label="credits",
    )
    academic_year = AcademicYear(
        id=uuid4(),
        organization_id=organization_id,
        name="2026-2027",
        starts_on=date(2026, 8, 1),
        ends_on=date(2027, 7, 31),
    )
    term = Term(
        id=uuid4(),
        organization_id=organization_id,
        academic_year_id=academic_year.id,
        name="Fall",
        starts_on=date(2026, 8, 10),
        ends_on=date(2026, 12, 20),
        enrollment_deadline=datetime(2026, 8, 20, tzinfo=UTC),
    )
    await repository.save_program(program)
    await repository.save_academic_year(academic_year)
    await repository.save_term(term)
    service = AcceptedStudentAcademicEnrollmentService(
        catalog=repository,
        registrations=repository,
    )
    command = AcceptedStudentAcademicEnrollmentCommand(
        idempotency_key=uuid4(),
        organization_id=organization_id,
        academic_enrollment_id=uuid4(),
        student_profile_id=uuid4(),
        program_id=program.id,
        intake_term_id=term.id,
        enrolled_at=datetime(2026, 8, 5, 12, tzinfo=UTC),
    )

    first = await service.enroll_accepted_student(command)
    await repository.save_term(replace(term, is_closed=True))
    second = await service.enroll_accepted_student(command)
    stored = await repository.get_student_enrollment(
        organization_id=organization_id,
        enrollment_id=command.academic_enrollment_id,
    )

    assert first == second
    assert first.academic_enrollment_id == command.academic_enrollment_id
    assert stored is not None
    assert stored.id == command.academic_enrollment_id
    assert stored.student_id == command.student_profile_id
    assert stored.program_id == program.id
    assert stored.academic_year_id == term.academic_year_id
    assert stored.cohort_id is None

    changed = AcceptedStudentAcademicEnrollmentCommand(
        idempotency_key=command.idempotency_key,
        organization_id=organization_id,
        academic_enrollment_id=command.academic_enrollment_id,
        student_profile_id=uuid4(),
        program_id=program.id,
        intake_term_id=term.id,
        enrolled_at=command.enrolled_at,
    )
    with pytest.raises(ConflictError, match="another academic enrollment"):
        await service.enroll_accepted_student(changed)


async def test_admissions_enrollment_fails_closed_across_tenants_and_closed_terms() -> (
    None
):
    repository = InMemoryAcademicRepository()
    organization_id = uuid4()
    program = Program(
        id=uuid4(),
        organization_id=organization_id,
        department_id=uuid4(),
        code="MED",
        name="Medicine",
        education_mode=EducationMode.FIXED_CURRICULUM,
        credit_unit_label="credits",
    )
    term = Term(
        id=uuid4(),
        organization_id=organization_id,
        academic_year_id=uuid4(),
        name="Closed intake",
        starts_on=date(2026, 1, 10),
        ends_on=date(2026, 5, 20),
        enrollment_deadline=datetime(2026, 1, 5, tzinfo=UTC),
        is_closed=True,
    )
    await repository.save_program(program)
    await repository.save_term(term)
    service = AcceptedStudentAcademicEnrollmentService(
        catalog=repository,
        registrations=repository,
    )
    command = AcceptedStudentAcademicEnrollmentCommand(
        idempotency_key=uuid4(),
        organization_id=organization_id,
        academic_enrollment_id=uuid4(),
        student_profile_id=uuid4(),
        program_id=program.id,
        intake_term_id=term.id,
        enrolled_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    with pytest.raises(AcademicRuleError, match="closed intake"):
        await service.enroll_accepted_student(command)

    with pytest.raises(NotFoundError):
        await service.enroll_accepted_student(
            AcceptedStudentAcademicEnrollmentCommand(
                idempotency_key=command.idempotency_key,
                organization_id=uuid4(),
                academic_enrollment_id=command.academic_enrollment_id,
                student_profile_id=command.student_profile_id,
                program_id=command.program_id,
                intake_term_id=command.intake_term_id,
                enrolled_at=command.enrolled_at,
            )
        )
