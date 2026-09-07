"""PostgreSQL scheduling repository with tenant scope and optimistic writes."""

from collections.abc import Iterable
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.errors import ConflictError
from core.identifiers import new_uuid7
from scheduling.domain.exceptions import ScheduleVersionConflictError
from scheduling.domain.exceptions import SchedulingRuleError
from scheduling.domain.models import RecurrenceRule
from scheduling.domain.models import ScheduledSession
from scheduling.domain.models import TeacherAvailabilityWindow
from scheduling.infrastructure.models import ScheduledSessionGroupModel
from scheduling.infrastructure.models import ScheduledSessionModel
from scheduling.infrastructure.models import ScheduledSessionTeacherModel
from scheduling.infrastructure.models import TeacherAvailabilityWindowModel
from shared.database import Database


class SQLAlchemySchedulingRepository:
    """Persist timetable sessions under PostgreSQL tenant transactions."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def list_sessions(
        self,
        *,
        organization_id: UUID,
    ) -> tuple[ScheduledSession, ...]:
        """Return stable ordered tenant sessions with assigned people and groups."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            return await self._load_sessions(
                session=session,
                organization_id=organization_id,
            )

    async def list_sessions_window(
        self,
        *,
        organization_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        limit: int,
        offset: int,
    ) -> tuple[ScheduledSession, ...]:
        """Return a bounded stable page intersecting one tenant time window."""

        async with self._database.session(organization_id=organization_id) as session:
            session_ids = tuple(
                (
                    await session.scalars(
                        select(ScheduledSessionModel.id)
                        .where(
                            ScheduledSessionModel.organization_id == organization_id,
                            ScheduledSessionModel.starts_at < ends_at,
                            or_(
                                ScheduledSessionModel.ends_at > starts_at,
                                ScheduledSessionModel.recurrence_until >= starts_at,
                            ),
                        )
                        .order_by(
                            ScheduledSessionModel.starts_at,
                            ScheduledSessionModel.ends_at,
                            ScheduledSessionModel.id,
                        )
                        .limit(limit)
                        .offset(offset)
                    )
                ).all()
            )
            if not session_ids:
                return ()
            return await self._load_sessions(
                session=session,
                organization_id=organization_id,
                session_ids=session_ids,
            )

    async def get_session(
        self,
        *,
        organization_id: UUID,
        session_id: UUID,
    ) -> ScheduledSession | None:
        """Return one session only when both identifier and tenant match."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            sessions = await self._load_sessions(
                session=session,
                organization_id=organization_id,
                session_ids=(session_id,),
            )
            return sessions[0] if sessions else None

    async def save_session(
        self,
        *,
        session: ScheduledSession,
        expected_version: int | None,
    ) -> None:
        """Create or compare-and-swap one timetable session atomically."""

        try:
            async with self._database.session(
                organization_id=session.organization_id,
            ) as database_session:
                current = await database_session.scalar(
                    select(ScheduledSessionModel)
                    .where(
                        ScheduledSessionModel.organization_id
                        == session.organization_id,
                        ScheduledSessionModel.id == session.id,
                    )
                    .with_for_update()
                )
                if expected_version is None:
                    if current is not None:
                        raise ConflictError("Timetable session already exists.")
                    database_session.add(self._to_model(session))
                else:
                    if current is None or current.version != expected_version:
                        raise ScheduleVersionConflictError(
                            "Timetable session changed during the requested edit."
                        )
                    self._apply(model=current, value=session)
                    await self._delete_members(
                        session=database_session,
                        organization_id=session.organization_id,
                        session_ids=(session.id,),
                    )
                self._add_members(database_session, session)
        except IntegrityError as exc:
            raise ConflictError(
                "Timetable session conflicts with stored data."
            ) from exc

    async def replace_generated_schedule(
        self,
        *,
        organization_id: UUID,
        proposed_sessions: tuple[ScheduledSession, ...],
        locked_session_ids: frozenset[UUID],
        expected_versions: dict[UUID, int],
    ) -> None:
        """Atomically replace a proposal after locking and validating current state."""

        proposed_by_id = {value.id: value for value in proposed_sessions}
        if len(proposed_by_id) != len(proposed_sessions):
            raise SchedulingRuleError("Generated schedule has duplicate sessions.")
        if any(value.organization_id != organization_id for value in proposed_sessions):
            raise SchedulingRuleError("Generated schedule tenant does not match.")
        try:
            async with self._database.session(
                organization_id=organization_id,
            ) as session:
                locked_models = tuple(
                    (
                        await session.scalars(
                            select(ScheduledSessionModel)
                            .where(
                                ScheduledSessionModel.organization_id == organization_id
                            )
                            .with_for_update()
                        )
                    ).all()
                )
                current_ids = tuple(model.id for model in locked_models)
                current = await self._load_sessions(
                    session=session,
                    organization_id=organization_id,
                    session_ids=current_ids,
                )
                current_by_id = {value.id: value for value in current}
                if {
                    identifier: value.version
                    for identifier, value in current_by_id.items()
                } != expected_versions:
                    raise ScheduleVersionConflictError(
                        "Timetable changed after schedule generation."
                    )
                if not locked_session_ids.issubset(current_by_id):
                    raise ScheduleVersionConflictError(
                        "A locked timetable session no longer exists."
                    )
                for locked_id in locked_session_ids:
                    if proposed_by_id.get(locked_id) != current_by_id[locked_id]:
                        raise ScheduleVersionConflictError(
                            "Generated schedule changed a locked session."
                        )
                await self._delete_members(
                    session=session,
                    organization_id=organization_id,
                    session_ids=current_ids,
                )
                current_model_by_id = {model.id: model for model in locked_models}
                for identifier, model in current_model_by_id.items():
                    proposed = proposed_by_id.get(identifier)
                    if proposed is None:
                        await session.delete(model)
                    else:
                        self._apply(model=model, value=proposed)
                for value in proposed_sessions:
                    if value.id not in current_model_by_id:
                        session.add(self._to_model(value))
                    self._add_members(session, value)
        except IntegrityError as exc:
            raise ConflictError(
                "Generated timetable conflicts with stored data."
            ) from exc

    @staticmethod
    def _to_model(value: ScheduledSession) -> ScheduledSessionModel:
        """Translate one validated session into its owned persistence row."""

        model = ScheduledSessionModel(
            id=value.id,
            organization_id=value.organization_id,
        )
        SQLAlchemySchedulingRepository._apply(model=model, value=value)
        return model

    @staticmethod
    def _apply(
        *,
        model: ScheduledSessionModel,
        value: ScheduledSession,
    ) -> None:
        """Apply complete mutable timetable state to one persistence row."""

        model.activity_id = value.activity_id
        model.course_offering_id = value.course_offering_id
        model.room_id = value.room_id
        model.starts_at = value.starts_at
        model.ends_at = value.ends_at
        model.activity_type = value.activity_type
        model.required_room_type = value.required_room_type
        model.expected_attendance = value.expected_attendance
        model.recurrence_interval_weeks = (
            value.recurrence.interval_weeks if value.recurrence is not None else None
        )
        model.recurrence_until = (
            value.recurrence.until if value.recurrence is not None else None
        )
        model.locked = value.locked
        model.version = value.version

    @staticmethod
    def _add_members(
        session: AsyncSession,
        value: ScheduledSession,
    ) -> None:
        """Append normalized teacher and group membership rows."""

        for teacher_id in value.teacher_ids:
            session.add(
                ScheduledSessionTeacherModel(
                    id=new_uuid7(),
                    organization_id=value.organization_id,
                    session_id=value.id,
                    teacher_id=teacher_id,
                )
            )
        required = frozenset(value.required_group_ids)
        for group_id in value.group_ids:
            session.add(
                ScheduledSessionGroupModel(
                    id=new_uuid7(),
                    organization_id=value.organization_id,
                    session_id=value.id,
                    group_id=group_id,
                    required=group_id in required,
                )
            )

    @staticmethod
    async def _delete_members(
        *,
        session: AsyncSession,
        organization_id: UUID,
        session_ids: tuple[UUID, ...],
    ) -> None:
        """Delete normalized session members for an exact tenant-owned ID set."""

        if not session_ids:
            return
        await session.execute(
            delete(ScheduledSessionTeacherModel).where(
                ScheduledSessionTeacherModel.organization_id == organization_id,
                ScheduledSessionTeacherModel.session_id.in_(session_ids),
            )
        )
        await session.execute(
            delete(ScheduledSessionGroupModel).where(
                ScheduledSessionGroupModel.organization_id == organization_id,
                ScheduledSessionGroupModel.session_id.in_(session_ids),
            )
        )

    @staticmethod
    async def _load_sessions(
        *,
        session: AsyncSession,
        organization_id: UUID,
        session_ids: Iterable[UUID] | None = None,
    ) -> tuple[ScheduledSession, ...]:
        """Load aggregate rows and normalized members inside one transaction."""

        statement = select(ScheduledSessionModel).where(
            ScheduledSessionModel.organization_id == organization_id
        )
        identifiers = tuple(session_ids) if session_ids is not None else None
        if identifiers is not None:
            if not identifiers:
                return ()
            statement = statement.where(ScheduledSessionModel.id.in_(identifiers))
        models = tuple((await session.scalars(statement)).all())
        if not models:
            return ()
        model_ids = tuple(model.id for model in models)
        teachers = tuple(
            (
                await session.scalars(
                    select(ScheduledSessionTeacherModel).where(
                        ScheduledSessionTeacherModel.organization_id == organization_id,
                        ScheduledSessionTeacherModel.session_id.in_(model_ids),
                    )
                )
            ).all()
        )
        groups = tuple(
            (
                await session.scalars(
                    select(ScheduledSessionGroupModel).where(
                        ScheduledSessionGroupModel.organization_id == organization_id,
                        ScheduledSessionGroupModel.session_id.in_(model_ids),
                    )
                )
            ).all()
        )
        teacher_ids = {
            identifier: tuple(
                sorted(
                    (
                        row.teacher_id
                        for row in teachers
                        if row.session_id == identifier
                    ),
                    key=str,
                )
            )
            for identifier in model_ids
        }
        group_ids = {
            identifier: tuple(
                sorted(
                    (row.group_id for row in groups if row.session_id == identifier),
                    key=str,
                )
            )
            for identifier in model_ids
        }
        required_group_ids = {
            identifier: tuple(
                sorted(
                    (
                        row.group_id
                        for row in groups
                        if row.session_id == identifier and row.required
                    ),
                    key=str,
                )
            )
            for identifier in model_ids
        }
        return tuple(
            sorted(
                (
                    SQLAlchemySchedulingRepository._to_domain(
                        model=model,
                        teacher_ids=teacher_ids[model.id],
                        group_ids=group_ids[model.id],
                        required_group_ids=required_group_ids[model.id],
                    )
                    for model in models
                ),
                key=lambda value: (value.starts_at, value.ends_at, str(value.id)),
            )
        )

    @staticmethod
    def _to_domain(
        *,
        model: ScheduledSessionModel,
        teacher_ids: tuple[UUID, ...],
        group_ids: tuple[UUID, ...],
        required_group_ids: tuple[UUID, ...],
    ) -> ScheduledSession:
        """Translate one aggregate snapshot into a validated domain value."""

        recurrence = None
        if (
            model.recurrence_interval_weeks is not None
            and model.recurrence_until is not None
        ):
            recurrence = RecurrenceRule(
                interval_weeks=model.recurrence_interval_weeks,
                until=model.recurrence_until,
            )
        return ScheduledSession(
            id=model.id,
            organization_id=model.organization_id,
            activity_id=model.activity_id,
            course_offering_id=model.course_offering_id,
            room_id=model.room_id,
            teacher_ids=teacher_ids,
            group_ids=group_ids,
            required_group_ids=required_group_ids,
            starts_at=model.starts_at,
            ends_at=model.ends_at,
            activity_type=model.activity_type,
            required_room_type=model.required_room_type,
            expected_attendance=model.expected_attendance,
            recurrence=recurrence,
            locked=model.locked,
            version=model.version,
        )


class SQLAlchemyTeacherAvailabilityRepository:
    """Persist tenant availability windows with exact interval uniqueness."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def create_window(self, window: TeacherAvailabilityWindow) -> None:
        """Create one validated tenant window."""

        try:
            async with self._database.session(
                organization_id=window.organization_id,
            ) as session:
                session.add(
                    TeacherAvailabilityWindowModel(
                        id=window.id,
                        organization_id=window.organization_id,
                        teacher_id=window.teacher_id,
                        starts_at=window.starts_at,
                        ends_at=window.ends_at,
                    )
                )
                await session.flush()
        except IntegrityError as exc:
            raise ConflictError(
                "Teacher availability window conflicts with stored data."
            ) from exc

    async def delete_window(
        self,
        *,
        organization_id: UUID,
        window_id: UUID,
    ) -> bool:
        """Delete only a matching tenant window."""

        async with self._database.session(organization_id=organization_id) as session:
            deleted = await session.scalar(
                delete(TeacherAvailabilityWindowModel)
                .where(
                    TeacherAvailabilityWindowModel.organization_id == organization_id,
                    TeacherAvailabilityWindowModel.id == window_id,
                )
                .returning(TeacherAvailabilityWindowModel.id)
            )
            return deleted is not None

    async def list_windows_page(
        self,
        *,
        organization_id: UUID,
        teacher_id: UUID | None,
        starts_at: datetime,
        ends_at: datetime,
        limit: int,
        offset: int,
    ) -> tuple[TeacherAvailabilityWindow, ...]:
        """Return a stable tenant page intersecting the requested horizon."""

        statement = select(TeacherAvailabilityWindowModel).where(
            TeacherAvailabilityWindowModel.organization_id == organization_id,
            TeacherAvailabilityWindowModel.starts_at < ends_at,
            TeacherAvailabilityWindowModel.ends_at > starts_at,
        )
        if teacher_id is not None:
            statement = statement.where(
                TeacherAvailabilityWindowModel.teacher_id == teacher_id
            )
        statement = statement.order_by(
            TeacherAvailabilityWindowModel.starts_at,
            TeacherAvailabilityWindowModel.ends_at,
            TeacherAvailabilityWindowModel.id,
        )
        async with self._database.session(organization_id=organization_id) as session:
            models = tuple(
                (await session.scalars(statement.limit(limit).offset(offset))).all()
            )
            return tuple(self._to_domain(model) for model in models)

    async def list_constraint_windows(
        self,
        *,
        organization_id: UUID,
        teacher_ids: frozenset[UUID],
        starts_at: datetime,
        ends_at: datetime,
    ) -> tuple[TeacherAvailabilityWindow, ...]:
        """Return complete overlap facts for the requested teacher set."""

        if not teacher_ids:
            return ()
        statement = (
            select(TeacherAvailabilityWindowModel)
            .where(
                TeacherAvailabilityWindowModel.organization_id == organization_id,
                TeacherAvailabilityWindowModel.teacher_id.in_(teacher_ids),
                TeacherAvailabilityWindowModel.starts_at < ends_at,
                TeacherAvailabilityWindowModel.ends_at > starts_at,
            )
            .order_by(
                TeacherAvailabilityWindowModel.teacher_id,
                TeacherAvailabilityWindowModel.starts_at,
                TeacherAvailabilityWindowModel.ends_at,
                TeacherAvailabilityWindowModel.id,
            )
        )
        async with self._database.session(organization_id=organization_id) as session:
            models = tuple((await session.scalars(statement)).all())
            return tuple(self._to_domain(model) for model in models)

    @staticmethod
    def _to_domain(
        model: TeacherAvailabilityWindowModel,
    ) -> TeacherAvailabilityWindow:
        """Translate one persistence row to its validated domain value."""

        return TeacherAvailabilityWindow(
            id=model.id,
            organization_id=model.organization_id,
            teacher_id=model.teacher_id,
            starts_at=model.starts_at,
            ends_at=model.ends_at,
        )


__all__ = [
    "SQLAlchemySchedulingRepository",
    "SQLAlchemyTeacherAvailabilityRepository",
]
