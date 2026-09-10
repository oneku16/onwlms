"""Operator-initiated selected-term Moodle grade reconciliation."""

import hashlib
from dataclasses import replace
from uuid import UUID

from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import NotFoundError
from core.errors import ValidationError
from core.identifiers import new_uuid7
from integrations.application.ports import ExternalGradeEvidenceIntake
from integrations.application.ports import IntegrationClock
from integrations.application.ports import MoodleGatewayFactory
from integrations.application.ports import MoodleIntegrationAuditSink
from integrations.application.ports import MoodleIntegrationRepository
from integrations.application.ports import MoodleReconciliationRunRepository
from integrations.application.ports import TermOfferingDirectory
from integrations.application.service import GRADE_EVIDENCE_READ
from integrations.domain.moodle import MoodleCourseGradeObservation
from integrations.domain.moodle import MoodleFinalGradeEvidence
from integrations.domain.moodle import MoodleGradeReconciliationRun
from integrations.domain.moodle import ReconciliationRunStatus

GRADE_EVIDENCE_RECONCILE = "integrations.grade_evidence.reconcile"
MAX_RECONCILIATION_OFFERINGS = 200
MAX_RECONCILIATION_PAGE_SIZE = 100
_MAX_EVENT_ID_LENGTH = 200


class MoodleGradeReconciliationService:
    """Pull selected-term Moodle course totals into duplicate-safe evidence.

    Reconciliation never writes official grades. It observes Moodle course
    totals for mapped offerings and mapped learners, translates each into
    non-authoritative evidence with a deterministic external key, and leaves
    acceptance to the grading policy. Unmapped offerings and users are counted
    rather than guessed.
    """

    def __init__(
        self,
        *,
        repository: MoodleIntegrationRepository,
        runs: MoodleReconciliationRunRepository,
        intake: ExternalGradeEvidenceIntake,
        gateway_factory: MoodleGatewayFactory,
        offerings: TermOfferingDirectory,
        clock: IntegrationClock,
        audit: MoodleIntegrationAuditSink,
    ) -> None:
        self._repository = repository
        self._runs = runs
        self._intake = intake
        self._gateway_factory = gateway_factory
        self._offerings = offerings
        self._clock = clock
        self._audit = audit

    async def reconcile_term(
        self,
        *,
        actor: TenantActorContext,
        term_id: UUID,
    ) -> MoodleGradeReconciliationRun:
        """Run one bounded reconciliation for the actor's tenant term."""

        _authorize(actor, GRADE_EVIDENCE_RECONCILE)
        offering_ids = await self._offerings.list_course_offering_ids(
            organization_id=actor.organization_id,
            term_id=term_id,
        )
        if offering_ids is None:
            raise NotFoundError("Academic term was not found.")
        if len(offering_ids) > MAX_RECONCILIATION_OFFERINGS:
            raise ValidationError(
                "Reconciliation is bounded to "
                f"{MAX_RECONCILIATION_OFFERINGS} offerings per term."
            )
        run = MoodleGradeReconciliationRun(
            id=new_uuid7(),
            organization_id=actor.organization_id,
            term_id=term_id,
            requested_by=actor.subject_id,
            status=ReconciliationRunStatus.RUNNING,
            started_at=self._clock.now(),
            offering_count=len(offering_ids),
        )
        await self._audit.record_grade_reconciliation_event(
            action="integrations.moodle.grade_reconciliation_requested",
            organization_id=actor.organization_id,
            actor_subject_id=actor.subject_id,
            run_id=run.id,
            correlation_id=actor.correlation_id,
            outcome="intent_recorded",
        )
        await self._runs.create_run(run)
        try:
            completed = await self._reconcile(
                run=run,
                offering_ids=offering_ids,
                correlation_id=actor.correlation_id,
            )
        except Exception as exc:
            error_code = self._safe_error_code(exc)
            await self._runs.complete_run(
                replace(
                    run,
                    status=ReconciliationRunStatus.FAILED,
                    finished_at=self._clock.now(),
                    error_code=error_code,
                )
            )
            await self._repository.record_failure(
                organization_id=actor.organization_id,
                error_code=error_code,
            )
            await self._audit.record_grade_reconciliation_event(
                action="integrations.moodle.grade_reconciliation.failed",
                organization_id=actor.organization_id,
                actor_subject_id=actor.subject_id,
                run_id=run.id,
                correlation_id=actor.correlation_id,
                outcome="failed",
            )
            raise
        await self._runs.complete_run(completed)
        await self._repository.record_success(actor.organization_id)
        await self._audit.record_grade_reconciliation_event(
            action="integrations.moodle.grade_reconciliation.succeeded",
            organization_id=actor.organization_id,
            actor_subject_id=actor.subject_id,
            run_id=run.id,
            correlation_id=actor.correlation_id,
            outcome="succeeded",
        )
        return completed

    async def list_runs(
        self,
        *,
        actor: TenantActorContext,
        limit: int,
        offset: int,
    ) -> tuple[MoodleGradeReconciliationRun, ...]:
        """Return a bounded newest-first page of the tenant's runs."""

        _authorize(actor, GRADE_EVIDENCE_READ)
        if limit < 1 or limit > MAX_RECONCILIATION_PAGE_SIZE or offset < 0:
            raise ValidationError(
                f"Run page limit must be 1-{MAX_RECONCILIATION_PAGE_SIZE} "
                "and offset cannot be negative."
            )
        return await self._runs.list_runs(
            organization_id=actor.organization_id,
            limit=limit,
            offset=offset,
        )

    async def get_run(
        self,
        *,
        actor: TenantActorContext,
        run_id: UUID,
    ) -> MoodleGradeReconciliationRun:
        """Return one of the tenant's runs or fail closed."""

        _authorize(actor, GRADE_EVIDENCE_READ)
        run = await self._runs.get_run(
            organization_id=actor.organization_id,
            run_id=run_id,
        )
        if run is None:
            raise NotFoundError("Reconciliation run was not found.")
        return run

    async def _reconcile(
        self,
        *,
        run: MoodleGradeReconciliationRun,
        offering_ids: frozenset[UUID],
        correlation_id: str,
    ) -> MoodleGradeReconciliationRun:
        """Observe every mapped offering and feed evidence through intake."""

        gateway = await self._gateway_factory.create_for_organization(
            run.organization_id
        )
        unmapped_offerings = 0
        observed = 0
        new_evidence = 0
        duplicates = 0
        unmapped_users = 0
        for offering_id in sorted(offering_ids, key=str):
            external_course_id = await self._repository.get_mapping(
                organization_id=run.organization_id,
                entity_type="course_offering",
                entity_id=offering_id,
            )
            if external_course_id is None:
                unmapped_offerings += 1
                continue
            observations = await gateway.list_course_grades(
                external_course_id=external_course_id
            )
            for observation in observations:
                observed += 1
                person_id = await self._repository.get_entity_id(
                    organization_id=run.organization_id,
                    entity_type="person",
                    external_id=observation.external_user_id,
                )
                if person_id is None:
                    unmapped_users += 1
                    continue
                receipt = await self._intake.receive_final_grade_evidence(
                    organization_id=run.organization_id,
                    evidence=MoodleFinalGradeEvidence(
                        external_event_id=_reconciliation_event_id(
                            external_course_id=external_course_id,
                            observation=observation,
                        ),
                        course_offering_id=offering_id,
                        student_person_id=person_id,
                        grade_value=observation.grade_raw,
                        observed_at=observation.observed_at,
                        source_version=observation.source_version,
                    ),
                    correlation_id=correlation_id,
                )
                if receipt.duplicate:
                    duplicates += 1
                else:
                    new_evidence += 1
        return replace(
            run,
            status=ReconciliationRunStatus.SUCCEEDED,
            finished_at=self._clock.now(),
            unmapped_offering_count=unmapped_offerings,
            observed_count=observed,
            new_evidence_count=new_evidence,
            duplicate_count=duplicates,
            unmapped_user_count=unmapped_users,
        )

    @staticmethod
    def _safe_error_code(exc: Exception) -> str:
        """Return an opaque failure class code without provider detail."""

        digest = hashlib.sha256(type(exc).__name__.encode("utf-8")).hexdigest()[:12]
        return f"moodle_error_{digest}"


def _authorize(
    actor: TenantActorContext,
    permission: str,
) -> None:
    """Fail closed unless the verified tenant actor holds one permission."""

    if permission not in actor.permissions:
        raise AuthorizationError


def _reconciliation_event_id(
    *,
    external_course_id: str,
    observation: MoodleCourseGradeObservation,
) -> str:
    """Derive a deterministic external key so re-runs stay duplicate-safe."""

    graded_at = (
        int(observation.graded_at.timestamp())
        if observation.graded_at is not None
        else 0
    )
    key = (
        f"reconciliation:{external_course_id}:{observation.external_user_id}:"
        f"{observation.grade_item_id}:{graded_at}:{observation.grade_raw}"
    )
    if len(key) <= _MAX_EVENT_ID_LENGTH:
        return key
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return f"reconciliation:sha256:{digest}"


__all__ = [
    "GRADE_EVIDENCE_RECONCILE",
    "MAX_RECONCILIATION_OFFERINGS",
    "MAX_RECONCILIATION_PAGE_SIZE",
    "MoodleGradeReconciliationService",
]
