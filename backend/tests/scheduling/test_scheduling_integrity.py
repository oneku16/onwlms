"""Reference-integrity and mutation-audit tests for Scheduling."""

from dataclasses import dataclass
from dataclasses import replace
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from uuid import UUID
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport
from httpx import AsyncClient

from core.context import TenantActorContext
from core.errors import NotFoundError
from core.http import install_error_handlers
from identity.presentation.dependencies import require_actor
from identity.presentation.dependencies import require_csrf
from scheduling.application.contracts import ExistingSchedulingReferences
from scheduling.application.generator import DeterministicHeuristicSchedulingGenerator
from scheduling.application.service import SCHEDULING_GENERATE
from scheduling.application.service import SCHEDULING_SESSION_MANAGE
from scheduling.application.service import TimetableService
from scheduling.domain.exceptions import SchedulingConflictError
from scheduling.domain.models import ActivityRequest
from scheduling.domain.models import CandidateSlot
from scheduling.domain.models import ConstraintContext
from scheduling.domain.models import DailyWindow
from scheduling.domain.models import RoomSpecification
from scheduling.domain.models import ScheduledSession
from scheduling.domain.models import SchedulingPolicy
from scheduling.domain.models import TeacherAvailability
from scheduling.domain.models import TimeWindow
from scheduling.infrastructure.repository import InMemorySchedulingAuditSink
from scheduling.infrastructure.repository import InMemorySchedulingReferenceDirectory
from scheduling.infrastructure.repository import InMemorySchedulingRepository
from scheduling.infrastructure.repository import InMemorySchedulingResourceDirectory
from scheduling.presentation.router import router


@dataclass(frozen=True, slots=True)
class _SchedulingIds:
    organization_id: UUID
    room_id: UUID
    course_offering_id: UUID
    group_id: UUID
    teacher_id: UUID


@dataclass(frozen=True, slots=True)
class _EnabledGeneration:
    async def is_timetable_generation_enabled(
        self,
        *,
        organization_id: UUID,
    ) -> bool:
        del organization_id
        return True


class _FailingAuditSink:
    def __init__(self, *, fail_on: str) -> None:
        self.fail_on = fail_on
        self.actions: list[str] = []

    async def record_scheduling_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        target_id: UUID,
        correlation_id: str,
        outcome: str,
    ) -> None:
        del organization_id, actor_subject_id, target_id, correlation_id, outcome
        self.actions.append(action)
        if action.endswith(self.fail_on):
            raise RuntimeError("audit unavailable")


class _RejectingSchedulingRepository(InMemorySchedulingRepository):
    async def save_conflict_free_session(
        self,
        *,
        session: ScheduledSession,
        expected_version: int | None,
        constraints: ConstraintContext,
    ) -> None:
        del session, expected_version, constraints
        raise SchedulingConflictError("concurrent booking")


def _ids() -> _SchedulingIds:
    return _SchedulingIds(
        organization_id=uuid4(),
        room_id=uuid4(),
        course_offering_id=uuid4(),
        group_id=uuid4(),
        teacher_id=uuid4(),
    )


def _actor(ids: _SchedulingIds, *permissions: str) -> TenantActorContext:
    return TenantActorContext(
        subject_id=uuid4(),
        organization_id=ids.organization_id,
        membership_id=uuid4(),
        correlation_id="scheduling-integrity-test",
        permissions=frozenset(permissions),
    )


def _session(ids: _SchedulingIds) -> ScheduledSession:
    starts_at = datetime(2026, 8, 10, 9, tzinfo=UTC)
    return ScheduledSession(
        id=uuid4(),
        organization_id=ids.organization_id,
        activity_id=uuid4(),
        course_offering_id=ids.course_offering_id,
        room_id=ids.room_id,
        teacher_ids=(ids.teacher_id,),
        group_ids=(ids.group_id,),
        required_group_ids=(ids.group_id,),
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        activity_type="lecture",
        required_room_type="lecture",
        expected_attendance=20,
    )


