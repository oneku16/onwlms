"""Thin FastAPI routes for official final-grade capabilities."""

from datetime import datetime
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

from core.context import PlatformActorContext
from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.identifiers import new_uuid7
from grading.application.service import OfficialGradingService
from grading.domain.models import FinalGrade
from grading.domain.models import FinalGradeHistory
from grading.domain.models import GpaSummary
from grading.domain.models import GradeBand
from grading.domain.models import GradeRevision
from grading.domain.models import GradingScale
from grading.domain.models import GradingScaleKind
from grading.domain.models import GradingScaleTemplate
from grading.domain.models import TranscriptRecord
from identity import ActorDep
from identity import CSRFDep

PageLimit = Annotated[int, Query(ge=1, le=100)]
PageOffset = Annotated[int, Query(ge=0)]


class GradeBandBody(BaseModel):
    """Validate one custom scale threshold and GPA outcome."""

    model_config = ConfigDict(frozen=True)

    minimum_score: Decimal
    symbol: str = Field(min_length=1, max_length=32)
    passing: bool
    grade_points: Decimal | None = Field(default=None, ge=0)


class GradingScaleBody(BaseModel):
    """Validate one complete immutable tenant grading scale."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=255)
    kind: GradingScaleKind
    minimum_score: Decimal
    maximum_score: Decimal
    bands: tuple[GradeBandBody, ...] = Field(min_length=1)


class GradingScaleTemplateBody(BaseModel):
    """Validate a request to publish a tenant copy of a built-in template."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=255)
    template: GradingScaleTemplate


class GradingScaleResponse(GradingScaleBody):
    """Serialize one complete official grading-scale definition."""

    id: UUID

    @classmethod
    def from_domain(cls, value: GradingScale) -> GradingScaleResponse:
        return cls(
            id=value.id,
            name=value.name,
            kind=value.kind,
            minimum_score=value.minimum_score,
            maximum_score=value.maximum_score,
            bands=tuple(
                GradeBandBody(
                    minimum_score=band.minimum_score,
                    symbol=band.symbol,
                    passing=band.passing,
                    grade_points=band.grade_points,
                )
                for band in value.bands
            ),
        )


class FinalGradeCreateBody(BaseModel):
    """Validate an official final-grade creation payload."""

    model_config = ConfigDict(frozen=True)

    course_enrollment_id: UUID
    grading_scale_id: UUID
    raw_score: Decimal
    explanation: str | None = Field(default=None, max_length=2000)


class FinalGradeRevisionBody(BaseModel):
    """Validate an official grade amendment payload."""

    model_config = ConfigDict(frozen=True)

    raw_score: Decimal
    explanation: str = Field(min_length=1, max_length=2000)
    grading_scale_id: UUID | None = None
    expected_revision_number: int = Field(ge=0)


class FinalGradeResponse(BaseModel):
    """Serialize current official final-grade state explicitly."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    student_academic_enrollment_id: UUID
    course_enrollment_id: UUID
    course_offering_id: UUID
    course_id: UUID
    term_id: UUID
    grading_scale_id: UUID
    raw_score: Decimal
    symbol: str
    credits_attempted: Decimal
    credits_earned: Decimal
    grade_points: Decimal | None
    gpa_contribution: Decimal | None
    revision_number: int

    @classmethod
    def from_domain(cls, grade: FinalGrade) -> FinalGradeResponse:
        """Map a final grade to its supported safe representation."""

        return cls(
            id=grade.id,
            student_academic_enrollment_id=grade.student_academic_enrollment_id,
            course_enrollment_id=grade.course_enrollment_id,
            course_offering_id=grade.course_offering_id,
            course_id=grade.course_id,
            term_id=grade.term_id,
            grading_scale_id=grade.grading_scale_id,
            raw_score=grade.raw_score,
            symbol=grade.symbol,
            credits_attempted=grade.credits_attempted,
            credits_earned=grade.credits_earned,
            grade_points=grade.grade_points,
            gpa_contribution=grade.gpa_contribution,
            revision_number=grade.revision_number,
        )


class GradeRevisionResponse(BaseModel):
    """Serialize one immutable official-grade amendment record."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    final_grade_id: UUID
    revision_number: int
    previous_raw_score: Decimal
    previous_symbol: str
    previous_credits_earned: Decimal
    previous_grade_points: Decimal | None
    previous_gpa_contribution: Decimal | None
    replacement_raw_score: Decimal
    replacement_symbol: str
    replacement_credits_earned: Decimal
    replacement_grade_points: Decimal | None
    replacement_gpa_contribution: Decimal | None
    explanation: str
    revised_by: UUID
    revised_at: datetime
    after_term_closure: bool

    @classmethod
    def from_domain(cls, revision: GradeRevision) -> GradeRevisionResponse:
        """Map an immutable grade revision to its explicit representation."""

        return cls(
            id=revision.id,
            final_grade_id=revision.final_grade_id,
            revision_number=revision.revision_number,
            previous_raw_score=revision.previous_raw_score,
            previous_symbol=revision.previous_symbol,
            previous_credits_earned=revision.previous_credits_earned,
            previous_grade_points=revision.previous_grade_points,
            previous_gpa_contribution=revision.previous_gpa_contribution,
            replacement_raw_score=revision.replacement_raw_score,
            replacement_symbol=revision.replacement_symbol,
            replacement_credits_earned=revision.replacement_credits_earned,
            replacement_grade_points=revision.replacement_grade_points,
            replacement_gpa_contribution=revision.replacement_gpa_contribution,
            explanation=revision.explanation,
            revised_by=revision.revised_by,
            revised_at=revision.revised_at,
            after_term_closure=revision.after_term_closure,
        )


