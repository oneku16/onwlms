from dataclasses import dataclass
from dataclasses import replace
from datetime import UTC
from datetime import datetime
from datetime import time
from datetime import timedelta
from decimal import Decimal
from uuid import UUID
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute

from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import NotFoundError
from scheduling.application.contracts import ExistingSchedulingReferences
from scheduling.application.generator import DeterministicHeuristicSchedulingGenerator
from scheduling.application.service import SCHEDULING_APPLY_GENERATION
from scheduling.application.service import SCHEDULING_GENERATE
from scheduling.application.service import SCHEDULING_READ
from scheduling.application.service import SCHEDULING_SESSION_MANAGE
from scheduling.application.service import TimetableService
from scheduling.domain.constraints import detect_hard_conflicts
from scheduling.domain.exceptions import ScheduleVersionConflictError
from scheduling.domain.exceptions import SchedulingConflictError
from scheduling.domain.models import ActivityRequest
from scheduling.domain.models import CandidateSlot
from scheduling.domain.models import ConstraintContext
from scheduling.domain.models import DailyWindow
from scheduling.domain.models import HardConstraintCode
from scheduling.domain.models import RecurrenceRule
from scheduling.domain.models import RoomSpecification
from scheduling.domain.models import ScheduledSession
from scheduling.domain.models import ScheduleGenerationRequest
from scheduling.domain.models import ScheduleGenerationResult
from scheduling.domain.models import SchedulingPolicy
from scheduling.domain.models import TeacherAvailability
from scheduling.domain.models import TimeWindow
from scheduling.infrastructure.repository import InMemorySchedulingAuditSink
from scheduling.infrastructure.repository import InMemorySchedulingRepository
from scheduling.infrastructure.repository import InMemorySchedulingResourceDirectory
from scheduling.presentation.router import SessionMoveBody
from scheduling.presentation.router import router


@dataclass(frozen=True, slots=True)
class StaticTimetableGenerationEntitlement:
    """Return one explicit entitlement decision to scheduling tests."""

    enabled: bool

    async def is_timetable_generation_enabled(
        self,
        *,
        organization_id: UUID,
    ) -> bool:
        """Return the configured decision without tenant-specific fixtures."""

        del organization_id
        return self.enabled


class RecordingSchedulingResourceDirectory:
    """Record requested horizons while returning a complete test context."""

    def __init__(self, context: ConstraintContext) -> None:
        self._context = context
        self.requests: list[tuple[UUID, datetime, datetime, frozenset[UUID]]] = []

    async def constraint_context(
        self,
        *,
        organization_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        teacher_ids: frozenset[UUID],
    ) -> ConstraintContext:
        self.requests.append((organization_id, starts_at, ends_at, teacher_ids))
        return self._context


class EchoSchedulingReferenceDirectory:
    """Treat every requested identifier as an exact known test reference."""

    async def existing_references(
        self,
        *,
        organization_id: UUID,
        room_ids: frozenset[UUID],
        course_offering_ids: frozenset[UUID],
        group_ids: frozenset[UUID],
        teacher_ids: frozenset[UUID],
    ) -> ExistingSchedulingReferences:
        return ExistingSchedulingReferences(
            organization_id=organization_id,
            room_ids=room_ids,
            course_offering_ids=course_offering_ids,
            group_ids=group_ids,
            teacher_ids=teacher_ids,
        )


def _context(
    *,
    organization_id: UUID,
    permissions: frozenset[str],
) -> TenantActorContext:
    return TenantActorContext(
        subject_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        correlation_id="scheduling-test",
        permissions=permissions,
    )


def _session(
    *,
    organization_id: UUID,
    room_id: UUID,
    teacher_id: UUID,
    group_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
    expected_attendance: int = 20,
    required_room_type: str = "lecture",
    locked: bool = False,
) -> ScheduledSession:
    return ScheduledSession(
        id=uuid4(),
        organization_id=organization_id,
        activity_id=uuid4(),
        course_offering_id=uuid4(),
        room_id=room_id,
        teacher_ids=(teacher_id,),
        group_ids=(group_id,),
        required_group_ids=(group_id,),
        starts_at=starts_at,
        ends_at=ends_at,
        activity_type="lecture",
        required_room_type=required_room_type,
        expected_attendance=expected_attendance,
        locked=locked,
    )


