"""Academic application capability for accepted Admissions conversions."""

from academics.application.contracts import AcceptedStudentAcademicEnrollmentCommand
from academics.application.contracts import AcceptedStudentAcademicEnrollmentResult
from academics.application.ports import AcademicCatalogRepository
from academics.application.ports import AdmissionsAcademicEnrollmentRepository
from academics.domain.exceptions import AcademicRuleError
from academics.domain.models import AcademicEnrollmentStatus
from academics.domain.models import StudentAcademicEnrollment
from core.errors import NotFoundError


class AcceptedStudentAcademicEnrollmentService:
    """Resolve intake ownership and create one exact official enrollment."""

    def __init__(
        self,
        *,
        catalog: AcademicCatalogRepository,
        registrations: AdmissionsAcademicEnrollmentRepository,
    ) -> None:
        self._catalog = catalog
        self._registrations = registrations

    async def enroll_accepted_student(
        self,
        command: AcceptedStudentAcademicEnrollmentCommand,
    ) -> AcceptedStudentAcademicEnrollmentResult:
        """Use the intake Term's Academic Year without inferring a cohort."""

        existing = await self._registrations.get_admissions_enrollment(command)
        if existing is not None:
            return existing
        program = await self._catalog.get_program(
            organization_id=command.organization_id,
            program_id=command.program_id,
        )
        term = await self._catalog.get_term(
            organization_id=command.organization_id,
            term_id=command.intake_term_id,
        )
        if program is None or term is None:
            raise NotFoundError("Admissions academic target was not found.")
        if term.is_closed:
            raise AcademicRuleError(
                "A closed intake term cannot receive an academic enrollment."
            )
        enrollment = StudentAcademicEnrollment(
            id=command.academic_enrollment_id,
            organization_id=command.organization_id,
            student_id=command.student_profile_id,
            program_id=program.id,
            academic_year_id=term.academic_year_id,
            cohort_id=None,
            status=AcademicEnrollmentStatus.ACTIVE,
            enrolled_at=command.enrolled_at,
        )
        return await self._registrations.register_admissions_enrollment(
            command=command,
            enrollment=enrollment,
        )


__all__ = ["AcceptedStudentAcademicEnrollmentService"]
