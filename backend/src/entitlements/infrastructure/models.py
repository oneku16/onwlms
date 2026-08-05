"""Entitlement-owned SQLAlchemy persistence representations."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import ForeignKeyConstraint
from sqlalchemy import Integer
from sqlalchemy import PrimaryKeyConstraint
from sqlalchemy import String
from sqlalchemy import UniqueConstraint
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from shared.models import BaseModel
from shared.models import TimestampMixin
from shared.models import UUIDPrimaryKeyMixin


class FeatureModel(UUIDPrimaryKeyMixin, TimestampMixin, BaseModel):
    """Persist one globally registered product feature."""

    __tablename__ = "entitlement_features"
    __table_args__ = (UniqueConstraint("code", name="uq_entitlement_features_code"),)

    code: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    base_included: Mapped[bool] = mapped_column(Boolean, nullable=False)


class PlanModel(UUIDPrimaryKeyMixin, TimestampMixin, BaseModel):
    """Persist one global subscription plan."""

    __tablename__ = "entitlement_plans"
    __table_args__ = (UniqueConstraint("code", name="uq_entitlement_plans_code"),)

    code: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PlanFeatureModel(BaseModel):
    """Persist one optional feature grant and usage limit within a plan."""

    __tablename__ = "entitlement_plan_features"
    __table_args__ = (
        PrimaryKeyConstraint(
            "plan_id",
            "feature_code",
            name="pk_entitlement_plan_features",
        ),
        ForeignKeyConstraint(
            ["feature_code"],
            ["entitlement_features.code"],
            name="fk_entitlement_plan_features_feature_code_features",
            ondelete="RESTRICT",
        ),
    )

    plan_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "entitlement_plans.id",
            name="fk_entitlement_plan_features_plan_id_plans",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    feature_code: Mapped[str] = mapped_column(String(80), nullable=False)
    usage_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage_period: Mapped[str | None] = mapped_column(String(32), nullable=True)


class SubscriptionModel(UUIDPrimaryKeyMixin, TimestampMixin, BaseModel):
    """Persist one organization's current subscription assignment."""

    __tablename__ = "organization_subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            name="uq_organization_subscriptions_organization_id",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "organizations.id",
            name="fk_organization_subscriptions_organization_id_organizations",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    plan_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "entitlement_plans.id",
            name="fk_organization_subscriptions_plan_id_plans",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class EntitlementOverrideModel(UUIDPrimaryKeyMixin, TimestampMixin, BaseModel):
    """Persist a tenant feature override managed only through platform policy."""

    __tablename__ = "organization_entitlement_overrides"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "feature_code",
            name="uq_organization_entitlement_overrides_organization_feature",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "organizations.id",
            name="fk_org_entitlement_overrides_organization",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    feature_code: Mapped[str] = mapped_column(
        String(80),
        ForeignKey(
            "entitlement_features.code",
            name="fk_organization_entitlement_overrides_feature_code_features",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    usage_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage_period: Mapped[str | None] = mapped_column(String(32), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


__all__ = [
    "EntitlementOverrideModel",
    "FeatureModel",
    "PlanFeatureModel",
    "PlanModel",
    "SubscriptionModel",
]