def _constraint_context(
    *,
    organization_id: UUID,
    room_id: UUID,
    teacher_ids: tuple[UUID, ...],
    calendar_start: datetime,
    calendar_end: datetime,
) -> ConstraintContext:
    availability = tuple(
        TeacherAvailability(
            organization_id=organization_id,
            teacher_id=teacher_id,
            windows=(TimeWindow(calendar_start, calendar_end),),
        )
        for teacher_id in teacher_ids
    )
    return ConstraintContext(
        organization_id=organization_id,
        rooms=(
            RoomSpecification(
                organization_id=organization_id,
                room_id=room_id,
                room_type="lecture",
                capacity=30,
            ),
        ),
        teacher_availability=availability,
        academic_calendar_windows=(TimeWindow(calendar_start, calendar_end),),
    )


def _policy() -> SchedulingPolicy:
    return SchedulingPolicy(
        maximum_consecutive_sessions=3,
        consecutive_break_threshold=timedelta(minutes=15),
        preferred_gap_limit=timedelta(hours=2),
        preferred_hours=(DailyWindow(1, time(8), time(17)),),
        penalty_per_violation=Decimal(5),
    )


def test_immediate_detector_reports_every_relevant_hard_constraint() -> None:
    organization_id = uuid4()
    room_id = uuid4()
    teacher_id = uuid4()
    group_id = uuid4()
    start = datetime(2026, 8, 10, 19, tzinfo=UTC)
    existing = _session(
        organization_id=organization_id,
        room_id=room_id,
        teacher_id=teacher_id,
        group_id=group_id,
        starts_at=start,
        ends_at=start + timedelta(hours=1),
    )
    candidate = _session(
        organization_id=organization_id,
        room_id=room_id,
        teacher_id=teacher_id,
        group_id=group_id,
        starts_at=start + timedelta(minutes=15),
        ends_at=start + timedelta(hours=1, minutes=15),
        expected_attendance=40,
        required_room_type="laboratory",
    )
    constraints = _constraint_context(
        organization_id=organization_id,
        room_id=room_id,
        teacher_ids=(teacher_id,),
        calendar_start=datetime(2026, 8, 10, 8, tzinfo=UTC),
        calendar_end=datetime(2026, 8, 10, 18, tzinfo=UTC),
    )

    conflicts = detect_hard_conflicts(
        candidate=candidate,
        existing_sessions=(existing,),
        context=constraints,
    )
    codes = {conflict.code for conflict in conflicts}

    assert HardConstraintCode.ROOM_CAPACITY in codes
    assert HardConstraintCode.ROOM_TYPE in codes
    assert HardConstraintCode.ACADEMIC_CALENDAR in codes
    assert HardConstraintCode.TEACHER_UNAVAILABLE in codes
    assert HardConstraintCode.ROOM_OVERLAP in codes
    assert HardConstraintCode.TEACHER_OVERLAP in codes
    assert HardConstraintCode.REQUIRED_GROUP_OVERLAP in codes


async def test_manual_session_creation_detects_conflicts_immediately() -> None:
    organization_id = uuid4()
    room_id = uuid4()
    teacher_id = uuid4()
    group_id = uuid4()
    day_start = datetime(2026, 8, 10, 8, tzinfo=UTC)
    constraints = _constraint_context(
        organization_id=organization_id,
        room_id=room_id,
        teacher_ids=(teacher_id,),
        calendar_start=day_start,
        calendar_end=day_start + timedelta(hours=10),
    )
    service = TimetableService(
        repository=InMemorySchedulingRepository(),
        resources=InMemorySchedulingResourceDirectory((constraints,)),
        references=EchoSchedulingReferenceDirectory(),
        audit=InMemorySchedulingAuditSink(),
        generator=DeterministicHeuristicSchedulingGenerator(),
    )
    actor = _context(
        organization_id=organization_id,
        permissions=frozenset({SCHEDULING_SESSION_MANAGE}),
    )
    first = _session(
        organization_id=organization_id,
        room_id=room_id,
        teacher_id=teacher_id,
        group_id=group_id,
        starts_at=day_start + timedelta(hours=1),
        ends_at=day_start + timedelta(hours=2),
    )
    overlapping = _session(
        organization_id=organization_id,
        room_id=room_id,
        teacher_id=teacher_id,
        group_id=group_id,
        starts_at=day_start + timedelta(hours=1, minutes=30),
        ends_at=day_start + timedelta(hours=2, minutes=30),
    )

    await service.create_session(context=actor, session=first)
    with pytest.raises(SchedulingConflictError, match="overlap"):
        await service.create_session(context=actor, session=overlapping)


