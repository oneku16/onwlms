"""Actor-bound ownership-safe reads shared by MCP and the browser portal."""

from collections.abc import Callable
from datetime import datetime
from datetime import timedelta
from uuid import UUID

from academics.application.read_service import AcademicSelfServiceReadService
from core.context import TenantActorContext
from core.errors import NotFoundError
from grading.application.read_models import OfficialStudentReport
from grading.application.read_service import OfficialGradingReadService
from integrations.application.read_service import IntegrationSelfServiceReadService
from mcp_gateway.domain.read_models import AssignedSection
from mcp_gateway.domain.read_models import GpaSummary
from mcp_gateway.domain.read_models import GradeSummary
from mcp_gateway.domain.read_models import GradeSyncSummary
from mcp_gateway.domain.read_models import GuardianStudentSummary
from mcp_gateway.domain.read_models import MoodleDeadline
from mcp_gateway.domain.read_models import ProfileSummary
from mcp_gateway.domain.read_models import ScheduleItem
from mcp_gateway.domain.read_models import SectionStudent
from mcp_gateway.domain.read_models import UpcomingEvent
from people.application.read_models import OwnedProfileSummary
from people.application.read_service import PeopleOwnershipReadService
from people.domain.models import ProfileKind
from scheduling.application.read_service import OwnedTimetableReadService
from scheduling.domain.models import ScheduledSession


