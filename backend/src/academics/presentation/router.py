"""Thin FastAPI routes for academic administration and course selection."""

from datetime import date
from datetime import datetime
from datetime import time
from decimal import Decimal
from typing import Annotated
from typing import cast
from uuid import UUID

from fastapi import APIRouter
from fastapi import Query
from fastapi import Request
from fastapi import status
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from academics.application.read_models import CourseSelectionEnrollmentOption
from academics.application.read_models import CourseSelectionOfferingOption
from academics.application.read_models import CourseSelectionTermOption
from academics.application.read_models import StudentCourseSelectionContext
from academics.application.service import MAX_ENROLLMENT_TRANSITION_EXPLANATION_LENGTH
from academics.application.service import MAX_TERM_CLOSURE_EXPLANATION_LENGTH
from academics.application.service import AcademicAdministrationService
from academics.application.service import AcademicEnrollmentTransitionService
from academics.application.service import CourseSelectionService
from academics.domain.models import AcademicCalendarEvent
from academics.domain.models import AcademicEnrollmentStatus
from academics.domain.models import AcademicYear
from academics.domain.models import Cohort
from academics.domain.models import Course
from academics.domain.models import CourseEnrollment
from academics.domain.models import CourseEnrollmentStatus
from academics.domain.models import CourseOffering
from academics.domain.models import CourseSelectionPolicy
from academics.domain.models import CourseSelectionRequest
from academics.domain.models import CourseSelectionStatus
from academics.domain.models import CurriculumCourse
from academics.domain.models import CurriculumCourseKind
from academics.domain.models import Department
from academics.domain.models import EducationMode
from academics.domain.models import Faculty
from academics.domain.models import MeetingWindow
from academics.domain.models import Program
from academics.domain.models import ProgramCurriculum
from academics.domain.models import Room
from academics.domain.models import StudentAcademicEnrollment
from academics.domain.models import TeacherAssignment
from academics.domain.models import Term
from core.context import PlatformActorContext
from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.identifiers import new_uuid7
from identity import ActorDep
from identity import CSRFDep

PageLimit = Annotated[int, Query(ge=1, le=100)]
PageOffset = Annotated[int, Query(ge=0)]


class _FrozenModel(BaseModel):
    """Apply the immutable request/response convention to local schemas."""

    model_config = ConfigDict(frozen=True)


class FacultyBody(_FrozenModel):
    campus_id: UUID
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)


class FacultyResponse(FacultyBody):
    id: UUID

    @classmethod
    def from_domain(cls, value: Faculty) -> FacultyResponse:
        return cls(
            id=value.id, campus_id=value.campus_id, code=value.code, name=value.name
        )


class DepartmentBody(_FrozenModel):
    faculty_id: UUID
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)


class DepartmentResponse(DepartmentBody):
    id: UUID

    @classmethod
    def from_domain(cls, value: Department) -> DepartmentResponse:
        return cls(
            id=value.id,
            faculty_id=value.faculty_id,
            code=value.code,
            name=value.name,
        )


class ProgramBody(_FrozenModel):
    department_id: UUID
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    education_mode: EducationMode
    credit_unit_label: str = Field(min_length=1, max_length=64)


class ProgramResponse(ProgramBody):
    id: UUID

    @classmethod
    def from_domain(cls, value: Program) -> ProgramResponse:
        return cls(
            id=value.id,
            department_id=value.department_id,
            code=value.code,
            name=value.name,
            education_mode=value.education_mode,
            credit_unit_label=value.credit_unit_label,
        )


class AcademicYearBody(_FrozenModel):
    name: str = Field(min_length=1, max_length=128)
    starts_on: date
    ends_on: date


class AcademicYearResponse(AcademicYearBody):
    id: UUID

    @classmethod
    def from_domain(cls, value: AcademicYear) -> AcademicYearResponse:
        return cls(
            id=value.id,
            name=value.name,
            starts_on=value.starts_on,
            ends_on=value.ends_on,
        )


class TermBody(_FrozenModel):
    academic_year_id: UUID
    name: str = Field(min_length=1, max_length=128)
    starts_on: date
    ends_on: date
    enrollment_deadline: datetime


class TermClosureBody(_FrozenModel):
    explanation: str = Field(
        min_length=1,
        max_length=MAX_TERM_CLOSURE_EXPLANATION_LENGTH,
    )


class TermResponse(TermBody):
    id: UUID
    is_closed: bool

    @classmethod
    def from_domain(cls, value: Term) -> TermResponse:
        return cls(
            id=value.id,
            academic_year_id=value.academic_year_id,
            name=value.name,
            starts_on=value.starts_on,
            ends_on=value.ends_on,
            enrollment_deadline=value.enrollment_deadline,
            is_closed=value.is_closed,
        )


