"""Admissions workflow, quota, review, decision, and conversion services."""

from dataclasses import replace
from datetime import datetime
from uuid import UUID

from admissions.application.contracts import AcceptedApplicantEnrollmentCommand
from admissions.application.contracts import AcceptedApplicantEnrollmentResult
from admissions.application.ports import AcceptedApplicantEnrollmentRegistrar
from admissions.application.ports import AdmissionsClock
from admissions.application.ports import AdmissionsRepository
from admissions.application.ports import AdmissionsTargetDirectory
from admissions.application.ports import DepositVerifier
from admissions.domain.exceptions import AdmissionsRuleError
from admissions.domain.exceptions import EnrollmentConversionError
from admissions.domain.models import AdmissionDecision
from admissions.domain.models import AdmissionDecisionOutcome
from admissions.domain.models import AdmissionQuota
from admissions.domain.models import AdmissionsPolicy
from admissions.domain.models import ApplicantProfile
from admissions.domain.models import Application
from admissions.domain.models import ApplicationDocument
from admissions.domain.models import ApplicationSource
from admissions.domain.models import ApplicationStatus
from admissions.domain.models import DepositRequirement
from admissions.domain.models import DepositStatus
from admissions.domain.models import EnrollmentConversion
from admissions.domain.models import EnrollmentConversionStatus
from admissions.domain.models import ReservationStatus
from admissions.domain.models import ReviewOutcome
from admissions.domain.models import ReviewRecord
from admissions.domain.models import ReviewStage
from admissions.domain.models import SeatReservation
from admissions.domain.models import transition_application
from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import NotFoundError
from core.identifiers import new_uuid7

ADMISSIONS_APPLICATION_CREATE = "admissions.application.create"
ADMISSIONS_APPLICATION_SUBMIT = "admissions.application.submit"
ADMISSIONS_DOCUMENT_MANAGE = "admissions.document.manage"
ADMISSIONS_REVIEW = "admissions.review"
ADMISSIONS_DECIDE = "admissions.decision.manage"
ADMISSIONS_POLICY_MANAGE = "admissions.policy.manage"
ADMISSIONS_ENROLL = "admissions.application.enroll"
MAX_ADMISSIONS_ADMIN_PAGE_SIZE = 100


