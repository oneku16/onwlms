"""Composition-level orchestration for resumable accepted enrollment."""

from academics.application.contracts import AcceptedStudentAcademicEnrollmentCommand
from academics.application.ports import AcceptedStudentAcademicEnrollmentRegistrar
from admissions.application.contracts import AcceptedApplicantEnrollmentCommand
from admissions.application.contracts import AcceptedApplicantEnrollmentResult
from admissions.domain.exceptions import EnrollmentConversionError
from people.application.contracts import AcceptedStudentRegistrationCommand
from people.application.ports import AcceptedStudentRegistrar


class ModuleOwnedAcceptedApplicantEnrollmentRegistrar:
    """Call People then Academics through idempotent public capabilities."""

    def __init__(
        self,
        *,
        people: AcceptedStudentRegistrar,
        academics: AcceptedStudentAcademicEnrollmentRegistrar,
    ) -> None:
        self._people = people
        self._academics = academics

    async def enroll_accepted_applicant(
        self,
        command: AcceptedApplicantEnrollmentCommand,
    ) -> AcceptedApplicantEnrollmentResult:
        """Resume either downstream step using Admissions-persisted identifiers."""

        people_result = await self._people.register_accepted_student(
            AcceptedStudentRegistrationCommand(
                idempotency_key=command.idempotency_key,
                organization_id=command.organization_id,
                student_profile_id=command.student_profile_id,
                actor_subject_id=command.actor_subject_id,
                correlation_id=command.correlation_id,
                given_name=command.given_name,
                family_name=command.family_name,
                email=command.email,
                phone=command.phone,
            )
        )
        if people_result.student_profile_id != command.student_profile_id:
            raise EnrollmentConversionError(
                "People returned a student identifier that differs from the "
                "durable conversion."
            )
        academic_result = await self._academics.enroll_accepted_student(
            AcceptedStudentAcademicEnrollmentCommand(
                idempotency_key=command.idempotency_key,
                organization_id=command.organization_id,
                academic_enrollment_id=command.academic_enrollment_id,
                student_profile_id=people_result.student_profile_id,
                program_id=command.program_id,
                intake_term_id=command.intake_id,
                enrolled_at=command.requested_at,
            )
        )
        if academic_result.academic_enrollment_id != command.academic_enrollment_id:
            raise EnrollmentConversionError(
                "Academics returned an enrollment identifier that differs from the "
                "durable conversion."
            )
        return AcceptedApplicantEnrollmentResult(
            student_id=people_result.student_profile_id,
            academic_enrollment_id=academic_result.academic_enrollment_id,
        )


__all__ = ["ModuleOwnedAcceptedApplicantEnrollmentRegistrar"]
