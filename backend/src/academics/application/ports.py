"""Application-owned academic persistence and collaboration contracts."""

from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Protocol
from uuid import UUID

from academics.application.contracts import AcademicGradeTarget
from academics.application.contracts import AcademicSchedulingReferenceIds
from academics.application.contracts import AcceptedStudentAcademicEnrollmentCommand
from academics.application.contracts import AcceptedStudentAcademicEnrollmentResult
from academics.domain.models import AcademicCalendarEvent
from academics.domain.models import AcademicYear
from academics.domain.models import Cohort
from academics.domain.models import Course
from academics.domain.models import CourseEnrollment
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
from core.context import TenantActorContext


class CampusDirectory(Protocol):
    """Check organization-owned campus references without sharing its model."""

    async def campus_exists(
        self,
        *,
        organization_id: UUID,
        campus_id: UUID,
    ) -> bool:
        """Return whether the campus exists inside the requested tenant."""
        ...


class AcademicProfileDirectory(Protocol):
    """Validate People-owned academic profile references by type and tenant."""

    async def teacher_profile_exists(
        self,
        *,
        organization_id: UUID,
        teacher_profile_id: UUID,
    ) -> bool:
        """Return whether the identifier is a teacher in the exact tenant."""
        ...

    async def student_profile_exists(
        self,
        *,
        organization_id: UUID,
        student_profile_id: UUID,
    ) -> bool:
        """Return whether the identifier is a student in the exact tenant."""
        ...


