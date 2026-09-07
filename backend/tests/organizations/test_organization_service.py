"""Domain and application tests for organization governance and tenant isolation."""

from typing import cast
from uuid import UUID
from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError

from core.context import PlatformActorContext
from core.context import TenantActorContext
from core.errors import AuthorizationError
from organizations.application.service import CREATE_ORGANIZATION_PERMISSION
from organizations.application.service import LIFECYCLE_PERMISSION
from organizations.application.service import MANAGE_CAMPUSES_PERMISSION
from organizations.application.service import READ_ORGANIZATION_PERMISSION
from organizations.application.service import OrganizationService
from organizations.domain.exceptions import OrganizationLifecycleError
from organizations.domain.exceptions import OrganizationNotFoundError
from organizations.domain.models import Campus
from organizations.domain.models import EducationMode
from organizations.domain.models import LogoMetadata
from organizations.domain.models import Organization
from organizations.domain.models import OrganizationBranding
from organizations.domain.models import OrganizationConfiguration
from organizations.domain.models import OrganizationStatus
from organizations.domain.models import OrganizationType
from organizations.presentation.router import CustomDomainRequest
from organizations.presentation.router import serialize_organization_safe


class FakeOrganizationRepository:
    def __init__(self) -> None:
        self.values: dict[UUID, Organization] = {}

    async def add(self, organization: Organization) -> None:
        self.values[organization.id] = organization

    async def get_platform(
        self,
        *,
        organization_id: UUID,
    ) -> Organization | None:
        return self.values.get(organization_id)

    async def list_platform(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[Organization]:
        values = sorted(self.values.values(), key=lambda item: item.slug)
        return values[offset : offset + limit]

    async def get_tenant(
        self,
        *,
        organization_id: UUID,
    ) -> Organization | None:
        return self.values.get(organization_id)

    async def save_platform(self, organization: Organization) -> None:
        self.values[organization.id] = organization

    async def save_tenant(self, organization: Organization) -> None:
        self.values[organization.id] = organization


class FakeCampusRepository:
    def __init__(self) -> None:
        self.values: dict[UUID, Campus] = {}

    async def add(self, campus: Campus) -> None:
        self.values[campus.id] = campus

    async def get(
        self,
        *,
        organization_id: UUID,
        campus_id: UUID,
    ) -> Campus | None:
        campus = self.values.get(campus_id)
        if campus is None or campus.organization_id != organization_id:
            return None
        return campus

    async def list_for_organization(
        self,
        *,
        organization_id: UUID,
    ) -> list[Campus]:
        return [
            campus
            for campus in self.values.values()
            if campus.organization_id == organization_id
        ]


class FakeOrganizationAuditSink:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[tuple[str, UUID, str]] = []

    async def record_organization_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        correlation_id: str,
        outcome: str,
    ) -> None:
        assert action and organization_id and actor_subject_id and correlation_id
        if self.fail:
            raise RuntimeError("audit unavailable")
        self.events.append((action, organization_id, outcome))


def _configuration() -> OrganizationConfiguration:
    return OrganizationConfiguration(
        locale="en",
        timezone="UTC",
        education_mode=EducationMode.HYBRID,
    )


def _branding() -> OrganizationBranding:
    return OrganizationBranding(display_name="North University")


def _organization(organization_id: UUID) -> Organization:
    return Organization(
        id=organization_id,
        slug=f"org-{str(organization_id)[:8]}",
        organization_type=OrganizationType.UNIVERSITY,
        status=OrganizationStatus.ACTIVE,
        branding=_branding(),
        configuration=_configuration(),
    )


def _service(
    audit: FakeOrganizationAuditSink | None = None,
) -> tuple[
    OrganizationService,
    FakeOrganizationRepository,
    FakeCampusRepository,
]:
    organizations = FakeOrganizationRepository()
    campuses = FakeCampusRepository()
    return (
        OrganizationService(
            organizations=organizations,
            campuses=campuses,
            audit=audit or FakeOrganizationAuditSink(),
        ),
        organizations,
        campuses,
    )


def _platform_actor(*permissions: str) -> PlatformActorContext:
    return PlatformActorContext(
        subject_id=uuid4(),
        correlation_id="correlation-1",
        permissions=frozenset(permissions),
    )


def _tenant_actor(
    organization_id: UUID,
    *permissions: str,
) -> TenantActorContext:
    return TenantActorContext(
        subject_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        correlation_id="correlation-1",
        permissions=frozenset(permissions),
    )


