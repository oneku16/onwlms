"""Application API port used by MCP instead of database access."""

from typing import Protocol
from uuid import UUID

from mcp_gateway.domain.read_models import AssignedSection
from mcp_gateway.domain.read_models import GpaSummary
from mcp_gateway.domain.read_models import GradeSummary
from mcp_gateway.domain.read_models import GradeSyncSummary
from mcp_gateway.domain.read_models import GuardianStudentSummary
from mcp_gateway.domain.read_models import MoodleDeadline
from mcp_gateway.domain.read_models import ScheduleItem
from mcp_gateway.domain.read_models import SectionStudent
from mcp_gateway.domain.read_models import UpcomingEvent


class AuthorizedReadGateway(Protocol):
    """Resolve OwnID subject, membership, permission, and MCP entitlement per call."""

    async def get_student_schedule(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[ScheduleItem]:
        """Return the current student's authorized schedule."""
        ...

    async def get_student_grades(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[GradeSummary]:
        """Return the current student's official grades."""
        ...

    async def get_student_gpa(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> GpaSummary:
        """Return the current student's official cumulative GPA summary."""
        ...

    async def get_student_events(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[UpcomingEvent]:
        """Return the current student's upcoming organization events."""
        ...

    async def get_student_moodle_deadlines(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[MoodleDeadline]:
        """Return Moodle deadline evidence for the current student."""
        ...

    async def get_teacher_sections(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[AssignedSection]:
        """Return sections assigned to the current teacher."""
        ...

    async def get_section_students(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
        section_id: UUID,
    ) -> list[SectionStudent]:
        """Return an authorized roster for one assigned section."""
        ...

    async def get_grade_sync_status(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[GradeSyncSummary]:
        """Return final-grade synchronization status for assigned sections."""
        ...

    async def get_guardian_students(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[GuardianStudentSummary]:
        """Return only students explicitly linked to the current guardian."""
        ...


class MCPAuditSink(Protocol):
    """Append privacy-minimized MCP invocation evidence."""

    async def record_mcp_invocation(
        self,
        *,
        tool: str,
        organization_id: UUID,
        actor_subject_id: UUID | None,
        correlation_id: str,
        outcome: str,
    ) -> None:
        """Record one invocation without prompts, tokens, or returned records."""
        ...


__all__ = ["AuthorizedReadGateway", "MCPAuditSink"]