class ActorOwnedReadService:
    """Serve minimum read models after a tenant actor has been authenticated."""

    def __init__(
        self,
        *,
        people: PeopleOwnershipReadService,
        academics: AcademicSelfServiceReadService,
        grading: OfficialGradingReadService,
        scheduling: OwnedTimetableReadService,
        integrations: IntegrationSelfServiceReadService,
        clock: Callable[[], datetime],
    ) -> None:
        self._people = people
        self._academics = academics
        self._grading = grading
        self._scheduling = scheduling
        self._integrations = integrations
        self._clock = clock

    async def student_schedule(
        self,
        *,
        actor: TenantActorContext,
    ) -> list[ScheduleItem]:
        """Return sessions only for the actor's active official enrollments."""

        student = await self._people.resolve_actor_profile(
            actor=actor,
            kind=ProfileKind.STUDENT,
        )
        snapshot = await self._academics.student_snapshot(
            actor=actor,
            student_profile_id=student.profile_id,
        )
        sessions = await self._scheduling.student_schedule(
            actor=actor,
            course_offering_ids=frozenset(snapshot.active_course_offering_ids),
        )
        return await self._schedule_items(actor=actor, sessions=sessions)

    async def teacher_schedule(
        self,
        *,
        actor: TenantActorContext,
    ) -> list[ScheduleItem]:
        """Return sessions only for the actor's exact teacher profile."""

        teacher = await self._people.resolve_actor_profile(
            actor=actor,
            kind=ProfileKind.TEACHER,
        )
        sessions = await self._scheduling.teacher_schedule(
            actor=actor,
            teacher_profile_id=teacher.profile_id,
        )
        return await self._schedule_items(actor=actor, sessions=sessions)

    async def _schedule_items(
        self,
        *,
        actor: TenantActorContext,
        sessions: tuple[ScheduledSession, ...],
    ) -> list[ScheduleItem]:
        """Join already authorized sessions to minimum academic descriptions."""

        sections = await self._academics.describe_sections(
            actor=actor,
            section_ids=frozenset(session.course_offering_id for session in sessions),
        )
        rooms = await self._academics.describe_rooms(
            actor=actor,
            room_ids=frozenset(session.room_id for session in sessions),
        )
        section_by_id = {section.id: section for section in sections}
        room_by_id = {room.id: room for room in rooms}
        if any(session.course_offering_id not in section_by_id for session in sessions):
            raise NotFoundError("Scheduled course description was not found")
        return [
            ScheduleItem(
                id=session.id,
                title=(
                    f"{section_by_id[session.course_offering_id].course_code} "
                    f"{section_by_id[session.course_offering_id].section_name}"
                ),
                starts_at=session.starts_at,
                ends_at=session.ends_at,
                room_name=(
                    room_by_id[session.room_id].name
                    if session.room_id in room_by_id
                    else None
                ),
            )
            for session in sessions
        ]

    async def student_profile(
        self,
        *,
        actor: TenantActorContext,
    ) -> ProfileSummary:
        """Return the current student's own minimum profile summary."""

        student = await self._people.resolve_actor_profile(
            actor=actor,
            kind=ProfileKind.STUDENT,
        )
        return ProfileSummary(
            person_id=student.person_id,
            display_name=student.display_name,
            institutional_reference=student.institutional_reference,
        )

    async def student_grades(
        self,
        *,
        actor: TenantActorContext,
    ) -> list[GradeSummary]:
        """Return current official grades for the actor's enrollments."""

        student = await self._people.resolve_actor_profile(
            actor=actor,
            kind=ProfileKind.STUDENT,
        )
        report = await self._student_report(actor=actor, student=student)
        return await self._grade_summaries(actor=actor, report=report)

    async def student_gpa(
        self,
        *,
        actor: TenantActorContext,
    ) -> GpaSummary:
        """Return official cumulative GPA for the actor's enrollments."""

        student = await self._people.resolve_actor_profile(
            actor=actor,
            kind=ProfileKind.STUDENT,
        )
        report = await self._student_report(actor=actor, student=student)
        return self._gpa_summary(report)

    async def student_events(
        self,
        *,
        actor: TenantActorContext,
    ) -> list[UpcomingEvent]:
        """Return a bounded upcoming academic calendar for a student actor."""

        await self._people.resolve_actor_profile(
            actor=actor,
            kind=ProfileKind.STUDENT,
        )
        starts_at = self._clock()
        events = await self._academics.upcoming_events(
            actor=actor,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(days=90),
        )
        return [
            UpcomingEvent(
                id=event.id,
                title=event.title,
                starts_at=event.starts_at,
                ends_at=event.ends_at,
            )
            for event in events
        ]

    async def student_moodle_deadlines(
        self,
        *,
        actor: TenantActorContext,
    ) -> list[MoodleDeadline]:
        """Return Moodle deadline evidence for the actor's mapped person."""

        student = await self._people.resolve_actor_profile(
            actor=actor,
            kind=ProfileKind.STUDENT,
        )
        values = await self._integrations.moodle_deadlines(
            actor=actor,
            person_id=student.person_id,
        )
        return [
            MoodleDeadline(
                external_reference=value.external_reference,
                title=value.title,
                due_at=value.due_at,
                observed_at=value.observed_at,
                source_version=value.source_version,
            )
            for value in values
        ]

    async def teacher_sections(
        self,
        *,
        actor: TenantActorContext,
    ) -> list[AssignedSection]:
        """Return sections explicitly assigned to the actor's teacher profile."""

        teacher = await self._people.resolve_actor_profile(
            actor=actor,
            kind=ProfileKind.TEACHER,
        )
        sections = await self._academics.teacher_sections(
            actor=actor,
            teacher_profile_id=teacher.profile_id,
        )
        return [
            AssignedSection(
                id=section.id,
                course_code=section.course_code,
                section_name=section.section_name,
                term_name=section.term_name,
            )
            for section in sections
        ]

    async def section_students(
        self,
        *,
        actor: TenantActorContext,
        section_id: UUID,
    ) -> list[SectionStudent]:
        """Return a minimum roster only for a section assigned to the actor."""

        teacher = await self._people.resolve_actor_profile(
            actor=actor,
            kind=ProfileKind.TEACHER,
        )
        student_ids = await self._academics.assigned_section_student_ids(
            actor=actor,
            teacher_profile_id=teacher.profile_id,
            section_id=section_id,
        )
        students = await self._people.list_assigned_roster_students(
            actor=actor,
            student_profile_ids=frozenset(student_ids),
        )
        student_by_id = {student.profile_id: student for student in students}
        return [
            SectionStudent(
                person_id=student_by_id[student_id].person_id,
                display_name=student_by_id[student_id].display_name,
                institutional_reference=(
                    student_by_id[student_id].institutional_reference
                ),
            )
            for student_id in student_ids
        ]

    async def teacher_grade_sync_status(
        self,
        *,
        actor: TenantActorContext,
    ) -> list[GradeSyncSummary]:
        """Return Moodle evidence status only for assigned sections."""

        teacher = await self._people.resolve_actor_profile(
            actor=actor,
            kind=ProfileKind.TEACHER,
        )
        sections = await self._academics.teacher_sections(
            actor=actor,
            teacher_profile_id=teacher.profile_id,
        )
        statuses = await self._integrations.grade_sync_status(
            actor=actor,
            course_offering_ids=frozenset(section.id for section in sections),
        )
        return [
            GradeSyncSummary(
                section_id=value.course_offering_id,
                status=value.status,
                last_observed_at=value.last_observed_at,
                unresolved_count=value.unresolved_count,
            )
            for value in statuses
        ]

    async def teacher_moodle_deadlines(
        self,
        *,
        actor: TenantActorContext,
    ) -> list[MoodleDeadline]:
        """Return Moodle deadlines for the actor's mapped teacher person."""

        teacher = await self._people.resolve_actor_profile(
            actor=actor,
            kind=ProfileKind.TEACHER,
        )
        values = await self._integrations.moodle_deadlines(
            actor=actor,
            person_id=teacher.person_id,
        )
        return [
            MoodleDeadline(
                external_reference=value.external_reference,
                title=value.title,
                due_at=value.due_at,
                observed_at=value.observed_at,
                source_version=value.source_version,
            )
            for value in values
        ]

    async def guardian_events(
        self,
        *,
        actor: TenantActorContext,
    ) -> list[UpcomingEvent]:
        """Return upcoming organization events after guardian-profile validation."""

        await self._people.resolve_actor_profile(
            actor=actor,
            kind=ProfileKind.GUARDIAN,
        )
        starts_at = self._clock()
        events = await self._academics.upcoming_events(
            actor=actor,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(days=90),
        )
        return [
            UpcomingEvent(
                id=event.id,
                title=event.title,
                starts_at=event.starts_at,
                ends_at=event.ends_at,
            )
            for event in events
        ]

    async def guardian_students(
        self,
        *,
        actor: TenantActorContext,
    ) -> list[GuardianStudentSummary]:
        """Return summaries only for explicitly linked guardian students."""

        students = await self._people.list_linked_students(actor=actor)
        summaries: list[GuardianStudentSummary] = []
        for student in students:
            snapshot = await self._academics.student_snapshot(
                actor=actor,
                student_profile_id=student.profile_id,
            )
            report = await self._grading.student_report(
                actor=actor,
                enrollment_ids=snapshot.enrollment_ids,
            )
            grades = await self._grade_summaries(actor=actor, report=report)
            summaries.append(
                GuardianStudentSummary(
                    student_person_id=student.person_id,
                    display_name=student.display_name,
                    current_program=snapshot.current_program,
                    latest_official_grades=tuple(grades[-20:]),
                )
            )
        return summaries

    async def _student_report(
        self,
        *,
        actor: TenantActorContext,
        student: OwnedProfileSummary,
    ) -> OfficialStudentReport:
        """Resolve enrollment ownership before reading official grading state."""

        snapshot = await self._academics.student_snapshot(
            actor=actor,
            student_profile_id=student.profile_id,
        )
        return await self._grading.student_report(
            actor=actor,
            enrollment_ids=snapshot.enrollment_ids,
        )

    async def _grade_summaries(
        self,
        *,
        actor: TenantActorContext,
        report: OfficialStudentReport,
    ) -> list[GradeSummary]:
        """Join authorized results to minimum academic descriptions."""

        courses = await self._academics.describe_courses(
            actor=actor,
            course_ids=frozenset(grade.course_id for grade in report.grades),
        )
        course_by_id = {course.id: course for course in courses}
        if any(grade.course_id not in course_by_id for grade in report.grades):
            raise NotFoundError("Official grade course description was not found")
        return [
            GradeSummary(
                course_code=course_by_id[grade.course_id].code,
                course_title=course_by_id[grade.course_id].title,
                display_grade=grade.symbol,
                credits_attempted=str(grade.credits_attempted),
                credits_earned=str(grade.credits_earned),
                grade_points=(
                    str(grade.grade_points) if grade.grade_points is not None else None
                ),
            )
            for grade in report.grades
        ]

    @staticmethod
    def _gpa_summary(report: OfficialStudentReport) -> GpaSummary:
        """Translate official Decimal GPA values without float precision loss."""

        return GpaSummary(
            credits_attempted=str(report.gpa.credits_attempted),
            credits_earned=str(report.gpa.credits_earned),
            gpa_credits_attempted=str(report.gpa.gpa_credits_attempted),
            quality_points=str(report.gpa.quality_points),
            gpa=str(report.gpa.gpa) if report.gpa.gpa is not None else None,
        )


__all__ = ["ActorOwnedReadService"]
