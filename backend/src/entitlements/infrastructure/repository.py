"""PostgreSQL centralized plans and entitlement repository adapter."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from entitlements.domain.exceptions import EntitlementConflictError
from entitlements.domain.exceptions import EntitlementNotFoundError
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
from entitlements.infrastructure.models import EntitlementOverrideModel
from entitlements.infrastructure.models import FeatureModel
from entitlements.infrastructure.models import PlanFeatureModel
from entitlements.infrastructure.models import PlanModel
from entitlements.infrastructure.models import SubscriptionModel
from shared.database import Database


class SQLAlchemyEntitlementRepository:
    """Persist global catalog and tenant subscription state through owned tables."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database

    async def add_feature(
        self,
        feature: Feature,
    ) -> None:
        """Register a global feature and translate duplicate-code conflicts."""

        try:
            async with self._database.session() as session:
                session.add(
                    FeatureModel(
                        id=feature.id,
                        code=feature.code.value,
                        display_name=feature.display_name,
                        base_included=feature.base_included,
                    )
                )
        except IntegrityError as exc:
            raise EntitlementConflictError("Feature code already exists") from exc

    async def list_features(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[Feature]:
        """List bounded global feature metadata in stable code order."""

        async with self._database.session() as session:
            models = await session.scalars(
                select(FeatureModel)
                .order_by(FeatureModel.code)
                .limit(limit)
                .offset(offset)
            )
            return [
                Feature(
                    id=model.id,
                    code=FeatureCode(model.code),
                    display_name=model.display_name,
                    base_included=model.base_included,
                )
                for model in models
            ]

    async def add_plan(
        self,
        plan: Plan,
    ) -> None:
        """Create a global plan and all feature grants atomically."""

        try:
            async with self._database.session() as session:
                session.add(
                    PlanModel(
                        id=plan.id,
                        code=plan.code,
                        display_name=plan.display_name,
                        active=plan.active,
                    )
                )
                for grant in plan.grants:
                    session.add(self._grant_to_model(plan_id=plan.id, grant=grant))
        except IntegrityError as exc:
            raise EntitlementConflictError(
                "Plan code or feature grant is invalid"
            ) from exc

    async def list_plans(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[Plan]:
        """List bounded global plans and their explicit grants."""

        async with self._database.session() as session:
            models = await session.scalars(
                select(PlanModel).order_by(PlanModel.code).limit(limit).offset(offset)
            )
            plans: list[Plan] = []
            for model in models:
                grant_models = await session.scalars(
                    select(PlanFeatureModel)
                    .where(PlanFeatureModel.plan_id == model.id)
                    .order_by(PlanFeatureModel.feature_code)
                )
                plans.append(
                    Plan(
                        id=model.id,
                        code=model.code,
                        display_name=model.display_name,
                        grants=tuple(
                            self._grant_to_domain(grant) for grant in grant_models
                        ),
                        active=model.active,
                    )
                )
            return plans

    async def get_plan(
        self,
        *,
        plan_id: UUID,
    ) -> Plan | None:
        """Return one global plan and its grants by stable identifier."""

        async with self._database.session() as session:
            model = await session.get(PlanModel, plan_id)
            if model is None:
                return None
            grant_models = await session.scalars(
                select(PlanFeatureModel)
                .where(PlanFeatureModel.plan_id == model.id)
                .order_by(PlanFeatureModel.feature_code)
            )
            return Plan(
                id=model.id,
                code=model.code,
                display_name=model.display_name,
                grants=tuple(self._grant_to_domain(grant) for grant in grant_models),
                active=model.active,
            )

    async def assign_subscription(
        self,
        subscription: Subscription,
    ) -> None:
        """Create or replace one organization's current subscription atomically."""

        try:
            async with self._database.session(
                organization_id=subscription.organization_id,
            ) as session:
                model = await session.scalar(
                    select(SubscriptionModel)
                    .where(
                        SubscriptionModel.organization_id
                        == subscription.organization_id,
                    )
                    .with_for_update()
                )
                if model is None:
                    model = SubscriptionModel(
                        id=subscription.id,
                        organization_id=subscription.organization_id,
                    )
                    session.add(model)
                else:
                    model.id = subscription.id
                model.plan_id = subscription.plan_id
                model.status = subscription.status.value
                model.starts_at = subscription.starts_at
                model.ends_at = subscription.ends_at
        except IntegrityError as exc:
            raise EntitlementConflictError("Subscription plan is invalid") from exc

    async def get_current_subscription(
        self,
        *,
        organization_id: UUID,
    ) -> Subscription | None:
        """Read one organization's current subscription under its tenant context."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(SubscriptionModel).where(
                    SubscriptionModel.organization_id == organization_id,
                )
            )
            if model is None:
                return None
            return self._subscription_to_domain(model)

    async def update_subscription(
        self,
        subscription: Subscription,
        *,
        expected_status: SubscriptionStatus,
    ) -> None:
        """Apply one lifecycle transition to the locked current subscription row."""

        try:
            async with self._database.session(
                organization_id=subscription.organization_id,
            ) as session:
                model = await session.scalar(
                    select(SubscriptionModel)
                    .where(
                        SubscriptionModel.organization_id
                        == subscription.organization_id,
                        SubscriptionModel.id == subscription.id,
                    )
                    .with_for_update()
                )
                if model is None:
                    raise EntitlementNotFoundError("Subscription was not found")
                # Re-check the locked status so a transition computed from a
                # stale read cannot overwrite a concurrent lifecycle change.
                if model.status != expected_status.value:
                    raise EntitlementConflictError(
                        "Subscription changed during the transition"
                    )
                model.plan_id = subscription.plan_id
                model.status = subscription.status.value
                model.starts_at = subscription.starts_at
                model.ends_at = subscription.ends_at
        except IntegrityError as exc:
            raise EntitlementConflictError("Subscription plan is invalid") from exc

    async def set_override(
        self,
        override: EntitlementOverride,
    ) -> None:
        """Create or replace one organization-feature override atomically."""

        try:
            async with self._database.session(
                organization_id=override.organization_id,
            ) as session:
                model = await session.scalar(
                    select(EntitlementOverrideModel)
                    .where(
                        EntitlementOverrideModel.organization_id
                        == override.organization_id,
                        EntitlementOverrideModel.feature_code == override.feature.value,
                    )
                    .with_for_update()
                )
                if model is None:
                    model = EntitlementOverrideModel(
                        id=override.id,
                        organization_id=override.organization_id,
                        feature_code=override.feature.value,
                    )
                    session.add(model)
                else:
                    model.id = override.id
                model.enabled = override.enabled
                model.usage_amount = (
                    override.usage_limit.amount
                    if override.usage_limit is not None
                    else None
                )
                model.usage_period = (
                    override.usage_limit.period.value
                    if override.usage_limit is not None
                    else None
                )
                model.expires_at = override.expires_at
        except IntegrityError as exc:
            raise EntitlementConflictError("Entitlement feature is invalid") from exc

    async def get_snapshot(
        self,
        *,
        organization_id: UUID,
    ) -> EntitlementSnapshot:
        """Read subscription and overrides under one PostgreSQL tenant context."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            subscription_model = await session.scalar(
                select(SubscriptionModel).where(
                    SubscriptionModel.organization_id == organization_id,
                )
            )
            subscription = (
                self._subscription_to_domain(subscription_model)
                if subscription_model is not None
                else None
            )
            plan = None
            if subscription is not None:
                plan_model = await session.get(PlanModel, subscription.plan_id)
                if plan_model is not None:
                    grant_models = await session.scalars(
                        select(PlanFeatureModel).where(
                            PlanFeatureModel.plan_id == plan_model.id,
                        )
                    )
                    plan = Plan(
                        id=plan_model.id,
                        code=plan_model.code,
                        display_name=plan_model.display_name,
                        grants=tuple(
                            self._grant_to_domain(model) for model in grant_models
                        ),
                        active=plan_model.active,
                    )
            override_models = await session.scalars(
                select(EntitlementOverrideModel).where(
                    EntitlementOverrideModel.organization_id == organization_id,
                )
            )
            return EntitlementSnapshot(
                plan=plan,
                subscription=subscription,
                overrides=tuple(
                    self._override_to_domain(model) for model in override_models
                ),
            )

    @staticmethod
    def _grant_to_model(
        *,
        plan_id: UUID,
        grant: PlanGrant,
    ) -> PlanFeatureModel:
        """Translate one validated plan grant into persistence state."""

        return PlanFeatureModel(
            plan_id=plan_id,
            feature_code=grant.feature.value,
            usage_amount=(
                grant.usage_limit.amount if grant.usage_limit is not None else None
            ),
            usage_period=(
                grant.usage_limit.period.value
                if grant.usage_limit is not None
                else None
            ),
        )

    @staticmethod
    def _grant_to_domain(model: PlanFeatureModel) -> PlanGrant:
        """Translate one persisted grant into a plan domain value."""

        usage_limit = None
        if model.usage_amount is not None and model.usage_period is not None:
            usage_limit = UsageLimit(
                amount=model.usage_amount,
                period=UsagePeriod(model.usage_period),
            )
        return PlanGrant(
            feature=FeatureCode(model.feature_code),
            usage_limit=usage_limit,
        )

    @staticmethod
    def _subscription_to_domain(model: SubscriptionModel) -> Subscription:
        """Translate one persisted tenant subscription into domain state."""

        return Subscription(
            id=model.id,
            organization_id=model.organization_id,
            plan_id=model.plan_id,
            status=SubscriptionStatus(model.status),
            starts_at=model.starts_at,
            ends_at=model.ends_at,
        )

    @staticmethod
    def _override_to_domain(
        model: EntitlementOverrideModel,
    ) -> EntitlementOverride:
        """Translate one persisted tenant override into domain state."""

        usage_limit = None
        if model.usage_amount is not None and model.usage_period is not None:
            usage_limit = UsageLimit(
                amount=model.usage_amount,
                period=UsagePeriod(model.usage_period),
            )
        return EntitlementOverride(
            id=model.id,
            organization_id=model.organization_id,
            feature=FeatureCode(model.feature_code),
            enabled=model.enabled,
            usage_limit=usage_limit,
            expires_at=model.expires_at,
        )


__all__ = ["SQLAlchemyEntitlementRepository"]