async def test_recurring_create_loads_constraints_through_final_occurrence_end() -> (
    None
):
    organization_id = uuid4()
    room_id = uuid4()
    teacher_id = uuid4()
    group_id = uuid4()
    starts_at = datetime(2026, 8, 10, 9, tzinfo=UTC)
    last_occurrence_start = starts_at + timedelta(weeks=2)
    session = replace(
        _session(
            organization_id=organization_id,
            room_id=room_id,
            teacher_id=teacher_id,
            group_id=group_id,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
        ),
        recurrence=RecurrenceRule(
            interval_weeks=1,
            until=last_occurrence_start,
        ),
    )
    resources = RecordingSchedulingResourceDirectory(
        _constraint_context(
            organization_id=organization_id,
            room_id=room_id,
            teacher_ids=(teacher_id,),
            calendar_start=starts_at,
            calendar_end=last_occurrence_start + timedelta(hours=1),
        )
    )
    service = TimetableService(
        repository=InMemorySchedulingRepository(),
        resources=resources,
        references=EchoSchedulingReferenceDirectory(),
        audit=InMemorySchedulingAuditSink(),
        generator=DeterministicHeuristicSchedulingGenerator(),
    )

    await service.create_session(
        context=_context(
            organization_id=organization_id,
            permissions=frozenset({SCHEDULING_SESSION_MANAGE}),
        ),
        session=session,
    )

    assert resources.requests == [
        (
            organization_id,
            starts_at,
            last_occurrence_start + timedelta(hours=1),
            frozenset({teacher_id}),
        )
    ]


async def test_recurring_apply_loads_constraints_through_final_occurrence_end() -> None:
    organization_id = uuid4()
    room_id = uuid4()
    teacher_id = uuid4()
    group_id = uuid4()
    starts_at = datetime(2026, 8, 10, 9, tzinfo=UTC)
    last_occurrence_start = starts_at + timedelta(weeks=3)
    proposed = replace(
        _session(
            organization_id=organization_id,
            room_id=room_id,
            teacher_id=teacher_id,
            group_id=group_id,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=90),
        ),
        recurrence=RecurrenceRule(
            interval_weeks=1,
            until=last_occurrence_start,
        ),
    )
    resources = RecordingSchedulingResourceDirectory(
        _constraint_context(
            organization_id=organization_id,
            room_id=room_id,
            teacher_ids=(teacher_id,),
            calendar_start=starts_at,
            calendar_end=last_occurrence_start + timedelta(minutes=90),
        )
    )
    service = TimetableService(
        repository=InMemorySchedulingRepository(),
        resources=resources,
        references=EchoSchedulingReferenceDirectory(),
        audit=InMemorySchedulingAuditSink(),
        generator=DeterministicHeuristicSchedulingGenerator(),
        entitlements=StaticTimetableGenerationEntitlement(enabled=True),
    )

    await service.apply_proposal(
        context=_context(
            organization_id=organization_id,
            permissions=frozenset({SCHEDULING_APPLY_GENERATION}),
        ),
        proposed_sessions=(proposed,),
        locked_session_ids=frozenset(),
        expected_versions={},
    )

    assert resources.requests == [
        (
            organization_id,
            starts_at,
            last_occurrence_start + timedelta(minutes=90),
            frozenset({teacher_id}),
        )
    ]