async def test_platform_creation_and_lifecycle_are_separately_authorized() -> None:
    service, _, _ = _service()
    actor = _platform_actor(
        CREATE_ORGANIZATION_PERMISSION,
        LIFECYCLE_PERMISSION,
    )
    organization = await service.create_organization(
        actor=actor,
        slug="north-university",
        organization_type=OrganizationType.UNIVERSITY,
        branding=_branding(),
        configuration=_configuration(),
    )

    suspended = await service.suspend_organization(
        actor=actor,
        organization_id=organization.id,
    )
    assert suspended.status is OrganizationStatus.SUSPENDED
    with pytest.raises(OrganizationLifecycleError):
        await service.suspend_organization(
            actor=actor,
            organization_id=organization.id,
        )


async def test_organization_mutation_aborts_when_audit_intent_fails() -> None:
    service, organizations, _ = _service(FakeOrganizationAuditSink(fail=True))

    with pytest.raises(RuntimeError, match="audit unavailable"):
        await service.create_organization(
            actor=_platform_actor(CREATE_ORGANIZATION_PERMISSION),
            slug="audit-protected",
            organization_type=OrganizationType.UNIVERSITY,
            branding=_branding(),
            configuration=_configuration(),
        )

    assert organizations.values == {}


async def test_platform_organization_list_is_bounded_and_authorized() -> None:
    service, organizations, _ = _service()
    first = _organization(uuid4())
    second = _organization(uuid4())
    organizations.values[first.id] = first
    organizations.values[second.id] = second

    listed = await service.list_organizations(
        actor=_platform_actor(LIFECYCLE_PERMISSION),
        limit=1,
        offset=0,
    )
    assert len(listed) == 1

    with pytest.raises(AuthorizationError):
        await service.list_organizations(
            actor=_platform_actor(),
            limit=50,
            offset=0,
        )


async def test_tenant_context_cannot_invoke_platform_capability() -> None:
    service, _, _ = _service()
    tenant = _tenant_actor(uuid4(), CREATE_ORGANIZATION_PERMISSION)

    with pytest.raises(AuthorizationError):
        await service.create_organization(
            actor=cast(PlatformActorContext, tenant),
            slug="forbidden",
            organization_type=OrganizationType.SCHOOL,
            branding=_branding(),
            configuration=_configuration(),
        )


async def test_campus_lookup_denies_cross_tenant_identifier() -> None:
    service, organizations, campuses = _service()
    organization_a = uuid4()
    organization_b = uuid4()
    organizations.values[organization_a] = _organization(organization_a)
    organizations.values[organization_b] = _organization(organization_b)
    campus_b = Campus(
        id=uuid4(),
        organization_id=organization_b,
        code="MAIN",
        name="Main Campus",
    )
    campuses.values[campus_b.id] = campus_b
    actor_a = _tenant_actor(
        organization_a,
        READ_ORGANIZATION_PERMISSION,
        MANAGE_CAMPUSES_PERMISSION,
    )

    with pytest.raises(OrganizationNotFoundError):
        await service.get_active_campus(actor=actor_a, campus_id=campus_b.id)


async def test_internal_campus_contract_requires_active_matching_tenant() -> None:
    service, organizations, campuses = _service()
    organization_id = uuid4()
    organization = _organization(organization_id)
    organizations.values[organization_id] = organization
    campus = Campus(
        id=uuid4(),
        organization_id=organization_id,
        code="MAIN",
        name="Main Campus",
    )
    campuses.values[campus.id] = campus

    assert await service.campus_exists(
        organization_id=organization_id,
        campus_id=campus.id,
    )
    organizations.values[organization_id] = organization.suspend()
    assert not await service.campus_exists(
        organization_id=organization_id,
        campus_id=campus.id,
    )
    assert not await service.campus_exists(
        organization_id=uuid4(),
        campus_id=campus.id,
    )


def test_safe_organization_serializer_excludes_logo_object_key() -> None:
    organization = _organization(uuid4())
    organization = organization.configure(
        branding=OrganizationBranding(
            display_name="North University",
            logo=LogoMetadata(
                file_name="logo.png",
                content_type="image/png",
                size_bytes=128,
                object_key="private/tenant/logo.png",
            ),
        ),
        configuration=_configuration(),
    )

    payload = serialize_organization_safe(organization)
    assert "object_key" not in str(payload)
    assert "private/tenant" not in str(payload)


def test_custom_domain_verification_cannot_be_self_asserted() -> None:
    with pytest.raises(PydanticValidationError):
        CustomDomainRequest.model_validate(
            {
                "domain": "portal.example.edu",
                "verification_status": "verified",
            }
        )