class AcademicCatalogRepository(Protocol):
    """Persist and resolve tenant-scoped academic catalog records."""

    async def save_faculty(self, faculty: Faculty) -> None:
        """Persist one faculty."""
        ...

    async def get_faculty(
        self,
        *,
        organization_id: UUID,
        faculty_id: UUID,
    ) -> Faculty | None:
        """Return a faculty only from the requested tenant."""
        ...

    async def save_department(self, department: Department) -> None:
        """Persist one department."""
        ...

    async def get_department(
        self,
        *,
        organization_id: UUID,
        department_id: UUID,
    ) -> Department | None:
        """Return a department only from the requested tenant."""
        ...

    async def save_program(self, program: Program) -> None:
        """Persist one program."""
        ...

    async def get_program(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
    ) -> Program | None:
        """Return a program only from the requested tenant."""
        ...

    async def save_academic_year(self, academic_year: AcademicYear) -> None:
        """Persist one academic year."""
        ...

    async def get_academic_year(
        self,
        *,
        organization_id: UUID,
        academic_year_id: UUID,
    ) -> AcademicYear | None:
        """Return an academic year only from the requested tenant."""
        ...

    async def save_term(self, term: Term) -> None:
        """Persist one term."""
        ...

    async def get_term(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> Term | None:
        """Return a term only from the requested tenant."""
        ...

    async def close_term(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> Term | None:
        """Close an existing tenant term one way and return its current state."""
        ...

    async def save_calendar_event(self, event: AcademicCalendarEvent) -> None:
        """Persist one organization-wide academic calendar event."""
        ...

    async def list_calendar_events(
        self,
        *,
        organization_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
    ) -> tuple[AcademicCalendarEvent, ...]:
        """Return calendar events intersecting a bounded tenant horizon."""
        ...

    async def save_course(self, course: Course) -> None:
        """Persist one official course."""
        ...

    async def get_course(
        self,
        *,
        organization_id: UUID,
        course_id: UUID,
    ) -> Course | None:
        """Return a course only from the requested tenant."""
        ...

    async def save_course_offering(self, offering: CourseOffering) -> None:
        """Persist one term course offering."""
        ...

    async def get_course_offering(
        self,
        *,
        organization_id: UUID,
        offering_id: UUID,
    ) -> CourseOffering | None:
        """Return an offering only from the requested tenant."""
        ...

    async def save_cohort(self, cohort: Cohort) -> None:
        """Persist one program cohort."""
        ...

    async def get_cohort(
        self,
        *,
        organization_id: UUID,
        cohort_id: UUID,
    ) -> Cohort | None:
        """Return a cohort only from the requested tenant."""
        ...

    async def save_room(self, room: Room) -> None:
        """Persist one campus room."""
        ...

    async def save_teacher_assignment(
        self,
        assignment: TeacherAssignment,
    ) -> None:
        """Persist one course-offering teacher assignment."""
        ...

    async def save_student_enrollment(
        self,
        enrollment: StudentAcademicEnrollment,
    ) -> None:
        """Persist one official student academic enrollment."""
        ...

    async def get_student_enrollment(
        self,
        *,
        organization_id: UUID,
        enrollment_id: UUID,
    ) -> StudentAcademicEnrollment | None:
        """Return an academic enrollment only from the requested tenant."""
        ...

    async def save_curriculum(self, curriculum: ProgramCurriculum) -> None:
        """Persist one versioned program curriculum."""
        ...

    async def get_curriculum(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        academic_year_id: UUID,
    ) -> ProgramCurriculum | None:
        """Return the curriculum for one tenant program and academic year."""
        ...

    async def save_selection_policy(
        self,
        policy: CourseSelectionPolicy,
    ) -> None:
        """Persist one tenant program and term selection policy."""
        ...

    async def get_selection_policy(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        term_id: UUID,
    ) -> CourseSelectionPolicy | None:
        """Return the configured selection policy."""
        ...

    async def list_faculties(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[Faculty, ...]:
        """Return a bounded stable page of tenant faculties."""
        ...

    async def list_departments(
        self,
        *,
        organization_id: UUID,
        faculty_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Department, ...]:
        """Return a bounded stable page of tenant departments."""
        ...

    async def list_programs(
        self,
        *,
        organization_id: UUID,
        department_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Program, ...]:
        """Return a bounded stable page of tenant programs."""
        ...

    async def list_academic_years(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[AcademicYear, ...]:
        """Return a bounded stable page of tenant academic years."""
        ...

    async def list_terms(
        self,
        *,
        organization_id: UUID,
        academic_year_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Term, ...]:
        """Return a bounded stable page of tenant terms."""
        ...

    async def list_courses(
        self,
        *,
        organization_id: UUID,
        department_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Course, ...]:
        """Return a bounded stable page of tenant courses."""
        ...

    async def list_course_offerings(
        self,
        *,
        organization_id: UUID,
        term_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[CourseOffering, ...]:
        """Return a bounded stable page of complete tenant offerings."""
        ...

    async def list_cohorts(
        self,
        *,
        organization_id: UUID,
        program_id: UUID | None,
        academic_year_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Cohort, ...]:
        """Return a bounded stable page of tenant cohorts."""
        ...

    async def list_rooms_page(
        self,
        *,
        organization_id: UUID,
        campus_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Room, ...]:
        """Return a bounded stable page of tenant rooms."""
        ...

    async def list_teacher_assignments(
        self,
        *,
        organization_id: UUID,
        course_offering_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[TeacherAssignment, ...]:
        """Return a bounded stable page of teacher assignments."""
        ...

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
        """Return a bounded stable page of official academic enrollments."""
        ...


class CourseSelectionEvaluationCatalog(Protocol):
    """Read the current catalog facts required to evaluate one selection."""

    async def get_term(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> Term | None:
        """Return one exact-tenant term."""
        ...

    async def get_course_offering(
        self,
        *,
        organization_id: UUID,
        offering_id: UUID,
    ) -> CourseOffering | None:
        """Return one complete exact-tenant offering."""
        ...

    async def get_curriculum(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        academic_year_id: UUID,
    ) -> ProgramCurriculum | None:
        """Return one current program-year curriculum."""
        ...

    async def get_selection_policy(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        term_id: UUID,
    ) -> CourseSelectionPolicy | None:
        """Return one current program-term selection policy."""
        ...


class CourseSelectionEnrollmentReader(Protocol):
    """Read current official enrollments for selection evaluation."""

    async def list_course_enrollments(
        self,
        *,
        organization_id: UUID,
        student_academic_enrollment_id: UUID,
    ) -> tuple[CourseEnrollment, ...]:
        """Return official course enrollments inside one tenant."""
        ...


class CourseSelectionSubmissionTransaction(
    CourseSelectionEvaluationCatalog,
    CourseSelectionEnrollmentReader,
    Protocol,
):
    """Hold one student enrollment lock through submission evaluation and save."""

    @property
    def student_enrollment(self) -> StudentAcademicEnrollment:
        """Return the exact locked student academic enrollment."""
        ...

    async def save_submission(
        self,
        *,
        request: CourseSelectionRequest,
        enrollments: tuple[CourseEnrollment, ...],
        offering_capacities: dict[UUID, int],
    ) -> None:
        """Save the evaluated submission in the active transaction."""
        ...


class CourseSelectionDecisionTransaction(
    CourseSelectionEvaluationCatalog,
    CourseSelectionEnrollmentReader,
    Protocol,
):
    """Hold request and student locks through decision evaluation and save."""

    @property
    def request(self) -> CourseSelectionRequest:
        """Return the exact locked selection request."""
        ...

    @property
    def student_enrollment(self) -> StudentAcademicEnrollment:
        """Return the exact locked student academic enrollment."""
        ...

    async def save_decision(
        self,
        *,
        request: CourseSelectionRequest,
        approval: CourseSelectionApproval,
        enrollments: tuple[CourseEnrollment, ...],
        offering_capacities: dict[UUID, int],
    ) -> None:
        """Save the evaluated decision in the active transaction."""
        ...


class CourseSelectionRepository(CourseSelectionEnrollmentReader, Protocol):
    """Persist selection aggregates with atomic enrollment finalization."""

    async def list_selection_requests(
        self,
        *,
        organization_id: UUID,
        status: CourseSelectionStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[CourseSelectionRequest, ...]:
        """Return a bounded stable page of tenant selection requests."""
        ...

    def submission_transaction(
        self,
        *,
        organization_id: UUID,
        student_academic_enrollment_id: UUID,
    ) -> AbstractAsyncContextManager[CourseSelectionSubmissionTransaction]:
        """Serialize one student's evaluation and submission mutation."""
        ...

    def decision_transaction(
        self,
        *,
        organization_id: UUID,
        request_id: UUID,
    ) -> AbstractAsyncContextManager[CourseSelectionDecisionTransaction]:
        """Serialize one pending request and its student aggregate decision."""
        ...

    async def get_selection_request(
        self,
        *,
        organization_id: UUID,
        request_id: UUID,
    ) -> CourseSelectionRequest | None:
        """Return a selection request only from the requested tenant."""
        ...


class AdmissionsAcademicEnrollmentRepository(Protocol):
    """Persist the idempotent Admissions-to-Academics enrollment boundary."""

    async def get_admissions_enrollment(
        self,
        command: AcceptedStudentAcademicEnrollmentCommand,
    ) -> AcceptedStudentAcademicEnrollmentResult | None:
        """Resolve an exact prior conversion binding before current-state rules."""
        ...

    async def register_admissions_enrollment(
        self,
        *,
        command: AcceptedStudentAcademicEnrollmentCommand,
        enrollment: StudentAcademicEnrollment,
    ) -> AcceptedStudentAcademicEnrollmentResult:
        """Create or resolve the exact enrollment bound to a conversion key."""
        ...


class AcceptedStudentAcademicEnrollmentRegistrar(Protocol):
    """Expose the public Academics accepted-student capability."""

    async def enroll_accepted_student(
        self,
        command: AcceptedStudentAcademicEnrollmentCommand,
    ) -> AcceptedStudentAcademicEnrollmentResult:
        """Create or resolve one official academic enrollment idempotently."""
        ...


class AcademicReferenceRepository(Protocol):
    """Resolve tenant-scoped academic facts for stable application contracts."""

    async def admissions_target_exists(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        intake_id: UUID,
    ) -> bool:
        """Return whether a program and intake-term both belong to the tenant."""
        ...

    async def admissions_target_is_open(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        intake_id: UUID,
    ) -> bool:
        """Return whether the exact target exists and its intake term is open."""
        ...

    async def get_grade_target(
        self,
        *,
        organization_id: UUID,
        course_enrollment_id: UUID,
    ) -> AcademicGradeTarget | None:
        """Return joined official facts for one tenant course enrollment."""
        ...

    async def get_term_closure(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> bool | None:
        """Return closure state, or None when the tenant term does not exist."""
        ...

    async def existing_scheduling_reference_ids(
        self,
        *,
        organization_id: UUID,
        room_ids: frozenset[UUID],
        course_offering_ids: frozenset[UUID],
        cohort_ids: frozenset[UUID],
    ) -> AcademicSchedulingReferenceIds:
        """Return only requested rooms, offerings, and cohorts in the tenant."""
        ...

    async def list_rooms(
        self,
        *,
        organization_id: UUID,
    ) -> tuple[Room, ...]:
        """Return rooms owned by one tenant."""
        ...

    async def list_calendar_events(
        self,
        *,
        organization_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
    ) -> tuple[AcademicCalendarEvent, ...]:
        """Return calendar events intersecting a bounded tenant horizon."""
        ...


class AcademicClock(Protocol):
    """Supply an explicit timezone-aware application time."""

    def now(self) -> datetime:
        """Return the current timezone-aware UTC time."""
        ...


class CourseSelectionAuditSink(Protocol):
    """Append privacy-minimized evidence for administrative selection actions."""

    async def record_course_selection_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        request_id: UUID,
        correlation_id: str,
        outcome: str,
    ) -> None:
        """Record one selection intent or outcome without free-form reasons."""
        ...


class TermClosureAuditSink(Protocol):
    """Record privacy-minimized evidence of an authorized closure intent."""

    async def record_term_closure_intent(
        self,
        *,
        organization_id: UUID,
        actor_subject_id: UUID,
        term_id: UUID,
        correlation_id: str,
        reason: str,
    ) -> None:
        """Record why an actor intends to close one tenant-owned term."""
        ...


class AcademicAuditSink(CourseSelectionAuditSink, TermClosureAuditSink, Protocol):
    """Combine the audit capabilities consumed by the Academics module."""


class CourseSelectionStudentOwnership(Protocol):
    """Resolve whether a tenant actor owns one student profile reference."""

    async def resolve_actor_student_profile_id(
        self,
        *,
        actor: TenantActorContext,
    ) -> UUID:
        """Return the exact student profile owned by the active membership."""
        ...

    async def actor_owns_student_profile(
        self,
        *,
        actor: TenantActorContext,
        student_profile_id: UUID,
    ) -> bool:
        """Return exact membership-linked student-profile ownership."""
        ...


__all__ = [
    "AcademicAuditSink",
    "AcademicCatalogRepository",
    "AcademicClock",
    "AcademicProfileDirectory",
    "AcademicReferenceRepository",
    "AcceptedStudentAcademicEnrollmentRegistrar",
    "AdmissionsAcademicEnrollmentRepository",
    "CampusDirectory",
    "CourseSelectionAuditSink",
    "CourseSelectionDecisionTransaction",
    "CourseSelectionEnrollmentReader",
    "CourseSelectionEvaluationCatalog",
    "CourseSelectionRepository",
    "CourseSelectionStudentOwnership",
    "CourseSelectionSubmissionTransaction",
    "TermClosureAuditSink",
]
