"""Thin FastAPI routes for organization governance and campus operations."""

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
from identity import ActorDep
from identity import CSRFDep
from organizations.application.service import OrganizationService
from organizations.domain.models import Campus
from organizations.domain.models import CustomDomainMetadata
from organizations.domain.models import DomainVerificationStatus
from organizations.domain.models import EducationMode
from organizations.domain.models import LogoMetadata
from organizations.domain.models import Organization
from organizations.domain.models import OrganizationBranding
from organizations.domain.models import OrganizationConfiguration
from organizations.domain.models import OrganizationType

router = APIRouter(prefix="/api/v1", tags=["organizations"])


class LogoMetadataRequest(BaseModel):
    """Validate logo metadata before domain construction."""

    file_name: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=100)
    size_bytes: int = Field(gt=0, le=5_000_000)
    object_key: str = Field(min_length=1, max_length=1024)


class BrandingRequest(BaseModel):
    """Validate organization branding input shape."""

    display_name: str = Field(min_length=1, max_length=200)
    primary_color: str = Field(default="#1D4ED8", max_length=7)
    secondary_color: str = Field(default="#0F172A", max_length=7)
    logo: LogoMetadataRequest | None = None


class CustomDomainRequest(BaseModel):
    """Validate a custom domain that must begin in pending state."""

    domain: str = Field(min_length=1, max_length=253)
    verification_status: Literal[DomainVerificationStatus.PENDING] = (
        DomainVerificationStatus.PENDING
    )


class ConfigurationRequest(BaseModel):
    """Validate non-secret organization configuration input shape."""

    locale: str = Field(default="en", max_length=16)
    timezone: str = Field(default="UTC", max_length=64)
    education_mode: EducationMode = EducationMode.FIXED
    custom_domain: CustomDomainRequest | None = None
    ownid_tenant_reference: str | None = Field(default=None, max_length=255)
    ownid_client_reference: str | None = Field(default=None, max_length=255)


class CreateOrganizationRequest(BaseModel):
    """Validate platform organization creation input."""

    slug: str = Field(min_length=1, max_length=80)
    organization_type: OrganizationType
    branding: BrandingRequest
    configuration: ConfigurationRequest


class ConfigureOrganizationRequest(BaseModel):
    """Validate a complete tenant configuration replacement."""

    branding: BrandingRequest
    configuration: ConfigurationRequest


class CreateCampusRequest(BaseModel):
    """Validate tenant-local campus input."""

    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=200)


def _service(request: Request) -> OrganizationService:
    """Return the explicitly composed organization service."""

    return cast(OrganizationService, request.app.state.organization_service)


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
    """Require a verified tenant membership context."""

    if not isinstance(actor, TenantActorContext):
        raise AuthorizationError
    return actor


def _branding(payload: BrandingRequest) -> OrganizationBranding:
    """Translate transport branding into validated domain values."""

    logo = payload.logo
    return OrganizationBranding(
        display_name=payload.display_name,
        primary_color=payload.primary_color,
        secondary_color=payload.secondary_color,
        logo=(
            LogoMetadata(
                file_name=logo.file_name,
                content_type=logo.content_type,
                size_bytes=logo.size_bytes,
                object_key=logo.object_key,
            )
            if logo is not None
            else None
        ),
    )


def _configuration(payload: ConfigurationRequest) -> OrganizationConfiguration:
    """Translate transport configuration into validated domain values."""

    custom_domain = payload.custom_domain
    return OrganizationConfiguration(
        locale=payload.locale,
        timezone=payload.timezone,
        education_mode=payload.education_mode,
        custom_domain=(
            CustomDomainMetadata(
                domain=custom_domain.domain,
                verification_status=custom_domain.verification_status,
            )
            if custom_domain is not None
            else None
        ),
        ownid_tenant_reference=payload.ownid_tenant_reference,
        ownid_client_reference=payload.ownid_client_reference,
    )


