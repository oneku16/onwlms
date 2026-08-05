"""Permission-aware organization lifecycle and campus application service."""

from uuid import UUID

from core.context import PlatformActorContext
from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.identifiers import new_uuid7
from organizations.application.ports import CampusRepository
from organizations.application.ports import OrganizationAuditSink
from organizations.application.ports import OrganizationRepository
from organizations.domain.exceptions import OrganizationNotFoundError
from organizations.domain.models import Campus
from organizations.domain.models import Organization
from organizations.domain.models import OrganizationBranding
from organizations.domain.models import OrganizationConfiguration
from organizations.domain.models import OrganizationStatus
from organizations.domain.models import OrganizationType

CREATE_ORGANIZATION_PERMISSION = "organizations.platform.create"
LIFECYCLE_PERMISSION = "organizations.platform.lifecycle"
READ_ORGANIZATION_PERMISSION = "organizations.read"
CONFIGURE_ORGANIZATION_PERMISSION = "organizations.configure"
MANAGE_CAMPUSES_PERMISSION = "organizations.campuses.manage"


class OrganizationService:
    """Coordinate organization changes across explicit platform and tenant paths."""

    def __init__(
        self,
        *,
        organizations: OrganizationRepository,
        campuses: CampusRepository,
        audit: OrganizationAuditSink,
    ) -> None:
        self._organizations = organizations
        self._campuses = campuses
        self._audit = audit

    async def create_organization(
        self,
        *,
        actor: PlatformActorContext,
        slug: str,
        organization_type: OrganizationType,
        branding: OrganizationBranding,
        configuration: OrganizationConfiguration,
    ) -> Organization:
        """Create one active tenant through separately authorized platform access."""

        self._require_platform_permission(actor, CREATE_ORGANIZATION_PERMISSION)
        organization = Organization(
            id=new_uuid7(),
            slug=slug,
            organization_type=organization_type,
            status=OrganizationStatus.ACTIVE,
            branding=branding,
            configuration=configuration,
        )
        await self._organizations.add(organization)
        await self._audit.record_organization_event(
            action="organization.created",
            organization_id=organization.id,
            actor_subject_id=actor.subject_id,
            correlation_id=actor.correlation_id,
            outcome="succeeded",
        )
        return organization

    async def list_organizations(
        self,
        *,
        actor: PlatformActorContext,
        limit: int,
        offset: int,
    ) -> list[Organization]:
        """List organization governance metadata without tenant academic access."""

        self._require_platform_permission(actor, LIFECYCLE_PERMISSION)
        return await self._organizations.list_platform(limit=limit, offset=offset)

    async def suspend_organization(
        self,
        *,
        actor: PlatformActorContext,
        organization_id: UUID,
    ) -> Organization:
        """Suspend one tenant without granting access to its institutional data."""

        self._require_platform_permission(actor, LIFECYCLE_PERMISSION)
        organization = await self._get_platform(organization_id=organization_id)
        suspended = organization.suspend()
        await self._organizations.save_platform(suspended)
        await self._audit.record_organization_event(
            action="organization.suspended",
            organization_id=organization_id,
            actor_subject_id=actor.subject_id,
            correlation_id=actor.correlation_id,
            outcome="succeeded",
        )
        return suspended

    async def reactivate_organization(
        self,
        *,
        actor: PlatformActorContext,
        organization_id: UUID,
    ) -> Organization:
        """Reactivate one suspended tenant through the platform path."""

        self._require_platform_permission(actor, LIFECYCLE_PERMISSION)
        organization = await self._get_platform(organization_id=organization_id)
        active = organization.reactivate()
        await self._organizations.save_platform(active)
        await self._audit.record_organization_event(
            action="organization.reactivated",
            organization_id=organization_id,
            actor_subject_id=actor.subject_id,
            correlation_id=actor.correlation_id,
            outcome="succeeded",
        )
        return active

    async def get_organization(
        self,
        *,
        actor: TenantActorContext,
    ) -> Organization:
        """Return tenant configuration only to a matching authorized membership."""

        self._require_tenant_permission(actor, READ_ORGANIZATION_PERMISSION)
        organization = await self._organizations.get_tenant(
            organization_id=actor.organization_id,
        )
        if organization is None:
            raise OrganizationNotFoundError
        return organization

    async def configure_organization(
        self,
        *,
        actor: TenantActorContext,
        branding: OrganizationBranding,
        configuration: OrganizationConfiguration,
    ) -> Organization:
        """Update non-secret organization configuration in its tenant context."""

        self._require_tenant_permission(actor, CONFIGURE_ORGANIZATION_PERMISSION)
        organization = await self.get_organization(actor=actor)
        configured = organization.configure(
            branding=branding,
            configuration=configuration,
        )
        await self._organizations.save_tenant(configured)
        await self._audit.record_organization_event(
            action="organization.configured",
            organization_id=actor.organization_id,
            actor_subject_id=actor.subject_id,
            correlation_id=actor.correlation_id,
            outcome="succeeded",
        )
        return configured

    async def create_campus(
        self,
        *,
        actor: TenantActorContext,
        code: str,
        name: str,
    ) -> Campus:
        """Create one campus bound to the actor's verified organization."""

        self._require_tenant_permission(actor, MANAGE_CAMPUSES_PERMISSION)
        campus = Campus(
            id=new_uuid7(),
            organization_id=actor.organization_id,
            code=code,
            name=name,
        )
        await self._campuses.add(campus)
        await self._audit.record_organization_event(
            action="campus.created",
            organization_id=actor.organization_id,
            actor_subject_id=actor.subject_id,
            correlation_id=actor.correlation_id,
            outcome="succeeded",
        )
        return campus

    async def list_campuses(
        self,
        *,
        actor: TenantActorContext,
    ) -> list[Campus]:
        """List campuses only within the actor's verified organization."""

        self._require_tenant_permission(actor, READ_ORGANIZATION_PERMISSION)
        return await self._campuses.list_for_organization(
            organization_id=actor.organization_id,
        )

    async def get_active_campus(
        self,
        *,
        actor: TenantActorContext,
        campus_id: UUID,
    ) -> Campus:
        """Resolve an active campus through the public tenant-safe directory."""

        self._require_tenant_permission(actor, READ_ORGANIZATION_PERMISSION)
        campus = await self._campuses.get(
            organization_id=actor.organization_id,
            campus_id=campus_id,
        )
        if campus is None or not campus.active:
            raise OrganizationNotFoundError
        return campus

    async def campus_exists(
        self,
        *,
        organization_id: UUID,
        campus_id: UUID,
    ) -> bool:
        """Validate an active campus for a trusted collaborating module."""

        if not await self.is_active(organization_id=organization_id):
            return False
        campus = await self._campuses.get(
            organization_id=organization_id,
            campus_id=campus_id,
        )
        return campus is not None and campus.active

    async def is_active(
        self,
        *,
        organization_id: UUID,
    ) -> bool:
        """Return lifecycle availability for trusted internal access resolution."""

        organization = await self._organizations.get_platform(
            organization_id=organization_id,
        )
        return (
            organization is not None
            and organization.status is OrganizationStatus.ACTIVE
        )

    async def _get_platform(
        self,
        *,
        organization_id: UUID,
    ) -> Organization:
        """Load organization metadata through the explicit platform path."""

        organization = await self._organizations.get_platform(
            organization_id=organization_id,
        )
        if organization is None:
            raise OrganizationNotFoundError
        return organization

    @staticmethod
    def _require_platform_permission(
        actor: PlatformActorContext,
        permission: str,
    ) -> None:
        """Deny platform operations without their exact separate permission."""

        if (
            not isinstance(actor, PlatformActorContext)
            or permission not in actor.permissions
        ):
            raise AuthorizationError

    @staticmethod
    def _require_tenant_permission(
        actor: TenantActorContext,
        permission: str,
    ) -> None:
        """Deny tenant operations without their exact membership permission."""

        if (
            not isinstance(actor, TenantActorContext)
            or permission not in actor.permissions
        ):
            raise AuthorizationError


__all__ = [
    "CONFIGURE_ORGANIZATION_PERMISSION",
    "CREATE_ORGANIZATION_PERMISSION",
    "LIFECYCLE_PERMISSION",
    "MANAGE_CAMPUSES_PERMISSION",
    "READ_ORGANIZATION_PERMISSION",
    "OrganizationService",
]
