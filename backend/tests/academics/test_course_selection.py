from dataclasses import dataclass
from datetime import UTC
from datetime import date
from datetime import datetime
from datetime import time
from decimal import Decimal
from uuid import UUID
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport
from httpx import AsyncClient

from academics.application.service import ACADEMICS_SELECTION_APPROVE
from academics.application.service import ACADEMICS_SELECTION_OVERRIDE
from academics.application.service import ACADEMICS_SELECTION_SUBMIT
from academics.application.service import CourseSelectionService
from academics.domain.exceptions import AcademicRuleError
from academics.domain.exceptions import CourseSelectionError
from academics.domain.models import AcademicEnrollmentStatus
from academics.domain.models import AcademicYear
from academics.domain.models import Course
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
from academics.domain.models import SelectionRuleCode
from academics.domain.models import StudentAcademicEnrollment
from academics.domain.models import Term
from academics.infrastructure.repository import InMemoryAcademicRepository
from academics.presentation.router import router
from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import NotFoundError
from core.http import install_error_handlers
from identity.presentation.dependencies import require_actor


@dataclass(frozen=True, slots=True)
class FakeClock:
    current: datetime

    def now(self) -> datetime:
        return self.current


@dataclass(frozen=True, slots=True)
class RecordedSelectionAuditEvent:
    action: str
    organization_id: UUID
    actor_subject_id: UUID
    request_id: UUID
    correlation_id: str


class RecordingCourseSelectionAuditSink:
    """Capture minimized administrative selection evidence."""

    def __init__(self) -> None:
        self.events: list[RecordedSelectionAuditEvent] = []

    async def record_course_selection_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        request_id: UUID,
        correlation_id: str,
    ) -> None:
        self.events.append(
            RecordedSelectionAuditEvent(
                action=action,
                organization_id=organization_id,
                actor_subject_id=actor_subject_id,
                request_id=request_id,
                correlation_id=correlation_id,
            )
        )


class FakeCourseSelectionStudentOwnership:
    """Resolve exact actor-to-student-profile bindings for selection tests."""

    def __init__(self) -> None:
        self.owned_profile_by_subject: dict[UUID, UUID] = {}
        self.checks: list[tuple[UUID, UUID]] = []

    async def actor_owns_student_profile(
        self,
        *,
        actor: TenantActorContext,
        student_profile_id: UUID,
    ) -> bool:
        self.checks.append((actor.subject_id, student_profile_id))
        return (
            self.owned_profile_by_subject.get(
                actor.subject_id,
                student_profile_id,
            )
            == student_profile_id
        )


@dataclass(frozen=True, slots=True)
class SelectionFixture:
    organization_id: UUID
    repository: InMemoryAcademicRepository
    audit: RecordingCourseSelectionAuditSink
    ownership: FakeCourseSelectionStudentOwnership
    service: CourseSelectionService
    enrollment: StudentAcademicEnrollment
    second_enrollment: StudentAcademicEnrollment
    term: Term
    first_offering: CourseOffering
    second_offering: CourseOffering


def _context(
    *,
    organization_id: UUID,
    permissions: frozenset[str],
) -> TenantActorContext:
    return TenantActorContext(
        subject_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        correlation_id="test-correlation",
        permissions=permissions,
    )


def _stored_request(
    *,
    request_id: UUID,
    organization_id: UUID,
    status: CourseSelectionStatus,
    submitted_at: datetime,
) -> CourseSelectionRequest:
    decided = status is not CourseSelectionStatus.PENDING
    return CourseSelectionRequest(
        id=request_id,
        organization_id=organization_id,
        student_academic_enrollment_id=uuid4(),
        term_id=uuid4(),
        offering_ids=(uuid4(),),
        requested_credits=Decimal("3"),
        status=status,
        submitted_at=submitted_at,
        submitted_by=uuid4(),
        decided_at=submitted_at if decided else None,
        decided_by=uuid4() if decided else None,
    )