def serialize_organization_safe(organization: Organization) -> dict[str, object]:
    """Serialize organization state without internal logo object references."""

    logo = organization.branding.logo
    custom_domain = organization.configuration.custom_domain
    return {
        "id": str(organization.id),
        "slug": organization.slug,
        "organization_type": organization.organization_type.value,
        "status": organization.status.value,
        "branding": {
            "display_name": organization.branding.display_name,
            "primary_color": organization.branding.primary_color,
            "secondary_color": organization.branding.secondary_color,
            "logo": (
                {
                    "file_name": logo.file_name,
                    "content_type": logo.content_type,
                    "size_bytes": logo.size_bytes,
                }
                if logo is not None
                else None
            ),
        },
        "configuration": {
            "locale": organization.configuration.locale,
            "timezone": organization.configuration.timezone,
            "education_mode": organization.configuration.education_mode.value,
            "custom_domain": (
                {
                    "domain": custom_domain.domain,
                    "verification_status": custom_domain.verification_status.value,
                }
                if custom_domain is not None
                else None
            ),
            "ownid_tenant_reference": (
                organization.configuration.ownid_tenant_reference
            ),
            "ownid_client_reference": (
                organization.configuration.ownid_client_reference
            ),
        },
    }


def serialize_campus_safe(campus: Campus) -> dict[str, object]:
    """Serialize public campus fields with explicit tenant identity."""

    return {
        "id": str(campus.id),
        "organization_id": str(campus.organization_id),
        "code": campus.code,
        "name": campus.name,
        "active": campus.active,
    }


@router.get("/platform/organizations")
async def list_organizations(
    request: Request,
    actor: ActorDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    """List bounded organization governance metadata for platform operators."""

    organizations = await _service(request).list_organizations(
        actor=_platform_actor(actor),
        limit=limit,
        offset=offset,
    )
    return JSONResponse(
        [serialize_organization_safe(organization) for organization in organizations]
    )


@router.post("/platform/organizations", status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: CreateOrganizationRequest,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> JSONResponse:
    """Create one organization through an explicit platform capability."""

    organization = await _service(request).create_organization(
        actor=_platform_actor(actor),
        slug=payload.slug,
        organization_type=payload.organization_type,
        branding=_branding(payload.branding),
        configuration=_configuration(payload.configuration),
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=serialize_organization_safe(organization),
    )


@router.post("/platform/organizations/{organization_id}/suspend")
async def suspend_organization(
    organization_id: UUID,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> JSONResponse:
    """Suspend organization operations without entering tenant data context."""

    organization = await _service(request).suspend_organization(
        actor=_platform_actor(actor),
        organization_id=organization_id,
    )
    return JSONResponse(serialize_organization_safe(organization))


@router.post("/platform/organizations/{organization_id}/reactivate")
async def reactivate_organization(
    organization_id: UUID,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> JSONResponse:
    """Reactivate one suspended organization through platform governance."""

    organization = await _service(request).reactivate_organization(
        actor=_platform_actor(actor),
        organization_id=organization_id,
    )
    return JSONResponse(serialize_organization_safe(organization))


@router.get("/organization")
async def get_organization(
    request: Request,
    actor: ActorDep,
) -> JSONResponse:
    """Return the actor's current organization configuration."""

    organization = await _service(request).get_organization(
        actor=_tenant_actor(actor),
    )
    return JSONResponse(serialize_organization_safe(organization))


@router.put("/organization")
async def configure_organization(
    payload: ConfigureOrganizationRequest,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> JSONResponse:
    """Replace validated non-secret configuration for the current tenant."""

    organization = await _service(request).configure_organization(
        actor=_tenant_actor(actor),
        branding=_branding(payload.branding),
        configuration=_configuration(payload.configuration),
    )
    return JSONResponse(serialize_organization_safe(organization))


@router.post("/campuses", status_code=status.HTTP_201_CREATED)
async def create_campus(
    payload: CreateCampusRequest,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> JSONResponse:
    """Create one campus within the actor's current organization."""

    campus = await _service(request).create_campus(
        actor=_tenant_actor(actor),
        code=payload.code,
        name=payload.name,
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=serialize_campus_safe(campus),
    )


@router.get("/campuses")
async def list_campuses(
    request: Request,
    actor: ActorDep,
) -> JSONResponse:
    """List campuses only for the actor's current organization."""

    campuses = await _service(request).list_campuses(actor=_tenant_actor(actor))
    return JSONResponse([serialize_campus_safe(campus) for campus in campuses])


__all__ = [
    "router",
    "serialize_campus_safe",
    "serialize_organization_safe",
]
