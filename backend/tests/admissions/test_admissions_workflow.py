import asyncio
from dataclasses import dataclass
from dataclasses import replace
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from uuid import UUID
from uuid import uuid4

import pytest

from academics.application.contracts import AcceptedStudentAcademicEnrollmentCommand
from academics.application.contracts import AcceptedStudentAcademicEnrollmentResult
from admissions.application.ports import AcceptedApplicantEnrollmentRegistrar
from admissions.application.ports import AdmissionsAuditSink
from admissions.application.service import ADMISSIONS_APPLICATION_CREATE
from admissions.application.service import ADMISSIONS_APPLICATION_SUBMIT
from admissions.application.service import ADMISSIONS_DECIDE
from admissions.application.service import ADMISSIONS_ENROLL
from admissions.application.service import ADMISSIONS_POLICY_MANAGE
from admissions.application.service import ADMISSIONS_REVIEW
from admissions.application.service import AdmissionsService
from admissions.domain.exceptions import AdmissionsRuleError
from admissions.domain.exceptions import EnrollmentConversionError
from admissions.domain.exceptions import QuotaUnavailableError
from admissions.domain.models import AdmissionDecision
from admissions.domain.models import AdmissionDecisionOutcome
from admissions.domain.models import AdmissionQuota
from admissions.domain.models import AdmissionsPolicy
from admissions.domain.models import ApplicantProfile
from admissions.domain.models import Application
from admissions.domain.models import ApplicationSource
from admissions.domain.models import ApplicationStatus
from admissions.domain.models import ReviewOutcome
from admissions.domain.models import ReviewStage
from admissions.infrastructure.repository import (
    InMemoryAcceptedApplicantEnrollmentRegistrar,
)
from admissions.infrastructure.repository import InMemoryAdmissionsRepository
from admissions.infrastructure.repository import InMemoryAdmissionsTargetDirectory
from admissions.infrastructure.repository import StaticDepositVerifier
from admissions.infrastructure.repository import UnconfiguredDepositVerifier
from admissions_enrollment_adapter import (
    ModuleOwnedAcceptedApplicantEnrollmentRegistrar,
)
from core.context import TenantActorContext
from core.errors import NotFoundError
from people.application.contracts import AcceptedStudentRegistrationCommand
from people.application.contracts import AcceptedStudentRegistrationResult


@dataclass(frozen=True, slots=True)
class FakeClock:
    current: datetime

    def now(self) -> datetime:
        return self.current


@dataclass(frozen=True, slots=True)
class AdmissionsFixture:
    organization_id: UUID
    program_id: UUID
    intake_id: UUID
    targets: InMemoryAdmissionsTargetDirectory
    repository: InMemoryAdmissionsRepository
    registrar: AcceptedApplicantEnrollmentRegistrar
    service: AdmissionsService


class IdempotentPeopleRegistrar:
    """Record idempotent People results for conversion-resume tests."""

    def __init__(self) -> None:
        self.calls: list[AcceptedStudentRegistrationCommand] = []
        self._results: dict[UUID, AcceptedStudentRegistrationResult] = {}

    async def register_accepted_student(
        self,
        command: AcceptedStudentRegistrationCommand,
    ) -> AcceptedStudentRegistrationResult:
        self.calls.append(command)
        result = self._results.get(command.idempotency_key)
        if result is None:
            result = AcceptedStudentRegistrationResult(
                person_id=uuid4(),
                student_profile_id=command.student_profile_id,
            )
            self._results[command.idempotency_key] = result
        return result


class FailOnceAcademicRegistrar:
    """Simulate a crash after the People step commits."""

    def __init__(self) -> None:
        self.calls: list[AcceptedStudentAcademicEnrollmentCommand] = []

    async def enroll_accepted_student(
        self,
        command: AcceptedStudentAcademicEnrollmentCommand,
    ) -> AcceptedStudentAcademicEnrollmentResult:
        self.calls.append(command)
        if len(self.calls) == 1:
            raise RuntimeError("simulated crash after People commit")
        return AcceptedStudentAcademicEnrollmentResult(
            academic_enrollment_id=command.academic_enrollment_id,
        )


