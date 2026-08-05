"""SQLAlchemy 2 persistence models owned by timetable scheduling."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean
from sqlalchemy import CheckConstraint
from sqlalchemy import DateTime
from sqlalchemy import ForeignKeyConstraint
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import UniqueConstraint
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from shared.models import BaseModel
from shared.models import TimestampMixin
from shared.models import UUIDPrimaryKeyMixin


class SchedulingTenantModelMixin:
    """Provide explicit tenant ownership for timetable records."""

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )


class ScheduledSessionModel(
    SchedulingTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist one manual or generated timetable session."""

    __tablename__ = "scheduling_sessions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_scheduling_sessions_organization_id_id",
        ),
        CheckConstraint(
            "starts_at < ends_at",
            name="scheduling_session_time_order",
        ),
        CheckConstraint(
            "expected_attendance > 0",
            name="scheduling_session_positive_attendance",
        ),
        CheckConstraint(
            "version >= 0",
            name="scheduling_session_version_nonnegative",
        ),
        CheckConstraint(
            "recurrence_interval_weeks IS NULL OR recurrence_interval_weeks > 0",
            name="recurrence_interval_positive",
        ),
    )

    activity_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    course_offering_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    room_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    activity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    required_room_type: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_attendance: Mapped[int] = mapped_column(Integer, nullable=False)
    recurrence_interval_weeks: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    recurrence_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ScheduledSessionTeacherModel(
    SchedulingTenantModelMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist one opaque teacher reference assigned to a session."""

    __tablename__ = "scheduling_session_teachers"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "session_id",
            "teacher_id",
            name="uq_scheduling_session_teachers_tenant_session_teacher",
        ),
        ForeignKeyConstraint(
            ["organization_id", "session_id"],
            ["scheduling_sessions.organization_id", "scheduling_sessions.id"],
            name="fk_scheduling_session_teachers_tenant_session",
        ),
    )

    session_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    teacher_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class ScheduledSessionGroupModel(
    SchedulingTenantModelMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist one opaque group reference and its required-session role."""

    __tablename__ = "scheduling_session_groups"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "session_id",
            "group_id",
            name="uq_scheduling_session_groups_tenant_session_group",
        ),
        ForeignKeyConstraint(
            ["organization_id", "session_id"],
            ["scheduling_sessions.organization_id", "scheduling_sessions.id"],
            name="fk_scheduling_session_groups_tenant_session",
        ),
    )

    session_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    group_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False)


class TeacherAvailabilityWindowModel(
    SchedulingTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist one explicit UTC availability interval for a teacher."""

    __tablename__ = "scheduling_teacher_availability_windows"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_scheduling_teacher_availability_org_id",
        ),
        UniqueConstraint(
            "organization_id",
            "teacher_id",
            "starts_at",
            "ends_at",
            name="uq_scheduling_teacher_availability_exact_window",
        ),
        CheckConstraint(
            "starts_at < ends_at",
            name="time_order",
        ),
        Index(
            "ix_scheduling_teacher_availability_teacher_time",
            "organization_id",
            "teacher_id",
            "starts_at",
            "ends_at",
        ),
    )

    teacher_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


__all__ = [
    "ScheduledSessionGroupModel",
    "ScheduledSessionModel",
    "ScheduledSessionTeacherModel",
    "TeacherAvailabilityWindowModel",
]
