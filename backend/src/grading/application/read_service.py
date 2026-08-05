"""Ownership-aware official grade and GPA read service."""

from uuid import UUID

from core.context import TenantActorContext
from core.errors import AuthorizationError
from grading.application.ports import GradingRepository
from grading.application.read_models import OfficialStudentReport
from grading.domain.models import FinalGrade
from grading.domain.models import calculate_gpa_summary

STUDENT_OFFICIAL_GRADES_READ = "grading.student.read_own"
GUARDIAN_OFFICIAL_GRADES_READ = "grading.guardian.read_linked"


class OfficialGradingReadService:
    """Return official results for enrollment IDs bound by an ownership gateway."""

    def __init__(
        self,
        repository: GradingRepository,
    ) -> None:
        self._repository = repository

    async def student_report(
        self,
        *,
        actor: TenantActorContext,
        enrollment_ids: tuple[UUID, ...],
    ) -> OfficialStudentReport:
        """Return current official grades and GPA for authorized enrollments."""

        if not isinstance(actor, TenantActorContext) or not (
            {
                STUDENT_OFFICIAL_GRADES_READ,
                GUARDIAN_OFFICIAL_GRADES_READ,
            }
            & actor.permissions
        ):
            raise AuthorizationError
        grades: list[FinalGrade] = []
        for enrollment_id in dict.fromkeys(enrollment_ids):
            grades.extend(
                await self._repository.list_student_final_grades(
                    organization_id=actor.organization_id,
                    student_academic_enrollment_id=enrollment_id,
                )
            )
        ordered = tuple(
            sorted(
                grades,
                key=lambda grade: (
                    str(grade.term_id),
                    str(grade.course_id),
                    str(grade.id),
                ),
            )
        )
        return OfficialStudentReport(
            grades=ordered,
            gpa=calculate_gpa_summary(ordered),
        )


__all__ = [
    "GUARDIAN_OFFICIAL_GRADES_READ",
    "STUDENT_OFFICIAL_GRADES_READ",
    "OfficialGradingReadService",
]
