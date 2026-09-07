"""Functional in-memory academic adapters for tests and local composition."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID

from academics.application.contracts import AcademicGradeTarget
from academics.application.contracts import AcademicSchedulingReferenceIds
from academics.application.contracts import AcceptedStudentAcademicEnrollmentCommand
from academics.application.contracts import AcceptedStudentAcademicEnrollmentResult
from academics.application.ports import CourseSelectionDecisionTransaction
from academics.application.ports import CourseSelectionSubmissionTransaction
from academics.domain.exceptions import CourseSelectionDecisionError
from academics.domain.exceptions import CourseSelectionError
from academics.domain.models import AcademicCalendarEvent
from academics.domain.models import AcademicEnrollmentStatus
from academics.domain.models import AcademicYear
from academics.domain.models import Cohort
from academics.domain.models import Course
from academics.domain.models import CourseEnrollment
from academics.domain.models import CourseEnrollmentStatus
from academics.domain.models import CourseOffering
from academics.domain.models import CourseSelectionApproval
from academics.domain.models import CourseSelectionPolicy
from academics.domain.models import CourseSelectionRequest
from academics.domain.models import CourseSelectionStatus
from academics.domain.models import Department
from academics.domain.models import Faculty
from academics.domain.models import Program
from academics.domain.models import ProgramCurriculum
from academics.domain.models import Room
from academics.domain.models import StudentAcademicEnrollment
from academics.domain.models import TeacherAssignment
from academics.domain.models import Term
from core.errors import ConflictError
from core.errors import NotFoundError

TenantKey = tuple[UUID, UUID]


class InMemoryCampusDirectory:
    """Resolve explicitly registered organization and campus identifier pairs."""

    def __init__(
        self,
        campus_ids: set[tuple[UUID, UUID]] | None = None,
    ) -> None:
        self._campus_ids = set(campus_ids or set())

    async def campus_exists(
        self,
        *,
        organization_id: UUID,
        campus_id: UUID,
    ) -> bool:
        """Return whether a campus is registered for the exact tenant."""

        return (organization_id, campus_id) in self._campus_ids

    def add(
        self,
        *,
        organization_id: UUID,
        campus_id: UUID,
    ) -> None:
        """Register a tenant and campus pair for deterministic tests."""

        self._campus_ids.add((organization_id, campus_id))


class InMemoryAcademicRepository:
    """Preserve academic repository semantics in isolated process memory."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._faculties: dict[TenantKey, Faculty] = {}
        self._departments: dict[TenantKey, Department] = {}
        self._programs: dict[TenantKey, Program] = {}
        self._academic_years: dict[TenantKey, AcademicYear] = {}
        self._terms: dict[TenantKey, Term] = {}
        self._calendar_events: dict[TenantKey, AcademicCalendarEvent] = {}
        self._courses: dict[TenantKey, Course] = {}
        self._offerings: dict[TenantKey, CourseOffering] = {}
        self._cohorts: dict[TenantKey, Cohort] = {}
        self._rooms: dict[TenantKey, Room] = {}
        self._teacher_assignments: dict[TenantKey, TeacherAssignment] = {}
        self._student_enrollments: dict[TenantKey, StudentAcademicEnrollment] = {}
        self._admissions_registrations: dict[
            TenantKey,
            tuple[
                AcceptedStudentAcademicEnrollmentCommand,
                AcceptedStudentAcademicEnrollmentResult,
            ],
        ] = {}
        self._curricula: dict[tuple[UUID, UUID, UUID], ProgramCurriculum] = {}
        self._selection_policies: dict[
            tuple[UUID, UUID, UUID], CourseSelectionPolicy
        ] = {}
        self._selection_requests: dict[TenantKey, CourseSelectionRequest] = {}
        self._selection_approvals: dict[TenantKey, CourseSelectionApproval] = {}
        self._course_enrollments: dict[TenantKey, CourseEnrollment] = {}

    async def save_faculty(self, faculty: Faculty) -> None:
        """Persist one faculty and enforce tenant-local code uniqueness."""

        _ensure_unique_code(
            records=self._faculties.values(),
            organization_id=faculty.organization_id,
            code=faculty.code,
            record_id=faculty.id,
            label="faculty",
        )
        self._faculties[(faculty.organization_id, faculty.id)] = faculty

    async def get_faculty(
        self,
        *,
        organization_id: UUID,
        faculty_id: UUID,
    ) -> Faculty | None:
        """Return a faculty only from the requested tenant."""

        return self._faculties.get((organization_id, faculty_id))

    async def save_department(self, department: Department) -> None:
        """Persist one department and enforce tenant-local code uniqueness."""

        _ensure_unique_code(
            records=self._departments.values(),
            organization_id=department.organization_id,
            code=department.code,
            record_id=department.id,
            label="department",
        )
        self._departments[(department.organization_id, department.id)] = department

    async def get_department(
        self,
        *,
        organization_id: UUID,
        department_id: UUID,
    ) -> Department | None:
        """Return a department only from the requested tenant."""

        return self._departments.get((organization_id, department_id))

    async def save_program(self, program: Program) -> None:
        """Persist one program and enforce tenant-local code uniqueness."""

        _ensure_unique_code(
            records=self._programs.values(),
            organization_id=program.organization_id,
            code=program.code,
            record_id=program.id,
            label="program",
        )
        self._programs[(program.organization_id, program.id)] = program

    async def get_program(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
    ) -> Program | None:
        """Return a program only from the requested tenant."""

        return self._programs.get((organization_id, program_id))

    async def save_academic_year(self, academic_year: AcademicYear) -> None:
        """Persist one academic year."""

        self._academic_years[(academic_year.organization_id, academic_year.id)] = (
            academic_year
        )

    async def get_academic_year(
        self,
        *,
        organization_id: UUID,
        academic_year_id: UUID,
    ) -> AcademicYear | None:
        """Return an academic year only from the requested tenant."""

        return self._academic_years.get((organization_id, academic_year_id))

    async def save_term(self, term: Term) -> None:
        """Persist one term."""

        self._terms[(term.organization_id, term.id)] = term

    async def get_term(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> Term | None:
        """Return a term only from the requested tenant."""

        return self._terms.get((organization_id, term_id))

    async def close_term(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> Term | None:
        """Close an exact-tenant term idempotently under one repository lock."""

        key = (organization_id, term_id)
        async with self._lock:
            term = self._terms.get(key)
            if term is None:
                return None
            closed_term = term.close()
            self._terms[key] = closed_term
            return closed_term

    async def save_calendar_event(self, event: AcademicCalendarEvent) -> None:
        """Persist one organization-wide calendar event."""

        self._calendar_events[(event.organization_id, event.id)] = event

    async def save_course(self, course: Course) -> None:
        """Persist one course and enforce tenant-local code uniqueness."""

        _ensure_unique_code(
            records=self._courses.values(),
            organization_id=course.organization_id,
            code=course.code,
            record_id=course.id,
            label="course",
        )
        self._courses[(course.organization_id, course.id)] = course

    async def get_course(
        self,
        *,
        organization_id: UUID,
        course_id: UUID,
    ) -> Course | None:
        """Return a course only from the requested tenant."""

        return self._courses.get((organization_id, course_id))

    async def save_course_offering(self, offering: CourseOffering) -> None:
        """Persist one tenant course offering."""

        self._offerings[(offering.organization_id, offering.id)] = offering

    async def get_course_offering(
        self,
        *,
        organization_id: UUID,
        offering_id: UUID,
    ) -> CourseOffering | None:
        """Return an offering only from the requested tenant."""

        return self._offerings.get((organization_id, offering_id))

    async def save_cohort(self, cohort: Cohort) -> None:
        """Persist one cohort and enforce tenant-local code uniqueness."""

        _ensure_unique_code(
            records=self._cohorts.values(),
            organization_id=cohort.organization_id,
            code=cohort.code,
            record_id=cohort.id,
            label="cohort",
        )
        self._cohorts[(cohort.organization_id, cohort.id)] = cohort

    async def get_cohort(
        self,
        *,
        organization_id: UUID,
        cohort_id: UUID,
    ) -> Cohort | None:
        """Return a cohort only from the requested tenant."""

        return self._cohorts.get((organization_id, cohort_id))

    async def save_room(self, room: Room) -> None:
        """Persist one room and enforce tenant-local code uniqueness."""

        _ensure_unique_code(
            records=self._rooms.values(),
            organization_id=room.organization_id,
            code=room.code,
            record_id=room.id,
            label="room",
        )
        self._rooms[(room.organization_id, room.id)] = room

    async def save_teacher_assignment(
        self,
        assignment: TeacherAssignment,
    ) -> None:
        """Persist one teacher assignment."""

        self._teacher_assignments[(assignment.organization_id, assignment.id)] = (
            assignment
        )

    async def save_student_enrollment(
        self,
        enrollment: StudentAcademicEnrollment,
    ) -> None:
        """Persist one official academic enrollment."""

        duplicate = next(
            (
                existing
                for existing in self._student_enrollments.values()
                if existing.organization_id == enrollment.organization_id
                and existing.student_id == enrollment.student_id
                and existing.program_id == enrollment.program_id
                and existing.academic_year_id == enrollment.academic_year_id
                and existing.id != enrollment.id
            ),
            None,
        )
        if duplicate is not None:
            raise ConflictError("Student already has this academic enrollment.")
        self._student_enrollments[(enrollment.organization_id, enrollment.id)] = (
            enrollment
        )

    async def get_student_enrollment(
        self,
        *,
        organization_id: UUID,
        enrollment_id: UUID,
    ) -> StudentAcademicEnrollment | None:
        """Return an academic enrollment only from the requested tenant."""

        return self._student_enrollments.get((organization_id, enrollment_id))

    async def register_admissions_enrollment(
        self,
        *,
        command: AcceptedStudentAcademicEnrollmentCommand,
        enrollment: StudentAcademicEnrollment,
    ) -> AcceptedStudentAcademicEnrollmentResult:
        """Create one exact enrollment per tenant conversion key."""

        key = (command.organization_id, command.idempotency_key)
        async with self._lock:
            existing = self._admissions_registrations.get(key)
            if existing is not None:
                existing_command, result = existing
                if existing_command != command:
                    raise ConflictError(
                        "Conversion key is bound to another academic enrollment."
                    )
                return result
            if (
                enrollment.organization_id != command.organization_id
                or enrollment.id != command.academic_enrollment_id
                or enrollment.student_id != command.student_profile_id
                or enrollment.program_id != command.program_id
                or enrollment.cohort_id is not None
                or enrollment.enrolled_at != command.enrolled_at
            ):
                raise ConflictError(
                    "Academic enrollment does not match the conversion command."
                )
            await self.save_student_enrollment(enrollment)
            result = AcceptedStudentAcademicEnrollmentResult(
                academic_enrollment_id=enrollment.id,
            )
            self._admissions_registrations[key] = (command, result)
            return result

    async def get_admissions_enrollment(
        self,
        command: AcceptedStudentAcademicEnrollmentCommand,
    ) -> AcceptedStudentAcademicEnrollmentResult | None:
        """Return an exact prior tenant binding or reject a changed replay."""

        existing = self._admissions_registrations.get(
            (command.organization_id, command.idempotency_key)
        )
        if existing is None:
            return None
        existing_command, result = existing
        if existing_command != command:
            raise ConflictError(
                "Conversion key is bound to another academic enrollment."
            )
        return result

    async def save_curriculum(self, curriculum: ProgramCurriculum) -> None:
        """Persist one versioned program curriculum."""

        key = (
            curriculum.organization_id,
            curriculum.program_id,
            curriculum.academic_year_id,
        )
        self._curricula[key] = curriculum

    async def get_curriculum(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        academic_year_id: UUID,
    ) -> ProgramCurriculum | None:
        """Return the curriculum for one tenant program and year."""

        return self._curricula.get((organization_id, program_id, academic_year_id))

    async def save_selection_policy(
        self,
        policy: CourseSelectionPolicy,
    ) -> None:
        """Persist one program and term selection policy."""

        key = (policy.organization_id, policy.program_id, policy.term_id)
        self._selection_policies[key] = policy

    async def get_selection_policy(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        term_id: UUID,
    ) -> CourseSelectionPolicy | None:
        """Return the selection policy for one tenant program and term."""

        return self._selection_policies.get((organization_id, program_id, term_id))

    async def list_faculties(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[Faculty, ...]:
        """Return a bounded stable faculty page for one tenant."""

        values = sorted(
            (
                value
                for value in self._faculties.values()
                if value.organization_id == organization_id
            ),
            key=lambda value: (value.code.casefold(), str(value.id)),
        )
        return tuple(values[offset : offset + limit])

    async def list_departments(
        self,
        *,
        organization_id: UUID,
        faculty_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Department, ...]:
        """Return a bounded stable department page for one tenant."""

        values = sorted(
            (
                value
                for value in self._departments.values()
                if value.organization_id == organization_id
                and (faculty_id is None or value.faculty_id == faculty_id)
            ),
            key=lambda value: (value.code.casefold(), str(value.id)),
        )
        return tuple(values[offset : offset + limit])

    async def list_programs(
        self,
        *,
        organization_id: UUID,
        department_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Program, ...]:
        """Return a bounded stable program page for one tenant."""

        values = sorted(
            (
                value
                for value in self._programs.values()
                if value.organization_id == organization_id
                and (department_id is None or value.department_id == department_id)
            ),
            key=lambda value: (value.code.casefold(), str(value.id)),
        )
        return tuple(values[offset : offset + limit])

    async def list_academic_years(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[AcademicYear, ...]:
        """Return a bounded stable academic-year page for one tenant."""

        values = sorted(
            (
                value
                for value in self._academic_years.values()
                if value.organization_id == organization_id
            ),
            key=lambda value: (value.starts_on, str(value.id)),
            reverse=True,
        )
        return tuple(values[offset : offset + limit])

    async def list_terms(
        self,
        *,
        organization_id: UUID,
        academic_year_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Term, ...]:
        """Return a bounded stable term page for one tenant."""

        values = sorted(
            (
                value
                for value in self._terms.values()
                if value.organization_id == organization_id
                and (
                    academic_year_id is None
                    or value.academic_year_id == academic_year_id
                )
            ),
            key=lambda value: (value.starts_on, str(value.id)),
            reverse=True,
        )
        return tuple(values[offset : offset + limit])

    async def list_courses(
        self,
        *,
        organization_id: UUID,
        department_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Course, ...]:
        """Return a bounded stable course page for one tenant."""

        values = sorted(
            (
                value
                for value in self._courses.values()
                if value.organization_id == organization_id
                and (department_id is None or value.department_id == department_id)
            ),
            key=lambda value: (value.code.casefold(), str(value.id)),
        )
        return tuple(values[offset : offset + limit])

    async def list_course_offerings(
        self,
        *,
        organization_id: UUID,
        term_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[CourseOffering, ...]:
        """Return a bounded stable offering page for one tenant."""

        values = sorted(
            (
                value
                for value in self._offerings.values()
                if value.organization_id == organization_id
                and (term_id is None or value.term_id == term_id)
            ),
            key=lambda value: (value.section_code.casefold(), str(value.id)),
        )
        return tuple(values[offset : offset + limit])

    async def list_cohorts(
        self,
        *,
        organization_id: UUID,
        program_id: UUID | None,
        academic_year_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Cohort, ...]:
        """Return a bounded stable cohort page for one tenant."""

        values = sorted(
            (
                value
                for value in self._cohorts.values()
                if value.organization_id == organization_id
                and (program_id is None or value.program_id == program_id)
                and (
                    academic_year_id is None
                    or value.academic_year_id == academic_year_id
                )
            ),
            key=lambda value: (value.code.casefold(), str(value.id)),
        )
        return tuple(values[offset : offset + limit])

    async def list_rooms_page(
        self,
        *,
        organization_id: UUID,
        campus_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Room, ...]:
        """Return a bounded stable room page for one tenant."""

        values = sorted(
            (
                value
                for value in self._rooms.values()
                if value.organization_id == organization_id
                and (campus_id is None or value.campus_id == campus_id)
            ),
            key=lambda value: (value.code.casefold(), str(value.id)),
        )
        return tuple(values[offset : offset + limit])

    async def list_teacher_assignments(
        self,
        *,
        organization_id: UUID,
        course_offering_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[TeacherAssignment, ...]:
        """Return a bounded stable teacher-assignment page for one tenant."""

        values = sorted(
            (
                value
                for value in self._teacher_assignments.values()
                if value.organization_id == organization_id
                and (
                    course_offering_id is None
                    or value.course_offering_id == course_offering_id
                )
            ),
            key=lambda value: (str(value.course_offering_id), str(value.id)),
        )
        return tuple(values[offset : offset + limit])

    async def list_student_enrollments(
        self,
        *,
        organization_id: UUID,
        student_id: UUID | None,
        program_id: UUID | None,
        academic_year_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[StudentAcademicEnrollment, ...]:
        """Return a bounded stable academic-enrollment page for one tenant."""

        values = sorted(
            (
                value
                for value in self._student_enrollments.values()
                if value.organization_id == organization_id
                and (student_id is None or value.student_id == student_id)
                and (program_id is None or value.program_id == program_id)
                and (
                    academic_year_id is None
                    or value.academic_year_id == academic_year_id
                )
            ),
            key=lambda value: (value.enrolled_at, str(value.id)),
            reverse=True,
        )
        return tuple(values[offset : offset + limit])

    async def admissions_target_exists(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        intake_id: UUID,
    ) -> bool:
        """Return whether a program and intake-as-term belong to one tenant."""

        return (organization_id, program_id) in self._programs and (
            organization_id,
            intake_id,
        ) in self._terms

    async def admissions_target_is_open(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        intake_id: UUID,
    ) -> bool:
        """Return whether a same-tenant target exists and its term remains open."""

        if (organization_id, program_id) not in self._programs:
            return False
        term = self._terms.get((organization_id, intake_id))
        return term is not None and not term.is_closed

    async def get_grade_target(
        self,
        *,
        organization_id: UUID,
        course_enrollment_id: UUID,
    ) -> AcademicGradeTarget | None:
        """Resolve joined official grading facts inside one tenant."""

        course_enrollment = self._course_enrollments.get(
            (organization_id, course_enrollment_id)
        )
        if course_enrollment is None:
            return None
        student_enrollment = self._student_enrollments.get(
            (
                organization_id,
                course_enrollment.student_academic_enrollment_id,
            )
        )
        offering = self._offerings.get(
            (organization_id, course_enrollment.course_offering_id)
        )
        if student_enrollment is None or offering is None:
            return None
        if student_enrollment.status is not AcademicEnrollmentStatus.ACTIVE:
            return None
        # Completed course participation remains a legitimate finalization and
        # revision target; withdrawal in either enrollment invalidates grading.
        if course_enrollment.status not in {
            CourseEnrollmentStatus.ENROLLED,
            CourseEnrollmentStatus.COMPLETED,
        }:
            return None
        course = self._courses.get((organization_id, offering.course_id))
        term = self._terms.get((organization_id, offering.term_id))
        if course is None or term is None:
            return None
        return AcademicGradeTarget(
            organization_id=organization_id,
            student_academic_enrollment_id=student_enrollment.id,
            course_enrollment_id=course_enrollment.id,
            course_offering_id=offering.id,
            course_id=course.id,
            term_id=term.id,
            credits=course_enrollment.credits,
        )

    async def get_term_closure(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> bool | None:
        """Return tenant term closure or None for an unknown term."""

        term = self._terms.get((organization_id, term_id))
        return term.is_closed if term is not None else None

    async def existing_scheduling_reference_ids(
        self,
        *,
        organization_id: UUID,
        room_ids: frozenset[UUID],
        course_offering_ids: frozenset[UUID],
        cohort_ids: frozenset[UUID],
    ) -> AcademicSchedulingReferenceIds:
        """Return exact requested references from one in-memory tenant."""

        return AcademicSchedulingReferenceIds(
            organization_id=organization_id,
            room_ids=frozenset(
                identifier
                for identifier in room_ids
                if (organization_id, identifier) in self._rooms
            ),
            course_offering_ids=frozenset(
                identifier
                for identifier in course_offering_ids
                if (organization_id, identifier) in self._offerings
            ),
            cohort_ids=frozenset(
                identifier
                for identifier in cohort_ids
                if (organization_id, identifier) in self._cohorts
            ),
        )

    async def list_rooms(
        self,
        *,
        organization_id: UUID,
    ) -> tuple[Room, ...]:
        """Return stable ordered rooms from one tenant."""

        return tuple(
            sorted(
                (
                    room
                    for room in self._rooms.values()
                    if room.organization_id == organization_id
                ),
                key=lambda room: (room.code.casefold(), str(room.id)),
            )
        )

    async def list_calendar_events(
        self,
        *,
        organization_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
    ) -> tuple[AcademicCalendarEvent, ...]:
        """Return all events intersecting one bounded tenant horizon."""

        return tuple(
            sorted(
                (
                    event
                    for event in self._calendar_events.values()
                    if event.organization_id == organization_id
                    and event.starts_at < ends_at
                    and event.ends_at > starts_at
                ),
                key=lambda event: (event.starts_at, event.ends_at, str(event.id)),
            )
        )

    async def list_course_enrollments(
        self,
        *,
        organization_id: UUID,
        student_academic_enrollment_id: UUID,
    ) -> tuple[CourseEnrollment, ...]:
        """Return stable ordered enrollments for one tenant student enrollment."""

        enrollments = (
            enrollment
            for enrollment in self._course_enrollments.values()
            if enrollment.organization_id == organization_id
            and enrollment.student_academic_enrollment_id
            == student_academic_enrollment_id
        )
        return tuple(sorted(enrollments, key=lambda enrollment: str(enrollment.id)))

    async def list_selection_requests(
        self,
        *,
        organization_id: UUID,
        status: CourseSelectionStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[CourseSelectionRequest, ...]:
        """Return a bounded newest-first selection-request page for one tenant."""

        requests = sorted(
            (
                request
                for request in self._selection_requests.values()
                if request.organization_id == organization_id
                and (status is None or request.status is status)
            ),
            key=lambda request: str(request.id),
        )
        requests.sort(key=lambda request: request.submitted_at, reverse=True)
        return tuple(requests[offset : offset + limit])

    async def get_selection_request(
        self,
        *,
        organization_id: UUID,
        request_id: UUID,
    ) -> CourseSelectionRequest | None:
        """Return a selection request only from the requested tenant."""

        return self._selection_requests.get((organization_id, request_id))

    @asynccontextmanager
    async def submission_transaction(
        self,
        *,
        organization_id: UUID,
        student_academic_enrollment_id: UUID,
    ) -> AsyncIterator[CourseSelectionSubmissionTransaction]:
        """Hold the student aggregate lock through evaluation and submission."""

        async with self._lock:
            enrollment = self._student_enrollments.get(
                (organization_id, student_academic_enrollment_id)
            )
            if enrollment is None:
                raise NotFoundError("Student academic enrollment was not found.")
            yield _InMemoryCourseSelectionTransaction(
                repository=self,
                organization_id=organization_id,
                student_enrollment=enrollment,
                request=None,
            )

    @asynccontextmanager
    async def decision_transaction(
        self,
        *,
        organization_id: UUID,
        request_id: UUID,
    ) -> AsyncIterator[CourseSelectionDecisionTransaction]:
        """Hold request and student aggregate locks through one decision."""

        async with self._lock:
            request = self._selection_requests.get((organization_id, request_id))
            if request is None:
                raise CourseSelectionDecisionError(
                    "Course-selection request no longer exists."
                )
            enrollment = self._student_enrollments.get(
                (organization_id, request.student_academic_enrollment_id)
            )
            if enrollment is None:
                raise NotFoundError("Student academic enrollment was not found.")
            yield _InMemoryCourseSelectionTransaction(
                repository=self,
                organization_id=organization_id,
                student_enrollment=enrollment,
                request=request,
            )

    async def save_submission(
        self,
        *,
        request: CourseSelectionRequest,
        enrollments: tuple[CourseEnrollment, ...],
        offering_capacities: dict[UUID, int],
    ) -> None:
        """Atomically save a new request and immediate course enrollments."""

        async with self._lock:
            self._save_submission_unlocked(
                request=request,
                enrollments=enrollments,
                offering_capacities=offering_capacities,
            )

    async def save_decision(
        self,
        *,
        request: CourseSelectionRequest,
        approval: CourseSelectionApproval,
        enrollments: tuple[CourseEnrollment, ...],
        offering_capacities: dict[UUID, int],
    ) -> None:
        """Atomically replace pending state and append decision effects."""

        async with self._lock:
            self._save_decision_unlocked(
                request=request,
                approval=approval,
                enrollments=enrollments,
                offering_capacities=offering_capacities,
            )

    def _save_submission_unlocked(
        self,
        *,
        request: CourseSelectionRequest,
        enrollments: tuple[CourseEnrollment, ...],
        offering_capacities: dict[UUID, int],
    ) -> None:
        """Persist a submission while the caller holds the repository lock."""

        key = (request.organization_id, request.id)
        if key in self._selection_requests:
            raise ConflictError("Course-selection request already exists.")
        self._check_enrollment_capacity(
            organization_id=request.organization_id,
            enrollments=enrollments,
            offering_capacities=offering_capacities,
        )
        self._selection_requests[key] = request
        self._persist_course_enrollments(enrollments)

    def _save_decision_unlocked(
        self,
        *,
        request: CourseSelectionRequest,
        approval: CourseSelectionApproval,
        enrollments: tuple[CourseEnrollment, ...],
        offering_capacities: dict[UUID, int],
    ) -> None:
        """Persist a decision while the caller holds the repository lock."""

        key = (request.organization_id, request.id)
        existing = self._selection_requests.get(key)
        if existing is None:
            raise CourseSelectionDecisionError(
                "Course-selection request no longer exists."
            )
        if existing.status is not CourseSelectionStatus.PENDING:
            raise CourseSelectionDecisionError(
                "Course-selection request was already decided."
            )
        self._check_enrollment_capacity(
            organization_id=request.organization_id,
            enrollments=enrollments,
            offering_capacities=offering_capacities,
        )
        self._selection_requests[key] = request
        self._selection_approvals[(approval.organization_id, approval.id)] = approval
        self._persist_course_enrollments(enrollments)

    async def list_approvals(
        self,
        *,
        organization_id: UUID,
        request_id: UUID,
    ) -> tuple[CourseSelectionApproval, ...]:
        """Return immutable decision history for test and read composition."""

        approvals = (
            approval
            for approval in self._selection_approvals.values()
            if approval.organization_id == organization_id
            and approval.request_id == request_id
        )
        return tuple(sorted(approvals, key=lambda approval: approval.decided_at))

    def _check_enrollment_capacity(
        self,
        *,
        organization_id: UUID,
        enrollments: tuple[CourseEnrollment, ...],
        offering_capacities: dict[UUID, int],
    ) -> None:
        """Reject atomic enrollment when any offering has no remaining seat."""

        for enrollment in enrollments:
            capacity = offering_capacities.get(enrollment.course_offering_id)
            if capacity is None:
                raise CourseSelectionError("Course offering capacity is unknown.")
            occupied = sum(
                1
                for existing in self._course_enrollments.values()
                if existing.organization_id == organization_id
                and existing.course_offering_id == enrollment.course_offering_id
                and existing.status is CourseEnrollmentStatus.ENROLLED
            )
            if occupied >= capacity:
                raise CourseSelectionError("Course offering capacity was reached.")

    def _persist_course_enrollments(
        self,
        enrollments: tuple[CourseEnrollment, ...],
    ) -> None:
        """Persist enrollments after all atomic preconditions have passed."""

        for enrollment in enrollments:
            duplicate = next(
                (
                    existing
                    for existing in self._course_enrollments.values()
                    if existing.organization_id == enrollment.organization_id
                    and existing.student_academic_enrollment_id
                    == enrollment.student_academic_enrollment_id
                    and existing.course_offering_id == enrollment.course_offering_id
                    and existing.status is CourseEnrollmentStatus.ENROLLED
                ),
                None,
            )
            if duplicate is not None:
                raise CourseSelectionError(
                    "Student is already enrolled in the course offering."
                )
        for enrollment in enrollments:
            self._course_enrollments[(enrollment.organization_id, enrollment.id)] = (
                enrollment
            )


class _InMemoryCourseSelectionTransaction:
    """Expose current selection reads while one repository lock is held."""

    def __init__(
        self,
        *,
        repository: InMemoryAcademicRepository,
        organization_id: UUID,
        student_enrollment: StudentAcademicEnrollment,
        request: CourseSelectionRequest | None,
    ) -> None:
        self._repository = repository
        self._organization_id = organization_id
        self._student_enrollment = student_enrollment
        self._request = request

    @property
    def student_enrollment(self) -> StudentAcademicEnrollment:
        """Return the student enrollment protected by the active lock."""

        return self._student_enrollment

    @property
    def request(self) -> CourseSelectionRequest:
        """Return the request protected by the active decision lock."""

        if self._request is None:
            raise RuntimeError("A submission transaction has no existing request.")
        return self._request

    async def get_term(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> Term | None:
        """Return one term while the student aggregate lock is held."""

        self._require_tenant(organization_id)
        return await self._repository.get_term(
            organization_id=organization_id,
            term_id=term_id,
        )

    async def get_course_offering(
        self,
        *,
        organization_id: UUID,
        offering_id: UUID,
    ) -> CourseOffering | None:
        """Return one offering while the student aggregate lock is held."""

        self._require_tenant(organization_id)
        return await self._repository.get_course_offering(
            organization_id=organization_id,
            offering_id=offering_id,
        )

    async def get_curriculum(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        academic_year_id: UUID,
    ) -> ProgramCurriculum | None:
        """Return current curriculum state inside the selection transaction."""

        self._require_tenant(organization_id)
        return await self._repository.get_curriculum(
            organization_id=organization_id,
            program_id=program_id,
            academic_year_id=academic_year_id,
        )

    async def get_selection_policy(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        term_id: UUID,
    ) -> CourseSelectionPolicy | None:
        """Return current policy state inside the selection transaction."""

        self._require_tenant(organization_id)
        return await self._repository.get_selection_policy(
            organization_id=organization_id,
            program_id=program_id,
            term_id=term_id,
        )

    async def list_course_enrollments(
        self,
        *,
        organization_id: UUID,
        student_academic_enrollment_id: UUID,
    ) -> tuple[CourseEnrollment, ...]:
        """Return current enrollment state inside the selection transaction."""

        self._require_tenant(organization_id)
        return await self._repository.list_course_enrollments(
            organization_id=organization_id,
            student_academic_enrollment_id=student_academic_enrollment_id,
        )

    async def save_submission(
        self,
        *,
        request: CourseSelectionRequest,
        enrollments: tuple[CourseEnrollment, ...],
        offering_capacities: dict[UUID, int],
    ) -> None:
        """Persist a submission without reacquiring the held lock."""

        self._require_request_scope(request)
        self._repository._save_submission_unlocked(
            request=request,
            enrollments=enrollments,
            offering_capacities=offering_capacities,
        )

    async def save_decision(
        self,
        *,
        request: CourseSelectionRequest,
        approval: CourseSelectionApproval,
        enrollments: tuple[CourseEnrollment, ...],
        offering_capacities: dict[UUID, int],
    ) -> None:
        """Persist a decision without reacquiring the held lock."""

        self._require_request_scope(request)
        if self.request.id != request.id:
            raise CourseSelectionDecisionError(
                "Course-selection request changed during decision."
            )
        self._repository._save_decision_unlocked(
            request=request,
            approval=approval,
            enrollments=enrollments,
            offering_capacities=offering_capacities,
        )

    def _require_tenant(self, organization_id: UUID) -> None:
        if organization_id != self._organization_id:
            raise NotFoundError("Course-selection state was not found.")

    def _require_request_scope(self, request: CourseSelectionRequest) -> None:
        self._require_tenant(request.organization_id)
        if request.student_academic_enrollment_id != self._student_enrollment.id:
            raise CourseSelectionDecisionError(
                "Course-selection student enrollment changed during mutation."
            )


def _ensure_unique_code(
    *,
    records: object,
    organization_id: UUID,
    code: str,
    record_id: UUID,
    label: str,
) -> None:
    """Enforce case-insensitive tenant-local codes in the in-memory adapter."""

    from collections.abc import Iterable
    from typing import Protocol
    from typing import cast

    class CodedRecord(Protocol):
        """Describe the fields needed for tenant code uniqueness."""

        id: UUID
        organization_id: UUID
        code: str

    typed_records = cast(Iterable[CodedRecord], records)
    normalized = code.casefold()
    duplicate = next(
        (
            record
            for record in typed_records
            if record.organization_id == organization_id
            and record.id != record_id
            and record.code.casefold() == normalized
        ),
        None,
    )
    if duplicate is not None:
        raise ConflictError(f"A {label} with this code already exists.")


__all__ = [
    "InMemoryAcademicRepository",
    "InMemoryCampusDirectory",
]
