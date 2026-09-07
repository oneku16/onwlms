"""Application-owned admissions persistence and collaboration ports."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from admissions.application.contracts import AcceptedApplicantEnrollmentCommand
from admissions.application.contracts import AcceptedApplicantEnrollmentResult
from admissions.domain.models import AdmissionDecision
from admissions.domain.models import AdmissionQuota
from admissions.domain.models import AdmissionsPolicy
from admissions.domain.models import ApplicantProfile
from admissions.domain.models import Application
from admissions.domain.models import ApplicationDocument
from admissions.domain.models import ApplicationStatus
from admissions.domain.models import DepositRequirement
from admissions.domain.models import EnrollmentConversion
from admissions.domain.models import ReviewRecord
from admissions.domain.models import SeatReservation


class AdmissionsRepository(Protocol):
    """Persist admissions aggregates and protect concurrent seat allocation."""

    async def save_applicant_profile(self, profile: ApplicantProfile) -> None:
        """Persist one tenant applicant profile."""
        ...

    async def create_application(
        self,
        *,
        profile: ApplicantProfile,
        application: Application,
    ) -> None:
        """Atomically create an applicant profile and draft application."""
        ...

    async def get_applicant_profile(
        self,
        *,
        organization_id: UUID,
        profile_id: UUID,
    ) -> ApplicantProfile | None:
        """Return an applicant profile only from the requested tenant."""
        ...

    async def save_application(
        self,
        *,
        application: Application,
        expected_status: ApplicationStatus | None,
    ) -> None:
        """Create or compare-and-swap one application lifecycle state."""
        ...

    async def get_application(
        self,
        *,
        organization_id: UUID,
        application_id: UUID,
    ) -> Application | None:
        """Return an application only from the requested tenant."""
        ...

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
        """Return a bounded stable page of tenant applications."""
        ...

    async def save_document(self, document: ApplicationDocument) -> None:
        """Persist safe metadata for one application document."""
        ...

    async def list_documents(
        self,
        *,
        organization_id: UUID,
        application_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[ApplicationDocument, ...]:
        """Return bounded safe document metadata for one application."""
        ...

    async def save_policy(self, policy: AdmissionsPolicy) -> None:
        """Persist one program and intake admissions policy."""
        ...

    async def get_policy(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        intake_id: UUID,
    ) -> AdmissionsPolicy | None:
        """Return one tenant program and intake policy."""
        ...

    async def save_quota(self, quota: AdmissionQuota) -> None:
        """Persist one categorized admission quota."""
        ...

    async def get_quota(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        intake_id: UUID,
        seat_category: str,
    ) -> AdmissionQuota | None:
        """Return one exact tenant quota."""
        ...

    async def save_review(
        self,
        *,
        review: ReviewRecord,
        application: Application,
        expected_status: ApplicationStatus,
    ) -> None:
        """Atomically append a review and advance application state."""
        ...

    async def list_reviews(
        self,
        *,
        organization_id: UUID,
        application_id: UUID,
    ) -> tuple[ReviewRecord, ...]:
        """Return immutable review history for one application."""
        ...

    async def list_reviews_page(
        self,
        *,
        organization_id: UUID,
        application_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[ReviewRecord, ...]:
        """Return a bounded stable page of immutable review history."""
        ...

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
        """Atomically accept an application when quota remains available."""
        ...

    async def save_decision(
        self,
        *,
        application: Application,
        expected_status: ApplicationStatus,
        decision: AdmissionDecision,
    ) -> None:
        """Atomically append a non-acceptance decision and lifecycle state."""
        ...

    async def get_reservation_for_application(
        self,
        *,
        organization_id: UUID,
        application_id: UUID,
    ) -> SeatReservation | None:
        """Return the application's seat reservation inside one tenant."""
        ...

    async def begin_conversion(
        self,
        conversion: EnrollmentConversion,
    ) -> EnrollmentConversion:
        """Create or return the idempotent conversion for an application."""
        ...

    async def get_conversion_for_application(
        self,
        *,
        organization_id: UUID,
        application_id: UUID,
    ) -> EnrollmentConversion | None:
        """Return existing idempotent conversion state for an application."""
        ...

    async def complete_conversion(
        self,
        *,
        conversion: EnrollmentConversion,
        application: Application,
        reservation: SeatReservation,
    ) -> None:
        """Atomically complete conversion and consume the reserved seat."""
        ...


class AcceptedApplicantEnrollmentRegistrar(Protocol):
    """Create downstream student and academic enrollment records idempotently."""

    async def enroll_accepted_applicant(
        self,
        command: AcceptedApplicantEnrollmentCommand,
    ) -> AcceptedApplicantEnrollmentResult:
        """Create or return records for the command idempotency key."""
        ...


class AdmissionsAuditSink(Protocol):
    """Append tenant-scoped evidence for official admissions decisions."""

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
        """Record decision intent or outcome without applicant profile data."""
        ...


class AdmissionsTargetDirectory(Protocol):
    """Validate academic program and intake references through a public contract."""

    async def target_exists(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        intake_id: UUID,
    ) -> bool:
        """Return whether the requested admissions target exists in the tenant."""
        ...

    async def acceptance_is_open(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        intake_id: UUID,
    ) -> bool:
        """Return whether the exact academic intake may still accept a decision."""
        ...


class DepositVerifier(Protocol):
    """Verify optional external deposit evidence without processing payment."""

    async def is_satisfied(
        self,
        *,
        organization_id: UUID,
        application_id: UUID,
        requirement: DepositRequirement,
    ) -> bool:
        """Return whether configured deposit evidence is satisfied."""
        ...


class AdmissionsClock(Protocol):
    """Supply explicit timezone-aware application time."""

    def now(self) -> datetime:
        """Return the current timezone-aware UTC time."""
        ...


__all__ = [
    "AcceptedApplicantEnrollmentRegistrar",
    "AdmissionsAuditSink",
    "AdmissionsClock",
    "AdmissionsRepository",
    "AdmissionsTargetDirectory",
    "DepositVerifier",
]
