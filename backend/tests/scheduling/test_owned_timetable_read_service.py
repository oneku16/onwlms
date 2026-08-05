"""Self-service timetable reads remain bound to exact actor-owned resources."""

from datetime import UTC
from datetime import datetime
from datetime import timedelta
from uuid import UUID
from uuid import uuid4

from core.context import TenantActorContext
from scheduling.application.read_service import TEACHER_SCHEDULE_READ
from scheduling.application.read_service import OwnedTimetableReadService
from scheduling.domain.models import ScheduledSession
from scheduling.infrastructure.repository import InMemorySchedulingRepository


def _session(
    *,
    organization_id: UUID,
    teacher_id: UUID,
    starts_at: datetime,
) -> ScheduledSession:
    """Build one valid tenant session for a single teacher."""

    group_id = uuid4()
    return ScheduledSession(
        id=uuid4(),
        organization_id=organization_id,
        activity_id=uuid4(),
        course_offering_id=uuid4(),
        room_id=uuid4(),
        teacher_ids=(teacher_id,),
        group_ids=(group_id,),
        required_group_ids=(group_id,),
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        activity_type="lecture",
        required_room_type="lecture",
        expected_attendance=20,
    )


async def test_teacher_schedule_returns_only_the_exact_teacher_profile() -> None:
    organization_id = uuid4()
    teacher_id = uuid4()
    repository = InMemorySchedulingRepository()
    assigned = _session(
        organization_id=organization_id,
        teacher_id=teacher_id,
        starts_at=datetime(2026, 8, 5, 9, tzinfo=UTC),
    )
    another_teacher = _session(
        organization_id=organization_id,
        teacher_id=uuid4(),
        starts_at=datetime(2026, 8, 5, 10, tzinfo=UTC),
    )
    await repository.save_session(session=assigned, expected_version=None)
    await repository.save_session(session=another_teacher, expected_version=None)
    actor = TenantActorContext(
        subject_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        correlation_id="teacher-schedule-test",
        permissions=frozenset({TEACHER_SCHEDULE_READ}),
    )

    sessions = await OwnedTimetableReadService(repository).teacher_schedule(
        actor=actor,
        teacher_profile_id=teacher_id,
    )

    assert [session.id for session in sessions] == [assigned.id]
