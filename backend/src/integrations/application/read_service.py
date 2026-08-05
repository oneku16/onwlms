"""Ownership-aware Moodle deadline and grade-evidence read service."""

import hashlib
from uuid import UUID

from core.context import TenantActorContext
from core.errors import AuthorizationError
from integrations.application.ports import MoodleGatewayFactory
from integrations.application.ports import MoodleIntegrationRepository
from integrations.application.read_models import GradeSynchronizationStatus
from integrations.application.read_ports import IntegrationEvidenceReadRepository
from integrations.domain.moodle import MoodleDeadlineEvidence

MOODLE_DEADLINES_READ_OWN = "integrations.moodle_deadlines.read_own"
GRADE_SYNC_READ_ASSIGNED = "integrations.grade_sync.read_assigned"


class IntegrationSelfServiceReadService:
    """Read external evidence only after person or section ownership is resolved."""

    def __init__(
        self,
        *,
        repository: MoodleIntegrationRepository,
        evidence: IntegrationEvidenceReadRepository,
        gateway_factory: MoodleGatewayFactory,
    ) -> None:
        self._repository = repository
        self._evidence = evidence
        self._gateway_factory = gateway_factory

    async def moodle_deadlines(
        self,
        *,
        actor: TenantActorContext,
        person_id: UUID,
    ) -> tuple[MoodleDeadlineEvidence, ...]:
        """Return Moodle-owned deadlines for the actor's mapped person only."""

        if (
            not isinstance(actor, TenantActorContext)
            or MOODLE_DEADLINES_READ_OWN not in actor.permissions
        ):
            raise AuthorizationError
        external_user_id = await self._repository.get_mapping(
            organization_id=actor.organization_id,
            entity_type="person",
            entity_id=person_id,
        )
        if external_user_id is None:
            return ()
        gateway = await self._gateway_factory.create_for_organization(
            actor.organization_id
        )
        try:
            values = tuple(
                await gateway.list_deadlines(external_user_id=external_user_id)
            )
        except Exception as exc:
            await self._repository.record_failure(
                organization_id=actor.organization_id,
                error_code=self._safe_error_code(exc),
            )
            raise
        await self._repository.record_success(actor.organization_id)
        return values

    async def grade_sync_status(
        self,
        *,
        actor: TenantActorContext,
        course_offering_ids: frozenset[UUID],
    ) -> tuple[GradeSynchronizationStatus, ...]:
        """Return status only for assignment-authorized section identifiers."""

        if (
            not isinstance(actor, TenantActorContext)
            or GRADE_SYNC_READ_ASSIGNED not in actor.permissions
        ):
            raise AuthorizationError
        return await self._evidence.grade_synchronization_status(
            organization_id=actor.organization_id,
            course_offering_ids=course_offering_ids,
        )

    @staticmethod
    def _safe_error_code(exc: Exception) -> str:
        """Map an exception class to a stable value without provider details."""

        digest = hashlib.sha256(type(exc).__name__.encode("utf-8")).hexdigest()[:12]
        return f"moodle_error_{digest}"


__all__ = [
    "GRADE_SYNC_READ_ASSIGNED",
    "MOODLE_DEADLINES_READ_OWN",
    "IntegrationSelfServiceReadService",
]