async def test_generated_replacement_derives_persisted_locks_without_client_ids() -> (
    None
):
    organization_id = uuid4()
    starts_at = datetime(2026, 8, 10, 9, tzinfo=UTC)
    persisted_locked = _session(
        organization_id=organization_id,
        room_id=uuid4(),
        teacher_id=uuid4(),
        group_id=uuid4(),
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        locked=True,
    )
    repository = InMemorySchedulingRepository()
    await repository.save_session(session=persisted_locked, expected_version=None)

    with pytest.raises(ScheduleVersionConflictError, match="changed a locked"):
        await repository.replace_generated_schedule(
            organization_id=organization_id,
            proposed_sessions=(),
            locked_session_ids=frozenset(),
            expected_versions={persisted_locked.id: persisted_locked.version},
            constraints=ConstraintContext(
                organization_id=organization_id,
                rooms=(),
                teacher_availability=(),
                academic_calendar_windows=(),
            ),
        )

    assert (
        await repository.get_session(
            organization_id=organization_id,
            session_id=persisted_locked.id,
        )
        == persisted_locked
    )


async def test_generated_replacement_assigns_server_versions() -> None:
    organization_id = uuid4()
    room_id = uuid4()
    first_teacher_id = uuid4()
    second_teacher_id = uuid4()
    first_group_id = uuid4()
    second_group_id = uuid4()
    starts_at = datetime(2026, 8, 10, 9, tzinfo=UTC)
    current = _session(
        organization_id=organization_id,
        room_id=room_id,
        teacher_id=first_teacher_id,
        group_id=first_group_id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
    )
    proposed_existing = replace(
        current,
        teacher_ids=(second_teacher_id,),
        group_ids=(second_group_id,),
        required_group_ids=(second_group_id,),
        starts_at=starts_at + timedelta(hours=1),
        ends_at=starts_at + timedelta(hours=2),
    )
    repository = InMemorySchedulingRepository()
    await repository.save_session(session=current, expected_version=None)
    constraints = _constraint_context(
        organization_id=organization_id,
        room_id=room_id,
        teacher_ids=(second_teacher_id,),
        calendar_start=starts_at,
        calendar_end=starts_at + timedelta(hours=4),
    )
    service = TimetableService(
        repository=repository,
        resources=InMemorySchedulingResourceDirectory((constraints,)),
        references=EchoSchedulingReferenceDirectory(),
        audit=InMemorySchedulingAuditSink(),
        generator=DeterministicHeuristicSchedulingGenerator(),
        entitlements=StaticTimetableGenerationEntitlement(enabled=True),
    )

    with pytest.raises(ScheduleVersionConflictError, match="changed a locked"):
        await repository.replace_generated_schedule(
            organization_id=organization_id,
            proposed_sessions=(proposed_existing,),
            locked_session_ids=frozenset({current.id}),
            expected_versions={current.id: 0},
            constraints=constraints,
        )

    with pytest.raises(ScheduleVersionConflictError, match="invalid session version"):
        await repository.replace_generated_schedule(
            organization_id=organization_id,
            proposed_sessions=(replace(proposed_existing, version=1),),
            locked_session_ids=frozenset(),
            expected_versions={current.id: 0},
            constraints=constraints,
        )

    first_replacement = await service.apply_proposal(
        context=_context(
            organization_id=organization_id,
            permissions=frozenset({SCHEDULING_APPLY_GENERATION}),
        ),
        proposed_sessions=(proposed_existing,),
        locked_session_ids=frozenset(),
        expected_versions={current.id: 0},
    )
    second_replacement = await repository.replace_generated_schedule(
        organization_id=organization_id,
        proposed_sessions=first_replacement,
        locked_session_ids=frozenset(),
        expected_versions={current.id: 1},
        constraints=constraints,
    )

    assert first_replacement == (replace(proposed_existing, version=1),)
    assert second_replacement == (replace(proposed_existing, version=2),)
    assert (
        await repository.get_session(
            organization_id=organization_id,
            session_id=current.id,
        )
        == second_replacement[0]
    )

    malformed_new = replace(
        _session(
            organization_id=organization_id,
            room_id=room_id,
            teacher_id=second_teacher_id,
            group_id=second_group_id,
            starts_at=starts_at + timedelta(hours=2),
            ends_at=starts_at + timedelta(hours=3),
        ),
        version=1,
    )
    with pytest.raises(ScheduleVersionConflictError, match="version zero"):
        await repository.replace_generated_schedule(
            organization_id=organization_id,
            proposed_sessions=(second_replacement[0], malformed_new),
            locked_session_ids=frozenset(),
            expected_versions={current.id: 2},
            constraints=constraints,
        )


