"""Cross-module academic adapter contract tests."""

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from uuid import UUID
from uuid import uuid4

from academic_adapters import AcademicGradeTargetAdapter
from academic_adapters import AcademicSchedulingResourceAdapter
from academic_adapters import AcademicTermClosureAdapter
from academic_adapters import AdmissionsAcademicTargetAdapter
from academics.application.contracts import AcademicGradeTarget
from academics.application.contracts import AcademicSchedulingReferenceIds
from academics.application.reference_service import AcademicReferenceService
from academics.domain.models import AcademicCalendarEvent
from academics.domain.models import Room
from admissions.application.ports import AdmissionsTargetDirectory
from grading.application.ports import GradeTargetDirectory
from grading.application.ports import TermClosureDirectory
from grading.domain.models import GradeTarget
from scheduling.application.availability_service import TeacherAvailabilityService
from scheduling.application.ports import SchedulingResourceDirectory
from scheduling.domain.constraints import detect_hard_conflicts
from scheduling.domain.models import HardConstraintCode
from scheduling.domain.models import ScheduledSession
from scheduling.domain.models import TeacherAvailabilityWindow
from scheduling.infrastructure.repository import InMemorySchedulingAuditSink
from scheduling.infrastructure.repository import InMemoryTeacherAvailabilityRepository


