"""Functional in-memory admissions adapters with atomic quota semantics."""

import asyncio
from datetime import datetime
from uuid import UUID

from admissions.application.contracts import AcceptedApplicantEnrollmentCommand
from admissions.application.contracts import AcceptedApplicantEnrollmentResult
from admissions.domain.exceptions import ApplicationTransitionError
from admissions.domain.exceptions import EnrollmentConversionError
from admissions.domain.exceptions import QuotaUnavailableError
from admissions.domain.models import AdmissionDecision
from admissions.domain.models import AdmissionQuota
from admissions.domain.models import AdmissionsPolicy
from admissions.domain.models import ApplicantProfile
from admissions.domain.models import Application
from admissions.domain.models import ApplicationDocument
from admissions.domain.models import ApplicationStatus
from admissions.domain.models import DepositRequirement
from admissions.domain.models import EnrollmentConversion
from admissions.domain.models import EnrollmentConversionStatus
from admissions.domain.models import ReservationStatus
from admissions.domain.models import ReviewRecord
from admissions.domain.models import SeatReservation
from core.errors import ConflictError

TenantKey = tuple[UUID, UUID]


class InMemoryAdmissionsTargetDirectory:
    """Validate explicitly registered tenant program and intake references."""

    def __init__(
        self,
        targets: set[tuple[UUID, UUID, UUID]] | None = None,
    ) -> None:
        self._targets = set(targets or set())

    async def target_exists(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        intake_id: UUID,
    ) -> bool:
        """Return whether the exact tenant target was registered."""

        return (organization_id, program_id, intake_id) in self._targets

    def add(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        intake_id: UUID,
    ) -> None:
        """Register a tenant admissions target for deterministic tests."""

        self._targets.add((organization_id, program_id, intake_id))


class StaticDepositVerifier:
    """Return an explicitly configured deposit verification result."""

    def __init__(
        self,
        *,
        satisfied: bool,
    ) -> None:
        self._satisfied = satisfied

    async def is_satisfied(
        self,
        *,
        organization_id: UUID,
        application_id: UUID,
        requirement: DepositRequirement,
    ) -> bool:
        """Return the configured result without contacting a payment provider."""

        del organization_id, application_id, requirement
        return self._satisfied


class UnconfiguredDepositVerifier:
    """Deny required-deposit conversion until a verifier is configured."""

    async def is_satisfied(
        self,
        *,
        organization_id: UUID,
        application_id: UUID,
        requirement: DepositRequirement,
    ) -> bool:
        """Fail closed without treating local state as payment evidence."""

        del organization_id, application_id, requirement
        return False


class InMemoryAcceptedApplicantEnrollmentRegistrar:
    """Create deterministic idempotent enrollment results in process memory."""

    def __init__(self) -> None:
        self._results: dict[UUID, AcceptedApplicantEnrollmentResult] = {}
        self.commands: list[AcceptedApplicantEnrollmentCommand] = []

    async def enroll_accepted_applicant(
        self,
        command: AcceptedApplicantEnrollmentCommand,
    ) -> AcceptedApplicantEnrollmentResult:
        """Create at most one downstream result per idempotency key."""

        existing = self._results.get(command.idempotency_key)
        if existing is not None:
            return existing
        result = AcceptedApplicantEnrollmentResult(
            student_id=command.student_profile_id,
            academic_enrollment_id=command.academic_enrollment_id,
        )
        self._results[command.idempotency_key] = result
        self.commands.append(command)
        return result