async def test_generator_is_deterministic_and_preserves_locked_sessions() -> None:
    organization_id = uuid4()
    room_id = uuid4()
    first_teacher = uuid4()
    second_teacher = uuid4()
    first_group = uuid4()
    second_group = uuid4()
    day_start = datetime(2026, 8, 10, 8, tzinfo=UTC)
    constraints = _constraint_context(
        organization_id=organization_id,
        room_id=room_id,
        teacher_ids=(first_teacher, second_teacher),
        calendar_start=day_start,
        calendar_end=day_start + timedelta(hours=10),
    )
    repository = InMemorySchedulingRepository()
    service = TimetableService(
        repository=repository,
        resources=InMemorySchedulingResourceDirectory((constraints,)),
        references=EchoSchedulingReferenceDirectory(),
        audit=InMemorySchedulingAuditSink(),
        generator=DeterministicHeuristicSchedulingGenerator(),
        entitlements=StaticTimetableGenerationEntitlement(enabled=True),
    )
    actor = _context(
        organization_id=organization_id,
        permissions=frozenset(
            {
                SCHEDULING_APPLY_GENERATION,
                SCHEDULING_GENERATE,
                SCHEDULING_READ,
                SCHEDULING_SESSION_MANAGE,
            }
        ),
    )
    locked = _session(
        organization_id=organization_id,
        room_id=room_id,
        teacher_id=first_teacher,
        group_id=first_group,
        starts_at=day_start + timedelta(hours=1),
        ends_at=day_start + timedelta(hours=2),
        locked=True,
    )
    await service.create_session(context=actor, session=locked)
    activity = ActivityRequest(
        id=uuid4(),
        organization_id=organization_id,
        course_offering_id=uuid4(),
        teacher_ids=(second_teacher,),
        group_ids=(second_group,),
        required_group_ids=(second_group,),
        activity_type="lecture",
        required_room_type="lecture",
        expected_attendance=20,
        duration=timedelta(hours=1),
        sessions_required=1,
    )
    slots = (
        CandidateSlot(
            id=uuid4(),
            organization_id=organization_id,
            starts_at=day_start + timedelta(hours=1),
            ends_at=day_start + timedelta(hours=2),
        ),
        CandidateSlot(
            id=uuid4(),
            organization_id=organization_id,
            starts_at=day_start + timedelta(hours=2),
            ends_at=day_start + timedelta(hours=3),
        ),
    )

    first = await service.generate(
        context=actor,
        activities=(activity,),
        candidate_slots=slots,
        locked_session_ids=frozenset({locked.id}),
        policy=_policy(),
    )
    second = await service.generate(
        context=actor,
        activities=(activity,),
        candidate_slots=slots,
        locked_session_ids=frozenset({locked.id}),
        policy=_policy(),
    )

    assert first == second
    assert first.proposed_sessions[0] == locked
    assert len(first.proposed_sessions) == 2
    assert first.proposed_sessions[1].starts_at == day_start + timedelta(hours=2)
    assert not first.unresolved_hard_conflicts
    assert dict(first.expected_versions) == {locked.id: locked.version}
    await service.apply_generation(context=actor, result=first)
    assert len(await service.list_sessions(context=actor)) == 2
    await service.set_session_lock(
        context=actor,
        session_id=locked.id,
        locked=False,
        expected_version=locked.version,
    )
    with pytest.raises(ScheduleVersionConflictError):
        await service.apply_generation(context=actor, result=first)