async def _selection_fixture(
    *,
    approval_required: bool = True,
    capacity: int = 10,
) -> SelectionFixture:
    organization_id = uuid4()
    campus_id = uuid4()
    repository = InMemoryAcademicRepository()
    audit = RecordingCourseSelectionAuditSink()
    ownership = FakeCourseSelectionStudentOwnership()
    now = datetime(2026, 8, 5, 8, tzinfo=UTC)
    faculty = Faculty(
        id=uuid4(),
        organization_id=organization_id,
        campus_id=campus_id,
        code="SCI",
        name="Science",
    )
    department = Department(
        id=uuid4(),
        organization_id=organization_id,
        faculty_id=faculty.id,
        code="CS",
        name="Computer Science",
    )
    program = Program(
        id=uuid4(),
        organization_id=organization_id,
        department_id=department.id,
        code="BSCS",
        name="Computer Science",
        education_mode=EducationMode.FLEXIBLE_SELECTION,
        credit_unit_label="credits",
    )
    academic_year = AcademicYear(
        id=uuid4(),
        organization_id=organization_id,
        name="2026-2027",
        starts_on=date(2026, 8, 1),
        ends_on=date(2027, 7, 31),
    )
    term = Term(
        id=uuid4(),
        organization_id=organization_id,
        academic_year_id=academic_year.id,
        name="Fall",
        starts_on=date(2026, 8, 10),
        ends_on=date(2026, 12, 20),
        enrollment_deadline=datetime(2026, 8, 20, tzinfo=UTC),
    )
    first_course = Course(
        id=uuid4(),
        organization_id=organization_id,
        department_id=department.id,
        code="CS101",
        title="Foundations",
        credits=Decimal("3"),
    )
    second_course = Course(
        id=uuid4(),
        organization_id=organization_id,
        department_id=department.id,
        code="CS201",
        title="Systems",
        credits=Decimal("4"),
    )
    first_offering = CourseOffering(
        id=uuid4(),
        organization_id=organization_id,
        course_id=first_course.id,
        term_id=term.id,
        campus_id=campus_id,
        section_code="A",
        capacity=capacity,
        meeting_windows=(MeetingWindow(1, time(9), time(10)),),
    )
    second_offering = CourseOffering(
        id=uuid4(),
        organization_id=organization_id,
        course_id=second_course.id,
        term_id=term.id,
        campus_id=campus_id,
        section_code="A",
        capacity=capacity,
        meeting_windows=(MeetingWindow(1, time(9, 30), time(10, 30)),),
    )
    curriculum = ProgramCurriculum(
        id=uuid4(),
        organization_id=organization_id,
        program_id=program.id,
        academic_year_id=academic_year.id,
        courses=(
            CurriculumCourse(
                course_id=first_course.id,
                kind=CurriculumCourseKind.REQUIRED,
                credits=first_course.credits,
            ),
            CurriculumCourse(
                course_id=second_course.id,
                kind=CurriculumCourseKind.ELECTIVE,
                credits=second_course.credits,
                prerequisite_course_ids=frozenset({first_course.id}),
            ),
        ),
    )
    policy = CourseSelectionPolicy(
        organization_id=organization_id,
        program_id=program.id,
        term_id=term.id,
        education_mode=program.education_mode,
        maximum_credits=Decimal("6"),
        deadline=datetime(2026, 8, 20, tzinfo=UTC),
        approval_required=approval_required,
    )
    enrollment = StudentAcademicEnrollment(
        id=uuid4(),
        organization_id=organization_id,
        student_id=uuid4(),
        program_id=program.id,
        academic_year_id=academic_year.id,
        cohort_id=None,
        status=AcademicEnrollmentStatus.ACTIVE,
        enrolled_at=now,
    )
    second_enrollment = StudentAcademicEnrollment(
        id=uuid4(),
        organization_id=organization_id,
        student_id=uuid4(),
        program_id=program.id,
        academic_year_id=academic_year.id,
        cohort_id=None,
        status=AcademicEnrollmentStatus.ACTIVE,
        enrolled_at=now,
    )
    await repository.save_faculty(faculty)
    await repository.save_department(department)
    await repository.save_program(program)
    await repository.save_academic_year(academic_year)
    await repository.save_term(term)
    await repository.save_course(first_course)
    await repository.save_course(second_course)
    await repository.save_course_offering(first_offering)
    await repository.save_course_offering(second_offering)
    await repository.save_curriculum(curriculum)
    await repository.save_selection_policy(policy)
    await repository.save_student_enrollment(enrollment)
    await repository.save_student_enrollment(second_enrollment)
    return SelectionFixture(
        organization_id=organization_id,
        repository=repository,
        audit=audit,
        ownership=ownership,
        service=CourseSelectionService(
            catalog=repository,
            selections=repository,
            clock=FakeClock(now),
            audit=audit,
            ownership=ownership,
        ),
        enrollment=enrollment,
        second_enrollment=second_enrollment,
        term=term,
        first_offering=first_offering,
        second_offering=second_offering,
    )


