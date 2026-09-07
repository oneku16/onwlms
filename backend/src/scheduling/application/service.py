"""Manual timetable and schedule-generation application services."""

from dataclasses import replace
from datetime import datetime
from datetime import timedelta
from uuid import UUID

from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import NotFoundError
from scheduling.application.contracts import ExistingSchedulingReferences
from scheduling.application.ports import SchedulingAuditSink
from scheduling.application.ports import SchedulingGenerator
from scheduling.application.ports import SchedulingReferenceDirectory
from scheduling.application.ports import SchedulingRepository
from scheduling.application.ports import SchedulingResourceDirectory
from scheduling.application.ports import TimetableGenerationEntitlement
from scheduling.domain.constraints import detect_hard_conflicts
from scheduling.domain.exceptions import ScheduleVersionConflictError
from scheduling.domain.exceptions import SchedulingConflictError
from scheduling.domain.exceptions import SchedulingRuleError
from scheduling.domain.models import ActivityRequest
from scheduling.domain.models import CandidateSlot
from scheduling.domain.models import ScheduledSession
from scheduling.domain.models import ScheduleGenerationRequest
from scheduling.domain.models import ScheduleGenerationResult
from scheduling.domain.models import SchedulingPolicy
from scheduling.domain.replacement import prepare_generated_replacement

SCHEDULING_SESSION_MANAGE = "scheduling.session.manage"
SCHEDULING_GENERATE = "scheduling.generate"
SCHEDULING_APPLY_GENERATION = "scheduling.generation.apply"
SCHEDULING_READ = "scheduling.read"
MAX_SCHEDULING_READ_HORIZON = timedelta(days=31)
MAX_SCHEDULING_READ_PAGE_SIZE = 200