class FinalGradeHistoryResponse(BaseModel):
    """Serialize initial recording evidence with immutable amendments."""

    model_config = ConfigDict(frozen=True)

    final_grade_id: UUID
    recorded_by: UUID
    recorded_at: datetime
    recorded_after_term_closure: bool
    recording_explanation: str | None
    revisions: tuple[GradeRevisionResponse, ...]

    @classmethod
    def from_domain(cls, history: FinalGradeHistory) -> FinalGradeHistoryResponse:
        """Map complete official grade history to its explicit response."""

        return cls(
            final_grade_id=history.final_grade_id,
            recorded_by=history.recorded_by,
            recorded_at=history.recorded_at,
            recorded_after_term_closure=history.recorded_after_term_closure,
            recording_explanation=history.recording_explanation,
            revisions=tuple(
                GradeRevisionResponse.from_domain(revision)
                for revision in history.revisions
            ),
        )


class TranscriptRecordResponse(BaseModel):
    """Serialize one official transcript line."""

    model_config = ConfigDict(frozen=True)

    final_grade_id: UUID
    course_id: UUID
    course_offering_id: UUID
    term_id: UUID
    symbol: str
    credits_attempted: Decimal
    credits_earned: Decimal
    grade_points: Decimal | None
    gpa_contribution: Decimal | None

    @classmethod
    def from_domain(cls, record: TranscriptRecord) -> TranscriptRecordResponse:
        """Map a transcript record to an explicit response."""

        return cls(
            final_grade_id=record.final_grade_id,
            course_id=record.course_id,
            course_offering_id=record.course_offering_id,
            term_id=record.term_id,
            symbol=record.symbol,
            credits_attempted=record.credits_attempted,
            credits_earned=record.credits_earned,
            grade_points=record.grade_points,
            gpa_contribution=record.gpa_contribution,
        )


class GpaSummaryResponse(BaseModel):
    """Serialize official GPA and credit totals."""

    model_config = ConfigDict(frozen=True)

    credits_attempted: Decimal
    credits_earned: Decimal
    gpa_credits_attempted: Decimal
    quality_points: Decimal
    gpa: Decimal | None

    @classmethod
    def from_domain(cls, summary: GpaSummary) -> GpaSummaryResponse:
        """Map a GPA summary to decimal strings without float loss."""

        return cls(
            credits_attempted=summary.credits_attempted,
            credits_earned=summary.credits_earned,
            gpa_credits_attempted=summary.gpa_credits_attempted,
            quality_points=summary.quality_points,
            gpa=summary.gpa,
        )


def _tenant_actor(
    actor: PlatformActorContext | TenantActorContext,
) -> TenantActorContext:
    """Require a verified tenant membership context."""

    if not isinstance(actor, TenantActorContext):
        raise AuthorizationError("A tenant actor is required.")
    return actor


def _grading_service(request: Request) -> OfficialGradingService:
    """Resolve the explicitly composed official grading service."""

    service: object = getattr(request.app.state, "official_grading_service", None)
    if not isinstance(service, OfficialGradingService):
        raise RuntimeError("OfficialGradingService was not composed.")
    return service


router = APIRouter(prefix="/api/v1/grading", tags=["grading"])