async def test_selection_requires_permissioned_audited_override() -> None:
    fixture = await _selection_fixture()
    context = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset(
            {ACADEMICS_SELECTION_SUBMIT, ACADEMICS_SELECTION_OVERRIDE}
        ),
    )

    with pytest.raises(CourseSelectionError, match="violates"):
        await fixture.service.submit(
            context=context,
            student_academic_enrollment_id=fixture.enrollment.id,
            term_id=fixture.term.id,
            offering_ids=(fixture.second_offering.id,),
        )

    request = await fixture.service.submit(
        context=context,
        student_academic_enrollment_id=fixture.enrollment.id,
        term_id=fixture.term.id,
        offering_ids=(fixture.second_offering.id,),
        override_reason="Registrar approved prerequisite exception.",
    )

    assert request.status is CourseSelectionStatus.PENDING
    assert request.override is not None
    assert request.override.actor_id == context.subject_id
    assert request.override.reason.startswith("Registrar")
    assert request.override.violated_rules[0].code is (
        SelectionRuleCode.PREREQUISITE_MISSING
    )
    assert [event.action for event in fixture.audit.events] == [
        "academics.course_selection.override_applied"
    ]
    assert fixture.audit.events[0].request_id == request.id


async def test_listing_selection_requests_requires_approval_permission() -> None:
    fixture = await _selection_fixture()

    with pytest.raises(AuthorizationError, match="permission"):
        await fixture.service.list_requests(
            context=_context(
                organization_id=fixture.organization_id,
                permissions=frozenset({ACADEMICS_SELECTION_SUBMIT}),
            ),
            status=CourseSelectionStatus.PENDING,
            limit=50,
            offset=0,
        )


async def test_listing_selection_requests_is_tenant_scoped_filtered_and_stable() -> (
    None
):
    fixture = await _selection_fixture()
    submitted_at = datetime(2026, 8, 5, 9, tzinfo=UTC)
    first_id = UUID(int=1)
    second_id = UUID(int=2)
    requests = (
        _stored_request(
            request_id=second_id,
            organization_id=fixture.organization_id,
            status=CourseSelectionStatus.PENDING,
            submitted_at=submitted_at,
        ),
        _stored_request(
            request_id=first_id,
            organization_id=fixture.organization_id,
            status=CourseSelectionStatus.PENDING,
            submitted_at=submitted_at,
        ),
        _stored_request(
            request_id=UUID(int=3),
            organization_id=fixture.organization_id,
            status=CourseSelectionStatus.APPROVED,
            submitted_at=submitted_at.replace(hour=10),
        ),
        _stored_request(
            request_id=UUID(int=4),
            organization_id=uuid4(),
            status=CourseSelectionStatus.PENDING,
            submitted_at=submitted_at.replace(hour=11),
        ),
    )
    for request in requests:
        await fixture.repository.save_submission(
            request=request,
            enrollments=(),
            offering_capacities={},
        )
    approver = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({ACADEMICS_SELECTION_APPROVE}),
    )

    values = await fixture.service.list_requests(
        context=approver,
        status=CourseSelectionStatus.PENDING,
        limit=100,
        offset=0,
    )
    second_page = await fixture.service.list_requests(
        context=approver,
        status=CourseSelectionStatus.PENDING,
        limit=1,
        offset=1,
    )

    assert tuple(value.id for value in values) == (first_id, second_id)
    assert tuple(value.id for value in second_page) == (second_id,)
    with pytest.raises(AcademicRuleError, match="1-100"):
        await fixture.service.list_requests(
            context=approver,
            status=None,
            limit=101,
            offset=0,
        )


