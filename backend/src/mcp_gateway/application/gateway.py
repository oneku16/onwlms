"""MCP bearer authorization around shared ownership-safe application reads."""

from collections.abc import Awaitable
from collections.abc import Callable
from datetime import datetime
from typing import TypeVar
from uuid import UUID

from core.context import TenantActorContext
from core.errors import AppError
from core.errors import AuthenticationError
from core.errors import AuthorizationError
from core.errors import NotFoundError
from core.identifiers import new_uuid7
from entitlements.application.ports import EntitlementResolver
from entitlements.domain.models import FeatureCode
from identity.application.ports import TenantContextResolver
from identity.application.read_service import IdentitySubjectReadService
from mcp_gateway.application.owned_read_service import ActorOwnedReadService
from mcp_gateway.application.ports import MCPAuditSink
from mcp_gateway.domain.read_models import AssignedSection
from mcp_gateway.domain.read_models import GpaSummary
from mcp_gateway.domain.read_models import GradeSummary
from mcp_gateway.domain.read_models import GradeSyncSummary
from mcp_gateway.domain.read_models import GuardianStudentSummary
from mcp_gateway.domain.read_models import MoodleDeadline
from mcp_gateway.domain.read_models import ScheduleItem
from mcp_gateway.domain.read_models import SectionStudent
from mcp_gateway.domain.read_models import UpcomingEvent

ResultT = TypeVar("ResultT")


class ApplicationAuthorizedReadGateway:
    """Reauthorize and audit every MCP call before actor-bound application reads."""

    def __init__(
        self,
        *,
        ownid_issuer: str,
        identities: IdentitySubjectReadService,
        memberships: TenantContextResolver,
        reads: ActorOwnedReadService,
        entitlements: EntitlementResolver,
        audit: MCPAuditSink,
        clock: Callable[[], datetime],
    ) -> None:
        self._ownid_issuer = ownid_issuer.rstrip("/")
        self._identities = identities
        self._memberships = memberships
        self._reads = reads
        self._entitlements = entitlements
        self._audit = audit
        self._clock = clock

    async def get_student_schedule(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[ScheduleItem]:
        """Return the actor's ownership-filtered official schedule."""

        return await self._execute(
            tool="get_own_schedule",
            ownid_subject=ownid_subject,
            organization_id=organization_id,
            operation=lambda actor: self._reads.student_schedule(actor=actor),
        )

    async def get_student_grades(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[GradeSummary]:
        """Return the actor's current official grades."""

        return await self._execute(
            tool="get_own_official_grades",
            ownid_subject=ownid_subject,
            organization_id=organization_id,
            operation=lambda actor: self._reads.student_grades(actor=actor),
        )

    async def get_student_gpa(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> GpaSummary:
        """Return the actor's official cumulative GPA."""

        return await self._execute(
            tool="get_own_gpa_summary",
            ownid_subject=ownid_subject,
            organization_id=organization_id,
            operation=lambda actor: self._reads.student_gpa(actor=actor),
        )

    async def get_student_events(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[UpcomingEvent]:
        """Return the actor's bounded upcoming academic calendar."""

        return await self._execute(
            tool="get_own_upcoming_events",
            ownid_subject=ownid_subject,
            organization_id=organization_id,
            operation=lambda actor: self._reads.student_events(actor=actor),
        )

    async def get_student_moodle_deadlines(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[MoodleDeadline]:
        """Return Moodle deadline evidence for the actor's mapped person."""

        return await self._execute(
            tool="get_own_moodle_deadlines",
            ownid_subject=ownid_subject,
            organization_id=organization_id,
            operation=lambda actor: self._reads.student_moodle_deadlines(actor=actor),
        )

    async def get_teacher_sections(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[AssignedSection]:
        """Return sections assigned to the actor's teacher profile."""

        return await self._execute(
            tool="get_assigned_sections",
            ownid_subject=ownid_subject,
            organization_id=organization_id,
            operation=lambda actor: self._reads.teacher_sections(actor=actor),
        )

    async def get_section_students(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
        section_id: UUID,
    ) -> list[SectionStudent]:
        """Return a minimum roster only for an assigned section."""

        return await self._execute(
            tool="get_section_student_list",
            ownid_subject=ownid_subject,
            organization_id=organization_id,
            operation=lambda actor: self._reads.section_students(
                actor=actor,
                section_id=section_id,
            ),
        )

    async def get_grade_sync_status(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[GradeSyncSummary]:
        """Return grade evidence status only for assigned sections."""

        return await self._execute(
            tool="get_grade_synchronization_status",
            ownid_subject=ownid_subject,
            organization_id=organization_id,
            operation=lambda actor: self._reads.teacher_grade_sync_status(actor=actor),
        )

    async def get_guardian_students(
        self,
        *,
        ownid_subject: str,
        organization_id: UUID,
    ) -> list[GuardianStudentSummary]:
        """Return summaries only for explicitly linked guardian students."""

        return await self._execute(
            tool="get_linked_student_summaries",
            ownid_subject=ownid_subject,
            organization_id=organization_id,
            operation=lambda actor: self._reads.guardian_students(actor=actor),
        )

    async def _execute(
        self,
        *,
        tool: str,
        ownid_subject: str,
        organization_id: UUID,
        operation: Callable[[TenantActorContext], Awaitable[ResultT]],
    ) -> ResultT:
        """Revalidate identity, tenant membership, entitlement, and invocation."""

        correlation_id = f"mcp-{new_uuid7()}"
        actor_subject_id: UUID | None = None
        try:
            identity = await self._identities.resolve_verified_subject(
                issuer=self._ownid_issuer,
                subject=ownid_subject,
            )
            actor_subject_id = identity.id
            actor = await self._memberships.resolve_tenant_context(
                identity_subject_id=identity.id,
                organization_id=organization_id,
                correlation_id=correlation_id,
            )
            entitlement = await self._entitlements.resolve_for_organization(
                organization_id=organization_id,
                feature=FeatureCode.MCP,
                at=self._clock(),
            )
            if not entitlement.enabled:
                raise AuthorizationError("MCP is not enabled for this organization")
            result = await operation(actor)
        except (AuthenticationError, AuthorizationError, NotFoundError) as exc:
            await self._record_invocation(
                tool=tool,
                organization_id=organization_id,
                actor_subject_id=actor_subject_id,
                correlation_id=correlation_id,
                outcome="denied",
            )
            raise AuthorizationError("MCP invocation is not authorized") from exc
        except AppError:
            await self._record_invocation(
                tool=tool,
                organization_id=organization_id,
                actor_subject_id=actor_subject_id,
                correlation_id=correlation_id,
                outcome="failed",
            )
            raise
        except Exception:
            await self._record_invocation(
                tool=tool,
                organization_id=organization_id,
                actor_subject_id=actor_subject_id,
                correlation_id=correlation_id,
                outcome="failed",
            )
            raise
        await self._record_invocation(
            tool=tool,
            organization_id=organization_id,
            actor_subject_id=actor_subject_id,
            correlation_id=correlation_id,
            outcome="succeeded",
        )
        return result

    async def _record_invocation(
        self,
        *,
        tool: str,
        organization_id: UUID,
        actor_subject_id: UUID | None,
        correlation_id: str,
        outcome: str,
    ) -> None:
        """Append one mandatory privacy-minimized invocation record."""

        await self._audit.record_mcp_invocation(
            tool=tool,
            organization_id=organization_id,
            actor_subject_id=actor_subject_id,
            correlation_id=correlation_id,
            outcome=outcome,
        )


__all__ = ["ApplicationAuthorizedReadGateway"]
