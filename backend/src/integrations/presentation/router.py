"""Thin Moodle configuration, evidence, ingress, and reconciliation routes."""

from collections.abc import Awaitable
from collections.abc import Callable
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Header
from fastapi import Query
from fastapi import Request
from fastapi import status
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import SecretStr

from core.context import ActorContext
from core.context import TenantActorContext
from core.errors import AuthenticationError
from core.errors import AuthorizationError
from core.errors import ValidationError
from integrations.application.reconciliation_service import (
    MoodleGradeReconciliationService,
)
from integrations.application.service import MoodleIntegrationService
from integrations.domain.exceptions import GradeEventRejectedError
from integrations.domain.exceptions import GradeEventSignatureError
from integrations.domain.grade_events import GRADE_EVENT_SIGNATURE_HEADER
from integrations.domain.grade_events import GRADE_EVENT_TIMESTAMP_HEADER
from integrations.domain.moodle import GradeEvidenceStatus
from integrations.domain.moodle import MoodleConfiguration
from integrations.domain.moodle import MoodleGradeEvidenceRecord
from integrations.domain.moodle import MoodleGradeReconciliationRun

PageLimit = Annotated[int, Query(ge=1, le=100)]
PageOffset = Annotated[int, Query(ge=0)]


class MoodleConfigurationRequest(BaseModel):
    """Validate tenant Moodle endpoint and credential input."""

    model_config = ConfigDict(extra="forbid")

    base_url: str = Field(min_length=12, max_length=500)
    token: SecretStr


class GradeEventSecretRequest(BaseModel):
    """Validate the shared secret that authenticates Moodle-side grade events."""

    model_config = ConfigDict(extra="forbid")

    secret: SecretStr


class MoodleStatusResponse(BaseModel):
    """Safe integration status without credential or provider payload."""

    model_config = ConfigDict(extra="forbid")

    configured: bool
    base_url: str | None
    status: str
    last_success_at: str | None
    last_error_code: str | None
    grade_events_configured: bool


class GradeEventReceiptResponse(BaseModel):
    """Report duplicate-safe intake of one authenticated grade event."""

    model_config = ConfigDict(extra="forbid")

    external_event_id: str
    duplicate: bool
    status: str


class GradeEvidenceResponse(BaseModel):
    """Serialize stored Moodle grade evidence and its resolution state."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    external_event_id: str
    course_offering_id: UUID
    student_person_id: UUID
    grade_value: str
    observed_at: datetime
    source_version: str
    status: str
    reason_code: str | None
    received_at: datetime
    accepted_final_grade_id: UUID | None
    resolved_at: datetime | None

    @classmethod
    def from_domain(cls, record: MoodleGradeEvidenceRecord) -> GradeEvidenceResponse:
        """Serialize one evidence record without resolver identity."""

        return cls(
            id=record.id,
            external_event_id=record.external_event_id,
            course_offering_id=record.course_offering_id,
            student_person_id=record.student_person_id,
            grade_value=record.grade_value,
            observed_at=record.observed_at,
            source_version=record.source_version,
            status=record.status.value,
            reason_code=record.reason_code,
            received_at=record.received_at,
            accepted_final_grade_id=record.accepted_final_grade_id,
            resolved_at=record.resolved_at,
        )


class ReconciliationRequest(BaseModel):
    """Select the tenant term whose mapped offerings should be observed."""

    model_config = ConfigDict(extra="forbid")

    term_id: UUID


class ReconciliationRunResponse(BaseModel):
    """Serialize one reconciliation run without provider payloads."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    term_id: UUID
    status: str
    started_at: datetime
    finished_at: datetime | None
    offering_count: int
    unmapped_offering_count: int
    observed_count: int
    new_evidence_count: int
    duplicate_count: int
    unmapped_user_count: int
    error_code: str | None

    @classmethod
    def from_domain(
        cls,
        run: MoodleGradeReconciliationRun,
    ) -> ReconciliationRunResponse:
        """Serialize one run's counts and outcome."""

        return cls(
            id=run.id,
            term_id=run.term_id,
            status=run.status.value,
            started_at=run.started_at,
            finished_at=run.finished_at,
            offering_count=run.offering_count,
            unmapped_offering_count=run.unmapped_offering_count,
            observed_count=run.observed_count,
            new_evidence_count=run.new_evidence_count,
            duplicate_count=run.duplicate_count,
            unmapped_user_count=run.unmapped_user_count,
            error_code=run.error_code,
        )