class AdmissionsService:
    """Orchestrate tenant admissions under configurable policy and quota rules."""

    def __init__(
        self,
        *,
        repository: AdmissionsRepository,
        targets: AdmissionsTargetDirectory,
        registrar: AcceptedApplicantEnrollmentRegistrar,
        deposits: DepositVerifier,
        clock: AdmissionsClock,
    ) -> None:
        self._repository = repository
        self._targets = targets
        self._registrar = registrar
        self._deposits = deposits
        self._clock = clock

    async def configure_policy(
        self,
        *,
        context: TenantActorContext,
        policy: AdmissionsPolicy,
    ) -> None:
        """Configure admissions stages and deposit policy for one target."""

        _authorize(context, ADMISSIONS_POLICY_MANAGE)
        _require_tenant(context, policy.organization_id)
        if not await self._targets.target_exists(
            organization_id=context.organization_id,
            program_id=policy.program_id,
            intake_id=policy.intake_id,
        ):
            raise NotFoundError("Admissions program or intake was not found.")
        await self._repository.save_policy(policy)

    async def configure_quota(
        self,
        *,
        context: TenantActorContext,
        quota: AdmissionQuota,
    ) -> None:
        """Configure a tenant program, intake, and seat-category quota."""

        _authorize(context, ADMISSIONS_POLICY_MANAGE)
        _require_tenant(context, quota.organization_id)
        if not await self._targets.target_exists(
            organization_id=context.organization_id,
            program_id=quota.program_id,
            intake_id=quota.intake_id,
        ):
            raise NotFoundError("Admissions program or intake was not found.")
        await self._repository.save_quota(quota)

    async def get_application(
        self,
        *,
        context: TenantActorContext,
        application_id: UUID,
    ) -> Application:
        """Return one tenant application to an authorized admissions reviewer."""

        _authorize(context, ADMISSIONS_REVIEW)
        return await self._require_application(context, application_id)

    async def list_applications(
        self,
        *,
        context: TenantActorContext,
        status: ApplicationStatus | None,
        program_id: UUID | None,
        intake_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Application, ...]:
        """Return a filtered, bounded page for admissions administration."""

        _authorize(context, ADMISSIONS_REVIEW)
        _validate_page(limit=limit, offset=offset)
        return await self._repository.list_applications(
            organization_id=context.organization_id,
            status=status,
            program_id=program_id,
            intake_id=intake_id,
            limit=limit,
            offset=offset,
        )

    async def list_documents(
        self,
        *,
        context: TenantActorContext,
        application_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[ApplicationDocument, ...]:
        """Return bounded safe metadata for an authorized application."""

        _authorize(context, ADMISSIONS_DOCUMENT_MANAGE)
        _validate_page(limit=limit, offset=offset)
        await self._require_application(context, application_id)
        return await self._repository.list_documents(
            organization_id=context.organization_id,
            application_id=application_id,
            limit=limit,
            offset=offset,
        )

    async def list_reviews(
        self,
        *,
        context: TenantActorContext,
        application_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[ReviewRecord, ...]:
        """Return a bounded immutable review history page."""

        _authorize(context, ADMISSIONS_REVIEW)
        _validate_page(limit=limit, offset=offset)
        await self._require_application(context, application_id)
        return await self._repository.list_reviews_page(
            organization_id=context.organization_id,
            application_id=application_id,
            limit=limit,
            offset=offset,
        )

    async def get_policy(
        self,
        *,
        context: TenantActorContext,
        program_id: UUID,
        intake_id: UUID,
    ) -> AdmissionsPolicy:
        """Return one authorized admissions policy configuration."""

        _authorize(context, ADMISSIONS_POLICY_MANAGE)
        policy = await self._repository.get_policy(
            organization_id=context.organization_id,
            program_id=program_id,
            intake_id=intake_id,
        )
        if policy is None:
            raise NotFoundError("Admissions policy was not found.")
        return policy

    async def get_quota(
        self,
        *,
        context: TenantActorContext,
        program_id: UUID,
        intake_id: UUID,
        seat_category: str,
    ) -> AdmissionQuota:
        """Return one authorized categorized admissions quota."""

        _authorize(context, ADMISSIONS_POLICY_MANAGE)
        quota = await self._repository.get_quota(
            organization_id=context.organization_id,
            program_id=program_id,
            intake_id=intake_id,
            seat_category=seat_category,
        )
        if quota is None:
            raise NotFoundError("Admission quota was not found.")
        return quota

    async def create_application(
        self,
        *,
        context: TenantActorContext,
        profile: ApplicantProfile,
        program_id: UUID,
        intake_id: UUID,
        seat_category: str,
        source: ApplicationSource,
    ) -> Application:
        """Create an applicant profile and draft application under target policy."""

        _authorize(context, ADMISSIONS_APPLICATION_CREATE)
        _require_tenant(context, profile.organization_id)
        if not await self._targets.target_exists(
            organization_id=context.organization_id,
            program_id=program_id,
            intake_id=intake_id,
        ):
            raise NotFoundError("Admissions program or intake was not found.")
        policy = await self._repository.get_policy(
            organization_id=context.organization_id,
            program_id=program_id,
            intake_id=intake_id,
        )
        if policy is None:
            raise NotFoundError("Admissions policy was not found.")
        now = self._clock.now()
        deposit = _deposit_requirement(policy=policy, created_at=now)
        application = Application(
            id=new_uuid7(),
            organization_id=context.organization_id,
            applicant_profile_id=profile.id,
            program_id=program_id,
            intake_id=intake_id,
            seat_category=seat_category,
            source=source,
            status=ApplicationStatus.DRAFT,
            created_at=now,
            status_changed_at=now,
            deposit=deposit,
        )
        await self._repository.create_application(
            profile=profile,
            application=application,
        )
        return application

    async def submit_application(
        self,
        *,
        context: TenantActorContext,
        application_id: UUID,
    ) -> Application:
        """Submit a draft admissions application for configured review."""

        _authorize(context, ADMISSIONS_APPLICATION_SUBMIT)
        application = await self._require_application(context, application_id)
        submitted = transition_application(
            application=application,
            target=ApplicationStatus.SUBMITTED,
            changed_at=self._clock.now(),
        )
        await self._repository.save_application(
            application=submitted,
            expected_status=application.status,
        )
        return submitted

    async def add_document(
        self,
        *,
        context: TenantActorContext,
        document: ApplicationDocument,
    ) -> None:
        """Append safe file metadata to a tenant application."""

        _authorize(context, ADMISSIONS_DOCUMENT_MANAGE)
        _require_tenant(context, document.organization_id)
        application = await self._require_application(context, document.application_id)
        if application.status in {
            ApplicationStatus.REJECTED,
            ApplicationStatus.ENROLLED,
            ApplicationStatus.WITHDRAWN,
        }:
            raise AdmissionsRuleError(
                "Documents cannot be added after the application is final."
            )
        await self._repository.save_document(document)

    async def record_review(
        self,
        *,
        context: TenantActorContext,
        application_id: UUID,
        stage: ReviewStage,
        outcome: ReviewOutcome,
        explanation: str | None = None,
    ) -> ReviewRecord:
        """Append a configured review result and advance the review lifecycle."""

        _authorize(context, ADMISSIONS_REVIEW)
        application = await self._require_application(context, application_id)
        if application.status not in {
            ApplicationStatus.SUBMITTED,
            ApplicationStatus.AWAITING_EXAM,
            ApplicationStatus.AWAITING_INTERVIEW,
            ApplicationStatus.UNDER_REVIEW,
        }:
            raise AdmissionsRuleError("Application is not open for review.")
        policy = await self._require_policy(application)
        if stage not in policy.required_stages:
            raise AdmissionsRuleError("Review stage is not configured for this intake.")
        completed_at = self._clock.now()
        review = ReviewRecord(
            id=new_uuid7(),
            organization_id=context.organization_id,
            application_id=application.id,
            stage=stage,
            outcome=outcome,
            reviewer_id=context.subject_id,
            completed_at=completed_at,
            explanation=explanation,
        )
        reviewed_application = (
            application
            if application.status is ApplicationStatus.UNDER_REVIEW
            else transition_application(
                application=application,
                target=ApplicationStatus.UNDER_REVIEW,
                changed_at=completed_at,
            )
        )
        await self._repository.save_review(
            review=review,
            application=reviewed_application,
            expected_status=application.status,
        )
        return review

    async def decide_application(
        self,
        *,
        context: TenantActorContext,
        application_id: UUID,
        outcome: AdmissionDecisionOutcome,
        reason: str,
    ) -> AdmissionDecision:
        """Make an official decision and reserve quota atomically on acceptance."""

        _authorize(context, ADMISSIONS_DECIDE)
        application = await self._require_application(context, application_id)
        if application.status not in {
            ApplicationStatus.SUBMITTED,
            ApplicationStatus.UNDER_REVIEW,
            ApplicationStatus.WAITLISTED,
        }:
            raise AdmissionsRuleError("Application is not ready for a decision.")
        policy = await self._require_policy(application)
        now = self._clock.now()
        if outcome is AdmissionDecisionOutcome.ACCEPTED:
            await self._require_passing_reviews(application, policy)
            quota = await self._repository.get_quota(
                organization_id=context.organization_id,
                program_id=application.program_id,
                intake_id=application.intake_id,
                seat_category=application.seat_category,
            )
            if quota is None:
                raise NotFoundError("Admission quota was not found.")
            reservation = SeatReservation(
                id=new_uuid7(),
                organization_id=context.organization_id,
                quota_id=quota.id,
                application_id=application.id,
                status=ReservationStatus.ACTIVE,
                reserved_at=now,
                expires_at=now + policy.reservation_duration,
            )
            accepted = transition_application(
                application=application,
                target=ApplicationStatus.ACCEPTED,
                changed_at=now,
            )
            decision = AdmissionDecision(
                id=new_uuid7(),
                organization_id=context.organization_id,
                application_id=application.id,
                outcome=outcome,
                decided_by=context.subject_id,
                decided_at=now,
                reason=reason,
                reservation_id=reservation.id,
            )
            await self._repository.decide_with_reservation(
                application=accepted,
                expected_status=application.status,
                decision=decision,
                quota=quota,
                reservation=reservation,
                evaluated_at=now,
            )
            return decision

        target = (
            ApplicationStatus.REJECTED
            if outcome is AdmissionDecisionOutcome.REJECTED
            else ApplicationStatus.WAITLISTED
        )
        decided_application = transition_application(
            application=application,
            target=target,
            changed_at=now,
        )
        decision = AdmissionDecision(
            id=new_uuid7(),
            organization_id=context.organization_id,
            application_id=application.id,
            outcome=outcome,
            decided_by=context.subject_id,
            decided_at=now,
            reason=reason,
        )
        await self._repository.save_decision(
            application=decided_application,
            expected_status=application.status,
            decision=decision,
        )
        return decision

    async def enroll_accepted_application(
        self,
        *,
        context: TenantActorContext,
        application_id: UUID,
    ) -> AcceptedApplicantEnrollmentResult:
        """Idempotently convert an accepted application into official enrollment."""

        _authorize(context, ADMISSIONS_ENROLL)
        application = await self._require_application(context, application_id)
        existing_conversion = await self._repository.get_conversion_for_application(
            organization_id=context.organization_id,
            application_id=application.id,
        )
        if (
            existing_conversion is not None
            and existing_conversion.status is EnrollmentConversionStatus.COMPLETED
        ):
            return AcceptedApplicantEnrollmentResult(
                student_id=existing_conversion.student_id,
                academic_enrollment_id=(existing_conversion.academic_enrollment_id),
            )
        if application.status is not ApplicationStatus.ACCEPTED:
            raise EnrollmentConversionError("Application has not been accepted.")
        now = self._clock.now()
        reservation = await self._repository.get_reservation_for_application(
            organization_id=context.organization_id,
            application_id=application.id,
        )
        if reservation is None or reservation.status is not ReservationStatus.ACTIVE:
            raise EnrollmentConversionError(
                "Application has no active seat reservation."
            )
        if existing_conversion is None:
            if not reservation.is_active_at(now):
                raise EnrollmentConversionError(
                    "Application has no active seat reservation."
                )
            if application.deposit.required and application.deposit.status not in {
                DepositStatus.SATISFIED,
                DepositStatus.WAIVED,
            }:
                satisfied = await self._deposits.is_satisfied(
                    organization_id=context.organization_id,
                    application_id=application.id,
                    requirement=application.deposit,
                )
                if not satisfied:
                    raise EnrollmentConversionError(
                        "Required deposit is not satisfied."
                    )
            requested = EnrollmentConversion(
                id=new_uuid7(),
                organization_id=context.organization_id,
                application_id=application.id,
                status=EnrollmentConversionStatus.PENDING,
                requested_by=context.subject_id,
                correlation_id=context.correlation_id,
                requested_at=now,
                student_id=new_uuid7(),
                academic_enrollment_id=new_uuid7(),
            )
            conversion = await self._repository.begin_conversion(requested)
        else:
            conversion = existing_conversion
        if conversion.status is EnrollmentConversionStatus.COMPLETED:
            return AcceptedApplicantEnrollmentResult(
                student_id=conversion.student_id,
                academic_enrollment_id=conversion.academic_enrollment_id,
            )
        profile = await self._repository.get_applicant_profile(
            organization_id=context.organization_id,
            profile_id=application.applicant_profile_id,
        )
        if profile is None:
            raise EnrollmentConversionError(
                "Accepted applicant profile was not found in the tenant."
            )
        result = await self._registrar.enroll_accepted_applicant(
            AcceptedApplicantEnrollmentCommand(
                idempotency_key=conversion.id,
                organization_id=context.organization_id,
                application_id=application.id,
                student_profile_id=conversion.student_id,
                academic_enrollment_id=conversion.academic_enrollment_id,
                program_id=application.program_id,
                intake_id=application.intake_id,
                requested_at=conversion.requested_at,
                actor_subject_id=conversion.requested_by,
                correlation_id=conversion.correlation_id,
                given_name=profile.given_name,
                family_name=profile.family_name,
                email=profile.email,
                phone=profile.phone,
            )
        )
        if result != AcceptedApplicantEnrollmentResult(
            student_id=conversion.student_id,
            academic_enrollment_id=conversion.academic_enrollment_id,
        ):
            raise EnrollmentConversionError(
                "Enrollment registrar returned identifiers that differ from the "
                "durable conversion."
            )
        completed_at = self._clock.now()
        completed = replace(
            conversion,
            status=EnrollmentConversionStatus.COMPLETED,
            student_id=result.student_id,
            academic_enrollment_id=result.academic_enrollment_id,
            completed_at=completed_at,
        )
        enrolled_application = transition_application(
            application=application,
            target=ApplicationStatus.ENROLLED,
            changed_at=completed_at,
        )
        consumed_reservation = replace(
            reservation,
            status=ReservationStatus.CONSUMED,
            consumed_at=completed_at,
        )
        await self._repository.complete_conversion(
            conversion=completed,
            application=enrolled_application,
            reservation=consumed_reservation,
        )
        return result

    async def _require_application(
        self,
        context: TenantActorContext,
        application_id: UUID,
    ) -> Application:
        """Resolve an application only inside trusted tenant context."""

        application = await self._repository.get_application(
            organization_id=context.organization_id,
            application_id=application_id,
        )
        if application is None:
            raise NotFoundError("Admissions application was not found.")
        return application

    async def _require_policy(
        self,
        application: Application,
    ) -> AdmissionsPolicy:
        """Resolve the policy governing an existing application."""

        policy = await self._repository.get_policy(
            organization_id=application.organization_id,
            program_id=application.program_id,
            intake_id=application.intake_id,
        )
        if policy is None:
            raise NotFoundError("Admissions policy was not found.")
        return policy

    async def _require_passing_reviews(
        self,
        application: Application,
        policy: AdmissionsPolicy,
    ) -> None:
        """Require the latest result for every configured stage to be passing."""

        reviews = await self._repository.list_reviews(
            organization_id=application.organization_id,
            application_id=application.id,
        )
        latest_by_stage: dict[ReviewStage, ReviewRecord] = {}
        for review in sorted(reviews, key=lambda item: item.completed_at):
            latest_by_stage[review.stage] = review
        missing_or_failed = tuple(
            stage
            for stage in policy.required_stages
            if stage not in latest_by_stage
            or latest_by_stage[stage].outcome is not ReviewOutcome.PASSED
        )
        if missing_or_failed:
            raise AdmissionsRuleError(
                "All configured admissions review stages must pass before acceptance."
            )


def _deposit_requirement(
    *,
    policy: AdmissionsPolicy,
    created_at: datetime,
) -> DepositRequirement:
    """Create bounded deposit metadata without initiating external payment."""

    if not policy.deposit_required:
        return DepositRequirement(
            required=False,
            amount=None,
            currency=None,
            due_at=None,
            external_reference=None,
            status=DepositStatus.NOT_REQUIRED,
        )
    return DepositRequirement(
        required=True,
        amount=policy.deposit_amount,
        currency=policy.deposit_currency,
        due_at=created_at + policy.reservation_duration,
        external_reference=None,
        status=DepositStatus.PENDING,
    )


def _authorize(
    context: TenantActorContext,
    permission: str,
) -> None:
    """Fail closed unless the trusted actor has an admissions permission."""

    if permission not in context.permissions:
        raise AuthorizationError("Required admissions permission is missing.")


def _validate_page(*, limit: int, offset: int) -> None:
    """Require a bounded non-negative admissions administration page."""

    if limit < 1 or limit > MAX_ADMISSIONS_ADMIN_PAGE_SIZE or offset < 0:
        raise AdmissionsRuleError(
            f"Admissions page limit must be 1-{MAX_ADMISSIONS_ADMIN_PAGE_SIZE} "
            "and offset cannot be negative."
        )


def _require_tenant(
    context: TenantActorContext,
    resource_organization_id: UUID,
) -> None:
    """Reject mismatched ownership without revealing another tenant resource."""

    if context.organization_id != resource_organization_id:
        raise NotFoundError("Admissions resource was not found.")


__all__ = [
    "ADMISSIONS_APPLICATION_CREATE",
    "ADMISSIONS_APPLICATION_SUBMIT",
    "ADMISSIONS_DECIDE",
    "ADMISSIONS_DOCUMENT_MANAGE",
    "ADMISSIONS_ENROLL",
    "ADMISSIONS_POLICY_MANAGE",
    "ADMISSIONS_REVIEW",
    "MAX_ADMISSIONS_ADMIN_PAGE_SIZE",
    "AdmissionsService",
]