def test_generator_chooses_lowest_incremental_soft_penalty() -> None:
    organization_id = uuid4()
    room_id = uuid4()
    teacher_id = uuid4()
    group_id = uuid4()
    day_start = datetime(2026, 8, 10, 7, tzinfo=UTC)
    constraints = _constraint_context(
        organization_id=organization_id,
        room_id=room_id,
        teacher_ids=(teacher_id,),
        calendar_start=day_start,
        calendar_end=day_start + timedelta(hours=5),
    )
    activity = ActivityRequest(
        id=uuid4(),
        organization_id=organization_id,
        course_offering_id=uuid4(),
        teacher_ids=(teacher_id,),
        group_ids=(group_id,),
        required_group_ids=(group_id,),
        activity_type="lecture",
        required_room_type="lecture",
        expected_attendance=20,
        duration=timedelta(hours=1),
        sessions_required=1,
    )
    early = CandidateSlot(
        id=UUID(int=1),
        organization_id=organization_id,
        starts_at=day_start,
        ends_at=day_start + timedelta(hours=1),
    )
    preferred = CandidateSlot(
        id=UUID(int=2),
        organization_id=organization_id,
        starts_at=day_start + timedelta(hours=2),
        ends_at=day_start + timedelta(hours=3),
    )

    result = DeterministicHeuristicSchedulingGenerator().generate(
        ScheduleGenerationRequest(
            organization_id=organization_id,
            activities=(activity,),
            candidate_slots=(early, preferred),
            existing_sessions=(),
            locked_session_ids=frozenset(),
            constraints=constraints,
            policy=_policy(),
        )
    )

    assert result.proposed_sessions[0].starts_at == preferred.starts_at
    assert not result.soft_constraint_violations


def test_generator_orders_by_scarcity_with_stable_input_independent_results() -> None:
    organization_id = uuid4()
    large_room_id = UUID(int=1)
    small_room_id = UUID(int=2)
    flexible_teacher = uuid4()
    scarce_teacher = uuid4()
    flexible_group = uuid4()
    scarce_group = uuid4()
    starts_at = datetime(2026, 8, 10, 9, tzinfo=UTC)
    constraints = ConstraintContext(
        organization_id=organization_id,
        rooms=(
            RoomSpecification(
                organization_id=organization_id,
                room_id=large_room_id,
                room_type="lecture",
                capacity=40,
            ),
            RoomSpecification(
                organization_id=organization_id,
                room_id=small_room_id,
                room_type="lecture",
                capacity=10,
            ),
        ),
        teacher_availability=tuple(
            TeacherAvailability(
                organization_id=organization_id,
                teacher_id=teacher_id,
                windows=(TimeWindow(starts_at, starts_at + timedelta(hours=1)),),
            )
            for teacher_id in (flexible_teacher, scarce_teacher)
        ),
        academic_calendar_windows=(
            TimeWindow(starts_at, starts_at + timedelta(hours=1)),
        ),
    )

    def activity(
        *,
        identifier: UUID,
        teacher_id: UUID,
        group_id: UUID,
        attendance: int,
    ) -> ActivityRequest:
        return ActivityRequest(
            id=identifier,
            organization_id=organization_id,
            course_offering_id=uuid4(),
            teacher_ids=(teacher_id,),
            group_ids=(group_id,),
            required_group_ids=(group_id,),
            activity_type="lecture",
            required_room_type="lecture",
            expected_attendance=attendance,
            duration=timedelta(hours=1),
            sessions_required=1,
        )

    flexible = activity(
        identifier=UUID(int=1),
        teacher_id=flexible_teacher,
        group_id=flexible_group,
        attendance=10,
    )
    scarce = activity(
        identifier=UUID(int=2),
        teacher_id=scarce_teacher,
        group_id=scarce_group,
        attendance=30,
    )
    slot = CandidateSlot(
        id=uuid4(),
        organization_id=organization_id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
    )
    generator = DeterministicHeuristicSchedulingGenerator()

    def generate(
        activities: tuple[ActivityRequest, ...],
    ) -> ScheduleGenerationResult:
        return generator.generate(
            ScheduleGenerationRequest(
                organization_id=organization_id,
                activities=activities,
                candidate_slots=(slot,),
                existing_sessions=(),
                locked_session_ids=frozenset(),
                constraints=constraints,
                policy=_policy(),
            )
        )

    forward = generate((flexible, scarce))
    reverse = generate((scarce, flexible))
    rooms_by_activity = {
        session.activity_id: session.room_id for session in forward.proposed_sessions
    }

    assert forward == reverse
    assert rooms_by_activity == {
        flexible.id: small_room_id,
        scarce.id: large_room_id,
    }
    assert not forward.unresolved_hard_conflicts


