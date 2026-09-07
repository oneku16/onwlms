"""Thin FastAPI routes for centralized plan and feature entitlement policy."""

from datetime import datetime
from typing import Annotated
from typing import Literal
from typing import cast
from uuid import UUID

from fastapi import APIRouter
from fastapi import Query
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic import Field

from core.context import PlatformActorContext
from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.time import utc_now
from entitlements.application.service import EntitlementService
from entitlements.domain.models import EntitlementOverride
from entitlements.domain.models import Feature
from entitlements.domain.models import FeatureCode
from entitlements.domain.models import Plan
from entitlements.domain.models import PlanGrant
from entitlements.domain.models import ResolvedEntitlement
from entitlements.domain.models import Subscription
from entitlements.domain.models import SubscriptionStatus
from entitlements.domain.models import UsageLimit
from entitlements.domain.models import UsagePeriod
from identity import ActorDep
from identity import CSRFDep

router = APIRouter(prefix="/api/v1", tags=["entitlements"])


class CreateFeatureRequest(BaseModel):
    """Validate registration of one known first-release feature."""

    code: FeatureCode
    display_name: str = Field(min_length=1, max_length=120)


class UsageLimitRequest(BaseModel):
    """Validate a positive usage allowance and reset period."""

    amount: int = Field(gt=0)
    period: UsagePeriod


class PlanGrantRequest(BaseModel):
    """Validate one feature grant inside a plan request."""

    feature: FeatureCode
    usage_limit: UsageLimitRequest | None = None


class CreatePlanRequest(BaseModel):
    """Validate creation of one global plan and its feature bundle."""

    code: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=120)
    grants: list[PlanGrantRequest] = Field(default_factory=list, max_length=50)


class AssignSubscriptionRequest(BaseModel):
    """Validate one organization's current subscription assignment."""

    plan_id: UUID
    status: Literal[
        SubscriptionStatus.TRIALING,
        SubscriptionStatus.ACTIVE,
    ]
    starts_at: datetime
    ends_at: datetime | None = None


class SetOverrideRequest(BaseModel):
    """Validate one platform-managed tenant feature override."""

    feature: FeatureCode
    enabled: bool
    usage_limit: UsageLimitRequest | None = None
    expires_at: datetime | None = None


class UsageLimitResponse(BaseModel):
    """Expose one bounded usage allowance."""

    amount: int
    period: UsagePeriod


class FeatureResponse(BaseModel):
    """Expose one supported platform feature definition."""

    id: UUID
    code: FeatureCode
    display_name: str
    base_included: bool


class PlanGrantResponse(BaseModel):
    """Expose one feature grant within a plan."""

    feature: FeatureCode
    usage_limit: UsageLimitResponse | None


class PlanResponse(BaseModel):
    """Expose one platform plan and its explicit grants."""

    id: UUID
    code: str
    display_name: str
    active: bool
    grants: list[PlanGrantResponse]


def _service(request: Request) -> EntitlementService:
    """Return the explicitly composed centralized entitlement service."""

    return cast(EntitlementService, request.app.state.entitlement_service)


def _platform_actor(
    actor: PlatformActorContext | TenantActorContext,
) -> PlatformActorContext:
    """Require separately established platform actor context."""

    if not isinstance(actor, PlatformActorContext):
        raise AuthorizationError
    return actor


def _tenant_actor(
    actor: PlatformActorContext | TenantActorContext,
) -> TenantActorContext:
    """Require one verified active tenant membership context."""

    if not isinstance(actor, TenantActorContext):
        raise AuthorizationError
    return actor


def _usage_limit(payload: UsageLimitRequest | None) -> UsageLimit | None:
    """Translate optional transport usage input into a domain value."""

    if payload is None:
        return None
    return UsageLimit(amount=payload.amount, period=payload.period)


def serialize_feature(feature: Feature) -> dict[str, object]:
    """Serialize safe global feature metadata."""

    return {
        "id": str(feature.id),
        "code": feature.code.value,
        "display_name": feature.display_name,
        "base_included": feature.base_included,
    }


def serialize_plan(plan: Plan) -> dict[str, object]:
    """Serialize a plan and explicit grants without customer information."""

    return {
        "id": str(plan.id),
        "code": plan.code,
        "display_name": plan.display_name,
        "active": plan.active,
        "grants": [
            {
                "feature": grant.feature.value,
                "usage_limit": (
                    {
                        "amount": grant.usage_limit.amount,
                        "period": grant.usage_limit.period.value,
                    }
                    if grant.usage_limit is not None
                    else None
                ),
            }
            for grant in plan.grants
        ],
    }


