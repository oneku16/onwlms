"""Tests for centralized base, subscription, override, and permission policy."""

from datetime import UTC
from datetime import datetime
from datetime import timedelta
from typing import cast
from uuid import UUID
from uuid import uuid4

import pytest

from core.context import PlatformActorContext
from core.context import TenantActorContext
from core.errors import AuthorizationError
from entitlements.application.service import MANAGE_ENTITLEMENTS_PERMISSION
from entitlements.application.service import READ_ENTITLEMENTS_PERMISSION
from entitlements.application.service import EntitlementService
from entitlements.domain.exceptions import InvalidEntitlementError
from entitlements.domain.models import EntitlementOverride
from entitlements.domain.models import EntitlementSnapshot
from entitlements.domain.models import Feature
from entitlements.domain.models import FeatureCode
from entitlements.domain.models import Plan
from entitlements.domain.models import PlanGrant
from entitlements.domain.models import Subscription
from entitlements.domain.models import SubscriptionStatus
from entitlements.domain.models import UsageLimit
from entitlements.domain.models import UsagePeriod

NOW = datetime(2026, 8, 5, 12, tzinfo=UTC)


class FakeEntitlementRepository:
    def __init__(self) -> None:
        self.snapshots: dict[UUID, EntitlementSnapshot] = {}
        self.reads: list[UUID] = []
        self.features: list[Feature] = []
        self.plans: list[Plan] = []

    async def add_feature(self, feature: Feature) -> None:
        self.features.append(feature)

    async def list_features(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[Feature]:
        return self.features[offset : offset + limit]

    async def add_plan(self, plan: Plan) -> None:
        self.plans.append(plan)

    async def list_plans(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[Plan]:
        return self.plans[offset : offset + limit]

    async def assign_subscription(self, subscription: Subscription) -> None:
        assert subscription.organization_id

    async def set_override(self, override: EntitlementOverride) -> None:
        assert override.organization_id

    async def get_snapshot(
        self,
        *,
        organization_id: UUID,
    ) -> EntitlementSnapshot:
        self.reads.append(organization_id)
        return self.snapshots.get(
            organization_id,
            EntitlementSnapshot(plan=None, subscription=None, overrides=()),
        )


class FakeEntitlementAuditSink:
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
        assert action and actor_subject_id and target_id and correlation_id
        assert outcome == "succeeded"


def _service() -> tuple[EntitlementService, FakeEntitlementRepository]:
    repository = FakeEntitlementRepository()
    return (
        EntitlementService(
            repository=repository,
            audit=FakeEntitlementAuditSink(),
        ),
        repository,
    )


def _tenant(organization_id: UUID) -> TenantActorContext:
    return TenantActorContext(
        subject_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        correlation_id="correlation-1",
        permissions=frozenset({READ_ENTITLEMENTS_PERMISSION}),
    )


def _platform() -> PlatformActorContext:
    return PlatformActorContext(
        subject_id=uuid4(),
        correlation_id="correlation-1",
        permissions=frozenset({MANAGE_ENTITLEMENTS_PERMISSION}),
    )


async def test_base_product_feature_is_enabled_without_subscription_query() -> None:
    service, repository = _service()
    organization_id = uuid4()

    resolved = await service.resolve(
        actor=_tenant(organization_id),
        feature=FeatureCode.OWNID_SSO,
        at=NOW,
    )

    assert resolved.enabled is True
    assert resolved.source == "base_product"
    assert repository.reads == []


async def test_active_subscription_resolves_optional_feature_and_limit() -> None:
    service, repository = _service()
    organization_id = uuid4()
    plan = Plan(
        id=uuid4(),
        code="professional",
        display_name="Professional",
        grants=(
            PlanGrant(
                feature=FeatureCode.MCP,
                usage_limit=UsageLimit(
                    amount=100,
                    period=UsagePeriod.MONTH,
                ),
            ),
        ),
    )
    repository.snapshots[organization_id] = EntitlementSnapshot(
        plan=plan,
        subscription=Subscription(
            id=uuid4(),
            organization_id=organization_id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            starts_at=NOW - timedelta(days=1),
        ),
        overrides=(),
    )

    resolved = await service.resolve(
        actor=_tenant(organization_id),
        feature=FeatureCode.MCP,
        at=NOW,
    )

    assert resolved.enabled is True
    assert resolved.source == "subscription"
    assert resolved.usage_limit == UsageLimit(
        amount=100,
        period=UsagePeriod.MONTH,
    )


async def test_effective_override_precedes_subscription_grant() -> None:
    service, repository = _service()
    organization_id = uuid4()
    plan = Plan(
        id=uuid4(),
        code="professional",
        display_name="Professional",
        grants=(PlanGrant(feature=FeatureCode.MCP),),
    )
    repository.snapshots[organization_id] = EntitlementSnapshot(
        plan=plan,
        subscription=Subscription(
            id=uuid4(),
            organization_id=organization_id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            starts_at=NOW - timedelta(days=1),
        ),
        overrides=(
            EntitlementOverride(
                id=uuid4(),
                organization_id=organization_id,
                feature=FeatureCode.MCP,
                enabled=False,
            ),
        ),
    )

    resolved = await service.resolve(
        actor=_tenant(organization_id),
        feature=FeatureCode.MCP,
        at=NOW,
    )
    assert resolved.enabled is False
    assert resolved.source == "platform_override"


async def test_tenant_context_cannot_manage_platform_entitlements() -> None:
    service, _ = _service()
    tenant = _tenant(uuid4())
    tenant = TenantActorContext(
        subject_id=tenant.subject_id,
        organization_id=tenant.organization_id,
        membership_id=tenant.membership_id,
        correlation_id=tenant.correlation_id,
        permissions=frozenset({MANAGE_ENTITLEMENTS_PERMISSION}),
    )

    with pytest.raises(AuthorizationError):
        await service.create_feature(
            actor=cast(PlatformActorContext, tenant),
            code=FeatureCode.MCP,
            display_name="MCP",
        )


async def test_platform_can_list_features_and_plans_but_tenant_cannot() -> None:
    service, repository = _service()
    feature = Feature(
        id=uuid4(),
        code=FeatureCode.MCP,
        display_name="MCP",
        base_included=False,
    )
    plan = Plan(
        id=uuid4(),
        code="professional",
        display_name="Professional",
        grants=(PlanGrant(feature=FeatureCode.MCP),),
    )
    repository.features.append(feature)
    repository.plans.append(plan)

    assert await service.list_features(actor=_platform(), limit=50, offset=0) == [
        feature
    ]
    assert await service.list_plans(actor=_platform(), limit=50, offset=0) == [plan]
    with pytest.raises(AuthorizationError):
        await service.list_plans(
            actor=cast(PlatformActorContext, _tenant(uuid4())),
            limit=50,
            offset=0,
        )


async def test_tenant_without_read_permission_cannot_resolve_entitlement() -> None:
    service, _ = _service()
    organization_id = uuid4()
    actor = TenantActorContext(
        subject_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        correlation_id="correlation-1",
        permissions=frozenset(),
    )

    with pytest.raises(AuthorizationError):
        await service.resolve(
            actor=actor,
            feature=FeatureCode.OWNID_SSO,
            at=NOW,
        )


async def test_base_feature_cannot_be_disabled_by_override() -> None:
    service, _ = _service()
    with pytest.raises(InvalidEntitlementError):
        await service.set_override(
            actor=_platform(),
            organization_id=uuid4(),
            feature=FeatureCode.ACADEMIC,
            enabled=False,
            usage_limit=None,
            expires_at=None,
        )


def test_disabled_override_cannot_retain_usage_limit() -> None:
    with pytest.raises(InvalidEntitlementError):
        EntitlementOverride(
            id=uuid4(),
            organization_id=uuid4(),
            feature=FeatureCode.MCP,
            enabled=False,
            usage_limit=UsageLimit(amount=10, period=UsagePeriod.MONTH),
        )