def _constraints(ids: _SchedulingIds) -> ConstraintContext:
    starts_at = datetime(2026, 8, 10, 8, tzinfo=UTC)
    ends_at = starts_at + timedelta(hours=10)
    return ConstraintContext(
        organization_id=ids.organization_id,
        rooms=(
            RoomSpecification(
                organization_id=ids.organization_id,
                room_id=ids.room_id,
                room_type="lecture",
                capacity=40,
            ),
        ),
        teacher_availability=(
            TeacherAvailability(
                organization_id=ids.organization_id,
                teacher_id=ids.teacher_id,
                windows=(TimeWindow(starts_at, ends_at),),
            ),
        ),
        academic_calendar_windows=(TimeWindow(starts_at, ends_at),),
    )


def _references(ids: _SchedulingIds) -> ExistingSchedulingReferences:
    return ExistingSchedulingReferences(
        organization_id=ids.organization_id,
        room_ids=frozenset({ids.room_id}),
        course_offering_ids=frozenset({ids.course_offering_id}),
        group_ids=frozenset({ids.group_id}),
        teacher_ids=frozenset({ids.teacher_id}),
    )


def _without_reference(
    references: ExistingSchedulingReferences,
    field: str,
) -> ExistingSchedulingReferences:
    if field == "room_ids":
        return replace(references, room_ids=frozenset())
    if field == "course_offering_ids":
        return replace(references, course_offering_ids=frozenset())
    if field == "group_ids":
        return replace(references, group_ids=frozenset())
    if field == "teacher_ids":
        return replace(references, teacher_ids=frozenset())
    raise AssertionError(f"unknown reference field: {field}")


def _service(
    *,
    ids: _SchedulingIds,
    references: ExistingSchedulingReferences,
    audit: InMemorySchedulingAuditSink | _FailingAuditSink,
    repository: InMemorySchedulingRepository | None = None,
    generation_enabled: bool = False,
) -> TimetableService:
    return TimetableService(
        repository=repository or InMemorySchedulingRepository(),
        resources=InMemorySchedulingResourceDirectory((_constraints(ids),)),
        references=InMemorySchedulingReferenceDirectory((references,)),
        audit=audit,
        generator=DeterministicHeuristicSchedulingGenerator(),
        entitlements=_EnabledGeneration() if generation_enabled else None,
    )


@pytest.mark.parametrize(
    "missing_field",
    ["room_ids", "course_offering_ids", "group_ids", "teacher_ids"],
)
async def test_manual_creation_rejects_every_missing_external_reference(
    missing_field: str,
) -> None:
    ids = _ids()
    repository = InMemorySchedulingRepository()
    audit = InMemorySchedulingAuditSink()
    service = _service(
        ids=ids,
        references=_without_reference(_references(ids), missing_field),
        audit=audit,
        repository=repository,
    )

    with pytest.raises(NotFoundError, match="Scheduling reference"):
        await service.create_session(
            context=_actor(ids, SCHEDULING_SESSION_MANAGE),
            session=_session(ids),
        )

    assert await repository.list_sessions(organization_id=ids.organization_id) == ()
    assert audit.events == []


@pytest.mark.parametrize(
    "missing_field",
    ["course_offering_ids", "group_ids", "teacher_ids"],
)
async def test_generation_rejects_missing_activity_references(
    missing_field: str,
) -> None:
    ids = _ids()
    service = _service(
        ids=ids,
        references=_without_reference(_references(ids), missing_field),
        audit=InMemorySchedulingAuditSink(),
        generation_enabled=True,
    )
    starts_at = datetime(2026, 8, 10, 9, tzinfo=UTC)
    activity = ActivityRequest(
        id=uuid4(),
        organization_id=ids.organization_id,
        course_offering_id=ids.course_offering_id,
        teacher_ids=(ids.teacher_id,),
        group_ids=(ids.group_id,),
        required_group_ids=(ids.group_id,),
        activity_type="lecture",
        required_room_type="lecture",
        expected_attendance=20,
        duration=timedelta(hours=1),
        sessions_required=1,
    )

    with pytest.raises(NotFoundError, match="Scheduling reference"):
        await service.generate(
            context=_actor(ids, SCHEDULING_GENERATE),
            activities=(activity,),
            candidate_slots=(
                CandidateSlot(
                    id=uuid4(),
                    organization_id=ids.organization_id,
                    starts_at=starts_at,
                    ends_at=starts_at + timedelta(hours=1),
                ),
            ),
            locked_session_ids=frozenset(),
            policy=SchedulingPolicy(
                maximum_consecutive_sessions=3,
                consecutive_break_threshold=timedelta(minutes=15),
                preferred_gap_limit=timedelta(hours=2),
                preferred_hours=(
                    DailyWindow(1, datetime.min.time(), datetime.max.time()),
                ),
            ),
        )


