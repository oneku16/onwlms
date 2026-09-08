"""Tests for centralized base, subscription, override, and permission policy."""

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from typing import cast
from uuid import UUID
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport
from httpx import AsyncClient
from pydantic import ValidationError as PydanticValidationError

from core.context import PlatformActorContext
from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.http import install_error_handlers
from entitlements.application.service import MANAGE_ENTITLEMENTS_PERMISSION
from entitlements.application.service import READ_ENTITLEMENTS_PERMISSION
from entitlements.application.service import EntitlementService
from entitlements.domain.exceptions import EntitlementConflictError
from entitlements.domain.exceptions import EntitlementNotFoundError
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
from entitlements.presentation.router import AssignSubscriptionRequest
from entitlements.presentation.router import router
from identity.presentation.dependencies import require_actor
from identity.presentation.dependencies import require_csrf

NOW = datetime(2026, 8, 5, 12, tzinfo=UTC)


class FakeEntitlementRepository:
    def __init__(self) -> None:
        self.snapshots: dict[UUID, EntitlementSnapshot] = {}
        self.reads: list[UUID] = []
        self.features: list[Feature] = []
        self.plans: list[Plan] = []
        self.subscriptions: list[Subscription] = []
        self.overrides: list[EntitlementOverride] = []

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

    async def get_plan(
        self,
        *,
        plan_id: UUID,
    ) -> Plan | None:
        return next((plan for plan in self.plans if plan.id == plan_id), None)

    async def assign_subscription(self, subscription: Subscription) -> None:
        self.subscriptions.append(subscription)

    async def get_current_subscription(
        self,
        *,
        organization_id: UUID,
    ) -> Subscription | None:
        return next(
            (
                subscription
                for subscription in reversed(self.subscriptions)
                if subscription.organization_id == organization_id
            ),
            None,
        )

    async def update_subscription(
        self,
        subscription: Subscription,
        *,
        expected_status: SubscriptionStatus,
    ) -> None:
        for index, existing in enumerate(self.subscriptions):
            if (existing.organization_id, existing.id) != (
                subscription.organization_id,
                subscription.id,
            ):
                continue
            if existing.status is not expected_status:
                raise EntitlementConflictError(
                    "Subscription changed during the transition"
                )
            self.subscriptions[index] = subscription
            return
        raise EntitlementNotFoundError("Subscription was not found")

    async def set_override(self, override: EntitlementOverride) -> None:
        self.overrides.append(override)

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
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[tuple[str, UUID, str]] = []

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
        if self.fail:
            raise RuntimeError("audit unavailable")
        self.events.append((action, target_id, outcome))


class FakeOrganizationAvailability:
    def __init__(
        self,
        states: dict[UUID, bool] | None = None,
    ) -> None:
        self.states = states or {}
        self.checks: list[UUID] = []

    async def is_active(
        self,
        *,
        organization_id: UUID,
    ) -> bool:
        self.checks.append(organization_id)
        return self.states.get(organization_id, False)


