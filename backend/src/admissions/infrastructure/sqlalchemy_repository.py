"""PostgreSQL admissions adapter with lifecycle and quota transactions."""

from datetime import datetime
from datetime import timedelta
from uuid import UUID

from sqlalchemy import and_
from sqlalchemy import delete
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from admissions.domain.exceptions import ApplicationTransitionError
from admissions.domain.exceptions import EnrollmentConversionError
from admissions.domain.exceptions import QuotaUnavailableError
from admissions.domain.models import AdmissionDecision
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
from admissions.infrastructure.models import AdmissionDecisionModel
from admissions.infrastructure.models import AdmissionQuotaModel
from admissions.infrastructure.models import AdmissionsPolicyModel
from admissions.infrastructure.models import AdmissionsPolicyStageModel
from admissions.infrastructure.models import ApplicantProfileModel
from admissions.infrastructure.models import ApplicationDocumentModel
from admissions.infrastructure.models import ApplicationModel
from admissions.infrastructure.models import EnrollmentConversionModel
from admissions.infrastructure.models import ReviewRecordModel
from admissions.infrastructure.models import SeatReservationModel
from core.errors import ConflictError
from core.field_encryption import FieldCipher
from core.identifiers import new_uuid7
from shared.database import Database


class SQLAlchemyAdmissionsRepository:
    """Persist admissions state under tenant-scoped PostgreSQL transactions."""

    def __init__(
        self,
        *,
        database: Database,
        pii_encryption_key: str,
    ) -> None:
        self._database = database
        self._cipher = FieldCipher(pii_encryption_key)

    async def save_applicant_profile(self, profile: ApplicantProfile) -> None:
        """Persist one applicant profile under its tenant owner."""

        try:
            async with self._database.session(
                organization_id=profile.organization_id,
            ) as session:
                session.add(self._profile_to_model(profile))
        except IntegrityError as exc:
            raise ConflictError("Applicant profile already exists.") from exc

    async def create_application(
        self,
        *,
        profile: ApplicantProfile,
        application: Application,
    ) -> None:
        """Atomically create a same-tenant profile and draft application."""

        if profile.organization_id != application.organization_id:
            raise ConflictError("Applicant and application tenants differ.")
        try:
            async with self._database.session(
                organization_id=application.organization_id,
            ) as session:
                session.add(self._profile_to_model(profile))
                session.add(self._application_to_model(application))
        except IntegrityError as exc:
            raise ConflictError("Applicant or application already exists.") from exc

    async def get_applicant_profile(
        self,
        *,
        organization_id: UUID,
        profile_id: UUID,
    ) -> ApplicantProfile | None:
        """Return an applicant profile only from the requested tenant."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(ApplicantProfileModel).where(
                    ApplicantProfileModel.organization_id == organization_id,
                    ApplicantProfileModel.id == profile_id,
                )
            )
            return self._profile_from_model(model) if model is not None else None

    async def save_application(
        self,
        *,
        application: Application,
        expected_status: ApplicationStatus | None,
    ) -> None:
        """Create or compare-and-swap one application lifecycle state."""

        try:
            async with self._database.session(
                organization_id=application.organization_id,
            ) as session:
                if expected_status is None:
                    existing = await session.scalar(
                        select(ApplicationModel).where(
                            ApplicationModel.organization_id
                            == application.organization_id,
                            ApplicationModel.id == application.id,
                        )
                    )
                    if existing is not None:
                        raise ConflictError("Admissions application already exists.")
                    session.add(self._application_to_model(application))
                    return
                model = await self._lock_application(
                    session=session,
                    organization_id=application.organization_id,
                    application_id=application.id,
                    expected_status=expected_status,
                )
                self._apply_application(model=model, application=application)
        except IntegrityError as exc:
            raise ConflictError("Admissions application already exists.") from exc

    async def get_application(
        self,
        *,
        organization_id: UUID,
        application_id: UUID,
    ) -> Application | None:
        """Return one application only when both tenant and ID match."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(ApplicationModel).where(
                    ApplicationModel.organization_id == organization_id,
                    ApplicationModel.id == application_id,
                )
            )
            return self._application_from_model(model) if model is not None else None

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

        statement = select(ApplicationModel).where(
            ApplicationModel.organization_id == organization_id
        )
        if status is not None:
            statement = statement.where(ApplicationModel.status == status.value)
        if program_id is not None:
            statement = statement.where(ApplicationModel.program_id == program_id)
        if intake_id is not None:
            statement = statement.where(ApplicationModel.intake_id == intake_id)
        async with self._database.session(organization_id=organization_id) as session:
            models = tuple(
                (
                    await session.scalars(
                        statement.order_by(
                            ApplicationModel.created_at.desc(),
                            ApplicationModel.id,
                        )
                        .limit(limit)
                        .offset(offset)
                    )
                ).all()
            )
        return tuple(self._application_from_model(model) for model in models)

    async def save_document(self, document: ApplicationDocument) -> None:
        """Append one immutable safe document-metadata record."""

        try:
            async with self._database.session(
                organization_id=document.organization_id,
            ) as session:
                session.add(
                    ApplicationDocumentModel(
                        id=document.id,
                        organization_id=document.organization_id,
                        application_id=document.application_id,
                        document_type=document.document_type,
                        file_reference=document.file_reference,
                        media_type=document.media_type,
                        size_bytes=document.size_bytes,
                        checksum_sha256=document.checksum_sha256,
                        uploaded_at=document.uploaded_at,
                    )
                )
        except IntegrityError as exc:
            raise ConflictError("Application document already exists.") from exc

    async def list_documents(
        self,
        *,
        organization_id: UUID,
        application_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[ApplicationDocument, ...]:
        """Return bounded safe document metadata for one application."""

        async with self._database.session(organization_id=organization_id) as session:
            models = tuple(
                (
                    await session.scalars(
                        select(ApplicationDocumentModel)
                        .where(
                            ApplicationDocumentModel.organization_id == organization_id,
                            ApplicationDocumentModel.application_id == application_id,
                        )
                        .order_by(
                            ApplicationDocumentModel.uploaded_at.desc(),
                            ApplicationDocumentModel.id,
                        )
                        .limit(limit)
                        .offset(offset)
                    )
                ).all()
            )
        return tuple(
            ApplicationDocument(
                id=model.id,
                organization_id=model.organization_id,
                application_id=model.application_id,
                document_type=model.document_type,
                file_reference=model.file_reference,
                media_type=model.media_type,
                size_bytes=model.size_bytes,
                checksum_sha256=model.checksum_sha256,
                uploaded_at=model.uploaded_at,
            )
            for model in models
        )

    async def save_policy(self, policy: AdmissionsPolicy) -> None:
        """Create or replace one program-intake policy and ordered stages."""

        try:
            async with self._database.session(
                organization_id=policy.organization_id,
            ) as session:
                model = await session.scalar(
                    select(AdmissionsPolicyModel)
                    .where(
                        AdmissionsPolicyModel.organization_id == policy.organization_id,
                        AdmissionsPolicyModel.program_id == policy.program_id,
                        AdmissionsPolicyModel.intake_id == policy.intake_id,
                    )
                    .with_for_update()
                )
                if model is None:
                    model = AdmissionsPolicyModel(
                        id=new_uuid7(),
                        organization_id=policy.organization_id,
                        program_id=policy.program_id,
                        intake_id=policy.intake_id,
                        deposit_required=policy.deposit_required,
                        deposit_amount=policy.deposit_amount,
                        deposit_currency=policy.deposit_currency,
                        reservation_duration_seconds=int(
                            policy.reservation_duration.total_seconds()
                        ),
                    )
                    session.add(model)
                else:
                    model.deposit_required = policy.deposit_required
                    model.deposit_amount = policy.deposit_amount
                    model.deposit_currency = policy.deposit_currency
                    model.reservation_duration_seconds = int(
                        policy.reservation_duration.total_seconds()
                    )
                    await session.execute(
                        delete(AdmissionsPolicyStageModel).where(
                            AdmissionsPolicyStageModel.organization_id
                            == policy.organization_id,
                            AdmissionsPolicyStageModel.policy_id == model.id,
                        )
                    )
                for position, stage in enumerate(policy.required_stages):
                    session.add(
                        AdmissionsPolicyStageModel(
                            id=new_uuid7(),
                            organization_id=policy.organization_id,
                            policy_id=model.id,
                            stage=stage.value,
                            position=position,
                        )
                    )
        except IntegrityError as exc:
            raise ConflictError(
                "Admissions policy conflicts with stored data."
            ) from exc

    async def get_policy(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        intake_id: UUID,
    ) -> AdmissionsPolicy | None:
        """Return one complete program-intake policy from the requested tenant."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(AdmissionsPolicyModel).where(
                    AdmissionsPolicyModel.organization_id == organization_id,
                    AdmissionsPolicyModel.program_id == program_id,
                    AdmissionsPolicyModel.intake_id == intake_id,
                )
            )
            if model is None:
                return None
            stages = tuple(
                (
                    await session.scalars(
                        select(AdmissionsPolicyStageModel).where(
                            AdmissionsPolicyStageModel.organization_id
                            == organization_id,
                            AdmissionsPolicyStageModel.policy_id == model.id,
                        )
                    )
                ).all()
            )
            return AdmissionsPolicy(
                organization_id=model.organization_id,
                program_id=model.program_id,
                intake_id=model.intake_id,
                required_stages=tuple(
                    ReviewStage(stage.stage)
                    for stage in sorted(stages, key=lambda value: value.position)
                ),
                deposit_required=model.deposit_required,
                deposit_amount=model.deposit_amount,
                deposit_currency=model.deposit_currency,
                reservation_duration=timedelta(
                    seconds=model.reservation_duration_seconds
                ),
            )

    async def save_quota(self, quota: AdmissionQuota) -> None:
        """Create or update one normalized categorized admission quota."""

        try:
            async with self._database.session(
                organization_id=quota.organization_id,
            ) as session:
                model = await session.scalar(
                    select(AdmissionQuotaModel)
                    .where(
                        AdmissionQuotaModel.organization_id == quota.organization_id,
                        AdmissionQuotaModel.program_id == quota.program_id,
                        AdmissionQuotaModel.intake_id == quota.intake_id,
                        AdmissionQuotaModel.seat_category
                        == quota.seat_category.casefold(),
                    )
                    .with_for_update()
                )
                if model is not None and model.id != quota.id:
                    raise ConflictError("Admission quota category already exists.")
                if model is None:
                    session.add(
                        AdmissionQuotaModel(
                            id=quota.id,
                            organization_id=quota.organization_id,
                            program_id=quota.program_id,
                            intake_id=quota.intake_id,
                            seat_category=quota.seat_category.casefold(),
                            capacity=quota.capacity,
                        )
                    )
                else:
                    model.capacity = quota.capacity
        except IntegrityError as exc:
            raise ConflictError("Admission quota category already exists.") from exc

    async def get_quota(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        intake_id: UUID,
        seat_category: str,
    ) -> AdmissionQuota | None:
        """Return one exact normalized tenant quota."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(AdmissionQuotaModel).where(
                    AdmissionQuotaModel.organization_id == organization_id,
                    AdmissionQuotaModel.program_id == program_id,
                    AdmissionQuotaModel.intake_id == intake_id,
                    AdmissionQuotaModel.seat_category == seat_category.casefold(),
                )
            )
            return self._quota_from_model(model) if model is not None else None

    async def save_review(
        self,
        *,
        review: ReviewRecord,
        application: Application,
        expected_status: ApplicationStatus,
    ) -> None:
        """Append review and compare-and-swap application state atomically."""

        try:
            async with self._database.session(
                organization_id=application.organization_id,
            ) as session:
                model = await self._lock_application(
                    session=session,
                    organization_id=application.organization_id,
                    application_id=application.id,
                    expected_status=expected_status,
                )
                session.add(self._review_to_model(review))
                self._apply_application(model=model, application=application)
        except IntegrityError as exc:
            raise ConflictError("Admissions review already exists.") from exc

    async def list_reviews(
        self,
        *,
        organization_id: UUID,
        application_id: UUID,
    ) -> tuple[ReviewRecord, ...]:
        """Return ordered immutable review history for one application."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            models = tuple(
                (
                    await session.scalars(
                        select(ReviewRecordModel).where(
                            ReviewRecordModel.organization_id == organization_id,
                            ReviewRecordModel.application_id == application_id,
                        )
                    )
                ).all()
            )
        return tuple(
            sorted(
                (self._review_from_model(model) for model in models),
                key=lambda value: value.completed_at,
            )
        )

    async def list_reviews_page(
        self,
        *,
        organization_id: UUID,
        application_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[ReviewRecord, ...]:
        """Return a bounded stable page of immutable review history."""

        async with self._database.session(organization_id=organization_id) as session:
            models = tuple(
                (
                    await session.scalars(
                        select(ReviewRecordModel)
                        .where(
                            ReviewRecordModel.organization_id == organization_id,
                            ReviewRecordModel.application_id == application_id,
                        )
                        .order_by(
                            ReviewRecordModel.completed_at,
                            ReviewRecordModel.id,
                        )
                        .limit(limit)
                        .offset(offset)
                    )
                ).all()
            )
        return tuple(self._review_from_model(model) for model in models)

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
        """Lock quota, re-count occupied seats, and accept atomically."""

        try:
            async with self._database.session(
                organization_id=application.organization_id,
            ) as session:
                application_model = await self._lock_application(
                    session=session,
                    organization_id=application.organization_id,
                    application_id=application.id,
                    expected_status=expected_status,
                )
                quota_model = await session.scalar(
                    select(AdmissionQuotaModel)
                    .where(
                        AdmissionQuotaModel.organization_id
                        == application.organization_id,
                        AdmissionQuotaModel.id == quota.id,
                    )
                    .with_for_update()
                )
                if quota_model is None or not self._quota_matches(
                    quota=quota_model,
                    application=application,
                ):
                    raise QuotaUnavailableError(
                        "Admission quota does not match the application."
                    )
                occupied = await session.scalar(
                    select(func.count(SeatReservationModel.id)).where(
                        SeatReservationModel.organization_id
                        == application.organization_id,
                        SeatReservationModel.quota_id == quota.id,
                        or_(
                            SeatReservationModel.status
                            == ReservationStatus.CONSUMED.value,
                            and_(
                                SeatReservationModel.status
                                == ReservationStatus.ACTIVE.value,
                                SeatReservationModel.expires_at > evaluated_at,
                            ),
                        ),
                    )
                )
                if (occupied or 0) >= quota_model.capacity:
                    raise QuotaUnavailableError(
                        "Admission quota has no available seat."
                    )
                session.add(self._reservation_to_model(reservation))
                session.add(self._decision_to_model(decision))
                self._apply_application(
                    model=application_model,
                    application=application,
                )
        except IntegrityError as exc:
            raise QuotaUnavailableError(
                "Admission quota reservation conflicts with stored state."
            ) from exc

    async def save_decision(
        self,
        *,
        application: Application,
        expected_status: ApplicationStatus,
        decision: AdmissionDecision,
    ) -> None:
        """Append a non-acceptance decision and lifecycle change atomically."""

        try:
            async with self._database.session(
                organization_id=application.organization_id,
            ) as session:
                model = await self._lock_application(
                    session=session,
                    organization_id=application.organization_id,
                    application_id=application.id,
                    expected_status=expected_status,
                )
                session.add(self._decision_to_model(decision))
                self._apply_application(model=model, application=application)
        except IntegrityError as exc:
            raise ConflictError("Admissions decision already exists.") from exc

    async def get_reservation_for_application(
        self,
        *,
        organization_id: UUID,
        application_id: UUID,
    ) -> SeatReservation | None:
        """Return the tenant-scoped reservation for an application."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(SeatReservationModel).where(
                    SeatReservationModel.organization_id == organization_id,
                    SeatReservationModel.application_id == application_id,
                )
            )
            return self._reservation_from_model(model) if model is not None else None

    async def begin_conversion(
        self,
        conversion: EnrollmentConversion,
    ) -> EnrollmentConversion:
        """Create or return one application-keyed conversion under an app lock."""

        try:
            async with self._database.session(
                organization_id=conversion.organization_id,
            ) as session:
                await session.scalar(
                    select(ApplicationModel)
                    .where(
                        ApplicationModel.organization_id == conversion.organization_id,
                        ApplicationModel.id == conversion.application_id,
                    )
                    .with_for_update()
                )
                existing = await session.scalar(
                    select(EnrollmentConversionModel).where(
                        EnrollmentConversionModel.organization_id
                        == conversion.organization_id,
                        EnrollmentConversionModel.application_id
                        == conversion.application_id,
                    )
                )
                if existing is not None:
                    return self._conversion_from_model(existing)
                session.add(self._conversion_to_model(conversion))
                return conversion
        except IntegrityError as exc:
            raise EnrollmentConversionError(
                "Enrollment conversion could not be started atomically."
            ) from exc

    async def get_conversion_for_application(
        self,
        *,
        organization_id: UUID,
        application_id: UUID,
    ) -> EnrollmentConversion | None:
        """Return an application conversion only from the requested tenant."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(EnrollmentConversionModel).where(
                    EnrollmentConversionModel.organization_id == organization_id,
                    EnrollmentConversionModel.application_id == application_id,
                )
            )
            return self._conversion_from_model(model) if model is not None else None

    async def complete_conversion(
        self,
        *,
        conversion: EnrollmentConversion,
        application: Application,
        reservation: SeatReservation,
    ) -> None:
        """Complete conversion, consume reservation, and enroll atomically."""

        async with self._database.session(
            organization_id=conversion.organization_id,
        ) as session:
            conversion_model = await session.scalar(
                select(EnrollmentConversionModel)
                .where(
                    EnrollmentConversionModel.organization_id
                    == conversion.organization_id,
                    EnrollmentConversionModel.application_id
                    == conversion.application_id,
                )
                .with_for_update()
            )
            if conversion_model is None:
                raise EnrollmentConversionError(
                    "Enrollment conversion was not started."
                )
            if conversion_model.status == EnrollmentConversionStatus.COMPLETED.value:
                if (
                    conversion_model.student_id == conversion.student_id
                    and conversion_model.academic_enrollment_id
                    == conversion.academic_enrollment_id
                ):
                    return
                raise EnrollmentConversionError(
                    "Enrollment conversion completed with another result."
                )
            application_model = await session.scalar(
                select(ApplicationModel)
                .where(
                    ApplicationModel.organization_id == application.organization_id,
                    ApplicationModel.id == application.id,
                )
                .with_for_update()
            )
            if (
                application_model is None
                or application_model.status != ApplicationStatus.ACCEPTED.value
            ):
                raise EnrollmentConversionError(
                    "Accepted application changed during enrollment conversion."
                )
            reservation_model = await session.scalar(
                select(SeatReservationModel)
                .where(
                    SeatReservationModel.organization_id == reservation.organization_id,
                    SeatReservationModel.id == reservation.id,
                )
                .with_for_update()
            )
            if (
                reservation_model is None
                or reservation_model.status != ReservationStatus.ACTIVE.value
            ):
                raise EnrollmentConversionError(
                    "Seat reservation changed during enrollment conversion."
                )
            self._apply_conversion(
                model=conversion_model,
                conversion=conversion,
            )
            self._apply_application(
                model=application_model,
                application=application,
            )
            self._apply_reservation(
                model=reservation_model,
                reservation=reservation,
            )

    @staticmethod
    async def _lock_application(
        *,
        session: AsyncSession,
        organization_id: UUID,
        application_id: UUID,
        expected_status: ApplicationStatus,
    ) -> ApplicationModel:
        """Lock and require exact tenant lifecycle state for compare-and-swap."""

        model = await session.scalar(
            select(ApplicationModel)
            .where(
                ApplicationModel.organization_id == organization_id,
                ApplicationModel.id == application_id,
            )
            .with_for_update()
        )
        if model is None or model.status != expected_status.value:
            raise ApplicationTransitionError(
                "Admissions application changed concurrently."
            )
        return model

    def _profile_to_model(self, profile: ApplicantProfile) -> ApplicantProfileModel:
        """Translate an admissions-owned applicant profile into persistence."""

        return ApplicantProfileModel(
            id=profile.id,
            organization_id=profile.organization_id,
            given_name=profile.given_name,
            family_name=profile.family_name,
            encrypted_email=(
                self._cipher.encrypt(profile.email)
                if profile.email is not None
                else None
            ),
            encrypted_phone=(
                self._cipher.encrypt(profile.phone)
                if profile.phone is not None
                else None
            ),
        )

    def _profile_from_model(self, model: ApplicantProfileModel) -> ApplicantProfile:
        """Translate a stored profile into a validated domain value."""

        return ApplicantProfile(
            id=model.id,
            organization_id=model.organization_id,
            given_name=model.given_name,
            family_name=model.family_name,
            email=(
                self._cipher.decrypt(model.encrypted_email)
                if model.encrypted_email is not None
                else None
            ),
            phone=(
                self._cipher.decrypt(model.encrypted_phone)
                if model.encrypted_phone is not None
                else None
            ),
        )

    @staticmethod
    def _application_to_model(application: Application) -> ApplicationModel:
        """Translate one admissions application into its persistence row."""

        model = ApplicationModel(
            id=application.id,
            organization_id=application.organization_id,
        )
        SQLAlchemyAdmissionsRepository._apply_application(
            model=model,
            application=application,
        )
        return model

    @staticmethod
    def _apply_application(
        *,
        model: ApplicationModel,
        application: Application,
    ) -> None:
        """Apply complete current lifecycle and deposit metadata."""

        deposit = application.deposit
        model.applicant_profile_id = application.applicant_profile_id
        model.program_id = application.program_id
        model.intake_id = application.intake_id
        model.seat_category = application.seat_category
        model.source = application.source.value
        model.status = application.status.value
        model.application_created_at = application.created_at
        model.status_changed_at = application.status_changed_at
        model.deposit_required = deposit.required
        model.deposit_amount = deposit.amount
        model.deposit_currency = deposit.currency
        model.deposit_due_at = deposit.due_at
        model.deposit_external_reference = deposit.external_reference
        model.deposit_status = deposit.status.value

    @staticmethod
    def _application_from_model(model: ApplicationModel) -> Application:
        """Translate a stored application into its validated aggregate."""

        return Application(
            id=model.id,
            organization_id=model.organization_id,
            applicant_profile_id=model.applicant_profile_id,
            program_id=model.program_id,
            intake_id=model.intake_id,
            seat_category=model.seat_category,
            source=ApplicationSource(model.source),
            status=ApplicationStatus(model.status),
            created_at=model.application_created_at,
            status_changed_at=model.status_changed_at,
            deposit=DepositRequirement(
                required=model.deposit_required,
                amount=model.deposit_amount,
                currency=model.deposit_currency,
                due_at=model.deposit_due_at,
                external_reference=model.deposit_external_reference,
                status=DepositStatus(model.deposit_status),
            ),
        )

    @staticmethod
    def _quota_from_model(model: AdmissionQuotaModel) -> AdmissionQuota:
        """Translate one persisted quota into a domain value."""

        return AdmissionQuota(
            id=model.id,
            organization_id=model.organization_id,
            program_id=model.program_id,
            intake_id=model.intake_id,
            seat_category=model.seat_category,
            capacity=model.capacity,
        )

    @staticmethod
    def _quota_matches(
        *,
        quota: AdmissionQuotaModel,
        application: Application,
    ) -> bool:
        """Return whether a locked quota owns the application's exact target."""

        return (
            quota.organization_id == application.organization_id
            and quota.program_id == application.program_id
            and quota.intake_id == application.intake_id
            and quota.seat_category == application.seat_category.casefold()
        )

    @staticmethod
    def _review_to_model(review: ReviewRecord) -> ReviewRecordModel:
        """Translate an immutable review record into persistence."""

        return ReviewRecordModel(
            id=review.id,
            organization_id=review.organization_id,
            application_id=review.application_id,
            stage=review.stage.value,
            outcome=review.outcome.value,
            reviewer_id=review.reviewer_id,
            completed_at=review.completed_at,
            explanation=review.explanation,
        )

    @staticmethod
    def _review_from_model(model: ReviewRecordModel) -> ReviewRecord:
        """Translate one stored review row into its domain history value."""

        return ReviewRecord(
            id=model.id,
            organization_id=model.organization_id,
            application_id=model.application_id,
            stage=ReviewStage(model.stage),
            outcome=ReviewOutcome(model.outcome),
            reviewer_id=model.reviewer_id,
            completed_at=model.completed_at,
            explanation=model.explanation,
        )

    @staticmethod
    def _decision_to_model(decision: AdmissionDecision) -> AdmissionDecisionModel:
        """Translate one official decision into append-only persistence."""

        return AdmissionDecisionModel(
            id=decision.id,
            organization_id=decision.organization_id,
            application_id=decision.application_id,
            outcome=decision.outcome.value,
            decided_by=decision.decided_by,
            decided_at=decision.decided_at,
            reason=decision.reason,
            reservation_id=decision.reservation_id,
        )

    @staticmethod
    def _reservation_to_model(
        reservation: SeatReservation,
    ) -> SeatReservationModel:
        """Translate one quota reservation into current persistence state."""

        model = SeatReservationModel(
            id=reservation.id,
            organization_id=reservation.organization_id,
        )
        SQLAlchemyAdmissionsRepository._apply_reservation(
            model=model,
            reservation=reservation,
        )
        return model

    @staticmethod
    def _apply_reservation(
        *,
        model: SeatReservationModel,
        reservation: SeatReservation,
    ) -> None:
        """Apply complete reservation lifecycle state."""

        model.quota_id = reservation.quota_id
        model.application_id = reservation.application_id
        model.status = reservation.status.value
        model.reserved_at = reservation.reserved_at
        model.expires_at = reservation.expires_at
        model.consumed_at = reservation.consumed_at
        model.released_at = reservation.released_at

    @staticmethod
    def _reservation_from_model(model: SeatReservationModel) -> SeatReservation:
        """Translate a stored reservation into its validated domain value."""

        return SeatReservation(
            id=model.id,
            organization_id=model.organization_id,
            quota_id=model.quota_id,
            application_id=model.application_id,
            status=ReservationStatus(model.status),
            reserved_at=model.reserved_at,
            expires_at=model.expires_at,
            consumed_at=model.consumed_at,
            released_at=model.released_at,
        )

    @staticmethod
    def _conversion_to_model(
        conversion: EnrollmentConversion,
    ) -> EnrollmentConversionModel:
        """Translate conversion state into its application-keyed persistence row."""

        model = EnrollmentConversionModel(
            id=conversion.id,
            organization_id=conversion.organization_id,
        )
        SQLAlchemyAdmissionsRepository._apply_conversion(
            model=model,
            conversion=conversion,
        )
        return model

    @staticmethod
    def _apply_conversion(
        *,
        model: EnrollmentConversionModel,
        conversion: EnrollmentConversion,
    ) -> None:
        """Apply complete accepted-to-enrolled workflow state."""

        model.application_id = conversion.application_id
        model.status = conversion.status.value
        model.requested_by = conversion.requested_by
        model.correlation_id = conversion.correlation_id
        model.requested_at = conversion.requested_at
        model.student_id = conversion.student_id
        model.academic_enrollment_id = conversion.academic_enrollment_id
        model.completed_at = conversion.completed_at

    @staticmethod
    def _conversion_from_model(
        model: EnrollmentConversionModel,
    ) -> EnrollmentConversion:
        """Translate stored idempotency state into a domain conversion."""

        return EnrollmentConversion(
            id=model.id,
            organization_id=model.organization_id,
            application_id=model.application_id,
            status=EnrollmentConversionStatus(model.status),
            requested_by=model.requested_by,
            correlation_id=model.correlation_id,
            requested_at=model.requested_at,
            student_id=model.student_id,
            academic_enrollment_id=model.academic_enrollment_id,
            completed_at=model.completed_at,
        )


__all__ = ["SQLAlchemyAdmissionsRepository"]