def serialize_subscription(subscription: Subscription) -> dict[str, object]:
    """Serialize tenant subscription state without payment or provider details."""

    return {
        "id": str(subscription.id),
        "organization_id": str(subscription.organization_id),
        "plan_id": str(subscription.plan_id),
        "status": subscription.status.value,
        "starts_at": subscription.starts_at.isoformat(),
        "ends_at": (
            subscription.ends_at.isoformat()
            if subscription.ends_at is not None
            else None
        ),
    }


def serialize_override(override: EntitlementOverride) -> dict[str, object]:
    """Serialize a tenant feature override without commercial metadata."""

    return {
        "id": str(override.id),
        "organization_id": str(override.organization_id),
        "feature": override.feature.value,
        "enabled": override.enabled,
        "usage_limit": (
            {
                "amount": override.usage_limit.amount,
                "period": override.usage_limit.period.value,
            }
            if override.usage_limit is not None
            else None
        ),
        "expires_at": (
            override.expires_at.isoformat() if override.expires_at is not None else None
        ),
    }


def serialize_resolution(resolution: ResolvedEntitlement) -> dict[str, object]:
    """Serialize one centralized feature decision and optional usage limit."""

    return {
        "feature": resolution.feature.value,
        "enabled": resolution.enabled,
        "source": resolution.source,
        "usage_limit": (
            {
                "amount": resolution.usage_limit.amount,
                "period": resolution.usage_limit.period.value,
            }
            if resolution.usage_limit is not None
            else None
        ),
    }


@router.post(
    "/platform/features",
    status_code=status.HTTP_201_CREATED,
    response_model=FeatureResponse,
)
async def create_feature(
    payload: CreateFeatureRequest,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> JSONResponse:
    """Register one feature through explicit platform administration."""

    feature = await _service(request).create_feature(
        actor=_platform_actor(actor),
        code=payload.code,
        display_name=payload.display_name,
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=serialize_feature(feature),
    )


@router.get("/platform/features", response_model=list[FeatureResponse])
async def list_features(
    request: Request,
    actor: ActorDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    """List bounded global feature metadata through platform authority."""

    features = await _service(request).list_features(
        actor=_platform_actor(actor),
        limit=limit,
        offset=offset,
    )
    return JSONResponse([serialize_feature(feature) for feature in features])


@router.post(
    "/platform/plans",
    status_code=status.HTTP_201_CREATED,
    response_model=PlanResponse,
)
async def create_plan(
    payload: CreatePlanRequest,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> JSONResponse:
    """Create one global plan through explicit platform administration."""

    plan = await _service(request).create_plan(
        actor=_platform_actor(actor),
        code=payload.code,
        display_name=payload.display_name,
        grants=tuple(
            PlanGrant(
                feature=grant.feature,
                usage_limit=_usage_limit(grant.usage_limit),
            )
            for grant in payload.grants
        ),
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=serialize_plan(plan),
    )


@router.get("/platform/plans", response_model=list[PlanResponse])
async def list_plans(
    request: Request,
    actor: ActorDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    """List bounded global plans and their explicit feature grants."""

    plans = await _service(request).list_plans(
        actor=_platform_actor(actor),
        limit=limit,
        offset=offset,
    )
    return JSONResponse([serialize_plan(plan) for plan in plans])


@router.put("/platform/organizations/{organization_id}/subscription")
async def assign_subscription(
    organization_id: UUID,
    payload: AssignSubscriptionRequest,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> JSONResponse:
    """Assign the current plan for one organization through platform policy."""

    subscription = await _service(request).assign_subscription(
        actor=_platform_actor(actor),
        organization_id=organization_id,
        plan_id=payload.plan_id,
        status=payload.status,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )
    return JSONResponse(serialize_subscription(subscription))


@router.put("/platform/organizations/{organization_id}/entitlements")
async def set_override(
    organization_id: UUID,
    payload: SetOverrideRequest,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> JSONResponse:
    """Set one feature override through explicit platform policy."""

    override = await _service(request).set_override(
        actor=_platform_actor(actor),
        organization_id=organization_id,
        feature=payload.feature,
        enabled=payload.enabled,
        usage_limit=_usage_limit(payload.usage_limit),
        expires_at=payload.expires_at,
    )
    return JSONResponse(serialize_override(override))


@router.get("/entitlements/{feature}")
async def resolve_entitlement(
    feature: FeatureCode,
    request: Request,
    actor: ActorDep,
) -> JSONResponse:
    """Resolve one feature for the actor's verified tenant context."""

    resolution = await _service(request).resolve(
        actor=_tenant_actor(actor),
        feature=feature,
        at=utc_now(),
    )
    return JSONResponse(serialize_resolution(resolution))


__all__ = [
    "router",
    "serialize_feature",
    "serialize_override",
    "serialize_plan",
    "serialize_resolution",
    "serialize_subscription",
]