async def test_selection_request_list_api_contract_is_bounded_and_typed() -> None:
    fixture = await _selection_fixture()
    pending = _stored_request(
        request_id=UUID(int=10),
        organization_id=fixture.organization_id,
        status=CourseSelectionStatus.PENDING,
        submitted_at=datetime(2026, 8, 5, 9, tzinfo=UTC),
    )
    await fixture.repository.save_submission(
        request=pending,
        enrollments=(),
        offering_capacities={},
    )
    approver = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({ACADEMICS_SELECTION_APPROVE}),
    )

    async def actor_dependency() -> TenantActorContext:
        return approver

    app = FastAPI()
    app.state.course_selection_service = fixture.service
    install_error_handlers(app)
    app.include_router(router)
    app.dependency_overrides[require_actor] = actor_dependency

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/v1/academics/course-selection-requests",
            params={"status": "pending", "limit": 1, "offset": 0},
        )
        invalid_status = await client.get(
            "/api/v1/academics/course-selection-requests",
            params={"status": "unknown"},
        )

    payload = response.json()
    assert response.status_code == 200
    assert len(payload) == 1
    assert payload[0]["id"] == str(pending.id)
    assert payload[0]["status"] == CourseSelectionStatus.PENDING
    assert set(payload[0]) == {
        "id",
        "student_academic_enrollment_id",
        "term_id",
        "offering_ids",
        "requested_credits",
        "status",
        "override_reason",
        "overridden_rules",
        "rejection_reason",
    }
    assert invalid_status.status_code == 422

    operation = app.openapi()["paths"]["/api/v1/academics/course-selection-requests"][
        "get"
    ]
    parameters = {value["name"]: value for value in operation["parameters"]}
    assert parameters["limit"]["schema"]["maximum"] == 100
    assert parameters["offset"]["schema"]["minimum"] == 0
    assert parameters["status"]["required"] is False
    response_schema = operation["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    assert response_schema["type"] == "array"


async def test_approval_creates_official_enrollment_and_history() -> None:
    fixture = await _selection_fixture()
    submitter = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({ACADEMICS_SELECTION_SUBMIT}),
    )
    approver = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({ACADEMICS_SELECTION_APPROVE}),
    )
    request = await fixture.service.submit(
        context=submitter,
        student_academic_enrollment_id=fixture.enrollment.id,
        term_id=fixture.term.id,
        offering_ids=(fixture.first_offering.id,),
    )

    decided = await fixture.service.decide(
        context=approver,
        request_id=request.id,
        approved=True,
    )

    enrollments = await fixture.repository.list_course_enrollments(
        organization_id=fixture.organization_id,
        student_academic_enrollment_id=fixture.enrollment.id,
    )
    approvals = await fixture.repository.list_approvals(
        organization_id=fixture.organization_id,
        request_id=request.id,
    )
    assert decided.status is CourseSelectionStatus.APPROVED
    assert len(enrollments) == 1
    assert enrollments[0].status is CourseEnrollmentStatus.ENROLLED
    assert enrollments[0].selection_request_id == request.id
    assert len(approvals) == 1
    assert approvals[0].actor_id == approver.subject_id
    assert fixture.audit.events[-1].action == ("academics.course_selection.approved")
    assert fixture.audit.events[-1].actor_subject_id == approver.subject_id


async def test_cross_tenant_selection_does_not_reveal_resource() -> None:
    fixture = await _selection_fixture()
    attacker = _context(
        organization_id=uuid4(),
        permissions=frozenset({ACADEMICS_SELECTION_SUBMIT}),
    )

    with pytest.raises(NotFoundError):
        await fixture.service.submit(
            context=attacker,
            student_academic_enrollment_id=fixture.enrollment.id,
            term_id=fixture.term.id,
            offering_ids=(fixture.first_offering.id,),
        )


async def test_student_cannot_submit_for_another_same_tenant_enrollment() -> None:
    fixture = await _selection_fixture()
    student = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({ACADEMICS_SELECTION_SUBMIT}),
    )
    fixture.ownership.owned_profile_by_subject[student.subject_id] = (
        fixture.enrollment.student_id
    )

    with pytest.raises(AuthorizationError, match="not owned"):
        await fixture.service.submit(
            context=student,
            student_academic_enrollment_id=fixture.second_enrollment.id,
            term_id=fixture.term.id,
            offering_ids=(fixture.first_offering.id,),
        )

    assert fixture.ownership.checks[-1] == (
        student.subject_id,
        fixture.second_enrollment.student_id,
    )


async def test_override_permission_is_deny_by_default() -> None:
    fixture = await _selection_fixture()
    submitter = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({ACADEMICS_SELECTION_SUBMIT}),
    )

    with pytest.raises(AuthorizationError):
        await fixture.service.submit(
            context=submitter,
            student_academic_enrollment_id=fixture.enrollment.id,
            term_id=fixture.term.id,
            offering_ids=(fixture.second_offering.id,),
            override_reason="Attempted exception.",
        )


async def test_auto_enrollment_capacity_is_atomic_under_concurrency() -> None:
    import asyncio

    fixture = await _selection_fixture(approval_required=False, capacity=1)
    submitter = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({ACADEMICS_SELECTION_SUBMIT}),
    )

    results = await asyncio.gather(
        fixture.service.submit(
            context=submitter,
            student_academic_enrollment_id=fixture.enrollment.id,
            term_id=fixture.term.id,
            offering_ids=(fixture.first_offering.id,),
        ),
        fixture.service.submit(
            context=submitter,
            student_academic_enrollment_id=fixture.second_enrollment.id,
            term_id=fixture.term.id,
            offering_ids=(fixture.first_offering.id,),
        ),
        return_exceptions=True,
    )

    assert sum(isinstance(result, CourseSelectionRequest) for result in results) == 1
    assert sum(isinstance(result, CourseSelectionError) for result in results) == 1
