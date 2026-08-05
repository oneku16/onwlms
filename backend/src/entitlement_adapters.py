"""Explicit adapters from centralized entitlements to consumer-owned ports."""

from uuid import UUID

from core.time import utc_now
from entitlements.application.ports import EntitlementResolver
from entitlements.domain.models import FeatureCode


class TimetableGenerationEntitlementAdapter:
    """Translate the central feature decision into scheduling language."""

    def __init__(self, resolver: EntitlementResolver) -> None:
        self._resolver = resolver

    async def is_timetable_generation_enabled(
        self,
        *,
        organization_id: UUID,
    ) -> bool:
        """Return the current tenant timetable-generation decision."""

        entitlement = await self._resolver.resolve_for_organization(
            organization_id=organization_id,
            feature=FeatureCode.TIMETABLE_GENERATION,
            at=utc_now(),
        )
        return entitlement.enabled


__all__ = ["TimetableGenerationEntitlementAdapter"]