async def test_generator_returns_unresolved_conflict_and_explained_score() -> None:
    organization_id = uuid4()
    room_id = uuid4()
    unavailable_teacher = uuid4()
    group_id = uuid4()
    day_start = datetime(2026, 8, 10, 8, tzinfo=UTC)
    constraints = _constraint_context(
        organization_id=organization_id,
        room_id=room_id,
        teacher_ids=(),
        calendar_start=day_start,
        calendar_end=day_start + timedelta(hours=10),
    )
    service = TimetableService(
        repository=InMemorySchedulingRepository(),
        resources=InMemorySchedulingResourceDirectory((constraints,)),
        references=EchoSchedulingReferenceDirectory(),
        audit=InMemorySchedulingAuditSink(),
        generator=DeterministicHeuristicSchedulingGenerator(),
        entitlements=StaticTimetableGenerationEntitlement(enabled=True),
    )
    actor = _context(
        organization_id=organization_id,
        permissions=frozenset({SCHEDULING_GENERATE}),
    )
    activity = ActivityRequest(
        id=uuid4(),
        organization_id=organization_id,
        course_offering_id=uuid4(),
        teacher_ids=(unavailable_teacher,),
        group_ids=(group_id,),
        required_group_ids=(group_id,),
        activity_type="lecture",
        required_room_type="lecture",
        expected_attendance=10,
        duration=timedelta(hours=1),
        sessions_required=1,
    )
    slot = CandidateSlot(
        id=uuid4(),
        organization_id=organization_id,
        starts_at=day_start + timedelta(hours=1),
        ends_at=day_start + timedelta(hours=2),
    )

    result = await service.generate(
        context=actor,
        activities=(activity,),
        candidate_slots=(slot,),
        locked_session_ids=frozenset(),
        policy=_policy(),
    )

    assert result.unresolved_hard_conflicts[0].code is (
        HardConstraintCode.UNSCHEDULED_ACTIVITY
    )
    assert "teacher_unavailable" in result.unresolved_hard_conflicts[0].explanation
    assert result.quality_score == Decimal(75)
    assert "hard conflicts remain" in result.explanation


async def test_generation_and_proposal_apply_fail_closed_without_entitlement() -> None:
    organization_id = uuid4()
    actor = _context(
        organization_id=organization_id,
        permissions=frozenset(
            {
                SCHEDULING_APPLY_GENERATION,
                SCHEDULING_GENERATE,
            }
        ),
    )
    service = TimetableService(
        repository=InMemorySchedulingRepository(),
        resources=InMemorySchedulingResourceDirectory(),
        references=EchoSchedulingReferenceDirectory(),
        audit=InMemorySchedulingAuditSink(),
        generator=DeterministicHeuristicSchedulingGenerator(),
    )

    with pytest.raises(AuthorizationError, match="not enabled"):
        await service.generate(
            context=actor,
            activities=(),
            candidate_slots=(),
            locked_session_ids=frozenset(),
            policy=_policy(),
        )
    with pytest.raises(AuthorizationError, match="not enabled"):
        await service.apply_proposal(
            context=actor,
            proposed_sessions=(),
            locked_session_ids=frozenset(),
            expected_versions={},
        )