async def test_mutation_audit_records_intent_before_persistence_and_success_after() -> (
    None
):
    ids = _ids()
    audit = InMemorySchedulingAuditSink()
    repository = InMemorySchedulingRepository()
    session = _session(ids)
    service = _service(
        ids=ids,
        references=_references(ids),
        audit=audit,
        repository=repository,
    )

    await service.create_session(
        context=_actor(ids, SCHEDULING_SESSION_MANAGE),
        session=session,
    )

    assert [(event[0], event[-1]) for event in audit.events] == [
        ("scheduling.session.create.intent", "intent_recorded"),
        ("scheduling.session.create.succeeded", "succeeded"),
    ]
    assert (
        await repository.get_session(
            organization_id=ids.organization_id,
            session_id=session.id,
        )
        == session
    )


async def test_audit_intent_failure_aborts_scheduling_mutation() -> None:
    ids = _ids()
    audit = _FailingAuditSink(fail_on=".intent")
    repository = InMemorySchedulingRepository()
    service = _service(
        ids=ids,
        references=_references(ids),
        audit=audit,
        repository=repository,
    )

    with pytest.raises(RuntimeError, match="audit unavailable"):
        await service.create_session(
            context=_actor(ids, SCHEDULING_SESSION_MANAGE),
            session=_session(ids),
        )

    assert await repository.list_sessions(organization_id=ids.organization_id) == ()
    assert audit.actions == ["scheduling.session.create.intent"]


async def test_failed_persistence_never_claims_scheduling_success() -> None:
    ids = _ids()
    audit = InMemorySchedulingAuditSink()
    service = _service(
        ids=ids,
        references=_references(ids),
        audit=audit,
        repository=_RejectingSchedulingRepository(),
    )

    with pytest.raises(SchedulingConflictError, match="concurrent booking"):
        await service.create_session(
            context=_actor(ids, SCHEDULING_SESSION_MANAGE),
            session=_session(ids),
        )

    assert [(event[0], event[-1]) for event in audit.events] == [
        ("scheduling.session.create.intent", "intent_recorded")
    ]


async def test_api_masks_missing_scheduling_reference_as_not_found() -> None:
    ids = _ids()
    repository = InMemorySchedulingRepository()
    audit = InMemorySchedulingAuditSink()
    service = _service(
        ids=ids,
        references=replace(_references(ids), room_ids=frozenset()),
        audit=audit,
        repository=repository,
    )
    actor = _actor(ids, SCHEDULING_SESSION_MANAGE)

    async def actor_dependency() -> TenantActorContext:
        return actor

    async def csrf_dependency() -> None:
        return None

    app = FastAPI()
    app.state.timetable_service = service
    install_error_handlers(app)
    app.include_router(router)
    app.dependency_overrides[require_actor] = actor_dependency
    app.dependency_overrides[require_csrf] = csrf_dependency
    session = _session(ids)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/scheduling/sessions",
            json={
                "activity_id": str(session.activity_id),
                "course_offering_id": str(session.course_offering_id),
                "room_id": str(session.room_id),
                "teacher_ids": [str(value) for value in session.teacher_ids],
                "group_ids": [str(value) for value in session.group_ids],
                "required_group_ids": [
                    str(value) for value in session.required_group_ids
                ],
                "starts_at": session.starts_at.isoformat(),
                "ends_at": session.ends_at.isoformat(),
                "activity_type": session.activity_type,
                "required_room_type": session.required_room_type,
                "expected_attendance": session.expected_attendance,
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "The requested resource was not found."
    assert await repository.list_sessions(organization_id=ids.organization_id) == ()
    assert audit.events == []
