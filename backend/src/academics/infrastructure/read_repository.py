"""PostgreSQL academic projections for self-service application reads."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.engine import Row
from sqlalchemy.sql import Select

from academics.application.read_models import AcademicCourseSummary
from academics.application.read_models import AcademicRoomSummary
from academics.application.read_models import AcademicSectionSummary
from academics.application.read_models import StudentAcademicSnapshot
from academics.domain.models import AcademicCalendarEvent
from academics.domain.models import AcademicEnrollmentStatus
from academics.domain.models import CourseEnrollmentStatus
from academics.infrastructure.models import AcademicCalendarEventModel
from academics.infrastructure.models import CourseEnrollmentModel
from academics.infrastructure.models import CourseModel
from academics.infrastructure.models import CourseOfferingModel
from academics.infrastructure.models import ProgramModel
from academics.infrastructure.models import RoomModel
from academics.infrastructure.models import StudentAcademicEnrollmentModel
from academics.infrastructure.models import TeacherAssignmentModel
from academics.infrastructure.models import TermModel
from shared.database import Database


class SQLAlchemyAcademicSelfServiceReadRepository:
    """Run ownership-shaped academic joins under exact tenant transactions."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database

    async def get_student_snapshot(
        self,
        *,
        organization_id: UUID,
        student_profile_id: UUID,
    ) -> StudentAcademicSnapshot:
        """Return enrollment IDs and active offerings for one tenant student."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            enrollment_rows = tuple(
                (
                    await session.execute(
                        select(StudentAcademicEnrollmentModel, ProgramModel)
                        .join(
                            ProgramModel,
                            (
                                ProgramModel.organization_id
                                == StudentAcademicEnrollmentModel.organization_id
                            )
                            & (
                                ProgramModel.id
                                == StudentAcademicEnrollmentModel.program_id
                            ),
                        )
                        .where(
                            StudentAcademicEnrollmentModel.organization_id
                            == organization_id,
                            StudentAcademicEnrollmentModel.student_id
                            == student_profile_id,
                        )
                        .order_by(
                            StudentAcademicEnrollmentModel.enrolled_at.desc(),
                            StudentAcademicEnrollmentModel.id,
                        )
                    )
                ).all()
            )
            enrollment_ids = tuple(row[0].id for row in enrollment_rows)
            active_enrollment_ids = tuple(
                row[0].id
                for row in enrollment_rows
                if row[0].status == AcademicEnrollmentStatus.ACTIVE.value
            )
            offering_ids: tuple[UUID, ...] = ()
            if active_enrollment_ids:
                offering_ids = tuple(
                    (
                        await session.scalars(
                            select(CourseEnrollmentModel.course_offering_id)
                            .where(
                                CourseEnrollmentModel.organization_id
                                == organization_id,
                                CourseEnrollmentModel.student_academic_enrollment_id.in_(
                                    active_enrollment_ids
                                ),
                                CourseEnrollmentModel.status
                                == CourseEnrollmentStatus.ENROLLED.value,
                            )
                            .order_by(CourseEnrollmentModel.course_offering_id)
                        )
                    ).all()
                )
        current_program = next(
            (
                row[1].name
                for row in enrollment_rows
                if row[0].status == AcademicEnrollmentStatus.ACTIVE.value
            ),
            None,
        )
        return StudentAcademicSnapshot(
            student_profile_id=student_profile_id,
            enrollment_ids=enrollment_ids,
            active_course_offering_ids=tuple(dict.fromkeys(offering_ids)),
            current_program=current_program,
        )

    async def list_teacher_sections(
        self,
        *,
        organization_id: UUID,
        teacher_profile_id: UUID,
    ) -> tuple[AcademicSectionSummary, ...]:
        """Return section projections reached through exact teacher assignments."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            rows = tuple(
                (
                    await session.execute(
                        self._section_statement(organization_id).where(
                            TeacherAssignmentModel.teacher_id == teacher_profile_id,
                        )
                    )
                ).all()
            )
        return tuple(self._section_summary(row) for row in rows)

    async def list_section_student_profile_ids(
        self,
        *,
        organization_id: UUID,
        teacher_profile_id: UUID,
        section_id: UUID,
    ) -> tuple[UUID, ...] | None:
        """Return active roster IDs only for an assigned tenant section."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            assignment = await session.scalar(
                select(TeacherAssignmentModel.id).where(
                    TeacherAssignmentModel.organization_id == organization_id,
                    TeacherAssignmentModel.teacher_id == teacher_profile_id,
                    TeacherAssignmentModel.course_offering_id == section_id,
                )
            )
            if assignment is None:
                return None
            identifiers = tuple(
                (
                    await session.scalars(
                        select(StudentAcademicEnrollmentModel.student_id)
                        .join(
                            CourseEnrollmentModel,
                            (
                                CourseEnrollmentModel.organization_id
                                == StudentAcademicEnrollmentModel.organization_id
                            )
                            & (
                                CourseEnrollmentModel.student_academic_enrollment_id
                                == StudentAcademicEnrollmentModel.id
                            ),
                        )
                        .where(
                            StudentAcademicEnrollmentModel.organization_id
                            == organization_id,
                            StudentAcademicEnrollmentModel.status
                            == AcademicEnrollmentStatus.ACTIVE.value,
                            CourseEnrollmentModel.course_offering_id == section_id,
                            CourseEnrollmentModel.status
                            == CourseEnrollmentStatus.ENROLLED.value,
                        )
                        .order_by(StudentAcademicEnrollmentModel.student_id)
                    )
                ).all()
            )
        return tuple(dict.fromkeys(identifiers))

    async def list_upcoming_events(
        self,
        *,
        organization_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
    ) -> tuple[AcademicCalendarEvent, ...]:
        """Return tenant calendar events intersecting a bounded horizon."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            models = tuple(
                (
                    await session.scalars(
                        select(AcademicCalendarEventModel)
                        .where(
                            AcademicCalendarEventModel.organization_id
                            == organization_id,
                            AcademicCalendarEventModel.starts_at < ends_at,
                            AcademicCalendarEventModel.ends_at > starts_at,
                        )
                        .order_by(
                            AcademicCalendarEventModel.starts_at,
                            AcademicCalendarEventModel.id,
                        )
                    )
                ).all()
            )
        return tuple(
            AcademicCalendarEvent(
                id=model.id,
                organization_id=model.organization_id,
                title=model.title,
                starts_at=model.starts_at,
                ends_at=model.ends_at,
                instruction_allowed=model.instruction_allowed,
            )
            for model in models
        )

    async def list_sections_by_id(
        self,
        *,
        organization_id: UUID,
        section_ids: frozenset[UUID],
    ) -> tuple[AcademicSectionSummary, ...]:
        """Describe the requested tenant sections without expanding their scope."""

        if not section_ids:
            return ()
        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            rows = tuple(
                (
                    await session.execute(
                        select(
                            CourseOfferingModel,
                            CourseModel,
                            TermModel,
                        )
                        .join(
                            CourseModel,
                            (CourseModel.organization_id == organization_id)
                            & (CourseModel.id == CourseOfferingModel.course_id),
                        )
                        .join(
                            TermModel,
                            (TermModel.organization_id == organization_id)
                            & (TermModel.id == CourseOfferingModel.term_id),
                        )
                        .where(
                            CourseOfferingModel.organization_id == organization_id,
                            CourseOfferingModel.id.in_(section_ids),
                        )
                        .order_by(CourseOfferingModel.id)
                    )
                ).all()
            )
        return tuple(self._section_summary(row) for row in rows)

    async def list_courses_by_id(
        self,
        *,
        organization_id: UUID,
        course_ids: frozenset[UUID],
    ) -> tuple[AcademicCourseSummary, ...]:
        """Describe the exact requested tenant course set."""

        if not course_ids:
            return ()
        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            models = tuple(
                (
                    await session.scalars(
                        select(CourseModel)
                        .where(
                            CourseModel.organization_id == organization_id,
                            CourseModel.id.in_(course_ids),
                        )
                        .order_by(CourseModel.id)
                    )
                ).all()
            )
        return tuple(
            AcademicCourseSummary(
                id=model.id,
                code=model.code,
                title=model.title,
            )
            for model in models
        )

    async def list_rooms_by_id(
        self,
        *,
        organization_id: UUID,
        room_ids: frozenset[UUID],
    ) -> tuple[AcademicRoomSummary, ...]:
        """Describe the exact requested tenant room set."""

        if not room_ids:
            return ()
        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            models = tuple(
                (
                    await session.scalars(
                        select(RoomModel)
                        .where(
                            RoomModel.organization_id == organization_id,
                            RoomModel.id.in_(room_ids),
                        )
                        .order_by(RoomModel.id)
                    )
                ).all()
            )
        return tuple(
            AcademicRoomSummary(id=model.id, name=model.code) for model in models
        )

    @staticmethod
    def _section_statement(
        organization_id: UUID,
    ) -> Select[tuple[CourseOfferingModel, CourseModel, TermModel]]:
        """Build the assigned-section join used by teacher reads."""

        return (
            select(CourseOfferingModel, CourseModel, TermModel)
            .join(
                TeacherAssignmentModel,
                (
                    TeacherAssignmentModel.organization_id
                    == CourseOfferingModel.organization_id
                )
                & (TeacherAssignmentModel.course_offering_id == CourseOfferingModel.id),
            )
            .join(
                CourseModel,
                (CourseModel.organization_id == CourseOfferingModel.organization_id)
                & (CourseModel.id == CourseOfferingModel.course_id),
            )
            .join(
                TermModel,
                (TermModel.organization_id == CourseOfferingModel.organization_id)
                & (TermModel.id == CourseOfferingModel.term_id),
            )
            .where(CourseOfferingModel.organization_id == organization_id)
            .order_by(TermModel.starts_on, CourseModel.code, CourseOfferingModel.id)
        )

    @staticmethod
    def _section_summary(
        row: Row[tuple[CourseOfferingModel, CourseModel, TermModel]],
    ) -> AcademicSectionSummary:
        """Translate one typed SQLAlchemy row into a stable read projection."""

        offering, course, term = row
        if not isinstance(offering, CourseOfferingModel):
            raise TypeError("Academic section projection is invalid")
        if not isinstance(course, CourseModel) or not isinstance(term, TermModel):
            raise TypeError("Academic section description is invalid")
        return AcademicSectionSummary(
            id=offering.id,
            course_id=course.id,
            course_code=course.code,
            course_title=course.title,
            section_name=offering.section_code,
            term_name=term.name,
        )


__all__ = ["SQLAlchemyAcademicSelfServiceReadRepository"]
