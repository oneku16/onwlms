"""Plans, features, subscriptions, overrides, and resolved entitlement values."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from entitlements.domain.exceptions import InvalidEntitlementError


class FeatureCode(StrEnum):
    """Stable first-release product capabilities resolved centrally."""

    ACADEMIC = "academic"
    MOODLE_INTEGRATION = "moodle_integration"
    OWNID_SSO = "ownid_sso"
    MCP = "mcp"
    HR = "hr"
    FINANCE = "finance"
    LIBRARY = "library"
    DORMITORY = "dormitory"
    ADVANCED_ANALYTICS = "advanced_analytics"
    MULTIPLE_ADMINISTRATORS = "multiple_administrators"
    CUSTOM_ROLES = "custom_roles"
    TIMETABLE_GENERATION = "timetable_generation"
    WHITE_LABEL = "white_label"


BASE_FEATURES = frozenset(
    {
        FeatureCode.ACADEMIC,
        FeatureCode.MOODLE_INTEGRATION,
        FeatureCode.OWNID_SSO,
    }
)


class SubscriptionStatus(StrEnum):
    """Govern whether plan grants participate in feature resolution."""

    TRIALING = "trialing"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CANCELED = "canceled"


class UsagePeriod(StrEnum):
    """Describe the reset period for an optional usage limit."""

    MONTH = "month"
    ACADEMIC_TERM = "academic_term"
    ABSOLUTE = "absolute"


@dataclass(frozen=True, slots=True)
class UsageLimit:
    """Define a positive usage allowance and its reset period."""

    amount: int
    period: UsagePeriod

    def __post_init__(self) -> None:
        """Reject non-positive usage allowances."""

        if self.amount <= 0:
            raise InvalidEntitlementError("Usage limit must be positive")


@dataclass(frozen=True, slots=True)
class Feature:
    """Describe one centrally registered product feature."""

    id: UUID
    code: FeatureCode
    display_name: str
    base_included: bool

    def __post_init__(self) -> None:
        """Validate feature presentation metadata and base-product consistency."""

        if not self.display_name.strip() or len(self.display_name) > 120:
            raise InvalidEntitlementError("Invalid feature display name")
        if self.base_included != (self.code in BASE_FEATURES):
            raise InvalidEntitlementError("Base feature metadata is inconsistent")


@dataclass(frozen=True, slots=True)
class PlanGrant:
    """Grant one feature and optional usage limit within a plan."""

    feature: FeatureCode
    usage_limit: UsageLimit | None = None


@dataclass(frozen=True, slots=True)
class Plan:
    """Represent one platform-global commercial feature bundle."""

    id: UUID
    code: str
    display_name: str
    grants: tuple[PlanGrant, ...]
    active: bool = True

    def __post_init__(self) -> None:
        """Validate stable plan code and prohibit duplicate feature grants."""

        normalized_code = self.code.replace("-", "")
        if not self.code or len(self.code) > 80 or not normalized_code.isalnum():
            raise InvalidEntitlementError("Invalid plan code")
        if not self.display_name.strip() or len(self.display_name) > 120:
            raise InvalidEntitlementError("Invalid plan display name")
        features = {grant.feature for grant in self.grants}
        if len(features) != len(self.grants):
            raise InvalidEntitlementError("Plan contains duplicate feature grants")


@dataclass(frozen=True, slots=True)
class Subscription:
    """Assign one platform plan to exactly one organization lifecycle."""

    id: UUID
    organization_id: UUID
    plan_id: UUID
    status: SubscriptionStatus
    starts_at: datetime
    ends_at: datetime | None = None

    def __post_init__(self) -> None:
        """Validate timezone awareness and chronological subscription bounds."""

        if self.starts_at.tzinfo is None:
            raise InvalidEntitlementError("Subscription start must be timezone-aware")
        if self.ends_at is not None:
            if self.ends_at.tzinfo is None or self.ends_at <= self.starts_at:
                raise InvalidEntitlementError("Invalid subscription end")

    def is_effective(
        self,
        *,
        at: datetime,
    ) -> bool:
        """Return whether plan grants apply at one explicit time."""

        return (
            self.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING}
            and self.starts_at <= at
            and (self.ends_at is None or at < self.ends_at)
        )


@dataclass(frozen=True, slots=True)
class EntitlementOverride:
    """Override one organization's feature resolution through platform policy."""

    id: UUID
    organization_id: UUID
    feature: FeatureCode
    enabled: bool
    usage_limit: UsageLimit | None = None
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        """Require coherent disabled state and timezone-aware expiration."""

        if not self.enabled and self.usage_limit is not None:
            raise InvalidEntitlementError(
                "Disabled entitlement overrides cannot carry usage limits"
            )
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise InvalidEntitlementError("Override expiration must be timezone-aware")

    def is_effective(
        self,
        *,
        at: datetime,
    ) -> bool:
        """Return whether this override applies at one explicit time."""

        return self.expires_at is None or at < self.expires_at


@dataclass(frozen=True, slots=True)
class EntitlementSnapshot:
    """Contain the plan, subscription, and overrides needed for central resolution."""

    plan: Plan | None
    subscription: Subscription | None
    overrides: tuple[EntitlementOverride, ...]


@dataclass(frozen=True, slots=True)
class ResolvedEntitlement:
    """Explain a centralized feature decision without exposing commercial internals."""

    feature: FeatureCode
    enabled: bool
    source: str
    usage_limit: UsageLimit | None = None


__all__ = [
    "BASE_FEATURES",
    "EntitlementOverride",
    "EntitlementSnapshot",
    "Feature",
    "FeatureCode",
    "Plan",
    "PlanGrant",
    "ResolvedEntitlement",
    "Subscription",
    "SubscriptionStatus",
    "UsageLimit",
    "UsagePeriod",
]
