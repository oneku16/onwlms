"""Explicit adapters from academic references to consumer-owned ports."""

from datetime import datetime
from uuid import UUID

from academics.application.contracts import AcademicGradeTarget
from academics.application.reference_service import AcademicReferenceService
from grading.domain.models import GradeTarget
from people.application.reference_service import PeopleReferenceService
from scheduling.application.contracts import ExistingSchedulingReferences
from scheduling.application.ports import TeacherAvailabilityDirectory
from scheduling.application.ports import TeacherReferenceDirectory
from scheduling.domain.models import ConstraintContext
from scheduling.domain.models import RoomSpecification
from scheduling.domain.models import TimeWindow


class AdmissionsAcademicTargetAdapter:
    """Validate admissions program/intake references through academics."""

    def __init__(self, references: AcademicReferenceService) -> None:
        self._references = references

    async def target_exists(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        intake_id: UUID,
    ) -> bool:
        """Treat the first-release intake identifier as an academic term."""

        return await self._references.admissions_target_exists(
            organization_id=organization_id,
            program_id=program_id,
            intake_id=intake_id,
        )

    async def acceptance_is_open(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        intake_id: UUID,
    ) -> bool:
        """Return whether the tenant intake is still open for acceptance."""

        return await self._references.admissions_target_is_open(
            organization_id=organization_id,
            program_id=program_id,
            intake_id=intake_id,
        )


class AcademicGradeTargetAdapter:
    """Translate academic-owned grade facts to grading's consumer contract."""

    def __init__(
        self,
        references: AcademicReferenceService,
        *,
        people: PeopleReferenceService,
    ) -> None:
        self._references = references
        self._people = people

    async def get_grade_target(
        self,
        *,
        organization_id: UUID,
        course_enrollment_id: UUID,
    ) -> GradeTarget | None:
        """Resolve an official course enrollment without sharing storage models."""

        target = await self._references.get_grade_target(
            organization_id=organization_id,
            course_enrollment_id=course_enrollment_id,
        )
        if target is None:
            return None
        return self._translate(target)

    async def get_grade_target_for_participant(
        self,
        *,
        organization_id: UUID,
        course_offering_id: UUID,
        student_person_id: UUID,
    ) -> GradeTarget | None:
        """Resolve one person's official participation without guessing.

        People owns the person-to-student-profile relationship and Academics
        owns course participation, so both boundaries are consulted and an
        absent or ambiguous answer at either resolves to None.
        """

        student_profile_id = await self._people.resolve_student_profile_id(
            organization_id=organization_id,
            person_id=student_person_id,
        )
        if student_profile_id is None:
            return None
        target = await self._references.get_grade_target_for_participant(
            organization_id=organization_id,
            course_offering_id=course_offering_id,
            student_profile_id=student_profile_id,
        )
        if target is None:
            return None
        return self._translate(target)

    @staticmethod
    def _translate(
        target: AcademicGradeTarget,
    ) -> GradeTarget:
        """Map an academic grade target to grading's own value object."""

        return GradeTarget(
            organization_id=target.organization_id,
            student_academic_enrollment_id=(target.student_academic_enrollment_id),
            course_enrollment_id=target.course_enrollment_id,
            course_offering_id=target.course_offering_id,
            term_id=target.term_id,
            course_id=target.course_id,
            credits=target.credits,
        )


class AcademicTermClosureAdapter:
    """Expose official term closure to grading through its own port."""

    def __init__(self, references: AcademicReferenceService) -> None:
        self._references = references

    async def is_term_closed(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> bool:
        """Fail closed for unknown terms through the academic boundary."""

        return await self._references.is_term_closed(
            organization_id=organization_id,
            term_id=term_id,
        )


class AcademicSchedulingResourceAdapter:
    """Compose Academic references with Scheduling-owned teacher availability."""

    def __init__(
        self,
        references: AcademicReferenceService,
        availability: TeacherAvailabilityDirectory,
        teachers: TeacherReferenceDirectory,
    ) -> None:
        self._references = references
        self._availability = availability
        self._teachers = teachers

    async def constraint_context(
        self,
        *,
        organization_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        teacher_ids: frozenset[UUID],
    ) -> ConstraintContext:
        """Build a bounded consumer-owned constraint snapshot."""

        references = await self._references.scheduling_references(
            organization_id=organization_id,
            starts_at=starts_at,
            ends_at=ends_at,
        )
        windows = tuple(
            TimeWindow(starts_at=window.starts_at, ends_at=window.ends_at)
            for window in references.instruction_windows
        )
        availability = await self._availability.availability_for_constraints(
            organization_id=organization_id,
            teacher_ids=teacher_ids,
            starts_at=starts_at,
            ends_at=ends_at,
        )
        return ConstraintContext(
            organization_id=organization_id,
            rooms=tuple(
                RoomSpecification(
                    organization_id=room.organization_id,
                    room_id=room.room_id,
                    room_type=room.room_type,
                    capacity=room.capacity,
                )
                for room in references.rooms
            ),
            teacher_availability=availability,
            academic_calendar_windows=windows,
        )

    async def existing_references(
        self,
        *,
        organization_id: UUID,
        room_ids: frozenset[UUID],
        course_offering_ids: frozenset[UUID],
        group_ids: frozenset[UUID],
        teacher_ids: frozenset[UUID],
    ) -> ExistingSchedulingReferences:
        """Resolve exact Academic and People references without sharing internals."""

        academic = await self._references.existing_scheduling_reference_ids(
            organization_id=organization_id,
            room_ids=room_ids,
            course_offering_ids=course_offering_ids,
            cohort_ids=group_ids,
        )
        existing_teachers = await self._teachers.existing_teacher_profile_ids(
            organization_id=organization_id,
            teacher_profile_ids=teacher_ids,
        )
        return ExistingSchedulingReferences(
            organization_id=organization_id,
            room_ids=academic.room_ids,
            course_offering_ids=academic.course_offering_ids,
            group_ids=academic.cohort_ids,
            teacher_ids=existing_teachers,
        )


__all__ = [
    "AcademicGradeTargetAdapter",
    "AcademicSchedulingResourceAdapter",
    "AcademicTermClosureAdapter",
    "AdmissionsAcademicTargetAdapter",
]
