"""Teacher-availability administration and constraint-query capabilities."""

from datetime import datetime
from datetime import timedelta
from uuid import UUID

from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import NotFoundError
from scheduling.application.ports import SchedulingAuditSink
from scheduling.application.ports import TeacherAvailabilityRepository
from scheduling.application.ports import TeacherReferenceDirectory
from scheduling.application.service import SCHEDULING_READ
from scheduling.application.service import SCHEDULING_SESSION_MANAGE
from scheduling.domain.exceptions import SchedulingRuleError
from scheduling.domain.models import MAX_TEACHER_AVAILABILITY_SPAN
from scheduling.domain.models import TeacherAvailability
from scheduling.domain.models import TeacherAvailabilityWindow
from scheduling.domain.models import TimeWindow

MAX_TEACHER_AVAILABILITY_PAGE_SIZE = 200


class TeacherAvailabilityService:
    """Manage tenant windows and expose complete constraint facts."""

    def __init__(
        self,
        repository: TeacherAvailabilityRepository,
        teachers: TeacherReferenceDirectory,
        audit: SchedulingAuditSink,
    ) -> None:
        self._repository = repository
        self._teachers = teachers
        self._audit = audit

    async def create_window(
        self,
        *,
        context: TenantActorContext,
        window: TeacherAvailabilityWindow,
    ) -> TeacherAvailabilityWindow:
        """Create one tenant-owned teacher availability window."""

        _authorize(context, SCHEDULING_SESSION_MANAGE)
        if context.organization_id != window.organization_id:
            raise NotFoundError("Teacher availability window was not found.")
        existing_teacher_ids = await self._teachers.existing_teacher_profile_ids(
            organization_id=context.organization_id,
            teacher_profile_ids=frozenset({window.teacher_id}),
        )
        if window.teacher_id not in existing_teacher_ids:
            raise NotFoundError("Teacher profile was not found.")
        await self._record_mutation_event(
            context=context,
            action="scheduling.teacher_availability.create.intent",
            target_id=window.id,
            outcome="intent_recorded",
        )
        await self._repository.create_window(window)
        await self._record_mutation_event(
            context=context,
            action="scheduling.teacher_availability.create.succeeded",
            target_id=window.id,
            outcome="succeeded",
        )
        return window

    async def delete_window(
        self,
        *,
        context: TenantActorContext,
        window_id: UUID,
    ) -> None:
        """Delete one exact tenant-owned availability window."""

        _authorize(context, SCHEDULING_SESSION_MANAGE)
        await self._record_mutation_event(
            context=context,
            action="scheduling.teacher_availability.delete.intent",
            target_id=window_id,
            outcome="intent_recorded",
        )
        deleted = await self._repository.delete_window(
            organization_id=context.organization_id,
            window_id=window_id,
        )
        if not deleted:
            raise NotFoundError("Teacher availability window was not found.")
        await self._record_mutation_event(
            context=context,
            action="scheduling.teacher_availability.delete.succeeded",
            target_id=window_id,
            outcome="succeeded",
        )

    async def list_windows(
        self,
        *,
        context: TenantActorContext,
        teacher_id: UUID | None,
        starts_at: datetime,
        ends_at: datetime,
        limit: int,
        offset: int,
    ) -> tuple[TeacherAvailabilityWindow, ...]:
        """List a stable bounded tenant page for administration."""

        _authorize(context, SCHEDULING_READ)
        _validate_query(
            starts_at=starts_at,
            ends_at=ends_at,
            limit=limit,
            offset=offset,
            require_utc=True,
        )
        return await self._repository.list_windows_page(
            organization_id=context.organization_id,
            teacher_id=teacher_id,
            starts_at=starts_at,
            ends_at=ends_at,
            limit=limit,
            offset=offset,
        )

    async def availability_for_constraints(
        self,
        *,
        organization_id: UUID,
        teacher_ids: frozenset[UUID],
        starts_at: datetime,
        ends_at: datetime,
    ) -> tuple[TeacherAvailability, ...]:
        """Return merged windows and explicit empty entries for unknown teachers."""

        _validate_query(
            starts_at=starts_at,
            ends_at=ends_at,
            limit=1,
            offset=0,
            require_utc=False,
        )
        existing_teacher_ids = await self._teachers.existing_teacher_profile_ids(
            organization_id=organization_id,
            teacher_profile_ids=teacher_ids,
        )
        windows = await self._repository.list_constraint_windows(
            organization_id=organization_id,
            teacher_ids=existing_teacher_ids,
            starts_at=starts_at,
            ends_at=ends_at,
        )
        return tuple(
            TeacherAvailability(
                organization_id=organization_id,
                teacher_id=teacher_id,
                windows=_merge_windows(
                    tuple(
                        window.as_time_window()
                        for window in windows
                        if teacher_id in existing_teacher_ids
                        and window.teacher_id == teacher_id
                    )
                ),
            )
            for teacher_id in sorted(teacher_ids, key=str)
        )

    async def _record_mutation_event(
        self,
        *,
        context: TenantActorContext,
        action: str,
        target_id: UUID,
        outcome: str,
    ) -> None:
        """Append ordered availability mutation evidence through the audit port."""

        await self._audit.record_scheduling_event(
            action=action,
            organization_id=context.organization_id,
            actor_subject_id=context.subject_id,
            target_id=target_id,
            correlation_id=context.correlation_id,
            outcome=outcome,
        )


def _merge_windows(windows: tuple[TimeWindow, ...]) -> tuple[TimeWindow, ...]:
    """Merge overlapping or adjacent intervals into their effective union."""

    merged: list[TimeWindow] = []
    for window in sorted(windows, key=lambda value: (value.starts_at, value.ends_at)):
        if not merged or window.starts_at > merged[-1].ends_at:
            merged.append(window)
            continue
        previous = merged[-1]
        merged[-1] = TimeWindow(
            starts_at=previous.starts_at,
            ends_at=max(previous.ends_at, window.ends_at),
        )
    return tuple(merged)


def _validate_query(
    *,
    starts_at: datetime,
    ends_at: datetime,
    limit: int,
    offset: int,
    require_utc: bool,
) -> None:
    """Require a bounded aware interval and valid stable page."""

    if starts_at.tzinfo is None or starts_at.utcoffset() is None:
        raise SchedulingRuleError(
            "Teacher-availability query start must be timezone-aware."
        )
    if ends_at.tzinfo is None or ends_at.utcoffset() is None:
        raise SchedulingRuleError(
            "Teacher-availability query end must be timezone-aware."
        )
    if require_utc and (
        starts_at.utcoffset() != timedelta(0) or ends_at.utcoffset() != timedelta(0)
    ):
        raise SchedulingRuleError("Teacher-availability query must use UTC.")
    if starts_at >= ends_at or ends_at - starts_at > MAX_TEACHER_AVAILABILITY_SPAN:
        raise SchedulingRuleError(
            "Teacher-availability query must increase and cannot exceed 370 days."
        )
    if limit < 1 or limit > MAX_TEACHER_AVAILABILITY_PAGE_SIZE or offset < 0:
        raise SchedulingRuleError(
            "Teacher-availability page limit must be 1-200 and "
            "offset cannot be negative."
        )


def _authorize(context: TenantActorContext, permission: str) -> None:
    """Fail closed unless the actor has one existing scheduling permission."""

    if permission not in context.permissions:
        raise AuthorizationError("Required scheduling permission is missing.")


__all__ = [
    "MAX_TEACHER_AVAILABILITY_PAGE_SIZE",
    "TeacherAvailabilityService",
]
