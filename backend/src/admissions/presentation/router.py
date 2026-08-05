"""Thin FastAPI routes for admissions application capabilities."""

from datetime import datetime
from datetime import timedelta
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

from admissions.application.contracts import AcceptedApplicantEnrollmentResult
from admissions.application.service import AdmissionsService
from admissions.domain.models import AdmissionDecision
from admissions.domain.models import AdmissionDecisionOutcome
from admissions.domain.models import AdmissionQuota
from admissions.domain.models import AdmissionsPolicy
from admissions.domain.models import ApplicantProfile
from admissions.domain.models import Application
from admissions.domain.models import ApplicationDocument
from admissions.domain.models import ApplicationSource
from admissions.domain.models import ApplicationStatus
from admissions.domain.models import ReviewOutcome
from admissions.domain.models import ReviewRecord
from admissions.domain.models import ReviewStage
from core.context import PlatformActorContext
from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.identifiers import new_uuid7
from core.time import utc_now
from identity import ActorDep
from identity import CSRFDep

PageLimit = Annotated[int, Query(ge=1, le=100)]
PageOffset = Annotated[int, Query(ge=0)]


class ApplicationCreateBody(BaseModel):
    """Validate administrator-entered or future self-submitted application data."""

    model_config = ConfigDict(frozen=True)

    given_name: str = Field(min_length=1, max_length=128)
    family_name: str = Field(min_length=1, max_length=128)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=64)
    program_id: UUID
    intake_id: UUID
    seat_category: str = Field(min_length=1, max_length=64)
    source: ApplicationSource


class ApplicationResponse(BaseModel):
    """Serialize application state without applicant contact information."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    applicant_profile_id: UUID
    program_id: UUID
    intake_id: UUID
    seat_category: str
    source: str
    status: str
    deposit_status: str
    deposit_required: bool
    deposit_amount: Decimal | None
    deposit_currency: str | None
    deposit_due_at: datetime | None
    created_at: datetime
    status_changed_at: datetime

    @classmethod
    def from_domain(cls, application: Application) -> ApplicationResponse:
        """Map an admissions application to its safe public representation."""

        return cls(
            id=application.id,
            applicant_profile_id=application.applicant_profile_id,
            program_id=application.program_id,
            intake_id=application.intake_id,
            seat_category=application.seat_category,
            source=application.source,
            status=application.status,
            deposit_status=application.deposit.status,
            deposit_required=application.deposit.required,
            deposit_amount=application.deposit.amount,
            deposit_currency=application.deposit.currency,
            deposit_due_at=application.deposit.due_at,
            created_at=application.created_at,
            status_changed_at=application.status_changed_at,
        )


class AdmissionsPolicyBody(BaseModel):
    """Validate review, deposit, and reservation policy configuration."""

    model_config = ConfigDict(frozen=True)

    required_stages: tuple[ReviewStage, ...] = ()
    deposit_required: bool = False
    deposit_amount: Decimal | None = Field(default=None, gt=0)
    deposit_currency: str | None = Field(default=None, max_length=3)
    reservation_duration_seconds: int = Field(ge=60, le=31_536_000)


class AdmissionsPolicyResponse(AdmissionsPolicyBody):
    """Serialize one exact tenant admissions policy."""

    program_id: UUID
    intake_id: UUID

    @classmethod
    def from_domain(cls, value: AdmissionsPolicy) -> AdmissionsPolicyResponse:
        return cls(
            program_id=value.program_id,
            intake_id=value.intake_id,
            required_stages=value.required_stages,
            deposit_required=value.deposit_required,
            deposit_amount=value.deposit_amount,
            deposit_currency=value.deposit_currency,
            reservation_duration_seconds=int(
                value.reservation_duration.total_seconds()
            ),
        )


class AdmissionQuotaBody(BaseModel):
    """Validate one program/intake/seat-category quota."""

    model_config = ConfigDict(frozen=True)

    program_id: UUID
    intake_id: UUID
    seat_category: str = Field(min_length=1, max_length=64)
    capacity: int = Field(gt=0)


class AdmissionQuotaResponse(AdmissionQuotaBody):
    """Serialize one configured tenant quota."""

    id: UUID

    @classmethod
    def from_domain(cls, value: AdmissionQuota) -> AdmissionQuotaResponse:
        return cls(
            id=value.id,
            program_id=value.program_id,
            intake_id=value.intake_id,
            seat_category=value.seat_category,
            capacity=value.capacity,
        )


class ApplicationDocumentBody(BaseModel):
    """Validate externally stored applicant document metadata only."""

    model_config = ConfigDict(frozen=True)

    document_type: str = Field(min_length=1, max_length=128)
    file_reference: str = Field(min_length=1, max_length=512)
    media_type: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0, le=100_000_000)
    checksum_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


class ApplicationDocumentResponse(ApplicationDocumentBody):
    """Serialize safe document metadata without file contents or contact data."""

    id: UUID
    application_id: UUID
    uploaded_at: datetime

    @classmethod
    def from_domain(cls, value: ApplicationDocument) -> ApplicationDocumentResponse:
        return cls(
            id=value.id,
            application_id=value.application_id,
            document_type=value.document_type,
            file_reference=value.file_reference,
            media_type=value.media_type,
            size_bytes=value.size_bytes,
            checksum_sha256=value.checksum_sha256,
            uploaded_at=value.uploaded_at,
        )


class ReviewBody(BaseModel):
    """Validate one configured admissions review result."""

    model_config = ConfigDict(frozen=True)

    stage: ReviewStage
    outcome: ReviewOutcome
    explanation: str | None = Field(default=None, max_length=2000)


class ReviewResponse(BaseModel):
    """Serialize a supported immutable review record."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    application_id: UUID
    stage: str
    outcome: str
    explanation: str | None

    @classmethod
    def from_domain(cls, review: ReviewRecord) -> ReviewResponse:
        """Map a review record to an explicit response."""

        return cls(
            id=review.id,
            application_id=review.application_id,
            stage=review.stage,
            outcome=review.outcome,
            explanation=review.explanation,
        )