async def test_manual_cross_tenant_resource_mismatch_fails_closed() -> None:
    organization_id = uuid4()
    other_organization_id = uuid4()
    room_id = uuid4()
    teacher_id = uuid4()
    group_id = uuid4()
    start = datetime(2026, 8, 10, 9, tzinfo=UTC)
    constraints = _constraint_context(
        organization_id=organization_id,
        room_id=room_id,
        teacher_ids=(teacher_id,),
        calendar_start=start - timedelta(hours=1),
        calendar_end=start + timedelta(hours=8),
    )
    service = TimetableService(
        repository=InMemorySchedulingRepository(),
        resources=InMemorySchedulingResourceDirectory((constraints,)),
        references=EchoSchedulingReferenceDirectory(),
        audit=InMemorySchedulingAuditSink(),
        generator=DeterministicHeuristicSchedulingGenerator(),
    )
    actor = _context(
        organization_id=organization_id,
        permissions=frozenset({SCHEDULING_SESSION_MANAGE}),
    )
    foreign_session = _session(
        organization_id=other_organization_id,
        room_id=room_id,
        teacher_id=teacher_id,
        group_id=group_id,
        starts_at=start,
        ends_at=start + timedelta(hours=1),
    )

    with pytest.raises(NotFoundError):
        await service.create_session(context=actor, session=foreign_session)


async def test_drag_drop_move_preserves_room_and_requires_current_version() -> None:
    organization_id = uuid4()
    room_id = uuid4()
    teacher_id = uuid4()
    group_id = uuid4()
    start = datetime(2026, 8, 10, 9, tzinfo=UTC)
    service = TimetableService(
        repository=InMemorySchedulingRepository(),
        resources=InMemorySchedulingResourceDirectory(
            (
                _constraint_context(
                    organization_id=organization_id,
                    room_id=room_id,
                    teacher_ids=(teacher_id,),
                    calendar_start=start - timedelta(hours=1),
                    calendar_end=start + timedelta(hours=8),
                ),
            )
        ),
        references=EchoSchedulingReferenceDirectory(),
        audit=InMemorySchedulingAuditSink(),
        generator=DeterministicHeuristicSchedulingGenerator(),
    )
    actor = _context(
        organization_id=organization_id,
        permissions=frozenset({SCHEDULING_SESSION_MANAGE}),
    )
    original = _session(
        organization_id=organization_id,
        room_id=room_id,
        teacher_id=teacher_id,
        group_id=group_id,
        starts_at=start,
        ends_at=start + timedelta(hours=1),
    )
    await service.create_session(context=actor, session=original)

    moved = await service.move_session(
        context=actor,
        session_id=original.id,
        starts_at=start + timedelta(hours=1),
        ends_at=start + timedelta(hours=2),
        expected_version=0,
    )

    assert moved.room_id == room_id
    assert moved.version == 1
    with pytest.raises(ScheduleVersionConflictError):
        await service.move_session(
            context=actor,
            session_id=original.id,
            starts_at=start + timedelta(hours=2),
            ends_at=start + timedelta(hours=3),
            expected_version=0,
        )


def test_scheduling_router_exposes_weekly_read_and_versioned_patch_contract() -> None:
    paths_and_methods = {
        (route.path, method)
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in (route.methods or set())
    }

    assert ("/api/v1/scheduling/sessions", "GET") in paths_and_methods
    assert ("/api/v1/scheduling/sessions/{session_id}", "PATCH") in (paths_and_methods)
    assert set(SessionMoveBody.model_fields) == {
        "starts_at",
        "ends_at",
        "version",
    }


async def test_resource_directory_declares_unknown_requested_teacher_unavailable() -> (
    None
):
    organization_id = uuid4()
    room_id = uuid4()
    known_teacher_id = uuid4()
    unknown_teacher_id = uuid4()
    starts_at = datetime(2026, 8, 10, 8, tzinfo=UTC)
    directory = InMemorySchedulingResourceDirectory(
        (
            _constraint_context(
                organization_id=organization_id,
                room_id=room_id,
                teacher_ids=(known_teacher_id,),
                calendar_start=starts_at,
                calendar_end=starts_at + timedelta(hours=10),
            ),
        )
    )

    context = await directory.constraint_context(
        organization_id=organization_id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=10),
        teacher_ids=frozenset({known_teacher_id, unknown_teacher_id}),
    )

    assert context.teacher_windows(known_teacher_id)
    assert context.teacher_windows(unknown_teacher_id) == ()
