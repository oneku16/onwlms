"""Ownership-filtered timetable query service."""

from uuid import UUID

from core.context import TenantActorContext
from core.errors import AuthorizationError
from scheduling.application.ports import SchedulingRepository
from scheduling.domain.models import ScheduledSession

STUDENT_SCHEDULE_READ = "scheduling.student.read_own"
TEACHER_SCHEDULE_READ = "scheduling.teacher.read_own"


class OwnedTimetableReadService:
    """Filter timetable sessions by already authorized academic ownership facts."""

    def __init__(
        self,
        repository: SchedulingRepository,
    ) -> None:
        self._repository = repository

    async def student_schedule(
        self,
        *,
        actor: TenantActorContext,
        course_offering_ids: frozenset[UUID],
    ) -> tuple[ScheduledSession, ...]:
        """Return only sessions for the student's official active offerings."""

        if (
            not isinstance(actor, TenantActorContext)
            or STUDENT_SCHEDULE_READ not in actor.permissions
        ):
            raise AuthorizationError
        if not course_offering_ids:
            return ()
        sessions = await self._repository.list_sessions(
            organization_id=actor.organization_id,
        )
        return tuple(
            session
            for session in sessions
            if session.course_offering_id in course_offering_ids
        )

    async def teacher_schedule(
        self,
        *,
        actor: TenantActorContext,
        teacher_profile_id: UUID,
    ) -> tuple[ScheduledSession, ...]:
        """Return only sessions explicitly assigned to the teacher profile."""

        if (
            not isinstance(actor, TenantActorContext)
            or TEACHER_SCHEDULE_READ not in actor.permissions
        ):
            raise AuthorizationError
        sessions = await self._repository.list_sessions(
            organization_id=actor.organization_id,
        )
        return tuple(
            session for session in sessions if teacher_profile_id in session.teacher_ids
        )


__all__ = [
    "STUDENT_SCHEDULE_READ",
    "TEACHER_SCHEDULE_READ",
    "OwnedTimetableReadService",
]
