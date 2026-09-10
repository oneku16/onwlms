"""Ports owned by centralized plans and entitlement capabilities."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from entitlements.domain.models import EntitlementOverride
from entitlements.domain.models import EntitlementSnapshot
from entitlements.domain.models import Feature
from entitlements.domain.models import FeatureCode
from entitlements.domain.models import Plan
from entitlements.domain.models import ResolvedEntitlement
from entitlements.domain.models import Subscription
from entitlements.domain.models import SubscriptionStatus


class EntitlementRepository(Protocol):
    """Persist platform-global catalog and tenant-owned commercial assignments."""

    async def add_feature(
        self,
        feature: Feature,
    ) -> None:
        """Register one global feature code."""
        ...

    async def list_features(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[Feature]:
        """List bounded global feature metadata for platform administration."""
        ...

    async def add_plan(
        self,
        plan: Plan,
    ) -> None:
        """Create one global plan and its feature grants atomically."""
        ...

    async def list_plans(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[Plan]:
        """List bounded global plans with their explicit feature grants."""
        ...

    async def get_plan(
        self,
        *,
        plan_id: UUID,
    ) -> Plan | None:
        """Return one global plan for an authorized assignment decision."""
        ...

    async def assign_subscription(
        self,
        subscription: Subscription,
    ) -> None:
        """Create or replace one organization's current subscription."""
        ...

    async def get_current_subscription(
        self,
        *,
        organization_id: UUID,
    ) -> Subscription | None:
        """Return the organization's current subscription when one is assigned."""
        ...

    async def update_subscription(
        self,
        subscription: Subscription,
        *,
        expected_status: SubscriptionStatus,
    ) -> None:
        """Replace the current subscription's lifecycle state under a row lock.

        The stored subscription must still carry the given identifier and the
        expected status; otherwise raise EntitlementNotFoundError or
        EntitlementConflictError so a transition computed from a stale read
        never overwrites a concurrent lifecycle change.
        """
        ...

    async def set_override(
        self,
        override: EntitlementOverride,
    ) -> None:
        """Create or replace one organization-feature override."""
        ...

    async def get_snapshot(
        self,
        *,
        organization_id: UUID,
    ) -> EntitlementSnapshot:
        """Return only the state needed to resolve one organization's features."""
        ...


class EntitlementAuditSink(Protocol):
    """Record privacy-minimized plan and entitlement governance outcomes."""

    async def record_entitlement_event(
        self,
        *,
        action: str,
        organization_id: UUID | None,
        actor_subject_id: UUID,
        target_id: UUID,
        correlation_id: str,
        outcome: str,
    ) -> None:
        """Append one commercial change without customer or payment payloads."""
        ...


class OrganizationAvailability(Protocol):
    """Expose organization lifecycle without leaking organization internals."""

    async def is_active(
        self,
        *,
        organization_id: UUID,
    ) -> bool:
        """Return whether a referenced organization exists and is active."""
        ...


class EntitlementResolver(Protocol):
    """Expose centralized feature policy to authorized application modules."""

    async def resolve_for_organization(
        self,
        *,
        organization_id: UUID,
        feature: FeatureCode,
        at: datetime,
    ) -> ResolvedEntitlement:
        """Resolve one feature from a trusted tenant and explicit time."""
        ...


__all__ = [
    "EntitlementAuditSink",
    "EntitlementRepository",
    "EntitlementResolver",
    "OrganizationAvailability",
]