def create_integrations_router(
    *,
    actor_dependency: Callable[[Request], Awaitable[ActorContext]],
    csrf_dependency: Callable[..., Awaitable[None]],
) -> APIRouter:
    """Create tenant integration routes with injected security dependencies."""

    router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])

    @router.get("/moodle/status")
    async def moodle_status(
        request: Request,
        actor: Annotated[ActorContext, Depends(actor_dependency)],
    ) -> MoodleStatusResponse:
        """Return safe Moodle synchronization and activation status."""

        configuration = await _integration_service(request).status(
            actor=_tenant_actor(actor)
        )
        return _status_response(configuration)

    @router.put("/moodle/configuration")
    async def configure_moodle(
        payload: MoodleConfigurationRequest,
        request: Request,
        actor: Annotated[ActorContext, Depends(actor_dependency)],
        _: Annotated[None, Depends(csrf_dependency)],
    ) -> MoodleStatusResponse:
        """Activate or rotate one tenant's Moodle integration."""

        configuration = await _integration_service(request).configure(
            actor=_tenant_actor(actor),
            base_url=payload.base_url,
            token=payload.token.get_secret_value(),
        )
        return _status_response(configuration)

    @router.put("/moodle/grade-event-secret")
    async def configure_grade_event_secret(
        payload: GradeEventSecretRequest,
        request: Request,
        actor: Annotated[ActorContext, Depends(actor_dependency)],
        _: Annotated[None, Depends(csrf_dependency)],
    ) -> MoodleStatusResponse:
        """Store or rotate the tenant's grade-event signing secret."""

        configuration = await _integration_service(
            request
        ).configure_grade_event_secret(
            actor=_tenant_actor(actor),
            secret=payload.secret.get_secret_value(),
        )
        return _status_response(configuration)

    @router.post(
        "/moodle/grade-events/{organization_id}",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def receive_grade_event(
        organization_id: UUID,
        request: Request,
        signature: Annotated[
            str | None,
            Header(alias=GRADE_EVENT_SIGNATURE_HEADER),
        ] = None,
        timestamp: Annotated[
            str | None,
            Header(alias=GRADE_EVENT_TIMESTAMP_HEADER),
        ] = None,
    ) -> GradeEventReceiptResponse:
        """Accept one tenant-signed Moodle grade event without a browser session."""

        if signature is None or timestamp is None:
            raise AuthenticationError
        body = await request.body()
        try:
            receipt = await _integration_service(request).ingest_signed_grade_event(
                organization_id=organization_id,
                body=body,
                timestamp=timestamp,
                signature=signature,
                correlation_id=_correlation_id(request),
            )
        except GradeEventSignatureError as exc:
            raise AuthenticationError from exc
        except GradeEventRejectedError as exc:
            raise ValidationError(str(exc)) from exc
        return GradeEventReceiptResponse(
            external_event_id=receipt.external_event_id,
            duplicate=receipt.duplicate,
            status=receipt.status.value,
        )

    @router.get("/moodle/grade-evidence")
    async def list_grade_evidence(
        request: Request,
        actor: Annotated[ActorContext, Depends(actor_dependency)],
        evidence_status: Annotated[
            GradeEvidenceStatus | None,
            Query(alias="status"),
        ] = None,
        course_offering_id: UUID | None = None,
        limit: PageLimit = 50,
        offset: PageOffset = 0,
    ) -> list[GradeEvidenceResponse]:
        """Return a bounded page of stored evidence for authorized reviewers."""

        records = await _integration_service(request).list_grade_evidence(
            actor=_tenant_actor(actor),
            status=evidence_status,
            course_offering_id=course_offering_id,
            limit=limit,
            offset=offset,
        )
        return [GradeEvidenceResponse.from_domain(record) for record in records]

    @router.get("/moodle/grade-evidence/{evidence_id}")
    async def get_grade_evidence(
        evidence_id: UUID,
        request: Request,
        actor: Annotated[ActorContext, Depends(actor_dependency)],
    ) -> GradeEvidenceResponse:
        """Return one stored evidence record for authorized reviewers."""

        record = await _integration_service(request).get_grade_evidence(
            actor=_tenant_actor(actor),
            evidence_id=evidence_id,
        )
        return GradeEvidenceResponse.from_domain(record)

    @router.post(
        "/moodle/grade-reconciliations",
        status_code=status.HTTP_201_CREATED,
    )
    async def reconcile_term_grades(
        payload: ReconciliationRequest,
        request: Request,
        actor: Annotated[ActorContext, Depends(actor_dependency)],
        _: Annotated[None, Depends(csrf_dependency)],
    ) -> ReconciliationRunResponse:
        """Observe Moodle course totals for one term as pending evidence."""

        run = await _reconciliation_service(request).reconcile_term(
            actor=_tenant_actor(actor),
            term_id=payload.term_id,
        )
        return ReconciliationRunResponse.from_domain(run)

    @router.get("/moodle/grade-reconciliations")
    async def list_reconciliation_runs(
        request: Request,
        actor: Annotated[ActorContext, Depends(actor_dependency)],
        limit: PageLimit = 50,
        offset: PageOffset = 0,
    ) -> list[ReconciliationRunResponse]:
        """Return a bounded newest-first page of reconciliation runs."""

        runs = await _reconciliation_service(request).list_runs(
            actor=_tenant_actor(actor),
            limit=limit,
            offset=offset,
        )
        return [ReconciliationRunResponse.from_domain(run) for run in runs]

    @router.get("/moodle/grade-reconciliations/{run_id}")
    async def get_reconciliation_run(
        run_id: UUID,
        request: Request,
        actor: Annotated[ActorContext, Depends(actor_dependency)],
    ) -> ReconciliationRunResponse:
        """Return one reconciliation run of the active organization."""

        run = await _reconciliation_service(request).get_run(
            actor=_tenant_actor(actor),
            run_id=run_id,
        )
        return ReconciliationRunResponse.from_domain(run)

    return router


def _integration_service(request: Request) -> MoodleIntegrationService:
    """Resolve the explicitly composed Moodle integration service."""

    service: object = getattr(request.app.state, "moodle_service", None)
    if not isinstance(service, MoodleIntegrationService):
        raise RuntimeError("MoodleIntegrationService was not composed.")
    return service


def _reconciliation_service(request: Request) -> MoodleGradeReconciliationService:
    """Resolve the explicitly composed reconciliation service."""

    service: object = getattr(request.app.state, "moodle_reconciliation_service", None)
    if not isinstance(service, MoodleGradeReconciliationService):
        raise RuntimeError("MoodleGradeReconciliationService was not composed.")
    return service


def _correlation_id(request: Request) -> str:
    """Return the middleware-established correlation identifier."""

    return str(getattr(request.state, "correlation_id", "unknown"))


def _tenant_actor(actor: ActorContext) -> TenantActorContext:
    """Reject platform context on ordinary tenant integration routes."""

    if not isinstance(actor, TenantActorContext):
        raise AuthorizationError
    return actor


def _status_response(
    configuration: MoodleConfiguration | None,
) -> MoodleStatusResponse:
    """Serialize integration metadata without credential material."""

    if configuration is None:
        return MoodleStatusResponse(
            configured=False,
            base_url=None,
            status="disabled",
            last_success_at=None,
            last_error_code=None,
            grade_events_configured=False,
        )
    return MoodleStatusResponse(
        configured=True,
        base_url=configuration.base_url,
        status=configuration.status.value,
        last_success_at=(
            configuration.last_success_at.isoformat()
            if configuration.last_success_at
            else None
        ),
        last_error_code=configuration.last_error_code,
        grade_events_configured=configuration.grade_events_configured,
    )


__all__ = [
    "GradeEventReceiptResponse",
    "GradeEventSecretRequest",
    "GradeEvidenceResponse",
    "MoodleConfigurationRequest",
    "MoodleStatusResponse",
    "ReconciliationRequest",
    "ReconciliationRunResponse",
    "create_integrations_router",
]