class TimetableService:
    """Manage tenant timetable sessions and deterministic generation."""

    def __init__(
        self,
        *,
        repository: SchedulingRepository,
        resources: SchedulingResourceDirectory,
        references: SchedulingReferenceDirectory,
        audit: SchedulingAuditSink,
        generator: SchedulingGenerator,
        entitlements: TimetableGenerationEntitlement | None = None,
    ) -> None:
        self._repository = repository
        self._resources = resources
        self._references = references
        self._audit = audit
        self._generator = generator
        self._entitlements = entitlements or _DisabledTimetableGeneration()

    async def create_session(
        self,
        *,
        context: TenantActorContext,
        session: ScheduledSession,
    ) -> ScheduledSession:
        """Create a manual session after immediate hard-conflict detection."""

        _authorize(context, SCHEDULING_SESSION_MANAGE)
        _require_tenant(context, session.organization_id)
        await self._require_session_references(
            organization_id=context.organization_id,
            sessions=(session,),
        )
        existing = await self._repository.list_sessions(
            organization_id=context.organization_id
        )
        constraints = await self._resources.constraint_context(
            organization_id=context.organization_id,
            starts_at=session.starts_at,
            ends_at=_horizon_end(session),
            teacher_ids=frozenset(session.teacher_ids),
        )
        conflicts = detect_hard_conflicts(
            candidate=session,
            existing_sessions=existing,
            context=constraints,
        )
        if conflicts:
            codes = ", ".join(conflict.code for conflict in conflicts)
            raise SchedulingConflictError(f"Session conflicts with: {codes}.")
        await self._record_mutation_event(
            context=context,
            action="scheduling.session.create.intent",
            target_id=session.id,
            outcome="intent_recorded",
        )
        await self._repository.save_conflict_free_session(
            session=session,
            expected_version=None,
            constraints=constraints,
        )
        await self._record_mutation_event(
            context=context,
            action="scheduling.session.create.succeeded",
            target_id=session.id,
            outcome="succeeded",
        )
        return session

    async def move_session(
        self,
        *,
        context: TenantActorContext,
        session_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        expected_version: int,
    ) -> ScheduledSession:
        """Move a session using optimistic version and immediate conflict checks."""

        _authorize(context, SCHEDULING_SESSION_MANAGE)
        current = await self._repository.get_session(
            organization_id=context.organization_id,
            session_id=session_id,
        )
        if current is None:
            raise NotFoundError("Timetable session was not found.")
        if current.version != expected_version:
            raise ScheduleVersionConflictError(
                "Timetable session changed during the requested edit."
            )
        moved = replace(
            current,
            starts_at=starts_at,
            ends_at=ends_at,
            version=current.version + 1,
        )
        await self._require_session_references(
            organization_id=context.organization_id,
            sessions=(moved,),
        )
        existing = tuple(
            session
            for session in await self._repository.list_sessions(
                organization_id=context.organization_id
            )
            if session.id != current.id
        )
        constraints = await self._resources.constraint_context(
            organization_id=context.organization_id,
            starts_at=moved.starts_at,
            ends_at=_horizon_end(moved),
            teacher_ids=frozenset(moved.teacher_ids),
        )
        conflicts = detect_hard_conflicts(
            candidate=moved,
            existing_sessions=existing,
            context=constraints,
        )
        if conflicts:
            codes = ", ".join(conflict.code for conflict in conflicts)
            raise SchedulingConflictError(f"Session conflicts with: {codes}.")
        await self._record_mutation_event(
            context=context,
            action="scheduling.session.move.intent",
            target_id=moved.id,
            outcome="intent_recorded",
        )
        await self._repository.save_conflict_free_session(
            session=moved,
            expected_version=current.version,
            constraints=constraints,
        )
        await self._record_mutation_event(
            context=context,
            action="scheduling.session.move.succeeded",
            target_id=moved.id,
            outcome="succeeded",
        )
        return moved

    async def set_session_lock(
        self,
        *,
        context: TenantActorContext,
        session_id: UUID,
        locked: bool,
        expected_version: int | None = None,
    ) -> ScheduledSession:
        """Set whether generation must preserve one session unchanged."""

        _authorize(context, SCHEDULING_SESSION_MANAGE)
        current = await self._repository.get_session(
            organization_id=context.organization_id,
            session_id=session_id,
        )
        if current is None:
            raise NotFoundError("Timetable session was not found.")
        if expected_version is not None and current.version != expected_version:
            raise ScheduleVersionConflictError(
                "Timetable session changed during the requested edit."
            )
        updated = replace(
            current,
            locked=locked,
            version=current.version + 1,
        )
        await self._record_mutation_event(
            context=context,
            action="scheduling.session.lock.intent",
            target_id=updated.id,
            outcome="intent_recorded",
        )
        await self._repository.save_session(
            session=updated,
            expected_version=current.version,
        )
        await self._record_mutation_event(
            context=context,
            action="scheduling.session.lock.succeeded",
            target_id=updated.id,
            outcome="succeeded",
        )
        return updated

    async def generate(
        self,
        *,
        context: TenantActorContext,
        activities: tuple[ActivityRequest, ...],
        candidate_slots: tuple[CandidateSlot, ...],
        locked_session_ids: frozenset[UUID],
        policy: SchedulingPolicy,
    ) -> ScheduleGenerationResult:
        """Generate a deterministic proposal while preserving requested locks."""

        _authorize(context, SCHEDULING_GENERATE)
        await self._require_generation_entitlement(context)
        if not candidate_slots:
            raise SchedulingRuleError("Schedule generation requires candidate slots.")
        if any(
            activity.organization_id != context.organization_id
            for activity in activities
        ) or any(
            slot.organization_id != context.organization_id for slot in candidate_slots
        ):
            raise NotFoundError("Scheduling reference was not found.")
        await self._require_activity_references(
            organization_id=context.organization_id,
            activities=activities,
        )
        existing = await self._repository.list_sessions(
            organization_id=context.organization_id
        )
        starts_at = min(slot.starts_at for slot in candidate_slots)
        ends_at = max(slot.ends_at for slot in candidate_slots)
        constraints = await self._resources.constraint_context(
            organization_id=context.organization_id,
            starts_at=starts_at,
            ends_at=ends_at,
            teacher_ids=frozenset(
                {
                    teacher_id
                    for activity in activities
                    for teacher_id in activity.teacher_ids
                }
                | {
                    teacher_id
                    for session in existing
                    for teacher_id in session.teacher_ids
                }
            ),
        )
        request = ScheduleGenerationRequest(
            organization_id=context.organization_id,
            activities=activities,
            candidate_slots=candidate_slots,
            existing_sessions=existing,
            locked_session_ids=locked_session_ids,
            constraints=constraints,
            policy=policy,
        )
        return self._generator.generate(request)

    async def apply_generation(
        self,
        *,
        context: TenantActorContext,
        result: ScheduleGenerationResult,
    ) -> None:
        """Atomically apply a conflict-free proposal while preserving locks."""

        _authorize(context, SCHEDULING_APPLY_GENERATION)
        if result.unresolved_hard_conflicts:
            raise SchedulingConflictError(
                "A schedule with unresolved hard conflicts cannot be applied."
            )
        if any(
            session.organization_id != context.organization_id
            for session in result.proposed_sessions
        ):
            raise NotFoundError("Generated schedule was not found for this tenant.")
        await self.apply_proposal(
            context=context,
            proposed_sessions=result.proposed_sessions,
            locked_session_ids=result.locked_session_ids,
            expected_versions=dict(result.expected_versions),
        )

    async def apply_proposal(
        self,
        *,
        context: TenantActorContext,
        proposed_sessions: tuple[ScheduledSession, ...],
        locked_session_ids: frozenset[UUID],
        expected_versions: dict[UUID, int],
    ) -> tuple[ScheduledSession, ...]:
        """Revalidate and atomically apply a version-bound generated proposal."""

        _authorize(context, SCHEDULING_APPLY_GENERATION)
        await self._require_generation_entitlement(context)
        if not proposed_sessions:
            raise SchedulingRuleError("A generated proposal cannot be empty.")
        if any(
            session.organization_id != context.organization_id
            for session in proposed_sessions
        ):
            raise NotFoundError("Generated schedule was not found for this tenant.")
        if len({session.id for session in proposed_sessions}) != len(proposed_sessions):
            raise SchedulingRuleError("Generated proposal has duplicate sessions.")
        await self._require_session_references(
            organization_id=context.organization_id,
            sessions=proposed_sessions,
        )
        current = await self._repository.list_sessions(
            organization_id=context.organization_id
        )
        prepare_generated_replacement(
            organization_id=context.organization_id,
            current_sessions=current,
            proposed_sessions=proposed_sessions,
            asserted_locked_session_ids=locked_session_ids,
            expected_versions=expected_versions,
        )
        constraints = await self._resources.constraint_context(
            organization_id=context.organization_id,
            starts_at=min(session.starts_at for session in proposed_sessions),
            ends_at=max(_horizon_end(session) for session in proposed_sessions),
            teacher_ids=frozenset(
                teacher_id
                for session in proposed_sessions
                for teacher_id in session.teacher_ids
            ),
        )
        conflicts = tuple(
            conflict
            for candidate in proposed_sessions
            for conflict in detect_hard_conflicts(
                candidate=candidate,
                existing_sessions=proposed_sessions,
                context=constraints,
            )
        )
        if conflicts:
            codes = ", ".join(dict.fromkeys(conflict.code for conflict in conflicts))
            raise SchedulingConflictError(
                f"Generated proposal conflicts with: {codes}."
            )
        await self._record_mutation_event(
            context=context,
            action="scheduling.generation.apply.intent",
            target_id=context.organization_id,
            outcome="intent_recorded",
        )
        persisted = await self._repository.replace_generated_schedule(
            organization_id=context.organization_id,
            proposed_sessions=proposed_sessions,
            locked_session_ids=locked_session_ids,
            expected_versions=expected_versions,
            constraints=constraints,
        )
        await self._record_mutation_event(
            context=context,
            action="scheduling.generation.apply.succeeded",
            target_id=context.organization_id,
            outcome="succeeded",
        )
        return persisted

    async def _require_session_references(
        self,
        *,
        organization_id: UUID,
        sessions: tuple[ScheduledSession, ...],
    ) -> None:
        """Fail closed unless every external session reference exists in the tenant."""

        requested = ExistingSchedulingReferences(
            organization_id=organization_id,
            room_ids=frozenset(session.room_id for session in sessions),
            course_offering_ids=frozenset(
                session.course_offering_id for session in sessions
            ),
            group_ids=frozenset(
                group_id for session in sessions for group_id in session.group_ids
            ),
            teacher_ids=frozenset(
                teacher_id for session in sessions for teacher_id in session.teacher_ids
            ),
        )
        await self._require_exact_references(requested)

    async def _require_activity_references(
        self,
        *,
        organization_id: UUID,
        activities: tuple[ActivityRequest, ...],
    ) -> None:
        """Fail closed unless every external generation reference exists."""

        requested = ExistingSchedulingReferences(
            organization_id=organization_id,
            room_ids=frozenset(),
            course_offering_ids=frozenset(
                activity.course_offering_id for activity in activities
            ),
            group_ids=frozenset(
                group_id for activity in activities for group_id in activity.group_ids
            ),
            teacher_ids=frozenset(
                teacher_id
                for activity in activities
                for teacher_id in activity.teacher_ids
            ),
        )
        await self._require_exact_references(requested)

    async def _require_exact_references(
        self,
        requested: ExistingSchedulingReferences,
    ) -> None:
        """Compare exact matches without disclosing which tenant resource is absent."""

        existing = await self._references.existing_references(
            organization_id=requested.organization_id,
            room_ids=requested.room_ids,
            course_offering_ids=requested.course_offering_ids,
            group_ids=requested.group_ids,
            teacher_ids=requested.teacher_ids,
        )
        if existing != requested:
            raise NotFoundError("Scheduling reference was not found.")

    async def _record_mutation_event(
        self,
        *,
        context: TenantActorContext,
        action: str,
        target_id: UUID,
        outcome: str,
    ) -> None:
        """Append ordered mutation evidence through Scheduling's audit port."""

        await self._audit.record_scheduling_event(
            action=action,
            organization_id=context.organization_id,
            actor_subject_id=context.subject_id,
            target_id=target_id,
            correlation_id=context.correlation_id,
            outcome=outcome,
        )

    async def _require_generation_entitlement(
        self,
        context: TenantActorContext,
    ) -> None:
        """Fail closed when the tenant lacks timetable generation."""

        enabled = await self._entitlements.is_timetable_generation_enabled(
            organization_id=context.organization_id,
        )
        if not enabled:
            raise AuthorizationError(
                "Timetable generation is not enabled for this organization."
            )

    async def get_session(
        self,
        *,
        context: TenantActorContext,
        session_id: UUID,
    ) -> ScheduledSession:
        """Return one authorized tenant timetable session."""

        _authorize(context, SCHEDULING_READ)
        session = await self._repository.get_session(
            organization_id=context.organization_id,
            session_id=session_id,
        )
        if session is None:
            raise NotFoundError("Timetable session was not found.")
        return session

    async def list_sessions_window(
        self,
        *,
        context: TenantActorContext,
        starts_at: datetime,
        ends_at: datetime,
        limit: int,
        offset: int,
    ) -> tuple[ScheduledSession, ...]:
        """Return an authorized bounded page intersecting one time window."""

        _authorize(context, SCHEDULING_READ)
        _validate_read_window(
            starts_at=starts_at,
            ends_at=ends_at,
            limit=limit,
            offset=offset,
        )
        return await self._repository.list_sessions_window(
            organization_id=context.organization_id,
            starts_at=starts_at,
            ends_at=ends_at,
            limit=limit,
            offset=offset,
        )

    async def list_sessions(
        self,
        *,
        context: TenantActorContext,
    ) -> tuple[ScheduledSession, ...]:
        """Return tenant timetable sessions for authorized calendar views."""

        _authorize(context, SCHEDULING_READ)
        return await self._repository.list_sessions(
            organization_id=context.organization_id
        )


