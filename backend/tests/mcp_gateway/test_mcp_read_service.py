"""MCP reads delegate to authorization-aware application capabilities."""

from uuid import UUID
from uuid import uuid7

from mcp_gateway.application.service import MCPReadService
from mcp_gateway.domain.read_models import AssignedSection
from mcp_gateway.domain.read_models import GpaSummary
from mcp_gateway.domain.read_models import GradeSummary
from mcp_gateway.domain.read_models import GradeSyncSummary
from mcp_gateway.domain.read_models import GuardianStudentSummary
from mcp_gateway.domain.read_models import MoodleDeadline
from mcp_gateway.domain.read_models import ScheduleItem
from mcp_gateway.domain.read_models import SectionStudent
from mcp_gateway.domain.read_models import UpcomingEvent


class RecordingAuthorizedReadGateway:
    """Record subject and tenant values supplied to the ordinary application API."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, UUID]] = []

    def _record(self, ownid_subject: str, organization_id: UUID) -> None:
        """Record one authorization context."""

        self.calls.append((ownid_subject, organization_id))

    async def get_student_schedule(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[ScheduleItem]:
        """Record and return an empty authorized schedule."""

        self._record(ownid_subject, organization_id)
        return []

    async def get_student_grades(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[GradeSummary]:
        """Record and return empty grades."""

        self._record(ownid_subject, organization_id)
        return []

    async def get_student_gpa(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> GpaSummary:
        """Record and return an empty official GPA summary."""

        self._record(ownid_subject, organization_id)
        return GpaSummary(
            credits_attempted="0",
            credits_earned="0",
            gpa_credits_attempted="0",
            quality_points="0",
            gpa=None,
        )

    async def get_student_events(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[UpcomingEvent]:
        """Record and return empty events."""

        self._record(ownid_subject, organization_id)
        return []

    async def get_student_moodle_deadlines(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[MoodleDeadline]:
        """Record and return empty deadlines."""

        self._record(ownid_subject, organization_id)
        return []

    async def get_teacher_sections(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[AssignedSection]:
        """Record and return empty teacher sections."""

        self._record(ownid_subject, organization_id)
        return []

    async def get_section_students(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
        section_id: UUID,
    ) -> list[SectionStudent]:
        """Record and return an empty authorized roster."""

        del section_id
        self._record(ownid_subject, organization_id)
        return []

    async def get_grade_sync_status(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[GradeSyncSummary]:
        """Record and return empty synchronization status."""

        self._record(ownid_subject, organization_id)
        return []

    async def get_guardian_students(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[GuardianStudentSummary]:
        """Record and return empty guardian summaries."""

        self._record(ownid_subject, organization_id)
        return []


async def test_student_schedule_revalidates_subject_and_tenant_per_call() -> None:
    gateway = RecordingAuthorizedReadGateway()
    service = MCPReadService(gateway)
    organization_id = uuid7()

    result = await service.own_schedule(
        ownid_subject="ownid-subject",
        organization_id=organization_id,
    )

    assert result == []
    assert gateway.calls == [("ownid-subject", organization_id)]


async def test_section_roster_does_not_offer_a_write_capability() -> None:
    gateway = RecordingAuthorizedReadGateway()
    service = MCPReadService(gateway)
    organization_id = uuid7()

    result = await service.section_students(
        ownid_subject="teacher-subject",
        organization_id=organization_id,
        section_id=uuid7(),
    )

    assert result == []
    assert not hasattr(service, "change_grade")
