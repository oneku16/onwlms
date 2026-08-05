"""Scheduling SQLAlchemy mapping regression tests."""

from datetime import UTC
from datetime import datetime
from datetime import timedelta
from uuid import uuid4

from scheduling.domain.models import RecurrenceRule
from scheduling.domain.models import ScheduledSession
from scheduling.domain.models import TeacherAvailabilityWindow
from scheduling.infrastructure.models import TeacherAvailabilityWindowModel
from scheduling.infrastructure.sqlalchemy_repository import (
    SQLAlchemySchedulingRepository,
)
from scheduling.infrastructure.sqlalchemy_repository import (
    SQLAlchemyTeacherAvailabilityRepository,
)


def test_scheduled_session_mapping_preserves_recurrence_and_assignments() -> None:
    starts_at = datetime(2026, 8, 10, 9, tzinfo=UTC)
    teacher_ids = (uuid4(), uuid4())
    group_ids = (uuid4(), uuid4())
    session = ScheduledSession(
        id=uuid4(),
        organization_id=uuid4(),
        activity_id=uuid4(),
        course_offering_id=uuid4(),
        room_id=uuid4(),
        teacher_ids=teacher_ids,
        group_ids=group_ids,
        required_group_ids=(group_ids[0],),
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        activity_type="lecture",
        required_room_type="lecture",
        expected_attendance=25,
        recurrence=RecurrenceRule(
            interval_weeks=1,
            until=starts_at + timedelta(weeks=12),
        ),
        locked=True,
        version=3,
    )

    model = SQLAlchemySchedulingRepository._to_model(session)
    restored = SQLAlchemySchedulingRepository._to_domain(
        model=model,
        teacher_ids=teacher_ids,
        group_ids=group_ids,
        required_group_ids=(group_ids[0],),
    )

    assert restored == session


def test_teacher_availability_mapping_preserves_tenant_and_utc_interval() -> None:
    starts_at = datetime(2026, 8, 10, 9, tzinfo=UTC)
    expected = TeacherAvailabilityWindow(
        id=uuid4(),
        organization_id=uuid4(),
        teacher_id=uuid4(),
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=2),
    )
    model = TeacherAvailabilityWindowModel(
        id=expected.id,
        organization_id=expected.organization_id,
        teacher_id=expected.teacher_id,
        starts_at=expected.starts_at,
        ends_at=expected.ends_at,
    )

    assert SQLAlchemyTeacherAvailabilityRepository._to_domain(model) == expected