def _horizon_end(session: ScheduledSession) -> datetime:
    """Return the last relevant time for bounded recurrence validation."""

    if session.recurrence is None:
        return session.ends_at
    return session.recurrence.until + (session.ends_at - session.starts_at)


class _DisabledTimetableGeneration:
    """Keep direct construction fail-closed until an entitlement is composed."""

    async def is_timetable_generation_enabled(
        self,
        *,
        organization_id: UUID,
    ) -> bool:
        """Deny the optional generator capability by default."""

        del organization_id
        return False


def _validate_read_window(
    *,
    starts_at: datetime,
    ends_at: datetime,
    limit: int,
    offset: int,
) -> None:
    """Require a timezone-aware bounded scheduling query page."""

    if starts_at.tzinfo is None or starts_at.utcoffset() is None:
        raise SchedulingRuleError("Scheduling window start must be timezone-aware.")
    if ends_at.tzinfo is None or ends_at.utcoffset() is None:
        raise SchedulingRuleError("Scheduling window end must be timezone-aware.")
    if starts_at >= ends_at or ends_at - starts_at > MAX_SCHEDULING_READ_HORIZON:
        raise SchedulingRuleError(
            "Scheduling read window must increase and cannot exceed 31 days."
        )
    if limit < 1 or limit > MAX_SCHEDULING_READ_PAGE_SIZE or offset < 0:
        raise SchedulingRuleError(
            f"Scheduling page limit must be 1-{MAX_SCHEDULING_READ_PAGE_SIZE} "
            "and offset cannot be negative."
        )


def _authorize(
    context: TenantActorContext,
    permission: str,
) -> None:
    """Fail closed unless the trusted actor has a scheduling permission."""

    if permission not in context.permissions:
        raise AuthorizationError("Required scheduling permission is missing.")


def _require_tenant(
    context: TenantActorContext,
    resource_organization_id: UUID,
) -> None:
    """Reject resource ownership mismatch without revealing another tenant."""

    if context.organization_id != resource_organization_id:
        raise NotFoundError("Scheduling resource was not found.")


__all__ = [
    "MAX_SCHEDULING_READ_HORIZON",
    "MAX_SCHEDULING_READ_PAGE_SIZE",
    "SCHEDULING_APPLY_GENERATION",
    "SCHEDULING_GENERATE",
    "SCHEDULING_READ",
    "SCHEDULING_SESSION_MANAGE",
    "TimetableService",
]