@dataclass(frozen=True, slots=True)
class _AcademicReferenceRepository:
    organization_id: UUID
    program_id: UUID
    term_id: UUID
    grade_target: AcademicGradeTarget
    term_closed: bool
    rooms: tuple[Room, ...]
    events: tuple[AcademicCalendarEvent, ...]
    cohort_ids: frozenset[UUID]

    async def admissions_target_exists(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        intake_id: UUID,
    ) -> bool:
        """Return whether all exact tenant academic target IDs match."""

        return (
            organization_id == self.organization_id
            and program_id == self.program_id
            and intake_id == self.term_id
        )

    async def admissions_target_is_open(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        intake_id: UUID,
    ) -> bool:
        """Return whether the exact test target exists and is not closed."""

        return (
            await self.admissions_target_exists(
                organization_id=organization_id,
                program_id=program_id,
                intake_id=intake_id,
            )
            and not self.term_closed
        )

    async def get_grade_target(
        self,
        *,
        organization_id: UUID,
        course_enrollment_id: UUID,
    ) -> AcademicGradeTarget | None:
        """Return the configured grade facts only under exact tenant and ID."""

        if (
            organization_id != self.organization_id
            or course_enrollment_id != self.grade_target.course_enrollment_id
        ):
            return None
        return self.grade_target

    async def get_term_closure(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> bool | None:
        """Return configured term closure only for exact tenant and term."""

        if organization_id != self.organization_id or term_id != self.term_id:
            return None
        return self.term_closed

    async def list_rooms(
        self,
        *,
        organization_id: UUID,
    ) -> tuple[Room, ...]:
        """Return configured rooms only for the exact tenant."""

        return self.rooms if organization_id == self.organization_id else ()

    async def existing_scheduling_reference_ids(
        self,
        *,
        organization_id: UUID,
        room_ids: frozenset[UUID],
        course_offering_ids: frozenset[UUID],
        cohort_ids: frozenset[UUID],
    ) -> AcademicSchedulingReferenceIds:
        """Return requested Academic references only for the exact tenant."""

        if organization_id != self.organization_id:
            return AcademicSchedulingReferenceIds(
                organization_id=organization_id,
                room_ids=frozenset(),
                course_offering_ids=frozenset(),
                cohort_ids=frozenset(),
            )
        return AcademicSchedulingReferenceIds(
            organization_id=organization_id,
            room_ids=room_ids & frozenset(room.id for room in self.rooms),
            course_offering_ids=(
                course_offering_ids & frozenset({self.grade_target.course_offering_id})
            ),
            cohort_ids=cohort_ids & self.cohort_ids,
        )

    async def list_calendar_events(
        self,
        *,
        organization_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
    ) -> tuple[AcademicCalendarEvent, ...]:
        """Return configured intersecting events only for the exact tenant."""

        if organization_id != self.organization_id:
            return ()
        return tuple(
            event
            for event in self.events
            if event.starts_at < ends_at and event.ends_at > starts_at
        )


@dataclass(frozen=True, slots=True)
class _TeacherReferences:
    organization_id: UUID
    teacher_ids: frozenset[UUID]

    async def existing_teacher_profile_ids(
        self,
        *,
        organization_id: UUID,
        teacher_profile_ids: frozenset[UUID],
    ) -> frozenset[UUID]:
        """Return only configured teacher profiles for the exact tenant."""

        if organization_id != self.organization_id:
            return frozenset()
        return teacher_profile_ids & self.teacher_ids


def _repository() -> _AcademicReferenceRepository:
    organization_id = uuid4()
    term_id = uuid4()
    course_enrollment_id = uuid4()
    starts_at = datetime(2026, 8, 10, 8, tzinfo=UTC)
    return _AcademicReferenceRepository(
        organization_id=organization_id,
        program_id=uuid4(),
        term_id=term_id,
        grade_target=AcademicGradeTarget(
            organization_id=organization_id,
            student_academic_enrollment_id=uuid4(),
            course_enrollment_id=course_enrollment_id,
            course_offering_id=uuid4(),
            course_id=uuid4(),
            term_id=term_id,
            credits=Decimal("4"),
        ),
        term_closed=True,
        rooms=(
            Room(
                id=uuid4(),
                organization_id=organization_id,
                campus_id=uuid4(),
                code="R-101",
                room_type="lecture",
                capacity=40,
            ),
        ),
        events=(
            AcademicCalendarEvent(
                id=uuid4(),
                organization_id=organization_id,
                title="Instruction day",
                starts_at=starts_at,
                ends_at=starts_at + timedelta(hours=10),
                instruction_allowed=True,
            ),
        ),
        cohort_ids=frozenset({uuid4()}),
    )


async def test_admissions_and_grading_adapters_translate_consumer_contracts() -> None:
    repository = _repository()
    references = AcademicReferenceService(repository=repository)
    admissions: AdmissionsTargetDirectory = AdmissionsAcademicTargetAdapter(references)
    grade_targets: GradeTargetDirectory = AcademicGradeTargetAdapter(references)
    terms: TermClosureDirectory = AcademicTermClosureAdapter(references)

    assert await admissions.target_exists(
        organization_id=repository.organization_id,
        program_id=repository.program_id,
        intake_id=repository.term_id,
    )
    assert not await admissions.acceptance_is_open(
        organization_id=repository.organization_id,
        program_id=repository.program_id,
        intake_id=repository.term_id,
    )
    target = await grade_targets.get_grade_target(
        organization_id=repository.organization_id,
        course_enrollment_id=repository.grade_target.course_enrollment_id,
    )

    assert target == GradeTarget(
        organization_id=repository.organization_id,
        student_academic_enrollment_id=(
            repository.grade_target.student_academic_enrollment_id
        ),
        course_enrollment_id=repository.grade_target.course_enrollment_id,
        course_offering_id=repository.grade_target.course_offering_id,
        term_id=repository.term_id,
        course_id=repository.grade_target.course_id,
        credits=Decimal("4"),
    )
    assert await terms.is_term_closed(
        organization_id=repository.organization_id,
        term_id=repository.term_id,
    )


async def test_scheduling_adapter_loads_authoritative_teacher_availability() -> None:
    repository = _repository()
    references = AcademicReferenceService(repository=repository)
    known_teacher_id = uuid4()
    unknown_teacher_id = uuid4()
    availability_repository = InMemoryTeacherAvailabilityRepository()
    availability_service = TeacherAvailabilityService(
        availability_repository,
        _TeacherReferences(
            organization_id=repository.organization_id,
            teacher_ids=frozenset({known_teacher_id}),
        ),
        InMemorySchedulingAuditSink(),
    )
    event = repository.events[0]
    await availability_repository.create_window(
        TeacherAvailabilityWindow(
            id=uuid4(),
            organization_id=repository.organization_id,
            teacher_id=known_teacher_id,
            starts_at=event.starts_at,
            ends_at=event.ends_at,
        )
    )
    teacher_references = _TeacherReferences(
        organization_id=repository.organization_id,
        teacher_ids=frozenset({known_teacher_id}),
    )
    resources = AcademicSchedulingResourceAdapter(
        references,
        availability_service,
        teacher_references,
    )
    resource_directory: SchedulingResourceDirectory = resources
    teacher_ids = frozenset({known_teacher_id, unknown_teacher_id})

    context = await resource_directory.constraint_context(
        organization_id=repository.organization_id,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        teacher_ids=teacher_ids,
    )

    assert {value.teacher_id for value in context.teacher_availability} == teacher_ids
    by_teacher = {value.teacher_id: value for value in context.teacher_availability}
    assert len(by_teacher[known_teacher_id].windows) == 1
    assert by_teacher[unknown_teacher_id].windows == ()
    session = ScheduledSession(
        id=uuid4(),
        organization_id=repository.organization_id,
        activity_id=uuid4(),
        course_offering_id=uuid4(),
        room_id=repository.rooms[0].id,
        teacher_ids=tuple(sorted(teacher_ids, key=str)),
        group_ids=(uuid4(),),
        required_group_ids=(),
        starts_at=event.starts_at + timedelta(hours=1),
        ends_at=event.starts_at + timedelta(hours=2),
        activity_type="lecture",
        required_room_type="lecture",
        expected_attendance=20,
    )
    conflicts = detect_hard_conflicts(
        candidate=session,
        existing_sessions=(),
        context=context,
    )

    assert {
        conflict.resource_id
        for conflict in conflicts
        if conflict.code is HardConstraintCode.TEACHER_UNAVAILABLE
    } == {unknown_teacher_id}

    existing = await resources.existing_references(
        organization_id=repository.organization_id,
        room_ids=frozenset({repository.rooms[0].id, uuid4()}),
        course_offering_ids=frozenset(
            {repository.grade_target.course_offering_id, uuid4()}
        ),
        group_ids=repository.cohort_ids | frozenset({uuid4()}),
        teacher_ids=teacher_ids,
    )
    assert existing.room_ids == frozenset({repository.rooms[0].id})
    assert existing.course_offering_ids == frozenset(
        {repository.grade_target.course_offering_id}
    )
    assert existing.group_ids == repository.cohort_ids
    assert existing.teacher_ids == frozenset({known_teacher_id})