class RecordingAdmissionsAuditSink:
    """Capture minimized decision evidence and optionally fail closed."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[tuple[str, UUID, UUID, str, str]] = []

    async def record_admissions_decision_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        application_id: UUID,
        correlation_id: str,
        outcome: str,
        reason: str,
    ) -> None:
        del actor_subject_id, correlation_id
        if self.fail:
            raise RuntimeError("audit unavailable")
        self.events.append((action, organization_id, application_id, outcome, reason))


def _context(
    *,
    organization_id: UUID,
    permissions: frozenset[str],
) -> TenantActorContext:
    return TenantActorContext(
        subject_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        correlation_id="admissions-test",
        permissions=permissions,
    )


async def _fixture(
    *,
    required_stages: tuple[ReviewStage, ...] = (),
    quota_capacity: int = 2,
    deposit_required: bool = False,
    deposit_satisfied: bool = True,
    registrar: AcceptedApplicantEnrollmentRegistrar | None = None,
    audit: AdmissionsAuditSink | None = None,
) -> AdmissionsFixture:
    organization_id = uuid4()
    program_id = uuid4()
    intake_id = uuid4()
    targets = InMemoryAdmissionsTargetDirectory(
        {(organization_id, program_id, intake_id)}
    )
    repository = InMemoryAdmissionsRepository()
    effective_registrar = registrar or InMemoryAcceptedApplicantEnrollmentRegistrar()
    service = AdmissionsService(
        repository=repository,
        targets=targets,
        registrar=effective_registrar,
        deposits=StaticDepositVerifier(satisfied=deposit_satisfied),
        clock=FakeClock(datetime(2026, 8, 5, 9, tzinfo=UTC)),
        audit=audit or RecordingAdmissionsAuditSink(),
    )
    administrator = _context(
        organization_id=organization_id,
        permissions=frozenset({ADMISSIONS_POLICY_MANAGE}),
    )
    await service.configure_policy(
        context=administrator,
        policy=AdmissionsPolicy(
            organization_id=organization_id,
            program_id=program_id,
            intake_id=intake_id,
            required_stages=required_stages,
            deposit_required=deposit_required,
            deposit_amount=Decimal("100") if deposit_required else None,
            deposit_currency="USD" if deposit_required else None,
            reservation_duration=timedelta(days=7),
        ),
    )
    await service.configure_quota(
        context=administrator,
        quota=AdmissionQuota(
            id=uuid4(),
            organization_id=organization_id,
            program_id=program_id,
            intake_id=intake_id,
            seat_category="general",
            capacity=quota_capacity,
        ),
    )
    return AdmissionsFixture(
        organization_id=organization_id,
        program_id=program_id,
        intake_id=intake_id,
        targets=targets,
        repository=repository,
        registrar=effective_registrar,
        service=service,
    )


async def _submitted_application(
    fixture: AdmissionsFixture,
    *,
    suffix: str,
) -> Application:
    actor = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset(
            {ADMISSIONS_APPLICATION_CREATE, ADMISSIONS_APPLICATION_SUBMIT}
        ),
    )
    application = await fixture.service.create_application(
        context=actor,
        profile=ApplicantProfile(
            id=uuid4(),
            organization_id=fixture.organization_id,
            given_name="Applicant",
            family_name=suffix,
            email=f"applicant-{suffix}@example.test",
            phone=None,
        ),
        program_id=fixture.program_id,
        intake_id=fixture.intake_id,
        seat_category="general",
        source=ApplicationSource.ADMINISTRATOR_ENTERED,
    )
    return await fixture.service.submit_application(
        context=actor,
        application_id=application.id,
    )


async def test_required_review_must_pass_before_acceptance() -> None:
    fixture = await _fixture(required_stages=(ReviewStage.INTERVIEW,))
    application = await _submitted_application(fixture, suffix="review")
    decision_actor = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({ADMISSIONS_DECIDE}),
    )

    with pytest.raises(AdmissionsRuleError, match="review stages"):
        await fixture.service.decide_application(
            context=decision_actor,
            application_id=application.id,
            outcome=AdmissionDecisionOutcome.ACCEPTED,
            reason="Meets admission requirements.",
        )

    reviewer = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({ADMISSIONS_REVIEW}),
    )
    review = await fixture.service.record_review(
        context=reviewer,
        application_id=application.id,
        stage=ReviewStage.INTERVIEW,
        outcome=ReviewOutcome.PASSED,
    )
    decision = await fixture.service.decide_application(
        context=decision_actor,
        application_id=application.id,
        outcome=AdmissionDecisionOutcome.ACCEPTED,
        reason="All configured reviews passed.",
    )

    assert review.reviewer_id == reviewer.subject_id
    assert decision.reservation_id is not None


async def test_acceptance_rejects_an_academic_intake_closed_after_submission() -> None:
    fixture = await _fixture()
    application = await _submitted_application(fixture, suffix="closed-intake")
    fixture.targets.close(
        organization_id=fixture.organization_id,
        program_id=fixture.program_id,
        intake_id=fixture.intake_id,
    )
    decision_actor = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({ADMISSIONS_DECIDE}),
    )

    with pytest.raises(AdmissionsRuleError, match="closed academic intake"):
        await fixture.service.decide_application(
            context=decision_actor,
            application_id=application.id,
            outcome=AdmissionDecisionOutcome.ACCEPTED,
            reason="The earlier submission no longer has a valid intake.",
        )

    stored = await fixture.repository.get_application(
        organization_id=fixture.organization_id,
        application_id=application.id,
    )
    assert stored is not None
    assert stored.status is ApplicationStatus.SUBMITTED


async def test_quota_reservation_is_atomic_under_concurrent_acceptance() -> None:
    fixture = await _fixture(quota_capacity=1)
    first = await _submitted_application(fixture, suffix="first")
    second = await _submitted_application(fixture, suffix="second")
    decision_actor = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({ADMISSIONS_DECIDE}),
    )

    results = await asyncio.gather(
        fixture.service.decide_application(
            context=decision_actor,
            application_id=first.id,
            outcome=AdmissionDecisionOutcome.ACCEPTED,
            reason="Qualified applicant.",
        ),
        fixture.service.decide_application(
            context=decision_actor,
            application_id=second.id,
            outcome=AdmissionDecisionOutcome.ACCEPTED,
            reason="Qualified applicant.",
        ),
        return_exceptions=True,
    )

    assert sum(isinstance(result, AdmissionDecision) for result in results) == 1
    assert sum(isinstance(result, QuotaUnavailableError) for result in results) == 1


async def test_accepted_application_conversion_is_idempotent() -> None:
    fixture = await _fixture()
    application = await _submitted_application(fixture, suffix="enroll")
    actor = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({ADMISSIONS_DECIDE, ADMISSIONS_ENROLL}),
    )
    await fixture.service.decide_application(
        context=actor,
        application_id=application.id,
        outcome=AdmissionDecisionOutcome.ACCEPTED,
        reason="Eligible for enrollment.",
    )

    first = await fixture.service.enroll_accepted_application(
        context=actor,
        application_id=application.id,
    )
    second = await fixture.service.enroll_accepted_application(
        context=actor,
        application_id=application.id,
    )

    stored = await fixture.repository.get_application(
        organization_id=fixture.organization_id,
        application_id=application.id,
    )
    assert first == second
    assert isinstance(
        fixture.registrar,
        InMemoryAcceptedApplicantEnrollmentRegistrar,
    )
    assert len(fixture.registrar.commands) == 1
    conversion = await fixture.repository.get_conversion_for_application(
        organization_id=fixture.organization_id,
        application_id=application.id,
    )
    assert conversion is not None
    assert first.student_id == conversion.student_id
    assert first.academic_enrollment_id == conversion.academic_enrollment_id
    assert first.student_id != application.applicant_profile_id
    assert stored is not None
    assert stored.status is ApplicationStatus.ENROLLED


async def test_required_deposit_blocks_enrollment_until_verified() -> None:
    fixture = await _fixture(
        deposit_required=True,
        deposit_satisfied=False,
    )
    application = await _submitted_application(fixture, suffix="deposit")
    actor = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({ADMISSIONS_DECIDE, ADMISSIONS_ENROLL}),
    )
    await fixture.service.decide_application(
        context=actor,
        application_id=application.id,
        outcome=AdmissionDecisionOutcome.ACCEPTED,
        reason="Conditional acceptance.",
    )

    with pytest.raises(EnrollmentConversionError, match="deposit"):
        await fixture.service.enroll_accepted_application(
            context=actor,
            application_id=application.id,
        )


async def test_cross_tenant_application_lookup_fails_closed() -> None:
    fixture = await _fixture()
    application = await _submitted_application(fixture, suffix="tenant")
    attacker = _context(
        organization_id=uuid4(),
        permissions=frozenset({ADMISSIONS_DECIDE}),
    )

    with pytest.raises(NotFoundError):
        await fixture.service.decide_application(
            context=attacker,
            application_id=application.id,
            outcome=AdmissionDecisionOutcome.REJECTED,
            reason="Unauthorized cross-tenant attempt.",
        )


async def test_decision_audit_intent_is_durable_before_mutation() -> None:
    audit = RecordingAdmissionsAuditSink()
    fixture = await _fixture(audit=audit)
    application = await _submitted_application(fixture, suffix="audited")
    actor = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({ADMISSIONS_DECIDE}),
    )

    await fixture.service.decide_application(
        context=actor,
        application_id=application.id,
        outcome=AdmissionDecisionOutcome.REJECTED,
        reason="Does not meet the published requirements.",
    )

    assert [event[0] for event in audit.events] == [
        "admissions.application.decision_requested",
        "admissions.application.decided",
    ]
    assert [event[3] for event in audit.events] == [
        "intent_recorded",
        "succeeded",
    ]


async def test_decision_aborts_when_audit_intent_cannot_be_recorded() -> None:
    fixture = await _fixture(audit=RecordingAdmissionsAuditSink(fail=True))
    application = await _submitted_application(fixture, suffix="audit-failure")
    actor = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({ADMISSIONS_DECIDE}),
    )

    with pytest.raises(RuntimeError, match="audit unavailable"):
        await fixture.service.decide_application(
            context=actor,
            application_id=application.id,
            outcome=AdmissionDecisionOutcome.REJECTED,
            reason="Decision requires durable evidence.",
        )

    stored = await fixture.repository.get_application(
        organization_id=fixture.organization_id,
        application_id=application.id,
    )
    assert stored is not None
    assert stored.status is ApplicationStatus.SUBMITTED


async def test_unconfigured_deposit_verifier_fails_closed() -> None:
    fixture = await _fixture(deposit_required=True)
    application = await _submitted_application(fixture, suffix="unconfigured")

    assert not await UnconfiguredDepositVerifier().is_satisfied(
        organization_id=fixture.organization_id,
        application_id=application.id,
        requirement=application.deposit,
    )


async def test_conversion_resumes_after_crash_between_downstream_modules() -> None:
    people = IdempotentPeopleRegistrar()
    academics = FailOnceAcademicRegistrar()
    registrar = ModuleOwnedAcceptedApplicantEnrollmentRegistrar(
        people=people,
        academics=academics,
    )
    fixture = await _fixture(registrar=registrar)
    application = await _submitted_application(fixture, suffix="resumable")
    actor = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({ADMISSIONS_DECIDE, ADMISSIONS_ENROLL}),
    )
    await fixture.service.decide_application(
        context=actor,
        application_id=application.id,
        outcome=AdmissionDecisionOutcome.ACCEPTED,
        reason="Eligible for durable enrollment.",
    )

    with pytest.raises(RuntimeError, match="after People"):
        await fixture.service.enroll_accepted_application(
            context=actor,
            application_id=application.id,
        )

    pending = await fixture.repository.get_conversion_for_application(
        organization_id=fixture.organization_id,
        application_id=application.id,
    )
    assert pending is not None
    assert pending.status.value == "pending"
    assert pending.student_id != application.applicant_profile_id
    assert people.calls[0].given_name == "Applicant"
    assert people.calls[0].family_name == "resumable"
    assert people.calls[0].email == "applicant-resumable@example.test"
    assert people.calls[0].student_profile_id == pending.student_id
    assert academics.calls[0].academic_enrollment_id == pending.academic_enrollment_id

    retry_actor = replace(
        actor,
        subject_id=uuid4(),
        correlation_id="retry-correlation",
    )
    result = await fixture.service.enroll_accepted_application(
        context=retry_actor,
        application_id=application.id,
    )

    assert result.student_id == pending.student_id
    assert result.academic_enrollment_id == pending.academic_enrollment_id
    assert len(people.calls) == 2
    assert people.calls[0].idempotency_key == people.calls[1].idempotency_key
    assert people.calls[1].actor_subject_id == actor.subject_id
    assert people.calls[1].correlation_id == actor.correlation_id
    assert academics.calls[0] == academics.calls[1]


async def test_cross_tenant_enrollment_cannot_start_a_conversion() -> None:
    people = IdempotentPeopleRegistrar()
    academics = FailOnceAcademicRegistrar()
    fixture = await _fixture(
        registrar=ModuleOwnedAcceptedApplicantEnrollmentRegistrar(
            people=people,
            academics=academics,
        )
    )
    application = await _submitted_application(fixture, suffix="protected")
    owner = _context(
        organization_id=fixture.organization_id,
        permissions=frozenset({ADMISSIONS_DECIDE}),
    )
    await fixture.service.decide_application(
        context=owner,
        application_id=application.id,
        outcome=AdmissionDecisionOutcome.ACCEPTED,
        reason="Accepted by the owning tenant.",
    )
    attacker = _context(
        organization_id=uuid4(),
        permissions=frozenset({ADMISSIONS_ENROLL}),
    )

    with pytest.raises(NotFoundError):
        await fixture.service.enroll_accepted_application(
            context=attacker,
            application_id=application.id,
        )

    assert people.calls == []
    assert academics.calls == []
