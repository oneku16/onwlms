"""Read-only MCP tool service over ordinary authorized application APIs."""

from uuid import UUID

from mcp_gateway.application.ports import AuthorizedReadGateway
from mcp_gateway.domain.read_models import AssignedSection
from mcp_gateway.domain.read_models import GpaSummary
from mcp_gateway.domain.read_models import GradeSummary
from mcp_gateway.domain.read_models import GradeSyncSummary
from mcp_gateway.domain.read_models import GuardianStudentSummary
from mcp_gateway.domain.read_models import MoodleDeadline
from mcp_gateway.domain.read_models import ScheduleItem
from mcp_gateway.domain.read_models import SectionStudent
from mcp_gateway.domain.read_models import UpcomingEvent


class MCPReadService:
    """Expose the minimal first-release MCP read capability set."""

    def __init__(
        self,
        gateway: AuthorizedReadGateway,
    ) -> None:
        self._gateway = gateway

    async def own_schedule(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[ScheduleItem]:
        """Return the actor's schedule through an authorized application query."""

        return await self._gateway.get_student_schedule(
            ownid_subject=ownid_subject,
            organization_id=organization_id,
        )

    async def own_official_grades(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[GradeSummary]:
        """Return the actor's official grades through the grading boundary."""

        return await self._gateway.get_student_grades(
            ownid_subject=ownid_subject,
            organization_id=organization_id,
        )

    async def own_gpa_summary(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> GpaSummary:
        """Return the actor's official GPA through the grading boundary."""

        return await self._gateway.get_student_gpa(
            ownid_subject=ownid_subject,
            organization_id=organization_id,
        )

    async def own_upcoming_events(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[UpcomingEvent]:
        """Return the actor's upcoming authorized organization events."""

        return await self._gateway.get_student_events(
            ownid_subject=ownid_subject,
            organization_id=organization_id,
        )

    async def own_moodle_deadlines(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[MoodleDeadline]:
        """Return deadline evidence without making Moodle authoritative."""

        return await self._gateway.get_student_moodle_deadlines(
            ownid_subject=ownid_subject,
            organization_id=organization_id,
        )

    async def assigned_sections(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[AssignedSection]:
        """Return sections assigned to the actor as a teacher."""

        return await self._gateway.get_teacher_sections(
            ownid_subject=ownid_subject,
            organization_id=organization_id,
        )

    async def section_students(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
        section_id: UUID,
    ) -> list[SectionStudent]:
        """Return a roster only after section-specific teacher authorization."""

        return await self._gateway.get_section_students(
            ownid_subject=ownid_subject,
            organization_id=organization_id,
            section_id=section_id,
        )

    async def grade_sync_status(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[GradeSyncSummary]:
        """Return synchronization status for the actor's assigned sections."""

        return await self._gateway.get_grade_sync_status(
            ownid_subject=ownid_subject,
            organization_id=organization_id,
        )

    async def linked_student_summaries(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[GuardianStudentSummary]:
        """Return only summaries authorized through explicit guardian links."""

        return await self._gateway.get_guardian_students(
            ownid_subject=ownid_subject,
            organization_id=organization_id,
        )


__all__ = ["MCPReadService"]