class InMemoryAdmissionsRepository:
    """Preserve admissions transaction and tenant semantics in process memory."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._profiles: dict[TenantKey, ApplicantProfile] = {}
        self._applications: dict[TenantKey, Application] = {}
        self._documents: dict[TenantKey, ApplicationDocument] = {}
        self._policies: dict[tuple[UUID, UUID, UUID], AdmissionsPolicy] = {}
        self._quotas: dict[TenantKey, AdmissionQuota] = {}
        self._quota_index: dict[tuple[UUID, UUID, UUID, str], UUID] = {}
        self._reviews: dict[TenantKey, ReviewRecord] = {}
        self._decisions: dict[TenantKey, AdmissionDecision] = {}
        self._reservations: dict[TenantKey, SeatReservation] = {}
        self._application_reservations: dict[TenantKey, UUID] = {}
        self._conversions: dict[TenantKey, EnrollmentConversion] = {}

    async def save_applicant_profile(self, profile: ApplicantProfile) -> None:
        """Persist one tenant applicant profile."""

        self._profiles[(profile.organization_id, profile.id)] = profile

    async def create_application(
        self,
        *,
        profile: ApplicantProfile,
        application: Application,
    ) -> None:
        """Atomically create a profile and draft application."""

        async with self._lock:
            if profile.organization_id != application.organization_id:
                raise ConflictError("Applicant and application tenants differ.")
            profile_key = (profile.organization_id, profile.id)
            application_key = (application.organization_id, application.id)
            if profile_key in self._profiles or application_key in self._applications:
                raise ConflictError("Applicant or application already exists.")
            self._profiles[profile_key] = profile
            self._applications[application_key] = application

    async def get_applicant_profile(
        self,
        *,
        organization_id: UUID,
        profile_id: UUID,
    ) -> ApplicantProfile | None:
        """Return an applicant profile only from the requested tenant."""

        return self._profiles.get((organization_id, profile_id))

    async def save_application(
        self,
        *,
        application: Application,
        expected_status: ApplicationStatus | None,
    ) -> None:
        """Create or compare-and-swap one application state."""

        async with self._lock:
            key = (application.organization_id, application.id)
            existing = self._applications.get(key)
            if expected_status is None:
                if existing is not None:
                    raise ConflictError("Admissions application already exists.")
            elif existing is None or existing.status is not expected_status:
                raise ApplicationTransitionError(
                    "Admissions application changed concurrently."
                )
            self._applications[key] = application

    async def get_application(
        self,
        *,
        organization_id: UUID,
        application_id: UUID,
    ) -> Application | None:
        """Return an application only from the requested tenant."""

        return self._applications.get((organization_id, application_id))

    async def list_applications(
        self,
        *,
        organization_id: UUID,
        status: ApplicationStatus | None,
        program_id: UUID | None,
        intake_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Application, ...]:
        """Return a bounded stable admissions application page."""

        values = sorted(
            (
                value
                for value in self._applications.values()
                if value.organization_id == organization_id
                and (status is None or value.status is status)
                and (program_id is None or value.program_id == program_id)
                and (intake_id is None or value.intake_id == intake_id)
            ),
            key=lambda value: (value.created_at, str(value.id)),
            reverse=True,
        )
        return tuple(values[offset : offset + limit])

    async def save_document(self, document: ApplicationDocument) -> None:
        """Persist one immutable document metadata record."""

        key = (document.organization_id, document.id)
        if key in self._documents:
            raise ConflictError("Application document already exists.")
        self._documents[key] = document

    async def list_documents(
        self,
        *,
        organization_id: UUID,
        application_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[ApplicationDocument, ...]:
        """Return bounded safe document metadata for one application."""

        values = sorted(
            (
                value
                for value in self._documents.values()
                if value.organization_id == organization_id
                and value.application_id == application_id
            ),
            key=lambda value: (value.uploaded_at, str(value.id)),
            reverse=True,
        )
        return tuple(values[offset : offset + limit])

    async def save_policy(self, policy: AdmissionsPolicy) -> None:
        """Persist one program and intake admissions policy."""

        self._policies[
            (policy.organization_id, policy.program_id, policy.intake_id)
        ] = policy

    async def get_policy(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        intake_id: UUID,
    ) -> AdmissionsPolicy | None:
        """Return one tenant program and intake policy."""

        return self._policies.get((organization_id, program_id, intake_id))

    async def save_quota(self, quota: AdmissionQuota) -> None:
        """Persist one unique program, intake, and seat-category quota."""

        normalized_category = quota.seat_category.casefold()
        index_key = (
            quota.organization_id,
            quota.program_id,
            quota.intake_id,
            normalized_category,
        )
        existing_id = self._quota_index.get(index_key)
        if existing_id is not None and existing_id != quota.id:
            raise ConflictError("Admission quota category already exists.")
        self._quotas[(quota.organization_id, quota.id)] = quota
        self._quota_index[index_key] = quota.id

    async def get_quota(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        intake_id: UUID,
        seat_category: str,
    ) -> AdmissionQuota | None:
        """Return one exact tenant quota by normalized seat category."""

        quota_id = self._quota_index.get(
            (
                organization_id,
                program_id,
                intake_id,
                seat_category.casefold(),
            )
        )
        if quota_id is None:
            return None
        return self._quotas.get((organization_id, quota_id))

    async def save_review(
        self,
        *,
        review: ReviewRecord,
        application: Application,
        expected_status: ApplicationStatus,
    ) -> None:
        """Atomically append a review and compare-and-swap application state."""

        async with self._lock:
            application_key = (application.organization_id, application.id)
            current = self._applications.get(application_key)
            if current is None or current.status is not expected_status:
                raise ApplicationTransitionError(
                    "Admissions application changed concurrently."
                )
            review_key = (review.organization_id, review.id)
            if review_key in self._reviews:
                raise ConflictError("Admissions review already exists.")
            self._reviews[review_key] = review
            self._applications[application_key] = application

    async def list_reviews(
        self,
        *,
        organization_id: UUID,
        application_id: UUID,
    ) -> tuple[ReviewRecord, ...]:
        """Return ordered immutable review history for one tenant application."""

        reviews = (
            review
            for review in self._reviews.values()
            if review.organization_id == organization_id
            and review.application_id == application_id
        )
        return tuple(sorted(reviews, key=lambda review: review.completed_at))

    async def list_reviews_page(
        self,
        *,
        organization_id: UUID,
        application_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[ReviewRecord, ...]:
        """Return a bounded stable page of immutable review history."""

        reviews = await self.list_reviews(
            organization_id=organization_id,
            application_id=application_id,
        )
        return reviews[offset : offset + limit]

    async def decide_with_reservation(
        self,
        *,
        application: Application,
        expected_status: ApplicationStatus,
        decision: AdmissionDecision,
        quota: AdmissionQuota,
        reservation: SeatReservation,
        evaluated_at: datetime,
    ) -> None:
        """Atomically reserve quota and persist an acceptance decision."""

        async with self._lock:
            self._require_current_status(application, expected_status)
            if (
                quota.organization_id != application.organization_id
                or quota.program_id != application.program_id
                or quota.intake_id != application.intake_id
                or quota.seat_category.casefold()
                != application.seat_category.casefold()
            ):
                raise QuotaUnavailableError(
                    "Admission quota does not match the application."
                )
            occupied = sum(
                1
                for existing in self._reservations.values()
                if existing.organization_id == quota.organization_id
                and existing.quota_id == quota.id
                and (
                    existing.status is ReservationStatus.CONSUMED
                    or existing.is_active_at(evaluated_at)
                )
            )
            if occupied >= quota.capacity:
                raise QuotaUnavailableError("Admission quota has no available seat.")
            application_key = (application.organization_id, application.id)
            reservation_key = (reservation.organization_id, reservation.id)
            decision_key = (decision.organization_id, decision.id)
            self._applications[application_key] = application
            self._reservations[reservation_key] = reservation
            self._application_reservations[application_key] = reservation.id
            self._decisions[decision_key] = decision

    async def save_decision(
        self,
        *,
        application: Application,
        expected_status: ApplicationStatus,
        decision: AdmissionDecision,
    ) -> None:
        """Atomically append a non-acceptance decision and lifecycle state."""

        async with self._lock:
            self._require_current_status(application, expected_status)
            self._applications[(application.organization_id, application.id)] = (
                application
            )
            self._decisions[(decision.organization_id, decision.id)] = decision

    async def get_reservation_for_application(
        self,
        *,
        organization_id: UUID,
        application_id: UUID,
    ) -> SeatReservation | None:
        """Return the application's tenant-scoped seat reservation."""

        reservation_id = self._application_reservations.get(
            (organization_id, application_id)
        )
        if reservation_id is None:
            return None
        return self._reservations.get((organization_id, reservation_id))

    async def begin_conversion(
        self,
        conversion: EnrollmentConversion,
    ) -> EnrollmentConversion:
        """Create or return one conversion keyed by tenant and application."""

        async with self._lock:
            key = (conversion.organization_id, conversion.application_id)
            existing = self._conversions.get(key)
            if existing is not None:
                return existing
            self._conversions[key] = conversion
            return conversion

    async def get_conversion_for_application(
        self,
        *,
        organization_id: UUID,
        application_id: UUID,
    ) -> EnrollmentConversion | None:
        """Return one conversion only from the requested tenant."""

        return self._conversions.get((organization_id, application_id))

    async def complete_conversion(
        self,
        *,
        conversion: EnrollmentConversion,
        application: Application,
        reservation: SeatReservation,
    ) -> None:
        """Atomically finalize conversion, application, and reservation state."""

        async with self._lock:
            conversion_key = (conversion.organization_id, conversion.application_id)
            existing = self._conversions.get(conversion_key)
            if existing is None:
                raise EnrollmentConversionError(
                    "Enrollment conversion was not started."
                )
            if existing.status is EnrollmentConversionStatus.COMPLETED:
                if (
                    existing.student_id == conversion.student_id
                    and existing.academic_enrollment_id
                    == conversion.academic_enrollment_id
                ):
                    return
                raise EnrollmentConversionError(
                    "Enrollment conversion completed with another result."
                )
            application_key = (application.organization_id, application.id)
            current_application = self._applications.get(application_key)
            if (
                current_application is None
                or current_application.status is not ApplicationStatus.ACCEPTED
            ):
                raise EnrollmentConversionError(
                    "Accepted application changed during enrollment conversion."
                )
            reservation_key = (reservation.organization_id, reservation.id)
            current_reservation = self._reservations.get(reservation_key)
            if (
                current_reservation is None
                or current_reservation.status is not ReservationStatus.ACTIVE
            ):
                raise EnrollmentConversionError(
                    "Seat reservation changed during enrollment conversion."
                )
            self._conversions[conversion_key] = conversion
            self._applications[application_key] = application
            self._reservations[reservation_key] = reservation

    async def list_decisions(
        self,
        *,
        organization_id: UUID,
        application_id: UUID,
    ) -> tuple[AdmissionDecision, ...]:
        """Return ordered decision history for tests and read composition."""

        decisions = (
            decision
            for decision in self._decisions.values()
            if decision.organization_id == organization_id
            and decision.application_id == application_id
        )
        return tuple(sorted(decisions, key=lambda decision: decision.decided_at))

    def _require_current_status(
        self,
        application: Application,
        expected_status: ApplicationStatus,
    ) -> None:
        """Require compare-and-swap state before a decision transaction."""

        current = self._applications.get((application.organization_id, application.id))
        if current is None or current.status is not expected_status:
            raise ApplicationTransitionError(
                "Admissions application changed concurrently."
            )


__all__ = [
    "InMemoryAcceptedApplicantEnrollmentRegistrar",
    "InMemoryAdmissionsRepository",
    "InMemoryAdmissionsTargetDirectory",
    "StaticDepositVerifier",
    "UnconfiguredDepositVerifier",
]