class CalendarEventBody(_FrozenModel):
    title: str = Field(min_length=1, max_length=255)
    starts_at: datetime
    ends_at: datetime
    instruction_allowed: bool


class CalendarEventResponse(CalendarEventBody):
    id: UUID

    @classmethod
    def from_domain(cls, value: AcademicCalendarEvent) -> CalendarEventResponse:
        return cls(
            id=value.id,
            title=value.title,
            starts_at=value.starts_at,
            ends_at=value.ends_at,
            instruction_allowed=value.instruction_allowed,
        )


class CourseBody(_FrozenModel):
    department_id: UUID
    code: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    credits: Decimal = Field(gt=0)


class CourseResponse(CourseBody):
    id: UUID

    @classmethod
    def from_domain(cls, value: Course) -> CourseResponse:
        return cls(
            id=value.id,
            department_id=value.department_id,
            code=value.code,
            title=value.title,
            credits=value.credits,
        )


class MeetingWindowBody(_FrozenModel):
    weekday: int = Field(ge=1, le=7)
    starts_at: time
    ends_at: time


class CourseOfferingBody(_FrozenModel):
    course_id: UUID
    term_id: UUID
    campus_id: UUID
    section_code: str = Field(min_length=1, max_length=64)
    capacity: int = Field(gt=0)
    meeting_windows: tuple[MeetingWindowBody, ...] = ()


class CourseOfferingResponse(CourseOfferingBody):
    id: UUID

    @classmethod
    def from_domain(cls, value: CourseOffering) -> CourseOfferingResponse:
        return cls(
            id=value.id,
            course_id=value.course_id,
            term_id=value.term_id,
            campus_id=value.campus_id,
            section_code=value.section_code,
            capacity=value.capacity,
            meeting_windows=tuple(
                MeetingWindowBody(
                    weekday=meeting.weekday,
                    starts_at=meeting.starts_at,
                    ends_at=meeting.ends_at,
                )
                for meeting in value.meeting_windows
            ),
        )


class CohortBody(_FrozenModel):
    program_id: UUID
    academic_year_id: UUID
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)


class CohortResponse(CohortBody):
    id: UUID

    @classmethod
    def from_domain(cls, value: Cohort) -> CohortResponse:
        return cls(
            id=value.id,
            program_id=value.program_id,
            academic_year_id=value.academic_year_id,
            code=value.code,
            name=value.name,
        )


class RoomBody(_FrozenModel):
    campus_id: UUID
    code: str = Field(min_length=1, max_length=64)
    room_type: str = Field(min_length=1, max_length=64)
    capacity: int = Field(gt=0)


class RoomResponse(RoomBody):
    id: UUID

    @classmethod
    def from_domain(cls, value: Room) -> RoomResponse:
        return cls(
            id=value.id,
            campus_id=value.campus_id,
            code=value.code,
            room_type=value.room_type,
            capacity=value.capacity,
        )


class TeacherAssignmentBody(_FrozenModel):
    course_offering_id: UUID
    teacher_id: UUID
    role: str = Field(min_length=1, max_length=64)


class TeacherAssignmentResponse(TeacherAssignmentBody):
    id: UUID

    @classmethod
    def from_domain(cls, value: TeacherAssignment) -> TeacherAssignmentResponse:
        return cls(
            id=value.id,
            course_offering_id=value.course_offering_id,
            teacher_id=value.teacher_id,
            role=value.role,
        )