@router.post(
    "/scales",
    response_model=GradingScaleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def configure_scale(
    body: GradingScaleBody,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> GradingScaleResponse:
    """Publish one immutable tenant grading-scale definition."""

    context = _tenant_actor(actor)
    scale = GradingScale(
        id=new_uuid7(),
        organization_id=context.organization_id,
        name=body.name,
        kind=body.kind,
        minimum_score=body.minimum_score,
        maximum_score=body.maximum_score,
        bands=tuple(
            GradeBand(
                minimum_score=band.minimum_score,
                symbol=band.symbol,
                passing=band.passing,
                grade_points=band.grade_points,
            )
            for band in body.bands
        ),
    )
    await _grading_service(request).configure_scale(context=context, scale=scale)
    return GradingScaleResponse.from_domain(scale)


@router.post(
    "/scale-templates",
    response_model=GradingScaleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def configure_scale_template(
    body: GradingScaleTemplateBody,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> GradingScaleResponse:
    """Publish a tenant-owned copy of one built-in grading template."""

    scale = await _grading_service(request).configure_template(
        context=_tenant_actor(actor),
        name=body.name,
        template=body.template,
    )
    return GradingScaleResponse.from_domain(scale)


@router.get("/scales", response_model=tuple[GradingScaleResponse, ...])
async def list_scales(
    request: Request,
    actor: ActorDep,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> tuple[GradingScaleResponse, ...]:
    """Return a bounded page of tenant grading-scale definitions."""

    scales = await _grading_service(request).list_scales(
        context=_tenant_actor(actor),
        limit=limit,
        offset=offset,
    )
    return tuple(GradingScaleResponse.from_domain(scale) for scale in scales)


@router.get("/scales/{scale_id}", response_model=GradingScaleResponse)
async def get_scale(
    scale_id: UUID,
    request: Request,
    actor: ActorDep,
) -> GradingScaleResponse:
    """Return one complete tenant grading-scale definition."""

    scale = await _grading_service(request).get_scale(
        context=_tenant_actor(actor),
        scale_id=scale_id,
    )
    return GradingScaleResponse.from_domain(scale)


@router.post(
    "/final-grades",
    response_model=FinalGradeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_final_grade(
    body: FinalGradeCreateBody,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> FinalGradeResponse:
    """Create one authoritative final grade."""

    grade = await _grading_service(request).record_final_grade(
        context=_tenant_actor(actor),
        course_enrollment_id=body.course_enrollment_id,
        grading_scale_id=body.grading_scale_id,
        raw_score=body.raw_score,
        explanation=body.explanation,
    )
    return FinalGradeResponse.from_domain(grade)


@router.post(
    "/final-grades/{final_grade_id}/revisions",
    response_model=FinalGradeResponse,
)
async def revise_final_grade(
    final_grade_id: UUID,
    body: FinalGradeRevisionBody,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> FinalGradeResponse:
    """Amend a final grade while preserving immutable history."""

    grade = await _grading_service(request).revise_final_grade(
        context=_tenant_actor(actor),
        final_grade_id=final_grade_id,
        raw_score=body.raw_score,
        explanation=body.explanation,
        grading_scale_id=body.grading_scale_id,
        expected_revision_number=body.expected_revision_number,
    )
    return FinalGradeResponse.from_domain(grade)


@router.get(
    "/final-grades/{final_grade_id}/revisions",
    response_model=tuple[GradeRevisionResponse, ...],
)
async def revision_history(
    final_grade_id: UUID,
    request: Request,
    actor: ActorDep,
) -> tuple[GradeRevisionResponse, ...]:
    """Return immutable history to actors authorized to amend final grades."""

    revisions = await _grading_service(request).revision_history(
        context=_tenant_actor(actor),
        final_grade_id=final_grade_id,
    )
    return tuple(GradeRevisionResponse.from_domain(revision) for revision in revisions)


@router.get(
    "/final-grades/{final_grade_id}/history",
    response_model=FinalGradeHistoryResponse,
)
async def grade_history(
    final_grade_id: UUID,
    request: Request,
    actor: ActorDep,
) -> FinalGradeHistoryResponse:
    """Return initial recording evidence and immutable grade amendments."""

    history = await _grading_service(request).grade_history(
        context=_tenant_actor(actor),
        final_grade_id=final_grade_id,
    )
    return FinalGradeHistoryResponse.from_domain(history)


@router.get(
    "/students/{student_academic_enrollment_id}/transcript",
    response_model=tuple[TranscriptRecordResponse, ...],
)
async def transcript(
    student_academic_enrollment_id: UUID,
    request: Request,
    actor: ActorDep,
) -> tuple[TranscriptRecordResponse, ...]:
    """Return official transcript lines for one student enrollment."""

    records = await _grading_service(request).transcript(
        context=_tenant_actor(actor),
        student_academic_enrollment_id=student_academic_enrollment_id,
    )
    return tuple(TranscriptRecordResponse.from_domain(record) for record in records)


@router.get(
    "/students/{student_academic_enrollment_id}/gpa",
    response_model=GpaSummaryResponse,
)
async def gpa_summary(
    student_academic_enrollment_id: UUID,
    request: Request,
    actor: ActorDep,
) -> GpaSummaryResponse:
    """Return official credit and GPA summary for one student enrollment."""

    summary = await _grading_service(request).gpa_summary(
        context=_tenant_actor(actor),
        student_academic_enrollment_id=student_academic_enrollment_id,
    )
    return GpaSummaryResponse.from_domain(summary)


cast(object, record_final_grade)
cast(object, configure_scale)
cast(object, revise_final_grade)
cast(object, revision_history)
cast(object, grade_history)
cast(object, transcript)
cast(object, gpa_summary)

__all__ = [
    "FinalGradeCreateBody",
    "FinalGradeHistoryResponse",
    "FinalGradeResponse",
    "FinalGradeRevisionBody",
    "GpaSummaryResponse",
    "GradeBandBody",
    "GradeRevisionResponse",
    "GradingScaleBody",
    "GradingScaleResponse",
    "GradingScaleTemplateBody",
    "TranscriptRecordResponse",
    "router",
]
