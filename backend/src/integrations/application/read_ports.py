"""Read contracts for assignment-scoped integration evidence."""

from typing import Protocol
from uuid import UUID

from integrations.application.read_models import GradeSynchronizationStatus


class IntegrationEvidenceReadRepository(Protocol):
    """Project synchronization evidence for an exact authorized section set."""

    async def grade_synchronization_status(
        self,
        *,
        organization_id: UUID,
        course_offering_ids: frozenset[UUID],
    ) -> tuple[GradeSynchronizationStatus, ...]:
        """Return one privacy-safe status projection per requested section."""
        ...


__all__ = ["IntegrationEvidenceReadRepository"]
