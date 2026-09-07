"""Academic structure, curriculum, and enrollment application services."""

from dataclasses import replace
from datetime import datetime
from datetime import timedelta
from uuid import UUID

from academics.application.ports import AcademicCatalogRepository
from academics.application.ports import AcademicClock
from academics.application.ports import CampusDirectory
from academics.application.ports import CourseSelectionAuditSink
from academics.application.ports import CourseSelectionRepository
from academics.application.ports import CourseSelectionStudentOwnership
from academics.application.ports import TermClosureAuditSink
from academics.domain.exceptions import AcademicRuleError
from academics.domain.exceptions import CourseSelectionDecisionError
from academics.domain.exceptions import CourseSelectionError
from academics.domain.models import AcademicCalendarEvent
from academics.domain.models import AcademicEnrollmentStatus
from academics.domain.models import AcademicYear
from academics.domain.models import AdministrativeOverride
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
from academics.domain.models import SelectionRuleViolation
from academics.domain.models import StudentAcademicEnrollment
from academics.domain.models import TeacherAssignment
from academics.domain.models import Term
from academics.domain.policies import evaluate_course_selection
from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import NotFoundError
from core.identifiers import new_uuid7

ACADEMICS_STRUCTURE_MANAGE = "academics.structure.manage"
ACADEMICS_CURRICULUM_MANAGE = "academics.curriculum.manage"
ACADEMICS_ENROLLMENT_MANAGE = "academics.enrollment.manage"
ACADEMICS_TERM_CLOSE = "academics.term.close"
ACADEMICS_SELECTION_SUBMIT = "academics.course_selection.submit"
ACADEMICS_SELECTION_APPROVE = "academics.course_selection.approve"
ACADEMICS_SELECTION_OVERRIDE = "academics.course_selection.override"
MAX_ACADEMIC_ADMIN_PAGE_SIZE = 100
MAX_ACADEMIC_CALENDAR_HORIZON = timedelta(days=366)
MAX_TERM_CLOSURE_EXPLANATION_LENGTH = 500