class StudentEnrollmentBody(_FrozenModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    student_id: UUID
    program_id: UUID
    academic_year_id: UUID
    cohort_id: UUID | None = None
    enrolled_at: datetime


class StudentEnrollmentResponse(StudentEnrollmentBody):
    id: UUID
    status: AcademicEnrollmentStatus

    @classmethod
    def from_domain(cls, value: StudentAcademicEnrollment) -> StudentEnrollmentResponse:
        return cls(
            id=value.id,
            student_id=value.student_id,
            program_id=value.program_id,
            academic_year_id=value.academic_year_id,
            cohort_id=value.cohort_id,
            status=value.status,
            enrolled_at=value.enrolled_at,
        )


class EnrollmentTransitionBody(_FrozenModel):
    """Carry the required explanation for one audited enrollment transition."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    explanation: str = Field(
        min_length=1,
        max_length=MAX_ENROLLMENT_TRANSITION_EXPLANATION_LENGTH,
    )


class CourseEnrollmentResponse(_FrozenModel):
    """Serialize one official course enrollment lifecycle fact."""

    id: UUID
    student_academic_enrollment_id: UUID
    course_offering_id: UUID
    credits: Decimal
    status: CourseEnrollmentStatus
    enrolled_at: datetime
    selection_request_id: UUID | None

    @classmethod
    def from_domain(cls, value: CourseEnrollment) -> CourseEnrollmentResponse:
        return cls(
            id=value.id,
            student_academic_enrollment_id=value.student_academic_enrollment_id,
            course_offering_id=value.course_offering_id,
            credits=value.credits,
            status=value.status,
            enrolled_at=value.enrolled_at,
            selection_request_id=value.selection_request_id,
        )


class CurriculumCourseBody(_FrozenModel):
    course_id: UUID
    kind: CurriculumCourseKind
    credits: Decimal = Field(gt=0)
    prerequisite_course_ids: frozenset[UUID] = frozenset()


class CurriculumBody(_FrozenModel):
    program_id: UUID
    academic_year_id: UUID
    courses: tuple[CurriculumCourseBody, ...]


class CurriculumResponse(CurriculumBody):
    id: UUID

    @classmethod
    def from_domain(cls, value: ProgramCurriculum) -> CurriculumResponse:
        return cls(
            id=value.id,
            program_id=value.program_id,
            academic_year_id=value.academic_year_id,
            courses=tuple(
                CurriculumCourseBody(
                    course_id=course.course_id,
                    kind=course.kind,
                    credits=course.credits,
                    prerequisite_course_ids=course.prerequisite_course_ids,
                )
                for course in value.courses
            ),
        )


class SelectionPolicyBody(_FrozenModel):
    education_mode: EducationMode
    maximum_credits: Decimal = Field(gt=0)
    deadline: datetime
    approval_required: bool


class SelectionPolicyResponse(SelectionPolicyBody):
    program_id: UUID
    term_id: UUID

    @classmethod
    def from_domain(cls, value: CourseSelectionPolicy) -> SelectionPolicyResponse:
        return cls(
            program_id=value.program_id,
            term_id=value.term_id,
            education_mode=value.education_mode,
            maximum_credits=value.maximum_credits,
            deadline=value.deadline,
            approval_required=value.approval_required,
        )


class CourseSelectionSubmissionBody(_FrozenModel):
    student_academic_enrollment_id: UUID
    term_id: UUID
    offering_ids: tuple[UUID, ...] = Field(min_length=1)
    override_reason: str | None = Field(default=None, max_length=1000)


class CourseSelectionDecisionBody(_FrozenModel):
    approved: bool
    reason: str | None = Field(default=None, max_length=1000)


class CourseSelectionResponse(_FrozenModel):
    id: UUID
    student_academic_enrollment_id: UUID
    term_id: UUID
    offering_ids: tuple[UUID, ...]
    requested_credits: Decimal
    status: str
    override_reason: str | None
    overridden_rules: tuple[str, ...]
    rejection_reason: str | None

    @classmethod
    def from_domain(cls, value: CourseSelectionRequest) -> CourseSelectionResponse:
        return cls(
            id=value.id,
            student_academic_enrollment_id=value.student_academic_enrollment_id,
            term_id=value.term_id,
            offering_ids=value.offering_ids,
            requested_credits=value.requested_credits,
            status=value.status,
            override_reason=value.override.reason if value.override else None,
            overridden_rules=(
                tuple(item.code for item in value.override.violated_rules)
                if value.override
                else ()
            ),
            rejection_reason=value.rejection_reason,
        )


class CourseSelectionOfferingOptionResponse(_FrozenModel):
    """Serialize one curriculum-backed selectable course offering."""

    id: UUID
    course_id: UUID
    course_code: str
    course_title: str
    section_code: str
    credits: Decimal
    capacity: int
    meeting_windows: tuple[MeetingWindowBody, ...]

    @classmethod
    def from_application(
        cls,
        value: CourseSelectionOfferingOption,
    ) -> CourseSelectionOfferingOptionResponse:
        """Map one owned selection offering to its safe response."""

        return cls(
            id=value.id,
            course_id=value.course_id,
            course_code=value.course_code,
            course_title=value.course_title,
            section_code=value.section_code,
            credits=value.credits,
            capacity=value.capacity,
            meeting_windows=tuple(
                MeetingWindowBody(
                    weekday=meeting.weekday,
                    starts_at=meeting.starts_at,
                    ends_at=meeting.ends_at,
                )
                for meeting in value.meeting_windows
            ),
        )


class CourseSelectionTermOptionResponse(_FrozenModel):
    """Serialize one open term and its bounded selectable offerings."""

    id: UUID
    name: str
    starts_on: date
    ends_on: date
    deadline: datetime
    maximum_credits: Decimal
    approval_required: bool
    offerings: tuple[CourseSelectionOfferingOptionResponse, ...]

    @classmethod
    def from_application(
        cls,
        value: CourseSelectionTermOption,
    ) -> CourseSelectionTermOptionResponse:
        """Map one owned selection term to its safe response."""

        return cls(
            id=value.id,
            name=value.name,
            starts_on=value.starts_on,
            ends_on=value.ends_on,
            deadline=value.deadline,
            maximum_credits=value.maximum_credits,
            approval_required=value.approval_required,
            offerings=tuple(
                CourseSelectionOfferingOptionResponse.from_application(offering)
                for offering in value.offerings
            ),
        )


class CourseSelectionEnrollmentOptionResponse(_FrozenModel):
    """Serialize one actor-owned active enrollment and selectable terms."""

    id: UUID
    program_id: UUID
    program_name: str
    academic_year_id: UUID
    terms: tuple[CourseSelectionTermOptionResponse, ...]

    @classmethod
    def from_application(
        cls,
        value: CourseSelectionEnrollmentOption,
    ) -> CourseSelectionEnrollmentOptionResponse:
        """Map one owned enrollment to its safe response."""

        return cls(
            id=value.id,
            program_id=value.program_id,
            program_name=value.program_name,
            academic_year_id=value.academic_year_id,
            terms=tuple(
                CourseSelectionTermOptionResponse.from_application(term)
                for term in value.terms
            ),
        )


class StudentCourseSelectionContextResponse(_FrozenModel):
    """Serialize bounded choices discovered for the current student actor."""

    student_profile_id: UUID
    enrollments: tuple[CourseSelectionEnrollmentOptionResponse, ...]

    @classmethod
    def from_application(
        cls,
        value: StudentCourseSelectionContext,
    ) -> StudentCourseSelectionContextResponse:
        """Map exact actor-owned selection context to its safe response."""

        return cls(
            student_profile_id=value.student_profile_id,
            enrollments=tuple(
                CourseSelectionEnrollmentOptionResponse.from_application(enrollment)
                for enrollment in value.enrollments
            ),
        )


def _tenant_actor(
    actor: PlatformActorContext | TenantActorContext,
) -> TenantActorContext:
    if not isinstance(actor, TenantActorContext):
        raise AuthorizationError("A tenant actor is required.")
    return actor


def _administration_service(request: Request) -> AcademicAdministrationService:
    service: object = getattr(
        request.app.state, "academic_administration_service", None
    )
    if not isinstance(service, AcademicAdministrationService):
        raise RuntimeError("AcademicAdministrationService was not composed.")
    return service


def _selection_service(request: Request) -> CourseSelectionService:
    service: object = getattr(request.app.state, "course_selection_service", None)
    if not isinstance(service, CourseSelectionService):
        raise RuntimeError("CourseSelectionService was not composed.")
    return service


def _enrollment_transition_service(
    request: Request,
) -> AcademicEnrollmentTransitionService:
    service: object = getattr(
        request.app.state, "academic_enrollment_transition_service", None
    )
    if not isinstance(service, AcademicEnrollmentTransitionService):
        raise RuntimeError("AcademicEnrollmentTransitionService was not composed.")
    return service


router = APIRouter(prefix="/api/v1/academics", tags=["academics"])


@router.post(
    "/faculties", response_model=FacultyResponse, status_code=status.HTTP_201_CREATED
)
async def create_faculty(
    body: FacultyBody, request: Request, actor: ActorDep, _csrf: CSRFDep
) -> FacultyResponse:
    context = _tenant_actor(actor)
    value = Faculty(
        id=new_uuid7(), organization_id=context.organization_id, **body.model_dump()
    )
    await _administration_service(request).register_faculty(
        context=context, faculty=value
    )
    return FacultyResponse.from_domain(value)


@router.get("/faculties", response_model=tuple[FacultyResponse, ...])
async def list_faculties(
    request: Request, actor: ActorDep, limit: PageLimit = 50, offset: PageOffset = 0
) -> tuple[FacultyResponse, ...]:
    values = await _administration_service(request).list_faculties(
        context=_tenant_actor(actor), limit=limit, offset=offset
    )
    return tuple(FacultyResponse.from_domain(value) for value in values)


@router.post(
    "/departments",
    response_model=DepartmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_department(
    body: DepartmentBody, request: Request, actor: ActorDep, _csrf: CSRFDep
) -> DepartmentResponse:
    context = _tenant_actor(actor)
    value = Department(
        id=new_uuid7(), organization_id=context.organization_id, **body.model_dump()
    )
    await _administration_service(request).register_department(
        context=context, department=value
    )
    return DepartmentResponse.from_domain(value)


@router.get("/departments", response_model=tuple[DepartmentResponse, ...])
async def list_departments(
    request: Request,
    actor: ActorDep,
    faculty_id: UUID | None = None,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> tuple[DepartmentResponse, ...]:
    values = await _administration_service(request).list_departments(
        context=_tenant_actor(actor), faculty_id=faculty_id, limit=limit, offset=offset
    )
    return tuple(DepartmentResponse.from_domain(value) for value in values)


@router.post(
    "/programs", response_model=ProgramResponse, status_code=status.HTTP_201_CREATED
)
async def create_program(
    body: ProgramBody, request: Request, actor: ActorDep, _csrf: CSRFDep
) -> ProgramResponse:
    context = _tenant_actor(actor)
    value = Program(
        id=new_uuid7(), organization_id=context.organization_id, **body.model_dump()
    )
    await _administration_service(request).register_program(
        context=context, program=value
    )
    return ProgramResponse.from_domain(value)


@router.get("/programs", response_model=tuple[ProgramResponse, ...])
async def list_programs(
    request: Request,
    actor: ActorDep,
    department_id: UUID | None = None,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> tuple[ProgramResponse, ...]:
    values = await _administration_service(request).list_programs(
        context=_tenant_actor(actor),
        department_id=department_id,
        limit=limit,
        offset=offset,
    )
    return tuple(ProgramResponse.from_domain(value) for value in values)


@router.post(
    "/academic-years",
    response_model=AcademicYearResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_academic_year(
    body: AcademicYearBody, request: Request, actor: ActorDep, _csrf: CSRFDep
) -> AcademicYearResponse:
    context = _tenant_actor(actor)
    value = AcademicYear(
        id=new_uuid7(), organization_id=context.organization_id, **body.model_dump()
    )
    await _administration_service(request).register_academic_year(
        context=context, academic_year=value
    )
    return AcademicYearResponse.from_domain(value)


@router.get("/academic-years", response_model=tuple[AcademicYearResponse, ...])
async def list_academic_years(
    request: Request, actor: ActorDep, limit: PageLimit = 50, offset: PageOffset = 0
) -> tuple[AcademicYearResponse, ...]:
    values = await _administration_service(request).list_academic_years(
        context=_tenant_actor(actor), limit=limit, offset=offset
    )
    return tuple(AcademicYearResponse.from_domain(value) for value in values)


@router.post("/terms", response_model=TermResponse, status_code=status.HTTP_201_CREATED)
async def create_term(
    body: TermBody, request: Request, actor: ActorDep, _csrf: CSRFDep
) -> TermResponse:
    context = _tenant_actor(actor)
    value = Term(
        id=new_uuid7(), organization_id=context.organization_id, **body.model_dump()
    )
    await _administration_service(request).register_term(context=context, term=value)
    return TermResponse.from_domain(value)


@router.post("/terms/{term_id}/close", response_model=TermResponse)
async def close_term(
    term_id: UUID,
    body: TermClosureBody,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> TermResponse:
    value = await _administration_service(request).close_term(
        context=_tenant_actor(actor),
        term_id=term_id,
        explanation=body.explanation,
    )
    return TermResponse.from_domain(value)


@router.get("/terms", response_model=tuple[TermResponse, ...])
async def list_terms(
    request: Request,
    actor: ActorDep,
    academic_year_id: UUID | None = None,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> tuple[TermResponse, ...]:
    values = await _administration_service(request).list_terms(
        context=_tenant_actor(actor),
        academic_year_id=academic_year_id,
        limit=limit,
        offset=offset,
    )
    return tuple(TermResponse.from_domain(value) for value in values)


@router.post(
    "/calendar-events",
    response_model=CalendarEventResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_calendar_event(
    body: CalendarEventBody, request: Request, actor: ActorDep, _csrf: CSRFDep
) -> CalendarEventResponse:
    context = _tenant_actor(actor)
    value = AcademicCalendarEvent(
        id=new_uuid7(), organization_id=context.organization_id, **body.model_dump()
    )
    await _administration_service(request).register_calendar_event(
        context=context, event=value
    )
    return CalendarEventResponse.from_domain(value)


@router.get("/calendar-events", response_model=tuple[CalendarEventResponse, ...])
async def list_calendar_events(
    starts_at: datetime, ends_at: datetime, request: Request, actor: ActorDep
) -> tuple[CalendarEventResponse, ...]:
    values = await _administration_service(request).list_calendar_events(
        context=_tenant_actor(actor), starts_at=starts_at, ends_at=ends_at
    )
    return tuple(CalendarEventResponse.from_domain(value) for value in values)


@router.post(
    "/courses", response_model=CourseResponse, status_code=status.HTTP_201_CREATED
)
async def create_course(
    body: CourseBody, request: Request, actor: ActorDep, _csrf: CSRFDep
) -> CourseResponse:
    context = _tenant_actor(actor)
    value = Course(
        id=new_uuid7(), organization_id=context.organization_id, **body.model_dump()
    )
    await _administration_service(request).register_course(
        context=context, course=value
    )
    return CourseResponse.from_domain(value)


@router.get("/courses", response_model=tuple[CourseResponse, ...])
async def list_courses(
    request: Request,
    actor: ActorDep,
    department_id: UUID | None = None,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> tuple[CourseResponse, ...]:
    values = await _administration_service(request).list_courses(
        context=_tenant_actor(actor),
        department_id=department_id,
        limit=limit,
        offset=offset,
    )
    return tuple(CourseResponse.from_domain(value) for value in values)


@router.post(
    "/course-offerings",
    response_model=CourseOfferingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_course_offering(
    body: CourseOfferingBody, request: Request, actor: ActorDep, _csrf: CSRFDep
) -> CourseOfferingResponse:
    context = _tenant_actor(actor)
    value = CourseOffering(
        id=new_uuid7(),
        organization_id=context.organization_id,
        course_id=body.course_id,
        term_id=body.term_id,
        campus_id=body.campus_id,
        section_code=body.section_code,
        capacity=body.capacity,
        meeting_windows=tuple(
            MeetingWindow(**item.model_dump()) for item in body.meeting_windows
        ),
    )
    await _administration_service(request).register_course_offering(
        context=context, offering=value
    )
    return CourseOfferingResponse.from_domain(value)


@router.get("/course-offerings", response_model=tuple[CourseOfferingResponse, ...])
async def list_course_offerings(
    request: Request,
    actor: ActorDep,
    term_id: UUID | None = None,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> tuple[CourseOfferingResponse, ...]:
    values = await _administration_service(request).list_course_offerings(
        context=_tenant_actor(actor), term_id=term_id, limit=limit, offset=offset
    )
    return tuple(CourseOfferingResponse.from_domain(value) for value in values)


@router.post(
    "/cohorts", response_model=CohortResponse, status_code=status.HTTP_201_CREATED
)
async def create_cohort(
    body: CohortBody, request: Request, actor: ActorDep, _csrf: CSRFDep
) -> CohortResponse:
    context = _tenant_actor(actor)
    value = Cohort(
        id=new_uuid7(), organization_id=context.organization_id, **body.model_dump()
    )
    await _administration_service(request).register_cohort(
        context=context, cohort=value
    )
    return CohortResponse.from_domain(value)


@router.get("/cohorts", response_model=tuple[CohortResponse, ...])
async def list_cohorts(
    request: Request,
    actor: ActorDep,
    program_id: UUID | None = None,
    academic_year_id: UUID | None = None,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> tuple[CohortResponse, ...]:
    values = await _administration_service(request).list_cohorts(
        context=_tenant_actor(actor),
        program_id=program_id,
        academic_year_id=academic_year_id,
        limit=limit,
        offset=offset,
    )
    return tuple(CohortResponse.from_domain(value) for value in values)


@router.post("/rooms", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
async def create_room(
    body: RoomBody, request: Request, actor: ActorDep, _csrf: CSRFDep
) -> RoomResponse:
    context = _tenant_actor(actor)
    value = Room(
        id=new_uuid7(), organization_id=context.organization_id, **body.model_dump()
    )
    await _administration_service(request).register_room(context=context, room=value)
    return RoomResponse.from_domain(value)


@router.get("/rooms", response_model=tuple[RoomResponse, ...])
async def list_rooms(
    request: Request,
    actor: ActorDep,
    campus_id: UUID | None = None,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> tuple[RoomResponse, ...]:
    values = await _administration_service(request).list_rooms(
        context=_tenant_actor(actor), campus_id=campus_id, limit=limit, offset=offset
    )
    return tuple(RoomResponse.from_domain(value) for value in values)


@router.post(
    "/teacher-assignments",
    response_model=TeacherAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_teacher_assignment(
    body: TeacherAssignmentBody, request: Request, actor: ActorDep, _csrf: CSRFDep
) -> TeacherAssignmentResponse:
    context = _tenant_actor(actor)
    value = TeacherAssignment(
        id=new_uuid7(), organization_id=context.organization_id, **body.model_dump()
    )
    await _administration_service(request).assign_teacher(
        context=context, assignment=value
    )
    return TeacherAssignmentResponse.from_domain(value)


@router.get(
    "/teacher-assignments", response_model=tuple[TeacherAssignmentResponse, ...]
)
async def list_teacher_assignments(
    request: Request,
    actor: ActorDep,
    course_offering_id: UUID | None = None,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> tuple[TeacherAssignmentResponse, ...]:
    values = await _administration_service(request).list_teacher_assignments(
        context=_tenant_actor(actor),
        course_offering_id=course_offering_id,
        limit=limit,
        offset=offset,
    )
    return tuple(TeacherAssignmentResponse.from_domain(value) for value in values)


@router.post(
    "/student-enrollments",
    response_model=StudentEnrollmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_student_enrollment(
    body: StudentEnrollmentBody, request: Request, actor: ActorDep, _csrf: CSRFDep
) -> StudentEnrollmentResponse:
    context = _tenant_actor(actor)
    value = StudentAcademicEnrollment(
        id=new_uuid7(),
        organization_id=context.organization_id,
        status=AcademicEnrollmentStatus.ACTIVE,
        **body.model_dump(),
    )
    await _administration_service(request).enroll_student(
        context=context, enrollment=value
    )
    return StudentEnrollmentResponse.from_domain(value)


@router.get(
    "/student-enrollments", response_model=tuple[StudentEnrollmentResponse, ...]
)
async def list_student_enrollments(
    request: Request,
    actor: ActorDep,
    student_id: UUID | None = None,
    program_id: UUID | None = None,
    academic_year_id: UUID | None = None,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> tuple[StudentEnrollmentResponse, ...]:
    values = await _administration_service(request).list_student_enrollments(
        context=_tenant_actor(actor),
        student_id=student_id,
        program_id=program_id,
        academic_year_id=academic_year_id,
        limit=limit,
        offset=offset,
    )
    return tuple(StudentEnrollmentResponse.from_domain(value) for value in values)


@router.post(
    "/student-enrollments/{enrollment_id}/withdraw",
    response_model=StudentEnrollmentResponse,
)
async def withdraw_student_enrollment(
    enrollment_id: UUID,
    body: EnrollmentTransitionBody,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> StudentEnrollmentResponse:
    """Withdraw one academic enrollment and cascade to its enrolled courses."""

    service = _enrollment_transition_service(request)
    value = await service.withdraw_student_enrollment(
        context=_tenant_actor(actor),
        enrollment_id=enrollment_id,
        explanation=body.explanation,
    )
    return StudentEnrollmentResponse.from_domain(value)


@router.post(
    "/student-enrollments/{enrollment_id}/complete",
    response_model=StudentEnrollmentResponse,
)
async def complete_student_enrollment(
    enrollment_id: UUID,
    body: EnrollmentTransitionBody,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> StudentEnrollmentResponse:
    """Complete one academic enrollment once no course remains enrolled."""

    service = _enrollment_transition_service(request)
    value = await service.complete_student_enrollment(
        context=_tenant_actor(actor),
        enrollment_id=enrollment_id,
        explanation=body.explanation,
    )
    return StudentEnrollmentResponse.from_domain(value)


@router.get("/course-enrollments", response_model=tuple[CourseEnrollmentResponse, ...])
async def list_course_enrollments(
    request: Request,
    actor: ActorDep,
    student_academic_enrollment_id: UUID | None = None,
    course_offering_id: UUID | None = None,
    enrollment_status: Annotated[
        CourseEnrollmentStatus | None,
        Query(alias="status"),
    ] = None,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> tuple[CourseEnrollmentResponse, ...]:
    """Return a bounded page of official course enrollments for the tenant."""

    values = await _administration_service(request).list_course_enrollments(
        context=_tenant_actor(actor),
        student_academic_enrollment_id=student_academic_enrollment_id,
        course_offering_id=course_offering_id,
        status=enrollment_status,
        limit=limit,
        offset=offset,
    )
    return tuple(CourseEnrollmentResponse.from_domain(value) for value in values)


@router.post(
    "/course-enrollments/{course_enrollment_id}/withdraw",
    response_model=CourseEnrollmentResponse,
)
async def withdraw_course_enrollment(
    course_enrollment_id: UUID,
    body: EnrollmentTransitionBody,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> CourseEnrollmentResponse:
    """Withdraw one course enrollment while its offering term remains open."""

    service = _enrollment_transition_service(request)
    value = await service.withdraw_course_enrollment(
        context=_tenant_actor(actor),
        course_enrollment_id=course_enrollment_id,
        explanation=body.explanation,
    )
    return CourseEnrollmentResponse.from_domain(value)


@router.post(
    "/course-enrollments/{course_enrollment_id}/complete",
    response_model=CourseEnrollmentResponse,
)
async def complete_course_enrollment(
    course_enrollment_id: UUID,
    body: EnrollmentTransitionBody,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> CourseEnrollmentResponse:
    """Complete one course enrollment; finalization remains allowed after closure."""

    service = _enrollment_transition_service(request)
    value = await service.complete_course_enrollment(
        context=_tenant_actor(actor),
        course_enrollment_id=course_enrollment_id,
        explanation=body.explanation,
    )
    return CourseEnrollmentResponse.from_domain(value)


@router.put("/curricula/{curriculum_id}", response_model=CurriculumResponse)
async def configure_curriculum(
    curriculum_id: UUID,
    body: CurriculumBody,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> CurriculumResponse:
    context = _tenant_actor(actor)
    value = ProgramCurriculum(
        id=curriculum_id,
        organization_id=context.organization_id,
        program_id=body.program_id,
        academic_year_id=body.academic_year_id,
        courses=tuple(CurriculumCourse(**item.model_dump()) for item in body.courses),
    )
    await _administration_service(request).configure_curriculum(
        context=context, curriculum=value
    )
    return CurriculumResponse.from_domain(value)


@router.get("/curricula", response_model=CurriculumResponse)
async def get_curriculum(
    program_id: UUID, academic_year_id: UUID, request: Request, actor: ActorDep
) -> CurriculumResponse:
    value = await _administration_service(request).get_curriculum(
        context=_tenant_actor(actor),
        program_id=program_id,
        academic_year_id=academic_year_id,
    )
    return CurriculumResponse.from_domain(value)


@router.put(
    "/course-selection-policies/{program_id}/{term_id}",
    response_model=SelectionPolicyResponse,
)
async def configure_selection_policy(
    program_id: UUID,
    term_id: UUID,
    body: SelectionPolicyBody,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> SelectionPolicyResponse:
    context = _tenant_actor(actor)
    value = CourseSelectionPolicy(
        organization_id=context.organization_id,
        program_id=program_id,
        term_id=term_id,
        **body.model_dump(),
    )
    await _administration_service(request).configure_selection_policy(
        context=context, policy=value
    )
    return SelectionPolicyResponse.from_domain(value)


@router.get(
    "/course-selection-policies/{program_id}/{term_id}",
    response_model=SelectionPolicyResponse,
)
async def get_selection_policy(
    program_id: UUID, term_id: UUID, request: Request, actor: ActorDep
) -> SelectionPolicyResponse:
    value = await _administration_service(request).get_selection_policy(
        context=_tenant_actor(actor), program_id=program_id, term_id=term_id
    )
    return SelectionPolicyResponse.from_domain(value)


@router.get(
    "/course-selection-context",
    response_model=StudentCourseSelectionContextResponse,
)
async def student_course_selection_context(
    request: Request,
    actor: ActorDep,
) -> StudentCourseSelectionContextResponse:
    """Return real tenant-owned selection choices for the current student."""

    value = await _selection_service(request).student_context(
        context=_tenant_actor(actor),
    )
    return StudentCourseSelectionContextResponse.from_application(value)


@router.post(
    "/course-selection-requests",
    response_model=CourseSelectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_course_selection(
    body: CourseSelectionSubmissionBody,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> CourseSelectionResponse:
    value = await _selection_service(request).submit(
        context=_tenant_actor(actor),
        student_academic_enrollment_id=body.student_academic_enrollment_id,
        term_id=body.term_id,
        offering_ids=body.offering_ids,
        override_reason=body.override_reason,
    )
    return CourseSelectionResponse.from_domain(value)


@router.get(
    "/course-selection-requests",
    response_model=tuple[CourseSelectionResponse, ...],
)
async def list_course_selection_requests(
    request: Request,
    actor: ActorDep,
    selection_status: Annotated[
        CourseSelectionStatus | None,
        Query(alias="status"),
    ] = None,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> tuple[CourseSelectionResponse, ...]:
    values = await _selection_service(request).list_requests(
        context=_tenant_actor(actor),
        status=selection_status,
        limit=limit,
        offset=offset,
    )
    return tuple(CourseSelectionResponse.from_domain(value) for value in values)


@router.patch(
    "/course-selection-requests/{request_id}/decision",
    response_model=CourseSelectionResponse,
)
async def decide_course_selection(
    request_id: UUID,
    body: CourseSelectionDecisionBody,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> CourseSelectionResponse:
    value = await _selection_service(request).decide(
        context=_tenant_actor(actor),
        request_id=request_id,
        approved=body.approved,
        reason=body.reason,
    )
    return CourseSelectionResponse.from_domain(value)


cast(object, create_faculty)
cast(object, student_course_selection_context)
cast(object, submit_course_selection)

__all__ = [
    "CourseEnrollmentResponse",
    "CourseSelectionDecisionBody",
    "CourseSelectionEnrollmentOptionResponse",
    "CourseSelectionOfferingOptionResponse",
    "CourseSelectionResponse",
    "CourseSelectionSubmissionBody",
    "CourseSelectionTermOptionResponse",
    "CurriculumBody",
    "EnrollmentTransitionBody",
    "SelectionPolicyBody",
    "StudentCourseSelectionContextResponse",
    "StudentEnrollmentBody",
    "TermClosureBody",
    "router",
]