class DecisionBody(BaseModel):
    """Validate an official admissions decision."""

    model_config = ConfigDict(frozen=True)

    outcome: AdmissionDecisionOutcome
    reason: str = Field(min_length=1, max_length=2000)


class DecisionResponse(BaseModel):
    """Serialize one immutable official admissions decision."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    application_id: UUID
    outcome: str
    reason: str
    reservation_id: UUID | None

    @classmethod
    def from_domain(cls, decision: AdmissionDecision) -> DecisionResponse:
        """Map an official decision to an explicit response."""

        return cls(
            id=decision.id,
            application_id=decision.application_id,
            outcome=decision.outcome,
            reason=decision.reason,
            reservation_id=decision.reservation_id,
        )


class EnrollmentConversionResponse(BaseModel):
    """Serialize stable identifiers from accepted-to-enrolled conversion."""

    model_config = ConfigDict(frozen=True)

    student_id: UUID
    academic_enrollment_id: UUID

    @classmethod
    def from_result(
        cls,
        result: AcceptedApplicantEnrollmentResult,
    ) -> EnrollmentConversionResponse:
        """Map the application collaboration result to an HTTP response."""

        return cls(
            student_id=result.student_id,
            academic_enrollment_id=result.academic_enrollment_id,
        )


def _tenant_actor(
    actor: PlatformActorContext | TenantActorContext,
) -> TenantActorContext:
    """Require a verified tenant membership context."""

    if not isinstance(actor, TenantActorContext):
        raise AuthorizationError("A tenant actor is required.")
    return actor


def _admissions_service(request: Request) -> AdmissionsService:
    """Resolve the explicitly composed admissions application service."""

    service: object = getattr(request.app.state, "admissions_service", None)
    if not isinstance(service, AdmissionsService):
        raise RuntimeError("AdmissionsService was not composed.")
    return service


router = APIRouter(prefix="/api/v1/admissions", tags=["admissions"])


@router.put(
    "/policies/{program_id}/{intake_id}",
    response_model=AdmissionsPolicyResponse,
)
async def configure_policy(
    program_id: UUID,
    intake_id: UUID,
    body: AdmissionsPolicyBody,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> AdmissionsPolicyResponse:
    """Configure one tenant program/intake admissions policy."""

    context = _tenant_actor(actor)
    policy = AdmissionsPolicy(
        organization_id=context.organization_id,
        program_id=program_id,
        intake_id=intake_id,
        required_stages=body.required_stages,
        deposit_required=body.deposit_required,
        deposit_amount=body.deposit_amount,
        deposit_currency=body.deposit_currency,
        reservation_duration=timedelta(seconds=body.reservation_duration_seconds),
    )
    await _admissions_service(request).configure_policy(
        context=context,
        policy=policy,
    )
    return AdmissionsPolicyResponse.from_domain(policy)


@router.get(
    "/policies/{program_id}/{intake_id}",
    response_model=AdmissionsPolicyResponse,
)
async def get_policy(
    program_id: UUID,
    intake_id: UUID,
    request: Request,
    actor: ActorDep,
) -> AdmissionsPolicyResponse:
    """Return one authorized tenant admissions policy."""

    policy = await _admissions_service(request).get_policy(
        context=_tenant_actor(actor),
        program_id=program_id,
        intake_id=intake_id,
    )
    return AdmissionsPolicyResponse.from_domain(policy)


@router.put("/quotas/{quota_id}", response_model=AdmissionQuotaResponse)
async def configure_quota(
    quota_id: UUID,
    body: AdmissionQuotaBody,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> AdmissionQuotaResponse:
    """Configure one stable categorized tenant admission quota."""

    context = _tenant_actor(actor)
    quota = AdmissionQuota(
        id=quota_id,
        organization_id=context.organization_id,
        program_id=body.program_id,
        intake_id=body.intake_id,
        seat_category=body.seat_category,
        capacity=body.capacity,
    )
    await _admissions_service(request).configure_quota(
        context=context,
        quota=quota,
    )
    return AdmissionQuotaResponse.from_domain(quota)


@router.get("/quotas", response_model=AdmissionQuotaResponse)
async def get_quota(
    program_id: UUID,
    intake_id: UUID,
    seat_category: str,
    request: Request,
    actor: ActorDep,
) -> AdmissionQuotaResponse:
    """Return one exact tenant quota by normalized seat category."""

    quota = await _admissions_service(request).get_quota(
        context=_tenant_actor(actor),
        program_id=program_id,
        intake_id=intake_id,
        seat_category=seat_category,
    )
    return AdmissionQuotaResponse.from_domain(quota)


@router.get("/applications", response_model=tuple[ApplicationResponse, ...])
async def list_applications(
    request: Request,
    actor: ActorDep,
    application_status: ApplicationStatus | None = None,
    program_id: UUID | None = None,
    intake_id: UUID | None = None,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> tuple[ApplicationResponse, ...]:
    """Return a filtered bounded page of safe admissions applications."""

    applications = await _admissions_service(request).list_applications(
        context=_tenant_actor(actor),
        status=application_status,
        program_id=program_id,
        intake_id=intake_id,
        limit=limit,
        offset=offset,
    )
    return tuple(ApplicationResponse.from_domain(value) for value in applications)


@router.get("/applications/{application_id}", response_model=ApplicationResponse)
async def get_application(
    application_id: UUID,
    request: Request,
    actor: ActorDep,
) -> ApplicationResponse:
    """Return one tenant application without applicant contact information."""

    application = await _admissions_service(request).get_application(
        context=_tenant_actor(actor),
        application_id=application_id,
    )
    return ApplicationResponse.from_domain(application)


@router.post(
    "/applications/{application_id}/documents",
    response_model=ApplicationDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_document(
    application_id: UUID,
    body: ApplicationDocumentBody,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> ApplicationDocumentResponse:
    """Append safe metadata for an externally stored applicant document."""

    context = _tenant_actor(actor)
    document = ApplicationDocument(
        id=new_uuid7(),
        organization_id=context.organization_id,
        application_id=application_id,
        document_type=body.document_type,
        file_reference=body.file_reference,
        media_type=body.media_type,
        size_bytes=body.size_bytes,
        checksum_sha256=body.checksum_sha256.casefold(),
        uploaded_at=utc_now(),
    )
    await _admissions_service(request).add_document(
        context=context,
        document=document,
    )
    return ApplicationDocumentResponse.from_domain(document)


@router.get(
    "/applications/{application_id}/documents",
    response_model=tuple[ApplicationDocumentResponse, ...],
)
async def list_documents(
    application_id: UUID,
    request: Request,
    actor: ActorDep,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> tuple[ApplicationDocumentResponse, ...]:
    """Return a bounded safe document-metadata page."""

    documents = await _admissions_service(request).list_documents(
        context=_tenant_actor(actor),
        application_id=application_id,
        limit=limit,
        offset=offset,
    )
    return tuple(ApplicationDocumentResponse.from_domain(value) for value in documents)


@router.get(
    "/applications/{application_id}/reviews",
    response_model=tuple[ReviewResponse, ...],
)
async def list_reviews(
    application_id: UUID,
    request: Request,
    actor: ActorDep,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> tuple[ReviewResponse, ...]:
    """Return a bounded immutable admissions review history."""

    reviews = await _admissions_service(request).list_reviews(
        context=_tenant_actor(actor),
        application_id=application_id,
        limit=limit,
        offset=offset,
    )
    return tuple(ReviewResponse.from_domain(value) for value in reviews)


@router.post(
    "/applications",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_application(
    body: ApplicationCreateBody,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> ApplicationResponse:
    """Create a tenant applicant profile and draft application."""

    context = _tenant_actor(actor)
    application = await _admissions_service(request).create_application(
        context=context,
        profile=ApplicantProfile(
            id=new_uuid7(),
            organization_id=context.organization_id,
            given_name=body.given_name,
            family_name=body.family_name,
            email=body.email,
            phone=body.phone,
        ),
        program_id=body.program_id,
        intake_id=body.intake_id,
        seat_category=body.seat_category,
        source=body.source,
    )
    return ApplicationResponse.from_domain(application)


@router.post(
    "/applications/{application_id}/submit",
    response_model=ApplicationResponse,
)
async def submit_application(
    application_id: UUID,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> ApplicationResponse:
    """Submit a draft tenant application."""

    application = await _admissions_service(request).submit_application(
        context=_tenant_actor(actor),
        application_id=application_id,
    )
    return ApplicationResponse.from_domain(application)


@router.post(
    "/applications/{application_id}/reviews",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_review(
    application_id: UUID,
    body: ReviewBody,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> ReviewResponse:
    """Record one configured application review."""

    review = await _admissions_service(request).record_review(
        context=_tenant_actor(actor),
        application_id=application_id,
        stage=body.stage,
        outcome=body.outcome,
        explanation=body.explanation,
    )
    return ReviewResponse.from_domain(review)


@router.post(
    "/applications/{application_id}/decisions",
    response_model=DecisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def decide_application(
    application_id: UUID,
    body: DecisionBody,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> DecisionResponse:
    """Make one official admissions decision."""

    decision = await _admissions_service(request).decide_application(
        context=_tenant_actor(actor),
        application_id=application_id,
        outcome=body.outcome,
        reason=body.reason,
    )
    return DecisionResponse.from_domain(decision)


@router.post(
    "/applications/{application_id}/enrollment",
    response_model=EnrollmentConversionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def enroll_accepted_application(
    application_id: UUID,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> EnrollmentConversionResponse:
    """Convert an accepted application through the idempotent public contract."""

    result = await _admissions_service(request).enroll_accepted_application(
        context=_tenant_actor(actor),
        application_id=application_id,
    )
    return EnrollmentConversionResponse.from_result(result)


cast(object, create_application)
cast(object, submit_application)
cast(object, record_review)
cast(object, decide_application)
cast(object, enroll_accepted_application)

__all__ = [
    "AdmissionQuotaBody",
    "AdmissionQuotaResponse",
    "AdmissionsPolicyBody",
    "AdmissionsPolicyResponse",
    "ApplicationCreateBody",
    "ApplicationDocumentBody",
    "ApplicationDocumentResponse",
    "ApplicationResponse",
    "DecisionBody",
    "DecisionResponse",
    "EnrollmentConversionResponse",
    "ReviewBody",
    "ReviewResponse",
    "router",
]