class AcademicAdministrationService:
    """Authorize and validate tenant-owned academic administration changes."""

    def __init__(
        self,
        *,
        catalog: AcademicCatalogRepository,
        campuses: CampusDirectory,
        audit: TermClosureAuditSink,
    ) -> None:
        self._catalog = catalog
        self._campuses = campuses
        self._audit = audit

    async def register_faculty(
        self,
        *,
        context: TenantActorContext,
        faculty: Faculty,
    ) -> None:
        """Register a faculty against an organization-owned campus."""

        _authorize(context, ACADEMICS_STRUCTURE_MANAGE)
        _require_tenant(context, faculty.organization_id)
        if not await self._campuses.campus_exists(
            organization_id=context.organization_id,
            campus_id=faculty.campus_id,
        ):
            raise NotFoundError("Campus was not found.")
        await self._catalog.save_faculty(faculty)

    async def register_department(
        self,
        *,
        context: TenantActorContext,
        department: Department,
    ) -> None:
        """Register a department below an existing tenant faculty."""

        _authorize(context, ACADEMICS_STRUCTURE_MANAGE)
        _require_tenant(context, department.organization_id)
        faculty = await self._catalog.get_faculty(
            organization_id=context.organization_id,
            faculty_id=department.faculty_id,
        )
        if faculty is None:
            raise NotFoundError("Faculty was not found.")
        await self._catalog.save_department(department)

    async def register_program(
        self,
        *,
        context: TenantActorContext,
        program: Program,
    ) -> None:
        """Register a program below an existing tenant department."""

        _authorize(context, ACADEMICS_STRUCTURE_MANAGE)
        _require_tenant(context, program.organization_id)
        department = await self._catalog.get_department(
            organization_id=context.organization_id,
            department_id=program.department_id,
        )
        if department is None:
            raise NotFoundError("Department was not found.")
        await self._catalog.save_program(program)

    async def register_academic_year(
        self,
        *,
        context: TenantActorContext,
        academic_year: AcademicYear,
    ) -> None:
        """Register a tenant academic year."""

        _authorize(context, ACADEMICS_STRUCTURE_MANAGE)
        _require_tenant(context, academic_year.organization_id)
        await self._catalog.save_academic_year(academic_year)

    async def register_term(
        self,
        *,
        context: TenantActorContext,
        term: Term,
    ) -> None:
        """Register a term inside an existing tenant academic year."""

        _authorize(context, ACADEMICS_STRUCTURE_MANAGE)
        _require_tenant(context, term.organization_id)
        academic_year = await self._catalog.get_academic_year(
            organization_id=context.organization_id,
            academic_year_id=term.academic_year_id,
        )
        if academic_year is None:
            raise NotFoundError("Academic year was not found.")
        if (
            term.starts_on < academic_year.starts_on
            or term.ends_on > academic_year.ends_on
        ):
            raise CourseSelectionError("Term dates must fall within the academic year.")
        await self._catalog.save_term(term)

    async def close_term(
        self,
        *,
        context: TenantActorContext,
        term_id: UUID,
        explanation: str,
    ) -> Term:
        """Record authorized intent before closing one tenant term one way.

        Audit and catalog persistence are separate transactions. Recording the
        intent first means an audit record can remain when the catalog write
        later fails, but the term is never closed without prior intent evidence.
        """

        _authorize(context, ACADEMICS_TERM_CLOSE)
        normalized_explanation = explanation.strip()
        if not normalized_explanation:
            raise AcademicRuleError("A term closure explanation is required.")
        if len(normalized_explanation) > MAX_TERM_CLOSURE_EXPLANATION_LENGTH:
            raise AcademicRuleError(
                "Term closure explanation cannot exceed "
                f"{MAX_TERM_CLOSURE_EXPLANATION_LENGTH} characters."
            )

        term = await self._catalog.get_term(
            organization_id=context.organization_id,
            term_id=term_id,
        )
        if term is None:
            raise NotFoundError("Academic term was not found.")
        if term.is_closed:
            return term

        await self._audit.record_term_closure_intent(
            organization_id=context.organization_id,
            actor_subject_id=context.subject_id,
            term_id=term.id,
            correlation_id=context.correlation_id,
            reason=normalized_explanation,
        )
        closed_term = await self._catalog.close_term(
            organization_id=context.organization_id,
            term_id=term.id,
        )
        if closed_term is None:
            # The preceding evidence remains an accurate authorized intent; the
            # separate catalog transaction did not complete the closure.
            raise NotFoundError("Academic term was not found.")
        return closed_term

    async def register_calendar_event(
        self,
        *,
        context: TenantActorContext,
        event: AcademicCalendarEvent,
    ) -> None:
        """Register an organization-wide academic calendar event."""

        _authorize(context, ACADEMICS_STRUCTURE_MANAGE)
        _require_tenant(context, event.organization_id)
        await self._catalog.save_calendar_event(event)

    async def register_course(
        self,
        *,
        context: TenantActorContext,
        course: Course,
    ) -> None:
        """Register an official course below an existing department."""

        _authorize(context, ACADEMICS_STRUCTURE_MANAGE)
        _require_tenant(context, course.organization_id)
        department = await self._catalog.get_department(
            organization_id=context.organization_id,
            department_id=course.department_id,
        )
        if department is None:
            raise NotFoundError("Department was not found.")
        await self._catalog.save_course(course)

    async def register_course_offering(
        self,
        *,
        context: TenantActorContext,
        offering: CourseOffering,
    ) -> None:
        """Register a course offering after validating tenant references."""

        _authorize(context, ACADEMICS_STRUCTURE_MANAGE)
        _require_tenant(context, offering.organization_id)
        course = await self._catalog.get_course(
            organization_id=context.organization_id,
            course_id=offering.course_id,
        )
        term = await self._catalog.get_term(
            organization_id=context.organization_id,
            term_id=offering.term_id,
        )
        campus_exists = await self._campuses.campus_exists(
            organization_id=context.organization_id,
            campus_id=offering.campus_id,
        )
        if course is None or term is None or not campus_exists:
            raise NotFoundError("Course offering reference was not found.")
        await self._catalog.save_course_offering(offering)

    async def register_cohort(
        self,
        *,
        context: TenantActorContext,
        cohort: Cohort,
    ) -> None:
        """Register a tenant program cohort."""

        _authorize(context, ACADEMICS_STRUCTURE_MANAGE)
        _require_tenant(context, cohort.organization_id)
        program = await self._catalog.get_program(
            organization_id=context.organization_id,
            program_id=cohort.program_id,
        )
        academic_year = await self._catalog.get_academic_year(
            organization_id=context.organization_id,
            academic_year_id=cohort.academic_year_id,
        )
        if program is None or academic_year is None:
            raise NotFoundError("Cohort reference was not found.")
        await self._catalog.save_cohort(cohort)

    async def register_room(
        self,
        *,
        context: TenantActorContext,
        room: Room,
    ) -> None:
        """Register a room at an organization-owned campus."""

        _authorize(context, ACADEMICS_STRUCTURE_MANAGE)
        _require_tenant(context, room.organization_id)
        if not await self._campuses.campus_exists(
            organization_id=context.organization_id,
            campus_id=room.campus_id,
        ):
            raise NotFoundError("Campus was not found.")
        await self._catalog.save_room(room)

    async def assign_teacher(
        self,
        *,
        context: TenantActorContext,
        assignment: TeacherAssignment,
    ) -> None:
        """Assign an opaque organization teacher reference to an offering."""

        _authorize(context, ACADEMICS_STRUCTURE_MANAGE)
        _require_tenant(context, assignment.organization_id)
        offering = await self._catalog.get_course_offering(
            organization_id=context.organization_id,
            offering_id=assignment.course_offering_id,
        )
        if offering is None:
            raise NotFoundError("Course offering was not found.")
        await self._catalog.save_teacher_assignment(assignment)

    async def enroll_student(
        self,
        *,
        context: TenantActorContext,
        enrollment: StudentAcademicEnrollment,
    ) -> None:
        """Create an official student academic enrollment."""

        _authorize(context, ACADEMICS_ENROLLMENT_MANAGE)
        _require_tenant(context, enrollment.organization_id)
        program = await self._catalog.get_program(
            organization_id=context.organization_id,
            program_id=enrollment.program_id,
        )
        academic_year = await self._catalog.get_academic_year(
            organization_id=context.organization_id,
            academic_year_id=enrollment.academic_year_id,
        )
        cohort = None
        if enrollment.cohort_id is not None:
            cohort = await self._catalog.get_cohort(
                organization_id=context.organization_id,
                cohort_id=enrollment.cohort_id,
            )
        if program is None or academic_year is None:
            raise NotFoundError("Student enrollment reference was not found.")
        if enrollment.cohort_id is not None and cohort is None:
            raise NotFoundError("Cohort was not found.")
        if cohort is not None and cohort.program_id != enrollment.program_id:
            raise CourseSelectionError("Cohort does not belong to the program.")
        await self._catalog.save_student_enrollment(enrollment)

    async def configure_curriculum(
        self,
        *,
        context: TenantActorContext,
        curriculum: ProgramCurriculum,
    ) -> None:
        """Persist a curriculum after validating all tenant-owned references."""

        _authorize(context, ACADEMICS_CURRICULUM_MANAGE)
        _require_tenant(context, curriculum.organization_id)
        program = await self._catalog.get_program(
            organization_id=context.organization_id,
            program_id=curriculum.program_id,
        )
        academic_year = await self._catalog.get_academic_year(
            organization_id=context.organization_id,
            academic_year_id=curriculum.academic_year_id,
        )
        if program is None or academic_year is None:
            raise NotFoundError("Curriculum reference was not found.")
        for curriculum_course in curriculum.courses:
            course = await self._catalog.get_course(
                organization_id=context.organization_id,
                course_id=curriculum_course.course_id,
            )
            if course is None:
                raise NotFoundError("Curriculum course was not found.")
            for prerequisite_id in curriculum_course.prerequisite_course_ids:
                prerequisite = await self._catalog.get_course(
                    organization_id=context.organization_id,
                    course_id=prerequisite_id,
                )
                if prerequisite is None:
                    raise NotFoundError("Curriculum prerequisite was not found.")
        await self._catalog.save_curriculum(curriculum)

    async def configure_selection_policy(
        self,
        *,
        context: TenantActorContext,
        policy: CourseSelectionPolicy,
    ) -> None:
        """Persist a program and term course-selection policy."""

        _authorize(context, ACADEMICS_CURRICULUM_MANAGE)
        _require_tenant(context, policy.organization_id)
        program = await self._catalog.get_program(
            organization_id=context.organization_id,
            program_id=policy.program_id,
        )
        term = await self._catalog.get_term(
            organization_id=context.organization_id,
            term_id=policy.term_id,
        )
        if program is None or term is None:
            raise NotFoundError("Course-selection policy reference was not found.")
        if program.education_mode is not policy.education_mode:
            raise CourseSelectionError(
                "Selection policy education mode must match the program."
            )
        await self._catalog.save_selection_policy(policy)

    async def list_faculties(
        self,
        *,
        context: TenantActorContext,
        limit: int,
        offset: int,
    ) -> tuple[Faculty, ...]:
        """Return an authorized bounded page of tenant faculties."""

        _authorize(context, ACADEMICS_STRUCTURE_MANAGE)
        _validate_page(limit=limit, offset=offset)
        return await self._catalog.list_faculties(
            organization_id=context.organization_id,
            limit=limit,
            offset=offset,
        )

    async def list_departments(
        self,
        *,
        context: TenantActorContext,
        faculty_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Department, ...]:
        """Return an authorized bounded page of tenant departments."""

        _authorize(context, ACADEMICS_STRUCTURE_MANAGE)
        _validate_page(limit=limit, offset=offset)
        return await self._catalog.list_departments(
            organization_id=context.organization_id,
            faculty_id=faculty_id,
            limit=limit,
            offset=offset,
        )

    async def list_programs(
        self,
        *,
        context: TenantActorContext,
        department_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Program, ...]:
        """Return an authorized bounded page of tenant programs."""

        _authorize(context, ACADEMICS_STRUCTURE_MANAGE)
        _validate_page(limit=limit, offset=offset)
        return await self._catalog.list_programs(
            organization_id=context.organization_id,
            department_id=department_id,
            limit=limit,
            offset=offset,
        )

    async def list_academic_years(
        self,
        *,
        context: TenantActorContext,
        limit: int,
        offset: int,
    ) -> tuple[AcademicYear, ...]:
        """Return an authorized bounded page of tenant academic years."""

        _authorize(context, ACADEMICS_STRUCTURE_MANAGE)
        _validate_page(limit=limit, offset=offset)
        return await self._catalog.list_academic_years(
            organization_id=context.organization_id,
            limit=limit,
            offset=offset,
        )

    async def list_terms(
        self,
        *,
        context: TenantActorContext,
        academic_year_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Term, ...]:
        """Return an authorized bounded page of tenant terms."""

        _authorize(context, ACADEMICS_STRUCTURE_MANAGE)
        _validate_page(limit=limit, offset=offset)
        return await self._catalog.list_terms(
            organization_id=context.organization_id,
            academic_year_id=academic_year_id,
            limit=limit,
            offset=offset,
        )

    async def list_calendar_events(
        self,
        *,
        context: TenantActorContext,
        starts_at: datetime,
        ends_at: datetime,
    ) -> tuple[AcademicCalendarEvent, ...]:
        """Return events intersecting an authorized bounded calendar horizon."""

        _authorize(context, ACADEMICS_STRUCTURE_MANAGE)
        _validate_calendar_horizon(starts_at=starts_at, ends_at=ends_at)
        return await self._catalog.list_calendar_events(
            organization_id=context.organization_id,
            starts_at=starts_at,
            ends_at=ends_at,
        )

    async def list_courses(
        self,
        *,
        context: TenantActorContext,
        department_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Course, ...]:
        """Return an authorized bounded page of tenant courses."""

        _authorize(context, ACADEMICS_STRUCTURE_MANAGE)
        _validate_page(limit=limit, offset=offset)
        return await self._catalog.list_courses(
            organization_id=context.organization_id,
            department_id=department_id,
            limit=limit,
            offset=offset,
        )

    async def list_course_offerings(
        self,
        *,
        context: TenantActorContext,
        term_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[CourseOffering, ...]:
        """Return an authorized bounded page of tenant course offerings."""

        _authorize(context, ACADEMICS_STRUCTURE_MANAGE)
        _validate_page(limit=limit, offset=offset)
        return await self._catalog.list_course_offerings(
            organization_id=context.organization_id,
            term_id=term_id,
            limit=limit,
            offset=offset,
        )

    async def list_cohorts(
        self,
        *,
        context: TenantActorContext,
        program_id: UUID | None,
        academic_year_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Cohort, ...]:
        """Return an authorized bounded page of tenant cohorts."""

        _authorize(context, ACADEMICS_STRUCTURE_MANAGE)
        _validate_page(limit=limit, offset=offset)
        return await self._catalog.list_cohorts(
            organization_id=context.organization_id,
            program_id=program_id,
            academic_year_id=academic_year_id,
            limit=limit,
            offset=offset,
        )

    async def list_rooms(
        self,
        *,
        context: TenantActorContext,
        campus_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Room, ...]:
        """Return an authorized bounded page of tenant rooms."""

        _authorize(context, ACADEMICS_STRUCTURE_MANAGE)
        _validate_page(limit=limit, offset=offset)
        return await self._catalog.list_rooms_page(
            organization_id=context.organization_id,
            campus_id=campus_id,
            limit=limit,
            offset=offset,
        )

    async def list_teacher_assignments(
        self,
        *,
        context: TenantActorContext,
        course_offering_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[TeacherAssignment, ...]:
        """Return an authorized bounded page of tenant teacher assignments."""

        _authorize(context, ACADEMICS_STRUCTURE_MANAGE)
        _validate_page(limit=limit, offset=offset)
        return await self._catalog.list_teacher_assignments(
            organization_id=context.organization_id,
            course_offering_id=course_offering_id,
            limit=limit,
            offset=offset,
        )

    async def list_student_enrollments(
        self,
        *,
        context: TenantActorContext,
        student_id: UUID | None,
        program_id: UUID | None,
        academic_year_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[StudentAcademicEnrollment, ...]:
        """Return an authorized bounded page of official student enrollments."""

        _authorize(context, ACADEMICS_ENROLLMENT_MANAGE)
        _validate_page(limit=limit, offset=offset)
        return await self._catalog.list_student_enrollments(
            organization_id=context.organization_id,
            student_id=student_id,
            program_id=program_id,
            academic_year_id=academic_year_id,
            limit=limit,
            offset=offset,
        )

    async def get_curriculum(
        self,
        *,
        context: TenantActorContext,
        program_id: UUID,
        academic_year_id: UUID,
    ) -> ProgramCurriculum:
        """Return one authorized tenant curriculum configuration."""

        _authorize(context, ACADEMICS_CURRICULUM_MANAGE)
        curriculum = await self._catalog.get_curriculum(
            organization_id=context.organization_id,
            program_id=program_id,
            academic_year_id=academic_year_id,
        )
        if curriculum is None:
            raise NotFoundError("Program curriculum was not found.")
        return curriculum

    async def get_selection_policy(
        self,
        *,
        context: TenantActorContext,
        program_id: UUID,
        term_id: UUID,
    ) -> CourseSelectionPolicy:
        """Return one authorized tenant course-selection policy."""

        _authorize(context, ACADEMICS_CURRICULUM_MANAGE)
        policy = await self._catalog.get_selection_policy(
            organization_id=context.organization_id,
            program_id=program_id,
            term_id=term_id,
        )
        if policy is None:
            raise NotFoundError("Course-selection policy was not found.")
        return policy


class CourseSelectionService:
    """Submit and decide course selections under explicit tenant policy."""

    def __init__(
        self,
        *,
        catalog: AcademicCatalogRepository,
        selections: CourseSelectionRepository,
        clock: AcademicClock,
        audit: CourseSelectionAuditSink,
        ownership: CourseSelectionStudentOwnership,
    ) -> None:
        self._catalog = catalog
        self._selections = selections
        self._clock = clock
        self._audit = audit
        self._ownership = ownership

    async def list_requests(
        self,
        *,
        context: TenantActorContext,
        status: CourseSelectionStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[CourseSelectionRequest, ...]:
        """Return an authorized bounded page of tenant selection requests."""

        _authorize(context, ACADEMICS_SELECTION_APPROVE)
        _validate_page(limit=limit, offset=offset)
        return await self._selections.list_selection_requests(
            organization_id=context.organization_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def submit(
        self,
        *,
        context: TenantActorContext,
        student_academic_enrollment_id: UUID,
        term_id: UUID,
        offering_ids: tuple[UUID, ...],
        override_reason: str | None = None,
    ) -> CourseSelectionRequest:
        """Validate and persist a tenant-bound course-selection request."""

        _authorize(context, ACADEMICS_SELECTION_SUBMIT)
        enrollment = await self._catalog.get_student_enrollment(
            organization_id=context.organization_id,
            enrollment_id=student_academic_enrollment_id,
        )
        if enrollment is None:
            raise NotFoundError("Student academic enrollment was not found.")
        await self._authorize_submission_scope(
            context=context,
            student_profile_id=enrollment.student_id,
        )
        if enrollment.status is not AcademicEnrollmentStatus.ACTIVE:
            raise CourseSelectionError("Student academic enrollment is not active.")
        policy = await self._catalog.get_selection_policy(
            organization_id=context.organization_id,
            program_id=enrollment.program_id,
            term_id=term_id,
        )
        curriculum = await self._catalog.get_curriculum(
            organization_id=context.organization_id,
            program_id=enrollment.program_id,
            academic_year_id=enrollment.academic_year_id,
        )
        if policy is None or curriculum is None:
            raise NotFoundError("Course-selection configuration was not found.")

        offerings = await self._resolve_offerings(
            organization_id=context.organization_id,
            offering_ids=offering_ids,
            term_id=term_id,
        )
        existing_enrollments = await self._selections.list_course_enrollments(
            organization_id=context.organization_id,
            student_academic_enrollment_id=enrollment.id,
        )
        existing_offerings = await self._resolve_existing_offerings(
            organization_id=context.organization_id,
            enrollments=existing_enrollments,
        )
        completed_course_ids = frozenset(
            offering.course_id
            for course_enrollment, offering in zip(
                existing_enrollments,
                existing_offerings,
                strict=True,
            )
            if course_enrollment.status is CourseEnrollmentStatus.COMPLETED
        )
        current_term_pairs = tuple(
            (course_enrollment, offering)
            for course_enrollment, offering in zip(
                existing_enrollments,
                existing_offerings,
                strict=True,
            )
            if offering.term_id == term_id
        )
        submitted_at = self._clock.now()
        evaluation = evaluate_course_selection(
            policy=policy,
            curriculum=curriculum,
            selected_offerings=offerings,
            existing_enrollments=tuple(
                course_enrollment for course_enrollment, _offering in current_term_pairs
            ),
            existing_offerings=tuple(
                offering
                for course_enrollment, offering in current_term_pairs
                if course_enrollment.status is CourseEnrollmentStatus.ENROLLED
            ),
            completed_course_ids=completed_course_ids,
            submitted_at=submitted_at,
        )
        override = self._resolve_override(
            context=context,
            violations=evaluation.violations,
            reason=override_reason,
            created_at=submitted_at,
        )
        status = (
            CourseSelectionStatus.PENDING
            if policy.approval_required
            else CourseSelectionStatus.APPROVED
        )
        request = CourseSelectionRequest(
            id=new_uuid7(),
            organization_id=context.organization_id,
            student_academic_enrollment_id=enrollment.id,
            term_id=term_id,
            offering_ids=offering_ids,
            requested_credits=evaluation.requested_credits,
            status=status,
            submitted_at=submitted_at,
            submitted_by=context.subject_id,
            override=override,
            decided_at=(
                submitted_at if status is CourseSelectionStatus.APPROVED else None
            ),
            decided_by=(
                context.subject_id if status is CourseSelectionStatus.APPROVED else None
            ),
        )
        resulting_enrollments = (
            self._build_course_enrollments(
                request=request,
                curriculum=curriculum,
                offerings=offerings,
                actor_time=submitted_at,
            )
            if status is CourseSelectionStatus.APPROVED
            else ()
        )
        await self._selections.save_submission(
            request=request,
            enrollments=resulting_enrollments,
            offering_capacities={
                offering.id: offering.capacity for offering in offerings
            },
        )
        if request.override is not None:
            await self._audit.record_course_selection_event(
                action="academics.course_selection.override_applied",
                organization_id=context.organization_id,
                actor_subject_id=context.subject_id,
                request_id=request.id,
                correlation_id=context.correlation_id,
            )
        return request

    async def decide(
        self,
        *,
        context: TenantActorContext,
        request_id: UUID,
        approved: bool,
        reason: str | None = None,
    ) -> CourseSelectionRequest:
        """Approve or reject one pending tenant-bound selection request."""

        _authorize(context, ACADEMICS_SELECTION_APPROVE)
        request = await self._selections.get_selection_request(
            organization_id=context.organization_id,
            request_id=request_id,
        )
        if request is None:
            raise NotFoundError("Course-selection request was not found.")
        if request.status is not CourseSelectionStatus.PENDING:
            raise CourseSelectionDecisionError(
                "Only pending course-selection requests can be decided."
            )
        if not approved and not (reason or "").strip():
            raise CourseSelectionDecisionError("A rejection reason is required.")
        decided_at = self._clock.now()
        decided_request = replace(
            request,
            status=(
                CourseSelectionStatus.APPROVED
                if approved
                else CourseSelectionStatus.REJECTED
            ),
            decided_at=decided_at,
            decided_by=context.subject_id,
            rejection_reason=None if approved else reason,
        )
        approval = CourseSelectionApproval(
            id=new_uuid7(),
            organization_id=context.organization_id,
            request_id=request.id,
            actor_id=context.subject_id,
            approved=approved,
            decided_at=decided_at,
            reason=reason,
        )
        offerings = await self._resolve_offerings(
            organization_id=context.organization_id,
            offering_ids=request.offering_ids,
            term_id=request.term_id,
        )
        enrollment = await self._catalog.get_student_enrollment(
            organization_id=context.organization_id,
            enrollment_id=request.student_academic_enrollment_id,
        )
        if enrollment is None:
            raise NotFoundError("Student academic enrollment was not found.")
        curriculum = await self._catalog.get_curriculum(
            organization_id=context.organization_id,
            program_id=enrollment.program_id,
            academic_year_id=enrollment.academic_year_id,
        )
        if curriculum is None:
            raise NotFoundError("Program curriculum was not found.")
        resulting_enrollments = (
            self._build_course_enrollments(
                request=decided_request,
                curriculum=curriculum,
                offerings=offerings,
                actor_time=decided_at,
            )
            if approved
            else ()
        )
        await self._selections.save_decision(
            request=decided_request,
            approval=approval,
            enrollments=resulting_enrollments,
            offering_capacities={
                offering.id: offering.capacity for offering in offerings
            },
        )
        await self._audit.record_course_selection_event(
            action=(
                "academics.course_selection.approved"
                if approved
                else "academics.course_selection.rejected"
            ),
            organization_id=context.organization_id,
            actor_subject_id=context.subject_id,
            request_id=request.id,
            correlation_id=context.correlation_id,
        )
        return decided_request

    async def _authorize_submission_scope(
        self,
        *,
        context: TenantActorContext,
        student_profile_id: UUID,
    ) -> None:
        """Allow administrators or exact membership-linked student ownership."""

        if ACADEMICS_ENROLLMENT_MANAGE in context.permissions:
            return
        if not await self._ownership.actor_owns_student_profile(
            actor=context,
            student_profile_id=student_profile_id,
        ):
            raise AuthorizationError(
                "Course selection is not owned by the active membership."
            )

    async def _resolve_offerings(
        self,
        *,
        organization_id: UUID,
        offering_ids: tuple[UUID, ...],
        term_id: UUID,
    ) -> tuple[CourseOffering, ...]:
        """Resolve offering identifiers without permitting tenant mismatch."""

        resolved: list[CourseOffering] = []
        for offering_id in offering_ids:
            offering = await self._catalog.get_course_offering(
                organization_id=organization_id,
                offering_id=offering_id,
            )
            if offering is None or offering.term_id != term_id:
                raise NotFoundError("Course offering was not found for the term.")
            resolved.append(offering)
        return tuple(resolved)

    async def _resolve_existing_offerings(
        self,
        *,
        organization_id: UUID,
        enrollments: tuple[CourseEnrollment, ...],
    ) -> tuple[CourseOffering, ...]:
        """Resolve the offering for every existing official enrollment."""

        resolved: list[CourseOffering] = []
        for enrollment in enrollments:
            offering = await self._catalog.get_course_offering(
                organization_id=organization_id,
                offering_id=enrollment.course_offering_id,
            )
            if offering is None:
                raise NotFoundError("Existing course offering was not found.")
            resolved.append(offering)
        return tuple(resolved)

    @staticmethod
    def _resolve_override(
        *,
        context: TenantActorContext,
        violations: tuple[SelectionRuleViolation, ...],
        reason: str | None,
        created_at: datetime,
    ) -> AdministrativeOverride | None:
        """Require an audited, permissioned override for failed rules."""

        if not violations:
            if reason is not None:
                raise CourseSelectionError(
                    "An override reason is not accepted when no rule failed."
                )
            return None
        _authorize(context, ACADEMICS_SELECTION_OVERRIDE)
        if not (reason or "").strip():
            codes = ", ".join(violation.code for violation in violations)
            raise CourseSelectionError(f"Course selection violates: {codes}.")
        return AdministrativeOverride(
            actor_id=context.subject_id,
            reason=reason or "",
            created_at=created_at,
            violated_rules=violations,
        )

    @staticmethod
    def _build_course_enrollments(
        *,
        request: CourseSelectionRequest,
        curriculum: ProgramCurriculum,
        offerings: tuple[CourseOffering, ...],
        actor_time: datetime,
    ) -> tuple[CourseEnrollment, ...]:
        """Build official course enrollments from an approved request."""

        result: list[CourseEnrollment] = []
        for offering in offerings:
            curriculum_course = curriculum.course(offering.course_id)
            if curriculum_course is None:
                raise CourseSelectionError(
                    "Approved offering is not present in the curriculum."
                )
            result.append(
                CourseEnrollment(
                    id=new_uuid7(),
                    organization_id=request.organization_id,
                    student_academic_enrollment_id=(
                        request.student_academic_enrollment_id
                    ),
                    course_offering_id=offering.id,
                    credits=curriculum_course.credits,
                    status=CourseEnrollmentStatus.ENROLLED,
                    enrolled_at=actor_time,
                    selection_request_id=request.id,
                )
            )
        return tuple(result)


def _authorize(
    context: TenantActorContext,
    permission: str,
) -> None:
    """Fail closed unless the trusted tenant actor has one permission."""

    if permission not in context.permissions:
        raise AuthorizationError("Required academic permission is missing.")


def _validate_page(*, limit: int, offset: int) -> None:
    """Require a bounded non-negative administrative page."""

    if limit < 1 or limit > MAX_ACADEMIC_ADMIN_PAGE_SIZE or offset < 0:
        raise AcademicRuleError(
            f"Academic page limit must be 1-{MAX_ACADEMIC_ADMIN_PAGE_SIZE} "
            "and offset cannot be negative."
        )


def _validate_calendar_horizon(*, starts_at: datetime, ends_at: datetime) -> None:
    """Require a timezone-aware calendar interval of at most one year."""

    if starts_at.tzinfo is None or starts_at.utcoffset() is None:
        raise AcademicRuleError("Calendar horizon start must be timezone-aware.")
    if ends_at.tzinfo is None or ends_at.utcoffset() is None:
        raise AcademicRuleError("Calendar horizon end must be timezone-aware.")
    if starts_at >= ends_at:
        raise AcademicRuleError("Calendar horizon end must follow its start.")
    if ends_at - starts_at > MAX_ACADEMIC_CALENDAR_HORIZON:
        raise AcademicRuleError("Calendar horizon cannot exceed 366 days.")


def _require_tenant(
    context: TenantActorContext,
    resource_organization_id: UUID,
) -> None:
    """Reject a resource whose ownership differs from trusted tenant context."""

    if resource_organization_id != context.organization_id:
        raise NotFoundError("Academic resource was not found.")


__all__ = [
    "ACADEMICS_CURRICULUM_MANAGE",
    "ACADEMICS_ENROLLMENT_MANAGE",
    "ACADEMICS_SELECTION_APPROVE",
    "ACADEMICS_SELECTION_OVERRIDE",
    "ACADEMICS_SELECTION_SUBMIT",
    "ACADEMICS_STRUCTURE_MANAGE",
    "ACADEMICS_TERM_CLOSE",
    "MAX_ACADEMIC_ADMIN_PAGE_SIZE",
    "MAX_ACADEMIC_CALENDAR_HORIZON",
    "MAX_TERM_CLOSURE_EXPLANATION_LENGTH",
    "AcademicAdministrationService",
    "CourseSelectionService",
]
