"""Explicit, audited, one-way academic and course enrollment transitions."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC
from datetime import date
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from uuid import UUID
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport
from httpx import AsyncClient

from academics.application.ports import StudentEnrollmentTransitionTransaction
from academics.application.service import ACADEMICS_ENROLLMENT_MANAGE
from academics.application.service import ACADEMICS_TERM_CLOSE
from academics.application.service import AcademicAdministrationService
from academics.application.service import AcademicEnrollmentTransitionService
from academics.domain.exceptions import AcademicRuleError
from academics.domain.exceptions import EnrollmentTransitionError
from academics.domain.models import AcademicEnrollmentStatus
from academics.domain.models import CourseEnrollment
from academics.domain.models import CourseEnrollmentStatus
from academics.domain.models import CourseOffering
from academics.domain.models import CourseSelectionRequest
from academics.domain.models import CourseSelectionStatus
from academics.domain.models import StudentAcademicEnrollment
from academics.domain.models import Term
from academics.infrastructure.repository import InMemoryAcademicRepository
from academics.infrastructure.repository import InMemoryCampusDirectory
from academics.presentation.router import router
from audit.application.service import AuditService
from audit.domain.records import AuditRecord
from audit.infrastructure.sinks import ApplicationAuditSink
from core.context import PlatformActorContext
from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import ConflictError
from core.errors import NotFoundError
from core.http import install_error_handlers
from identity.presentation.dependencies import require_actor
from identity.presentation.dependencies import require_csrf

NOW = datetime(2026, 9, 1, 9, tzinfo=UTC)
EXPLANATION = "Registrar approved the request in writing."
ACADEMICS_PREFIX = "/api/v1/academics"


@dataclass(frozen=True, slots=True)
class RecordedTransitionEvent:
    action: str
    organization_id: UUID
    actor_subject_id: UUID
    target_type: str
    target_id: UUID
    correlation_id: str
    outcome: str
    reason: str


class RecordingEnrollmentTransitionAuditSink:
    """Capture minimized transition evidence or fail on selected actions."""

    def __init__(self, *, fail_on_actions: frozenset[str] = frozenset()) -> None:
        self.fail_on_actions = fail_on_actions
        self.events: list[RecordedTransitionEvent] = []

    async def record_enrollment_transition_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        target_type: str,
        target_id: UUID,
        correlation_id: str,
        outcome: str,
        reason: str,
    ) -> None:
        if action in self.fail_on_actions:
            raise RuntimeError("Enrollment audit is unavailable.")
        self.events.append(
            RecordedTransitionEvent(
                action=action,
                organization_id=organization_id,
                actor_subject_id=actor_subject_id,
                target_type=target_type,
                target_id=target_id,
                correlation_id=correlation_id,
                outcome=outcome,
                reason=reason,
            )
        )

    @property
    def actions(self) -> list[tuple[str, str]]:
        return [(event.action, event.outcome) for event in self.events]


class UnusedTermClosureAuditSink:
    """Fail loudly if enrollment listing records term-closure intent."""

    async def record_term_closure_intent(
        self,
        *,
        organization_id: UUID,
        actor_subject_id: UUID,
        term_id: UUID,
        correlation_id: str,
        reason: str,
    ) -> None:
        del organization_id, actor_subject_id, term_id, correlation_id, reason
        raise AssertionError("Enrollment transitions must not close terms.")


class UnusedAcademicProfileDirectory:
    """Fail loudly if enrollment transitions resolve a People profile."""

    async def teacher_profile_exists(
        self,
        *,
        organization_id: UUID,
        teacher_profile_id: UUID,
    ) -> bool:
        del organization_id, teacher_profile_id
        raise AssertionError("Transitions must not resolve teacher profiles.")

    async def student_profile_exists(
        self,
        *,
        organization_id: UUID,
        student_profile_id: UUID,
    ) -> bool:
        del organization_id, student_profile_id
        raise AssertionError("Transitions must not resolve student profiles.")


class InMemoryAuditRepository:
    """Keep appended audit evidence in insertion order."""

    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    async def append(self, record: AuditRecord) -> None:
        self.records.append(record)

    async def list_for_organization(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> list[AuditRecord]:
        values = [
            record
            for record in self.records
            if record.organization_id == organization_id
        ]
        return values[offset : offset + limit]

    async def list_platform(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[AuditRecord]:
        values = [record for record in self.records if record.organization_id is None]
        return values[offset : offset + limit]


class _FailingSaveTransition:
    """Expose the locked enrollment but fail the catalog write itself."""

    def __init__(self, inner: StudentEnrollmentTransitionTransaction) -> None:
        self._inner = inner

    @property
    def student_enrollment(self) -> StudentAcademicEnrollment:
        return self._inner.student_enrollment

    async def list_course_enrollments(self) -> tuple[CourseEnrollment, ...]:
        return await self._inner.list_course_enrollments()

    async def save_transition(
        self,
        *,
        enrollment: StudentAcademicEnrollment,
        course_enrollments: tuple[CourseEnrollment, ...],
    ) -> None:
        del enrollment, course_enrollments
        raise RuntimeError("Catalog write failed.")


class FailingSaveAcademicRepository(InMemoryAcademicRepository):
    """Fail the catalog transaction after transition intent is recorded."""

    @asynccontextmanager
    async def student_enrollment_transition(
        self,
        *,
        organization_id: UUID,
        enrollment_id: UUID,
    ) -> AsyncIterator[StudentEnrollmentTransitionTransaction]:
        async with super().student_enrollment_transition(
            organization_id=organization_id,
            enrollment_id=enrollment_id,
        ) as transaction:
            yield _FailingSaveTransition(transaction)


class StaleReadAcademicRepository(InMemoryAcademicRepository):
    """Serve one stale academic enrollment outside the lock, like a racing reader."""

    def __init__(self) -> None:
        super().__init__()
        self.stale: StudentAcademicEnrollment | None = None

    async def get_student_enrollment(
        self,
        *,
        organization_id: UUID,
        enrollment_id: UUID,
    ) -> StudentAcademicEnrollment | None:
        current = await super().get_student_enrollment(
            organization_id=organization_id,
            enrollment_id=enrollment_id,
        )
        if (
            self.stale is not None
            and current is not None
            and current.id == self.stale.id
        ):
            return self.stale
        return current


@dataclass(frozen=True, slots=True)
class TransitionFixture:
    organization_id: UUID
    repository: InMemoryAcademicRepository
    audit: RecordingEnrollmentTransitionAuditSink
    service: AcademicEnrollmentTransitionService
    administration: AcademicAdministrationService
    term: Term
    offering: CourseOffering
    enrollment: StudentAcademicEnrollment
    actor: TenantActorContext


@dataclass(slots=True)
class CsrfCounter:
    """Count CSRF validations performed by the overridden dependency."""

    calls: int = 0


def _term(*, organization_id: UUID) -> Term:
    return Term(
        id=uuid4(),
        organization_id=organization_id,
        academic_year_id=uuid4(),
        name="Fall 2026",
        starts_on=date(2026, 8, 10),
        ends_on=date(2026, 12, 20),
        enrollment_deadline=datetime(2026, 8, 20, tzinfo=UTC),
    )


def _offering(*, organization_id: UUID, term_id: UUID) -> CourseOffering:
    return CourseOffering(
        id=uuid4(),
        organization_id=organization_id,
        course_id=uuid4(),
        term_id=term_id,
        campus_id=uuid4(),
        section_code="A",
        capacity=10,
    )


def _student_enrollment(
    *,
    organization_id: UUID,
    status: AcademicEnrollmentStatus = AcademicEnrollmentStatus.ACTIVE,
) -> StudentAcademicEnrollment:
    return StudentAcademicEnrollment(
        id=uuid4(),
        organization_id=organization_id,
        student_id=uuid4(),
        program_id=uuid4(),
        academic_year_id=uuid4(),
        cohort_id=None,
        status=status,
        enrolled_at=NOW,
    )


def _actor(
    *,
    organization_id: UUID,
    permissions: frozenset[str] = frozenset({ACADEMICS_ENROLLMENT_MANAGE}),
) -> TenantActorContext:
    return TenantActorContext(
        subject_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        correlation_id="enrollment-transition-correlation",
        permissions=permissions,
    )


async def _seed_course_enrollment(
    repository: InMemoryAcademicRepository,
    *,
    enrollment: StudentAcademicEnrollment,
    offering: CourseOffering,
    status: CourseEnrollmentStatus = CourseEnrollmentStatus.ENROLLED,
    enrolled_at: datetime = NOW,
) -> CourseEnrollment:
    """Persist one official course enrollment through the atomic submission path."""

    request = CourseSelectionRequest(
        id=uuid4(),
        organization_id=enrollment.organization_id,
        student_academic_enrollment_id=enrollment.id,
        term_id=offering.term_id,
        offering_ids=(offering.id,),
        requested_credits=Decimal("3"),
        status=CourseSelectionStatus.PENDING,
        submitted_at=enrolled_at,
        submitted_by=enrollment.student_id,
    )
    course_enrollment = CourseEnrollment(
        id=uuid4(),
        organization_id=enrollment.organization_id,
        student_academic_enrollment_id=enrollment.id,
        course_offering_id=offering.id,
        credits=Decimal("3"),
        status=status,
        enrolled_at=enrolled_at,
        selection_request_id=request.id,
    )
    await repository.save_submission(
        request=request,
        enrollments=(course_enrollment,),
        offering_capacities={offering.id: offering.capacity},
    )
    return course_enrollment


async def _fixture(
    *,
    repository: InMemoryAcademicRepository | None = None,
    audit: RecordingEnrollmentTransitionAuditSink | None = None,
) -> TransitionFixture:
    organization_id = uuid4()
    repository = repository or InMemoryAcademicRepository()
    audit = audit or RecordingEnrollmentTransitionAuditSink()
    term = _term(organization_id=organization_id)
    offering = _offering(organization_id=organization_id, term_id=term.id)
    enrollment = _student_enrollment(organization_id=organization_id)
    await repository.save_term(term)
    await repository.save_course_offering(offering)
    await repository.save_student_enrollment(enrollment)
    return TransitionFixture(
        organization_id=organization_id,
        repository=repository,
        audit=audit,
        service=AcademicEnrollmentTransitionService(catalog=repository, audit=audit),
        administration=AcademicAdministrationService(
            catalog=repository,
            campuses=InMemoryCampusDirectory(),
            profiles=UnusedAcademicProfileDirectory(),
            audit=UnusedTermClosureAuditSink(),
        ),
        term=term,
        offering=offering,
        enrollment=enrollment,
        actor=_actor(organization_id=organization_id),
    )


async def _stored_enrollment(fixture: TransitionFixture) -> StudentAcademicEnrollment:
    value = await fixture.repository.get_student_enrollment(
        organization_id=fixture.organization_id,
        enrollment_id=fixture.enrollment.id,
    )
    assert value is not None
    return value


async def _stored_course_enrollment(
    fixture: TransitionFixture,
    course_enrollment_id: UUID,
) -> CourseEnrollment:
    value = await fixture.repository.get_course_enrollment(
        organization_id=fixture.organization_id,
        course_enrollment_id=course_enrollment_id,
    )
    assert value is not None
    return value


def _application(
    fixture: TransitionFixture,
    *,
    actor: PlatformActorContext | TenantActorContext | None = None,
) -> tuple[FastAPI, CsrfCounter]:
    csrf = CsrfCounter()
    current_actor = fixture.actor if actor is None else actor

    async def actor_dependency() -> PlatformActorContext | TenantActorContext:
        return current_actor

    async def csrf_dependency() -> None:
        csrf.calls += 1

    app = FastAPI()
    app.state.academic_administration_service = fixture.administration
    app.state.academic_enrollment_transition_service = fixture.service
    install_error_handlers(app)
    app.include_router(router)
    app.dependency_overrides[require_actor] = actor_dependency
    app.dependency_overrides[require_csrf] = csrf_dependency
    return app, csrf


def test_academic_enrollment_transitions_are_one_way() -> None:
    enrollment = _student_enrollment(organization_id=uuid4())

    withdrawn = enrollment.withdraw()
    completed = enrollment.complete()

    assert withdrawn.status is AcademicEnrollmentStatus.WITHDRAWN
    assert completed.status is AcademicEnrollmentStatus.COMPLETED
    assert enrollment.status is AcademicEnrollmentStatus.ACTIVE
    for terminal in (withdrawn, completed):
        with pytest.raises(EnrollmentTransitionError):
            terminal.withdraw()
        with pytest.raises(EnrollmentTransitionError):
            terminal.complete()


def test_course_enrollment_transitions_are_one_way() -> None:
    organization_id = uuid4()
    enrollment = _student_enrollment(organization_id=organization_id)
    offering = _offering(organization_id=organization_id, term_id=uuid4())
    enrolled = CourseEnrollment(
        id=uuid4(),
        organization_id=organization_id,
        student_academic_enrollment_id=enrollment.id,
        course_offering_id=offering.id,
        credits=Decimal("3"),
        status=CourseEnrollmentStatus.ENROLLED,
        enrolled_at=NOW,
    )

    withdrawn = enrolled.withdraw()
    completed = enrolled.complete()

    assert withdrawn.status is CourseEnrollmentStatus.WITHDRAWN
    assert completed.status is CourseEnrollmentStatus.COMPLETED
    assert enrolled.status is CourseEnrollmentStatus.ENROLLED
    for terminal in (withdrawn, completed):
        with pytest.raises(ConflictError):
            terminal.withdraw()
        with pytest.raises(ConflictError):
            terminal.complete()


async def test_withdrawing_academic_enrollment_cascades_to_enrolled_courses() -> None:
    fixture = await _fixture()
    second_offering = _offering(
        organization_id=fixture.organization_id,
        term_id=fixture.term.id,
    )
    await fixture.repository.save_course_offering(second_offering)
    enrolled = await _seed_course_enrollment(
        fixture.repository,
        enrollment=fixture.enrollment,
        offering=fixture.offering,
    )
    completed = await _seed_course_enrollment(
        fixture.repository,
        enrollment=fixture.enrollment,
        offering=second_offering,
        status=CourseEnrollmentStatus.COMPLETED,
    )
    bystander_enrollment = _student_enrollment(organization_id=fixture.organization_id)
    await fixture.repository.save_student_enrollment(bystander_enrollment)
    bystander = await _seed_course_enrollment(
        fixture.repository,
        enrollment=bystander_enrollment,
        offering=fixture.offering,
    )

    result = await fixture.service.withdraw_student_enrollment(
        context=fixture.actor,
        enrollment_id=fixture.enrollment.id,
        explanation=f"  {EXPLANATION}  ",
    )

    assert result.status is AcademicEnrollmentStatus.WITHDRAWN
    assert await _stored_enrollment(fixture) == result
    assert (
        await _stored_course_enrollment(fixture, enrolled.id)
    ).status is CourseEnrollmentStatus.WITHDRAWN
    assert await _stored_course_enrollment(fixture, completed.id) == completed
    assert await _stored_course_enrollment(fixture, bystander.id) == bystander
    assert fixture.audit.events == [
        RecordedTransitionEvent(
            action="academics.enrollment.withdrawal_requested",
            organization_id=fixture.organization_id,
            actor_subject_id=fixture.actor.subject_id,
            target_type="academic_enrollment",
            target_id=fixture.enrollment.id,
            correlation_id=fixture.actor.correlation_id,
            outcome="intent_recorded",
            reason=EXPLANATION,
        ),
        RecordedTransitionEvent(
            action="academics.enrollment.withdrawn",
            organization_id=fixture.organization_id,
            actor_subject_id=fixture.actor.subject_id,
            target_type="academic_enrollment",
            target_id=fixture.enrollment.id,
            correlation_id=fixture.actor.correlation_id,
            outcome="succeeded",
            reason=EXPLANATION,
        ),
    ]


async def test_completing_academic_enrollment_requires_settled_courses() -> None:
    fixture = await _fixture()
    course_enrollment = await _seed_course_enrollment(
        fixture.repository,
        enrollment=fixture.enrollment,
        offering=fixture.offering,
    )

    with pytest.raises(ConflictError):
        await fixture.service.complete_student_enrollment(
            context=fixture.actor,
            enrollment_id=fixture.enrollment.id,
            explanation=EXPLANATION,
        )

    assert fixture.audit.events == []
    assert await _stored_enrollment(fixture) == fixture.enrollment

    settled = await fixture.service.complete_course_enrollment(
        context=fixture.actor,
        course_enrollment_id=course_enrollment.id,
        explanation=EXPLANATION,
    )
    result = await fixture.service.complete_student_enrollment(
        context=fixture.actor,
        enrollment_id=fixture.enrollment.id,
        explanation=EXPLANATION,
    )

    assert settled.status is CourseEnrollmentStatus.COMPLETED
    assert result.status is AcademicEnrollmentStatus.COMPLETED
    assert await _stored_enrollment(fixture) == result
    assert fixture.audit.actions == [
        ("academics.course_enrollment.completion_requested", "intent_recorded"),
        ("academics.course_enrollment.completed", "succeeded"),
        ("academics.enrollment.completion_requested", "intent_recorded"),
        ("academics.enrollment.completed", "succeeded"),
    ]
    assert fixture.audit.events[0].target_type == "course_enrollment"
    assert fixture.audit.events[0].target_id == course_enrollment.id


async def test_course_withdrawal_records_evidence_while_the_term_is_open() -> None:
    fixture = await _fixture()
    course_enrollment = await _seed_course_enrollment(
        fixture.repository,
        enrollment=fixture.enrollment,
        offering=fixture.offering,
    )

    result = await fixture.service.withdraw_course_enrollment(
        context=fixture.actor,
        course_enrollment_id=course_enrollment.id,
        explanation=EXPLANATION,
    )

    assert result.status is CourseEnrollmentStatus.WITHDRAWN
    assert await _stored_course_enrollment(fixture, course_enrollment.id) == result
    assert await _stored_enrollment(fixture) == fixture.enrollment
    assert fixture.audit.events == [
        RecordedTransitionEvent(
            action="academics.course_enrollment.withdrawal_requested",
            organization_id=fixture.organization_id,
            actor_subject_id=fixture.actor.subject_id,
            target_type="course_enrollment",
            target_id=course_enrollment.id,
            correlation_id=fixture.actor.correlation_id,
            outcome="intent_recorded",
            reason=EXPLANATION,
        ),
        RecordedTransitionEvent(
            action="academics.course_enrollment.withdrawn",
            organization_id=fixture.organization_id,
            actor_subject_id=fixture.actor.subject_id,
            target_type="course_enrollment",
            target_id=course_enrollment.id,
            correlation_id=fixture.actor.correlation_id,
            outcome="succeeded",
            reason=EXPLANATION,
        ),
    ]


async def test_course_withdrawal_is_rejected_after_closure_but_completion_is_not() -> (
    None
):
    fixture = await _fixture()
    second_offering = _offering(
        organization_id=fixture.organization_id,
        term_id=fixture.term.id,
    )
    await fixture.repository.save_course_offering(second_offering)
    first = await _seed_course_enrollment(
        fixture.repository,
        enrollment=fixture.enrollment,
        offering=fixture.offering,
    )
    second = await _seed_course_enrollment(
        fixture.repository,
        enrollment=fixture.enrollment,
        offering=second_offering,
    )
    await fixture.repository.save_term(fixture.term.close())

    with pytest.raises(ConflictError):
        await fixture.service.withdraw_course_enrollment(
            context=fixture.actor,
            course_enrollment_id=first.id,
            explanation=EXPLANATION,
        )

    assert fixture.audit.events == []
    assert await _stored_course_enrollment(fixture, first.id) == first

    completed = await fixture.service.complete_course_enrollment(
        context=fixture.actor,
        course_enrollment_id=second.id,
        explanation=EXPLANATION,
    )

    assert completed.status is CourseEnrollmentStatus.COMPLETED
    assert await _stored_course_enrollment(fixture, second.id) == completed


async def test_service_requires_the_enrollment_manage_permission() -> None:
    fixture = await _fixture()
    course_enrollment = await _seed_course_enrollment(
        fixture.repository,
        enrollment=fixture.enrollment,
        offering=fixture.offering,
    )
    unauthorized = _actor(
        organization_id=fixture.organization_id,
        permissions=frozenset({ACADEMICS_TERM_CLOSE}),
    )

    with pytest.raises(AuthorizationError):
        await fixture.service.withdraw_student_enrollment(
            context=unauthorized,
            enrollment_id=fixture.enrollment.id,
            explanation=EXPLANATION,
        )
    with pytest.raises(AuthorizationError):
        await fixture.service.complete_student_enrollment(
            context=unauthorized,
            enrollment_id=fixture.enrollment.id,
            explanation=EXPLANATION,
        )
    with pytest.raises(AuthorizationError):
        await fixture.service.withdraw_course_enrollment(
            context=unauthorized,
            course_enrollment_id=course_enrollment.id,
            explanation=EXPLANATION,
        )
    with pytest.raises(AuthorizationError):
        await fixture.service.complete_course_enrollment(
            context=unauthorized,
            course_enrollment_id=course_enrollment.id,
            explanation=EXPLANATION,
        )
    with pytest.raises(AuthorizationError):
        await fixture.administration.list_course_enrollments(
            context=unauthorized,
            student_academic_enrollment_id=None,
            course_offering_id=None,
            status=None,
            limit=50,
            offset=0,
        )

    assert fixture.audit.events == []
    assert await _stored_enrollment(fixture) == fixture.enrollment
    assert (
        await _stored_course_enrollment(fixture, course_enrollment.id)
        == course_enrollment
    )


@pytest.mark.parametrize("explanation", ["   ", "x" * 2001])
async def test_service_requires_a_bounded_explanation(explanation: str) -> None:
    fixture = await _fixture()
    course_enrollment = await _seed_course_enrollment(
        fixture.repository,
        enrollment=fixture.enrollment,
        offering=fixture.offering,
    )

    with pytest.raises(AcademicRuleError):
        await fixture.service.withdraw_student_enrollment(
            context=fixture.actor,
            enrollment_id=fixture.enrollment.id,
            explanation=explanation,
        )
    with pytest.raises(AcademicRuleError):
        await fixture.service.complete_course_enrollment(
            context=fixture.actor,
            course_enrollment_id=course_enrollment.id,
            explanation=explanation,
        )

    assert fixture.audit.events == []
    assert await _stored_enrollment(fixture) == fixture.enrollment
    assert (
        await _stored_course_enrollment(fixture, course_enrollment.id)
        == course_enrollment
    )


async def test_service_accepts_an_explanation_at_the_maximum_length() -> None:
    fixture = await _fixture()

    result = await fixture.service.withdraw_student_enrollment(
        context=fixture.actor,
        enrollment_id=fixture.enrollment.id,
        explanation="x" * 2000,
    )

    assert result.status is AcademicEnrollmentStatus.WITHDRAWN
    assert fixture.audit.events[0].reason == "x" * 2000


async def test_service_does_not_reveal_cross_tenant_or_unknown_enrollments() -> None:
    fixture = await _fixture()
    course_enrollment = await _seed_course_enrollment(
        fixture.repository,
        enrollment=fixture.enrollment,
        offering=fixture.offering,
    )
    other_tenant_actor = _actor(organization_id=uuid4())

    with pytest.raises(NotFoundError):
        await fixture.service.withdraw_student_enrollment(
            context=other_tenant_actor,
            enrollment_id=fixture.enrollment.id,
            explanation=EXPLANATION,
        )
    with pytest.raises(NotFoundError):
        await fixture.service.withdraw_course_enrollment(
            context=other_tenant_actor,
            course_enrollment_id=course_enrollment.id,
            explanation=EXPLANATION,
        )
    with pytest.raises(NotFoundError):
        await fixture.service.complete_student_enrollment(
            context=fixture.actor,
            enrollment_id=uuid4(),
            explanation=EXPLANATION,
        )
    with pytest.raises(NotFoundError):
        await fixture.service.complete_course_enrollment(
            context=fixture.actor,
            course_enrollment_id=uuid4(),
            explanation=EXPLANATION,
        )

    assert fixture.audit.events == []
    assert await _stored_enrollment(fixture) == fixture.enrollment
    assert (
        await _stored_course_enrollment(fixture, course_enrollment.id)
        == course_enrollment
    )


async def test_repeated_transition_is_rejected_without_new_intent() -> None:
    fixture = await _fixture()

    await fixture.service.withdraw_student_enrollment(
        context=fixture.actor,
        enrollment_id=fixture.enrollment.id,
        explanation=EXPLANATION,
    )

    with pytest.raises(EnrollmentTransitionError):
        await fixture.service.withdraw_student_enrollment(
            context=fixture.actor,
            enrollment_id=fixture.enrollment.id,
            explanation="Safe retry",
        )
    with pytest.raises(EnrollmentTransitionError):
        await fixture.service.complete_student_enrollment(
            context=fixture.actor,
            enrollment_id=fixture.enrollment.id,
            explanation="Late completion",
        )

    assert fixture.audit.actions == [
        ("academics.enrollment.withdrawal_requested", "intent_recorded"),
        ("academics.enrollment.withdrawn", "succeeded"),
    ]


async def test_failing_audit_intent_aborts_the_transition() -> None:
    audit = RecordingEnrollmentTransitionAuditSink(
        fail_on_actions=frozenset(
            {
                "academics.enrollment.withdrawal_requested",
                "academics.course_enrollment.withdrawal_requested",
            }
        )
    )
    fixture = await _fixture(audit=audit)
    course_enrollment = await _seed_course_enrollment(
        fixture.repository,
        enrollment=fixture.enrollment,
        offering=fixture.offering,
    )

    with pytest.raises(RuntimeError, match="Enrollment audit is unavailable"):
        await fixture.service.withdraw_student_enrollment(
            context=fixture.actor,
            enrollment_id=fixture.enrollment.id,
            explanation=EXPLANATION,
        )
    with pytest.raises(RuntimeError, match="Enrollment audit is unavailable"):
        await fixture.service.withdraw_course_enrollment(
            context=fixture.actor,
            course_enrollment_id=course_enrollment.id,
            explanation=EXPLANATION,
        )

    assert fixture.audit.events == []
    assert await _stored_enrollment(fixture) == fixture.enrollment
    assert (
        await _stored_course_enrollment(fixture, course_enrollment.id)
        == course_enrollment
    )


async def test_catalog_failure_leaves_intent_without_claiming_success() -> None:
    fixture = await _fixture(repository=FailingSaveAcademicRepository())

    with pytest.raises(RuntimeError, match="Catalog write failed"):
        await fixture.service.withdraw_student_enrollment(
            context=fixture.actor,
            enrollment_id=fixture.enrollment.id,
            explanation=EXPLANATION,
        )

    assert fixture.audit.actions == [
        ("academics.enrollment.withdrawal_requested", "intent_recorded"),
    ]
    assert await _stored_enrollment(fixture) == fixture.enrollment


async def test_locked_re_read_rejects_a_transition_computed_from_stale_state() -> None:
    repository = StaleReadAcademicRepository()
    fixture = await _fixture(repository=repository)
    await fixture.service.withdraw_student_enrollment(
        context=fixture.actor,
        enrollment_id=fixture.enrollment.id,
        explanation=EXPLANATION,
    )
    repository.stale = fixture.enrollment

    with pytest.raises(EnrollmentTransitionError):
        await fixture.service.complete_student_enrollment(
            context=fixture.actor,
            enrollment_id=fixture.enrollment.id,
            explanation=EXPLANATION,
        )

    repository.stale = None
    assert (await _stored_enrollment(fixture)).status is (
        AcademicEnrollmentStatus.WITHDRAWN
    )
    assert fixture.audit.actions == [
        ("academics.enrollment.withdrawal_requested", "intent_recorded"),
        ("academics.enrollment.withdrawn", "succeeded"),
        ("academics.enrollment.completion_requested", "intent_recorded"),
    ]


async def test_list_course_enrollments_filters_within_the_tenant_and_bounds_pages() -> (
    None
):
    fixture = await _fixture()
    second_offering = _offering(
        organization_id=fixture.organization_id,
        term_id=fixture.term.id,
    )
    await fixture.repository.save_course_offering(second_offering)
    other_enrollment = _student_enrollment(organization_id=fixture.organization_id)
    await fixture.repository.save_student_enrollment(other_enrollment)
    first = await _seed_course_enrollment(
        fixture.repository,
        enrollment=fixture.enrollment,
        offering=fixture.offering,
        enrolled_at=NOW,
    )
    second = await _seed_course_enrollment(
        fixture.repository,
        enrollment=fixture.enrollment,
        offering=second_offering,
        status=CourseEnrollmentStatus.COMPLETED,
        enrolled_at=NOW + timedelta(hours=1),
    )
    third = await _seed_course_enrollment(
        fixture.repository,
        enrollment=other_enrollment,
        offering=fixture.offering,
        enrolled_at=NOW + timedelta(hours=2),
    )
    foreign_organization_id = uuid4()
    foreign_offering = _offering(
        organization_id=foreign_organization_id,
        term_id=uuid4(),
    )
    foreign_enrollment = _student_enrollment(organization_id=foreign_organization_id)
    await fixture.repository.save_course_offering(foreign_offering)
    await fixture.repository.save_student_enrollment(foreign_enrollment)
    await _seed_course_enrollment(
        fixture.repository,
        enrollment=foreign_enrollment,
        offering=foreign_offering,
        enrolled_at=NOW + timedelta(hours=3),
    )

    async def listed(
        *,
        student_academic_enrollment_id: UUID | None = None,
        course_offering_id: UUID | None = None,
        status: CourseEnrollmentStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[UUID, ...]:
        values = await fixture.administration.list_course_enrollments(
            context=fixture.actor,
            student_academic_enrollment_id=student_academic_enrollment_id,
            course_offering_id=course_offering_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        return tuple(value.id for value in values)

    assert await listed() == (third.id, second.id, first.id)
    assert await listed(student_academic_enrollment_id=fixture.enrollment.id) == (
        second.id,
        first.id,
    )
    assert await listed(course_offering_id=fixture.offering.id) == (
        third.id,
        first.id,
    )
    assert await listed(status=CourseEnrollmentStatus.COMPLETED) == (second.id,)
    assert await listed(limit=1, offset=1) == (second.id,)
    with pytest.raises(AcademicRuleError):
        await listed(limit=101)


async def test_student_enrollment_routes_are_typed_and_csrf_protected() -> None:
    fixture = await _fixture()
    course_enrollment = await _seed_course_enrollment(
        fixture.repository,
        enrollment=fixture.enrollment,
        offering=fixture.offering,
    )
    app, csrf = _application(fixture)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        withdrawn = await client.post(
            f"{ACADEMICS_PREFIX}/student-enrollments/{fixture.enrollment.id}/withdraw",
            json={"explanation": "  Registrar approval  "},
        )
        listed = await client.get(
            f"{ACADEMICS_PREFIX}/course-enrollments",
            params={"student_academic_enrollment_id": str(fixture.enrollment.id)},
        )

    assert withdrawn.status_code == 200
    assert withdrawn.json()["id"] == str(fixture.enrollment.id)
    assert withdrawn.json()["status"] == "withdrawn"
    assert csrf.calls == 1
    assert fixture.audit.events[0].reason == "Registrar approval"
    assert listed.status_code == 200
    (payload,) = listed.json()
    assert payload["id"] == str(course_enrollment.id)
    assert payload["student_academic_enrollment_id"] == str(fixture.enrollment.id)
    assert payload["course_offering_id"] == str(fixture.offering.id)
    assert Decimal(str(payload["credits"])) == Decimal("3")
    assert payload["status"] == "withdrawn"
    assert datetime.fromisoformat(payload["enrolled_at"]) == NOW
    assert payload["selection_request_id"] == str(
        course_enrollment.selection_request_id
    )


async def test_completion_routes_translate_unsettled_courses_into_conflicts() -> None:
    fixture = await _fixture()
    course_enrollment = await _seed_course_enrollment(
        fixture.repository,
        enrollment=fixture.enrollment,
        offering=fixture.offering,
    )
    app, csrf = _application(fixture)
    enrollment_url = (
        f"{ACADEMICS_PREFIX}/student-enrollments/{fixture.enrollment.id}/complete"
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        blocked = await client.post(
            enrollment_url, json={"explanation": "Program finished"}
        )
        course_completed = await client.post(
            f"{ACADEMICS_PREFIX}/course-enrollments/{course_enrollment.id}/complete",
            json={"explanation": "Final grade recorded"},
        )
        completed = await client.post(
            enrollment_url, json={"explanation": "Program finished"}
        )

    assert blocked.status_code == 409
    assert course_completed.status_code == 200
    assert course_completed.json()["id"] == str(course_enrollment.id)
    assert course_completed.json()["status"] == "completed"
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert csrf.calls == 3


async def test_course_withdrawal_route_reports_term_closure_as_conflict() -> None:
    fixture = await _fixture()
    second_offering = _offering(
        organization_id=fixture.organization_id,
        term_id=fixture.term.id,
    )
    await fixture.repository.save_course_offering(second_offering)
    first = await _seed_course_enrollment(
        fixture.repository,
        enrollment=fixture.enrollment,
        offering=fixture.offering,
    )
    second = await _seed_course_enrollment(
        fixture.repository,
        enrollment=fixture.enrollment,
        offering=second_offering,
    )
    app, _ = _application(fixture)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        withdrawn = await client.post(
            f"{ACADEMICS_PREFIX}/course-enrollments/{first.id}/withdraw",
            json={"explanation": "Dropped before the deadline"},
        )
        await fixture.repository.save_term(fixture.term.close())
        rejected = await client.post(
            f"{ACADEMICS_PREFIX}/course-enrollments/{second.id}/withdraw",
            json={"explanation": "Dropped after closure"},
        )
        filtered = await client.get(
            f"{ACADEMICS_PREFIX}/course-enrollments",
            params={"course_offering_id": str(fixture.offering.id)},
        )
        by_status = await client.get(
            f"{ACADEMICS_PREFIX}/course-enrollments",
            params={"status": "enrolled", "limit": 1, "offset": 0},
        )

    assert withdrawn.status_code == 200
    assert withdrawn.json()["status"] == "withdrawn"
    assert rejected.status_code == 409
    assert [value["id"] for value in filtered.json()] == [str(first.id)]
    assert [value["id"] for value in by_status.json()] == [str(second.id)]


async def test_transition_routes_reject_invalid_input_and_unknown_targets() -> None:
    fixture = await _fixture()
    app, csrf = _application(fixture)
    withdraw_url = (
        f"{ACADEMICS_PREFIX}/student-enrollments/{fixture.enrollment.id}/withdraw"
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        unknown_field = await client.post(
            withdraw_url, json={"explanation": "x", "force": True}
        )
        empty = await client.post(withdraw_url, json={"explanation": ""})
        overlong = await client.post(withdraw_url, json={"explanation": "x" * 2001})
        missing_enrollment = await client.post(
            f"{ACADEMICS_PREFIX}/student-enrollments/{uuid4()}/withdraw",
            json={"explanation": "x"},
        )
        missing_course = await client.post(
            f"{ACADEMICS_PREFIX}/course-enrollments/{uuid4()}/complete",
            json={"explanation": "x"},
        )
        overlong_page = await client.get(
            f"{ACADEMICS_PREFIX}/course-enrollments", params={"limit": 101}
        )
        unknown_status = await client.get(
            f"{ACADEMICS_PREFIX}/course-enrollments", params={"status": "paused"}
        )

    assert unknown_field.status_code == 422
    assert empty.status_code == 422
    assert overlong.status_code == 422
    assert missing_enrollment.status_code == 404
    assert missing_course.status_code == 404
    assert overlong_page.status_code == 422
    assert unknown_status.status_code == 422
    assert fixture.audit.events == []
    assert await _stored_enrollment(fixture) == fixture.enrollment
    assert csrf.calls == 5


async def test_transition_routes_require_an_authorized_tenant_actor() -> None:
    fixture = await _fixture()
    withdraw_url = (
        f"{ACADEMICS_PREFIX}/student-enrollments/{fixture.enrollment.id}/withdraw"
    )
    platform_actor = PlatformActorContext(
        subject_id=uuid4(),
        correlation_id="platform-correlation",
        permissions=frozenset({ACADEMICS_ENROLLMENT_MANAGE}),
    )
    unauthorized_tenant = _actor(
        organization_id=fixture.organization_id,
        permissions=frozenset(),
    )

    for actor in (platform_actor, unauthorized_tenant):
        app, _ = _application(fixture, actor=actor)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            forbidden = await client.post(withdraw_url, json={"explanation": "x"})
            forbidden_list = await client.get(f"{ACADEMICS_PREFIX}/course-enrollments")
        assert forbidden.status_code == 403
        assert forbidden_list.status_code == 403

    assert fixture.audit.events == []
    assert await _stored_enrollment(fixture) == fixture.enrollment


async def test_application_audit_sink_records_transition_reason_only() -> None:
    repository = InMemoryAuditRepository()
    sink = ApplicationAuditSink(AuditService(repository))
    organization_id = uuid4()
    actor_subject_id = uuid4()
    enrollment_id = uuid4()
    course_enrollment_id = uuid4()

    await sink.record_enrollment_transition_event(
        action="academics.enrollment.withdrawal_requested",
        organization_id=organization_id,
        actor_subject_id=actor_subject_id,
        target_type="academic_enrollment",
        target_id=enrollment_id,
        correlation_id="enrollment-correlation",
        outcome="intent_recorded",
        reason="Registrar approval",
    )
    await sink.record_enrollment_transition_event(
        action="academics.course_enrollment.completed",
        organization_id=organization_id,
        actor_subject_id=actor_subject_id,
        target_type="course_enrollment",
        target_id=course_enrollment_id,
        correlation_id="enrollment-correlation",
        outcome="succeeded",
        reason="Final grade recorded",
    )

    academic, course = repository.records
    assert academic.organization_id == organization_id
    assert academic.actor_subject_id == actor_subject_id
    assert academic.action == "academics.enrollment.withdrawal_requested"
    assert academic.entity_type == "academic_enrollment"
    assert academic.entity_id == str(enrollment_id)
    assert academic.correlation_id == "enrollment-correlation"
    assert academic.outcome == "intent_recorded"
    assert academic.reason == "Registrar approval"
    assert academic.metadata is None
    assert course.entity_type == "course_enrollment"
    assert course.entity_id == str(course_enrollment_id)
    assert course.outcome == "succeeded"
    assert course.reason == "Final grade recorded"
    assert course.metadata is None