def _service(
    audit: FakeEntitlementAuditSink | None = None,
    organizations: FakeOrganizationAvailability | None = None,
) -> tuple[EntitlementService, FakeEntitlementRepository]:
    repository = FakeEntitlementRepository()
    return (
        EntitlementService(
            repository=repository,
            organizations=organizations or FakeOrganizationAvailability(),
            audit=audit or FakeEntitlementAuditSink(),
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


async def test_entitlement_mutation_aborts_when_audit_intent_fails() -> None:
    service, repository = _service(FakeEntitlementAuditSink(fail=True))

    with pytest.raises(RuntimeError, match="audit unavailable"):
        await service.create_feature(
            actor=_platform(),
            code=FeatureCode.MCP,
            display_name="MCP",
        )

    assert repository.features == []


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


async def test_assignment_uses_exact_active_organization_and_plan() -> None:
    organization_id = uuid4()
    other_organization_id = uuid4()
    organizations = FakeOrganizationAvailability(
        {
            organization_id: True,
            other_organization_id: False,
        }
    )
    service, repository = _service(organizations=organizations)
    plan = Plan(
        id=uuid4(),
        code="professional",
        display_name="Professional",
        grants=(PlanGrant(feature=FeatureCode.MCP),),
    )
    repository.plans.append(plan)

    subscription = await service.assign_subscription(
        actor=_platform(),
        organization_id=organization_id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=NOW,
        ends_at=None,
    )

    assert subscription.organization_id == organization_id
    assert subscription.plan_id == plan.id
    assert organizations.checks == [organization_id]
    assert repository.subscriptions == [subscription]


@pytest.mark.parametrize(
    "organization_state",
    [None, False],
    ids=["nonexistent", "inactive"],
)
async def test_subscription_assignment_rejects_unavailable_organization(
    organization_state: bool | None,
) -> None:
    organization_id = uuid4()
    states = {} if organization_state is None else {organization_id: organization_state}
    organizations = FakeOrganizationAvailability(states)
    service, repository = _service(organizations=organizations)
    plan = Plan(
        id=uuid4(),
        code="professional",
        display_name="Professional",
        grants=(PlanGrant(feature=FeatureCode.MCP),),
    )
    repository.plans.append(plan)

    with pytest.raises(InvalidEntitlementError, match="Organization is not active"):
        await service.assign_subscription(
            actor=_platform(),
            organization_id=organization_id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            starts_at=NOW,
            ends_at=None,
        )

    assert organizations.checks == [organization_id]
    assert repository.subscriptions == []


async def test_subscription_assignment_rejects_nonexistent_plan() -> None:
    organization_id = uuid4()
    service, repository = _service(
        organizations=FakeOrganizationAvailability({organization_id: True})
    )

    with pytest.raises(EntitlementNotFoundError, match="Plan was not found"):
        await service.assign_subscription(
            actor=_platform(),
            organization_id=organization_id,
            plan_id=uuid4(),
            status=SubscriptionStatus.ACTIVE,
            starts_at=NOW,
            ends_at=None,
        )

    assert repository.subscriptions == []


async def test_subscription_assignment_rejects_inactive_plan() -> None:
    organization_id = uuid4()
    service, repository = _service(
        organizations=FakeOrganizationAvailability({organization_id: True})
    )
    plan = Plan(
        id=uuid4(),
        code="retired",
        display_name="Retired",
        grants=(),
        active=False,
    )
    repository.plans.append(plan)

    with pytest.raises(InvalidEntitlementError, match="Inactive plans"):
        await service.assign_subscription(
            actor=_platform(),
            organization_id=organization_id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            starts_at=NOW,
            ends_at=None,
        )

    assert repository.subscriptions == []


@pytest.mark.parametrize(
    "subscription_status",
    [SubscriptionStatus.SUSPENDED, SubscriptionStatus.CANCELED],
)
async def test_assignment_endpoint_rejects_unmodeled_lifecycle_transitions(
    subscription_status: SubscriptionStatus,
) -> None:
    organization_id = uuid4()
    organizations = FakeOrganizationAvailability({organization_id: True})
    service, repository = _service(organizations=organizations)

    with pytest.raises(InvalidEntitlementError, match="start active or trialing"):
        await service.assign_subscription(
            actor=_platform(),
            organization_id=organization_id,
            plan_id=uuid4(),
            status=subscription_status,
            starts_at=NOW,
            ends_at=None,
        )

    assert organizations.checks == []
    assert repository.subscriptions == []


@pytest.mark.parametrize("subscription_status", ["suspended", "canceled"])
def test_assignment_request_rejects_unmodeled_lifecycle_statuses(
    subscription_status: str,
) -> None:
    with pytest.raises(PydanticValidationError):
        AssignSubscriptionRequest.model_validate(
            {
                "plan_id": str(uuid4()),
                "status": subscription_status,
                "starts_at": NOW.isoformat(),
            }
        )


@pytest.mark.parametrize(
    "organization_state",
    [None, False],
    ids=["nonexistent", "inactive"],
)
async def test_override_rejects_unavailable_organization(
    organization_state: bool | None,
) -> None:
    organization_id = uuid4()
    states = {} if organization_state is None else {organization_id: organization_state}
    organizations = FakeOrganizationAvailability(states)
    service, repository = _service(organizations=organizations)

    with pytest.raises(InvalidEntitlementError, match="Organization is not active"):
        await service.set_override(
            actor=_platform(),
            organization_id=organization_id,
            feature=FeatureCode.MCP,
            enabled=True,
            usage_limit=None,
            expires_at=None,
        )

    assert organizations.checks == [organization_id]
    assert repository.overrides == []


async def test_override_uses_exact_active_organization() -> None:
    organization_id = uuid4()
    other_organization_id = uuid4()
    organizations = FakeOrganizationAvailability(
        {
            organization_id: True,
            other_organization_id: False,
        }
    )
    service, repository = _service(organizations=organizations)

    override = await service.set_override(
        actor=_platform(),
        organization_id=organization_id,
        feature=FeatureCode.MCP,
        enabled=True,
        usage_limit=None,
        expires_at=None,
    )

    assert override.organization_id == organization_id
    assert organizations.checks == [organization_id]
    assert repository.overrides == [override]


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


class RacingEntitlementRepository(FakeEntitlementRepository):
    """Cancel the subscription behind the service's back after it is read."""

    async def get_current_subscription(
        self,
        *,
        organization_id: UUID,
    ) -> Subscription | None:
        current = await super().get_current_subscription(
            organization_id=organization_id,
        )
        if current is not None and current.status is SubscriptionStatus.ACTIVE:
            # A concurrent platform administrator commits a cancellation
            # between this read and the caller's locked write.
            await super().update_subscription(
                current.cancel(),
                expected_status=current.status,
            )
        return current


@dataclass(slots=True)
class CsrfCounter:
    """Count CSRF validations performed by the overridden dependency."""

    calls: int = 0


def _subscription(
    *,
    organization_id: UUID,
    status: SubscriptionStatus,
) -> Subscription:
    return Subscription(
        id=uuid4(),
        organization_id=organization_id,
        plan_id=uuid4(),
        status=status,
        starts_at=NOW - timedelta(days=1),
    )


def _application(
    service: EntitlementService,
    *,
    actor: PlatformActorContext | TenantActorContext,
) -> tuple[FastAPI, CsrfCounter]:
    csrf = CsrfCounter()

    async def actor_dependency() -> PlatformActorContext | TenantActorContext:
        return actor

    async def csrf_dependency() -> None:
        csrf.calls += 1

    app = FastAPI()
    app.state.entitlement_service = service
    install_error_handlers(app)
    app.include_router(router)
    app.dependency_overrides[require_actor] = actor_dependency
    app.dependency_overrides[require_csrf] = csrf_dependency
    return app, csrf


def test_subscription_lifecycle_transitions_are_explicit_and_terminal() -> None:
    organization_id = uuid4()
    active = _subscription(
        organization_id=organization_id,
        status=SubscriptionStatus.ACTIVE,
    )
    trialing = _subscription(
        organization_id=organization_id,
        status=SubscriptionStatus.TRIALING,
    )

    suspended = active.suspend()
    canceled = active.cancel()

    assert suspended.status is SubscriptionStatus.SUSPENDED
    assert suspended.id == active.id
    assert suspended.is_effective(at=NOW) is False
    assert active.status is SubscriptionStatus.ACTIVE
    assert trialing.suspend().status is SubscriptionStatus.SUSPENDED
    assert suspended.reactivate().status is SubscriptionStatus.ACTIVE
    assert canceled.status is SubscriptionStatus.CANCELED
    assert trialing.cancel().status is SubscriptionStatus.CANCELED
    assert suspended.cancel().status is SubscriptionStatus.CANCELED
    with pytest.raises(InvalidEntitlementError, match="active subscription"):
        active.reactivate()
    with pytest.raises(InvalidEntitlementError, match="trialing subscription"):
        trialing.reactivate()
    with pytest.raises(InvalidEntitlementError, match="cannot be suspended"):
        suspended.suspend()
    with pytest.raises(InvalidEntitlementError, match="canceled subscription"):
        canceled.suspend()
    with pytest.raises(InvalidEntitlementError, match="cannot be reactivated"):
        canceled.reactivate()
    with pytest.raises(InvalidEntitlementError, match="cannot be canceled"):
        canceled.cancel()


async def test_subscription_lifecycle_is_audited_through_platform_authority() -> None:
    organization_id = uuid4()
    audit = FakeEntitlementAuditSink()
    service, repository = _service(audit=audit)
    subscription = _subscription(
        organization_id=organization_id,
        status=SubscriptionStatus.TRIALING,
    )
    other = _subscription(organization_id=uuid4(), status=SubscriptionStatus.ACTIVE)
    repository.subscriptions.extend((subscription, other))

    suspended = await service.suspend_subscription(
        actor=_platform(),
        organization_id=organization_id,
    )
    reactivated = await service.reactivate_subscription(
        actor=_platform(),
        organization_id=organization_id,
    )
    canceled = await service.cancel_subscription(
        actor=_platform(),
        organization_id=organization_id,
    )

    assert suspended.status is SubscriptionStatus.SUSPENDED
    assert reactivated.status is SubscriptionStatus.ACTIVE
    assert canceled.status is SubscriptionStatus.CANCELED
    assert canceled.id == subscription.id
    assert repository.subscriptions == [canceled, other]
    assert (
        await service.get_current_subscription(
            actor=_platform(),
            organization_id=organization_id,
        )
        == canceled
    )
    assert (
        await service.get_current_subscription(
            actor=_platform(),
            organization_id=other.organization_id,
        )
        == other
    )
    assert audit.events == [
        ("subscription.suspension_requested", subscription.id, "intent_recorded"),
        ("subscription.suspended", subscription.id, "succeeded"),
        ("subscription.reactivation_requested", subscription.id, "intent_recorded"),
        ("subscription.reactivated", subscription.id, "succeeded"),
        ("subscription.cancellation_requested", subscription.id, "intent_recorded"),
        ("subscription.canceled", subscription.id, "succeeded"),
    ]


async def test_subscription_lifecycle_reports_missing_subscriptions_as_not_found() -> (
    None
):
    audit = FakeEntitlementAuditSink()
    service, repository = _service(audit=audit)
    unknown_organization_id = uuid4()

    assert (
        await service.get_current_subscription(
            actor=_platform(),
            organization_id=unknown_organization_id,
        )
        is None
    )
    with pytest.raises(EntitlementNotFoundError, match="Subscription was not found"):
        await service.suspend_subscription(
            actor=_platform(),
            organization_id=unknown_organization_id,
        )
    with pytest.raises(EntitlementNotFoundError):
        await service.reactivate_subscription(
            actor=_platform(),
            organization_id=unknown_organization_id,
        )
    with pytest.raises(EntitlementNotFoundError):
        await service.cancel_subscription(
            actor=_platform(),
            organization_id=unknown_organization_id,
        )

    assert audit.events == []
    assert repository.subscriptions == []


async def test_invalid_lifecycle_transition_leaves_no_intent_evidence() -> None:
    organization_id = uuid4()
    audit = FakeEntitlementAuditSink()
    service, repository = _service(audit=audit)
    subscription = _subscription(
        organization_id=organization_id,
        status=SubscriptionStatus.ACTIVE,
    )
    repository.subscriptions.append(subscription)

    with pytest.raises(InvalidEntitlementError, match="cannot be reactivated"):
        await service.reactivate_subscription(
            actor=_platform(),
            organization_id=organization_id,
        )

    assert audit.events == []
    assert repository.subscriptions == [subscription]


async def test_subscription_lifecycle_aborts_when_audit_intent_fails() -> None:
    organization_id = uuid4()
    service, repository = _service(FakeEntitlementAuditSink(fail=True))
    subscription = _subscription(
        organization_id=organization_id,
        status=SubscriptionStatus.ACTIVE,
    )
    repository.subscriptions.append(subscription)

    with pytest.raises(RuntimeError, match="audit unavailable"):
        await service.suspend_subscription(
            actor=_platform(),
            organization_id=organization_id,
        )

    assert repository.subscriptions == [subscription]


async def test_stale_lifecycle_transition_is_rejected_after_intent() -> None:
    organization_id = uuid4()
    audit = FakeEntitlementAuditSink()
    repository = RacingEntitlementRepository()
    service = EntitlementService(
        repository=repository,
        organizations=FakeOrganizationAvailability(),
        audit=audit,
    )
    subscription = _subscription(
        organization_id=organization_id,
        status=SubscriptionStatus.ACTIVE,
    )
    repository.subscriptions.append(subscription)

    with pytest.raises(EntitlementConflictError, match="changed during the transition"):
        await service.suspend_subscription(
            actor=_platform(),
            organization_id=organization_id,
        )

    assert audit.events == [
        ("subscription.suspension_requested", subscription.id, "intent_recorded"),
    ]
    assert [value.status for value in repository.subscriptions] == [
        SubscriptionStatus.CANCELED
    ]


async def test_only_platform_authority_can_manage_subscription_lifecycle() -> None:
    organization_id = uuid4()
    audit = FakeEntitlementAuditSink()
    service, repository = _service(audit=audit)
    subscription = _subscription(
        organization_id=organization_id,
        status=SubscriptionStatus.ACTIVE,
    )
    repository.subscriptions.append(subscription)
    tenant = cast(
        PlatformActorContext,
        TenantActorContext(
            subject_id=uuid4(),
            organization_id=organization_id,
            membership_id=uuid4(),
            correlation_id="correlation-1",
            permissions=frozenset({MANAGE_ENTITLEMENTS_PERMISSION}),
        ),
    )
    unprivileged = PlatformActorContext(
        subject_id=uuid4(),
        correlation_id="correlation-1",
        permissions=frozenset(),
    )

    for actor in (tenant, unprivileged):
        with pytest.raises(AuthorizationError):
            await service.get_current_subscription(
                actor=actor,
                organization_id=organization_id,
            )
        with pytest.raises(AuthorizationError):
            await service.suspend_subscription(
                actor=actor,
                organization_id=organization_id,
            )
        with pytest.raises(AuthorizationError):
            await service.reactivate_subscription(
                actor=actor,
                organization_id=organization_id,
            )
        with pytest.raises(AuthorizationError):
            await service.cancel_subscription(
                actor=actor,
                organization_id=organization_id,
            )

    assert audit.events == []
    assert repository.subscriptions == [subscription]


async def test_subscription_lifecycle_routes_are_typed_and_csrf_protected() -> None:
    organization_id = uuid4()
    audit = FakeEntitlementAuditSink()
    service, repository = _service(audit=audit)
    subscription = _subscription(
        organization_id=organization_id,
        status=SubscriptionStatus.TRIALING,
    )
    repository.subscriptions.append(subscription)
    app, csrf = _application(service, actor=_platform())
    base = f"/api/v1/platform/organizations/{organization_id}/subscription"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        current = await client.get(base)
        missing = await client.get(
            f"/api/v1/platform/organizations/{uuid4()}/subscription"
        )
        suspended = await client.post(f"{base}/suspend")
        reactivated = await client.post(f"{base}/reactivate")
        invalid = await client.post(f"{base}/reactivate")
        canceled = await client.post(f"{base}/cancel")
        terminal = await client.post(f"{base}/suspend")
        gone = await client.post(
            f"/api/v1/platform/organizations/{uuid4()}/subscription/cancel"
        )

    assert current.status_code == 200
    assert current.json() == {
        "id": str(subscription.id),
        "organization_id": str(organization_id),
        "plan_id": str(subscription.plan_id),
        "status": "trialing",
        "starts_at": subscription.starts_at.isoformat(),
        "ends_at": None,
    }
    assert missing.status_code == 404
    assert suspended.status_code == 200
    assert suspended.json()["status"] == "suspended"
    assert reactivated.status_code == 200
    assert reactivated.json()["status"] == "active"
    assert invalid.status_code == 422
    assert canceled.status_code == 200
    assert canceled.json()["id"] == str(subscription.id)
    assert canceled.json()["status"] == "canceled"
    assert terminal.status_code == 422
    assert gone.status_code == 404
    assert csrf.calls == 6
    assert [event[0] for event in audit.events] == [
        "subscription.suspension_requested",
        "subscription.suspended",
        "subscription.reactivation_requested",
        "subscription.reactivated",
        "subscription.cancellation_requested",
        "subscription.canceled",
    ]


async def test_subscription_lifecycle_routes_reject_tenant_actors() -> None:
    organization_id = uuid4()
    audit = FakeEntitlementAuditSink()
    service, repository = _service(audit=audit)
    subscription = _subscription(
        organization_id=organization_id,
        status=SubscriptionStatus.ACTIVE,
    )
    repository.subscriptions.append(subscription)
    tenant = TenantActorContext(
        subject_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        correlation_id="correlation-1",
        permissions=frozenset({MANAGE_ENTITLEMENTS_PERMISSION}),
    )
    app, _ = _application(service, actor=tenant)
    base = f"/api/v1/platform/organizations/{organization_id}/subscription"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        responses = (
            await client.get(base),
            await client.post(f"{base}/suspend"),
            await client.post(f"{base}/reactivate"),
            await client.post(f"{base}/cancel"),
        )

    assert [response.status_code for response in responses] == [403, 403, 403, 403]
    assert audit.events == []
    assert repository.subscriptions == [subscription]
