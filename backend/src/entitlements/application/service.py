"""Centralized permission-aware feature entitlement application service."""

from datetime import datetime
from uuid import UUID

from core.context import PlatformActorContext
from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.identifiers import new_uuid7
from entitlements.application.ports import EntitlementAuditSink
from entitlements.application.ports import EntitlementRepository
from entitlements.application.ports import OrganizationAvailability
from entitlements.domain.exceptions import EntitlementNotFoundError
from entitlements.domain.exceptions import InvalidEntitlementError
from entitlements.domain.models import BASE_FEATURES
from entitlements.domain.models import EntitlementOverride
from entitlements.domain.models import Feature
from entitlements.domain.models import FeatureCode
from entitlements.domain.models import Plan
from entitlements.domain.models import PlanGrant
from entitlements.domain.models import ResolvedEntitlement
from entitlements.domain.models import Subscription
from entitlements.domain.models import SubscriptionStatus
from entitlements.domain.models import UsageLimit

MANAGE_ENTITLEMENTS_PERMISSION = "entitlements.platform.manage"
READ_ENTITLEMENTS_PERMISSION = "entitlements.read"
_ASSIGNABLE_SUBSCRIPTION_STATUSES = frozenset(
    {
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.TRIALING,
    }
)


class EntitlementService:
    """Manage catalog state and resolve every feature in one policy boundary."""

    def __init__(
        self,
        *,
        repository: EntitlementRepository,
        organizations: OrganizationAvailability,
        audit: EntitlementAuditSink,
    ) -> None:
        self._repository = repository
        self._organizations = organizations
        self._audit = audit

    async def create_feature(
        self,
        *,
        actor: PlatformActorContext,
        code: FeatureCode,
        display_name: str,
    ) -> Feature:
        """Register one known feature through explicit platform authority."""

        self._require_platform_permission(actor)
        feature = Feature(
            id=new_uuid7(),
            code=code,
            display_name=display_name,
            base_included=code in BASE_FEATURES,
        )
        await self._audit_change(
            action="feature.creation_requested",
            actor=actor,
            target_id=feature.id,
            organization_id=None,
            outcome="intent_recorded",
        )
        await self._repository.add_feature(feature)
        await self._audit_change(
            action="feature.created",
            actor=actor,
            target_id=feature.id,
            organization_id=None,
        )
        return feature

    async def list_features(
        self,
        *,
        actor: PlatformActorContext,
        limit: int,
        offset: int,
    ) -> list[Feature]:
        """List known product capabilities through platform authority."""

        self._require_platform_permission(actor)
        return await self._repository.list_features(limit=limit, offset=offset)

    async def create_plan(
        self,
        *,
        actor: PlatformActorContext,
        code: str,
        display_name: str,
        grants: tuple[PlanGrant, ...],
    ) -> Plan:
        """Create one global plan with a complete explicit grant set."""

        self._require_platform_permission(actor)
        plan = Plan(
            id=new_uuid7(),
            code=code,
            display_name=display_name,
            grants=grants,
        )
        await self._audit_change(
            action="plan.creation_requested",
            actor=actor,
            target_id=plan.id,
            organization_id=None,
            outcome="intent_recorded",
        )
        await self._repository.add_plan(plan)
        await self._audit_change(
            action="plan.created",
            actor=actor,
            target_id=plan.id,
            organization_id=None,
        )
        return plan

    async def list_plans(
        self,
        *,
        actor: PlatformActorContext,
        limit: int,
        offset: int,
    ) -> list[Plan]:
        """List product plans and grants through platform authority."""

        self._require_platform_permission(actor)
        return await self._repository.list_plans(limit=limit, offset=offset)

    async def assign_subscription(
        self,
        *,
        actor: PlatformActorContext,
        organization_id: UUID,
        plan_id: UUID,
        status: SubscriptionStatus,
        starts_at: datetime,
        ends_at: datetime | None,
    ) -> Subscription:
        """Assign one organization's current plan through platform authority."""

        self._require_platform_permission(actor)
        if status not in _ASSIGNABLE_SUBSCRIPTION_STATUSES:
            raise InvalidEntitlementError(
                "Subscription assignment must start active or trialing"
            )
        await self._require_active_organization(organization_id=organization_id)
        plan = await self._repository.get_plan(plan_id=plan_id)
        if plan is None:
            raise EntitlementNotFoundError("Plan was not found")
        if not plan.active:
            raise InvalidEntitlementError("Inactive plans cannot be assigned")
        subscription = Subscription(
            id=new_uuid7(),
            organization_id=organization_id,
            plan_id=plan_id,
            status=status,
            starts_at=starts_at,
            ends_at=ends_at,
        )
        await self._audit_change(
            action="subscription.assignment_requested",
            actor=actor,
            target_id=subscription.id,
            organization_id=organization_id,
            outcome="intent_recorded",
        )
        await self._repository.assign_subscription(subscription)
        await self._audit_change(
            action="subscription.assigned",
            actor=actor,
            target_id=subscription.id,
            organization_id=organization_id,
        )
        return subscription

    async def set_override(
        self,
        *,
        actor: PlatformActorContext,
        organization_id: UUID,
        feature: FeatureCode,
        enabled: bool,
        usage_limit: UsageLimit | None,
        expires_at: datetime | None,
    ) -> EntitlementOverride:
        """Set one optional feature override without weakening base features."""

        self._require_platform_permission(actor)
        if feature in BASE_FEATURES and not enabled:
            raise InvalidEntitlementError("Base product features cannot be disabled")
        await self._require_active_organization(organization_id=organization_id)
        override = EntitlementOverride(
            id=new_uuid7(),
            organization_id=organization_id,
            feature=feature,
            enabled=enabled,
            usage_limit=usage_limit,
            expires_at=expires_at,
        )
        await self._audit_change(
            action="entitlement.override_set_requested",
            actor=actor,
            target_id=override.id,
            organization_id=organization_id,
            outcome="intent_recorded",
        )
        await self._repository.set_override(override)
        await self._audit_change(
            action="entitlement.override_set",
            actor=actor,
            target_id=override.id,
            organization_id=organization_id,
        )
        return override

    async def resolve(
        self,
        *,
        actor: TenantActorContext,
        feature: FeatureCode,
        at: datetime,
    ) -> ResolvedEntitlement:
        """Resolve a feature for the actor's already verified tenant context."""

        self._require_tenant_permission(actor)
        return await self.resolve_for_organization(
            organization_id=actor.organization_id,
            feature=feature,
            at=at,
        )

    async def resolve_for_organization(
        self,
        *,
        organization_id: UUID,
        feature: FeatureCode,
        at: datetime,
    ) -> ResolvedEntitlement:
        """Resolve one feature centrally for a trusted module-owned tenant ID."""

        if at.tzinfo is None:
            raise InvalidEntitlementError("Entitlement time must be timezone-aware")
        if feature in BASE_FEATURES:
            return ResolvedEntitlement(
                feature=feature,
                enabled=True,
                source="base_product",
            )
        snapshot = await self._repository.get_snapshot(
            organization_id=organization_id,
        )
        for override in snapshot.overrides:
            if override.feature is feature and override.is_effective(at=at):
                return ResolvedEntitlement(
                    feature=feature,
                    enabled=override.enabled,
                    source="platform_override",
                    usage_limit=override.usage_limit if override.enabled else None,
                )
        subscription = snapshot.subscription
        plan = snapshot.plan
        if (
            subscription is not None
            and plan is not None
            and plan.active
            and subscription.plan_id == plan.id
            and subscription.is_effective(at=at)
        ):
            grant = next(
                (grant for grant in plan.grants if grant.feature is feature),
                None,
            )
            if grant is not None:
                return ResolvedEntitlement(
                    feature=feature,
                    enabled=True,
                    source="subscription",
                    usage_limit=grant.usage_limit,
                )
        return ResolvedEntitlement(
            feature=feature,
            enabled=False,
            source="not_entitled",
        )

    async def _audit_change(
        self,
        *,
        action: str,
        actor: PlatformActorContext,
        target_id: UUID,
        organization_id: UUID | None,
        outcome: str = "succeeded",
    ) -> None:
        """Record one entitlement change without commercial payload details."""

        await self._audit.record_entitlement_event(
            action=action,
            organization_id=organization_id,
            actor_subject_id=actor.subject_id,
            target_id=target_id,
            correlation_id=actor.correlation_id,
            outcome=outcome,
        )

    async def _require_active_organization(
        self,
        *,
        organization_id: UUID,
    ) -> None:
        """Reject references that do not resolve to an active organization."""

        if not await self._organizations.is_active(
            organization_id=organization_id,
        ):
            raise InvalidEntitlementError("Organization is not active")

    @staticmethod
    def _require_platform_permission(actor: PlatformActorContext) -> None:
        """Deny catalog and subscription changes without exact platform authority."""

        if (
            not isinstance(actor, PlatformActorContext)
            or MANAGE_ENTITLEMENTS_PERMISSION not in actor.permissions
        ):
            raise AuthorizationError

    @staticmethod
    def _require_tenant_permission(actor: TenantActorContext) -> None:
        """Deny entitlement discovery without exact tenant read authority."""

        if (
            not isinstance(actor, TenantActorContext)
            or READ_ENTITLEMENTS_PERMISSION not in actor.permissions
        ):
            raise AuthorizationError


__all__ = [
    "MANAGE_ENTITLEMENTS_PERMISSION",
    "READ_ENTITLEMENTS_PERMISSION",
    "EntitlementService",
]
