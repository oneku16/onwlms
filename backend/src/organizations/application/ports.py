"""Ports owned by organization application capabilities."""

from typing import Protocol
from uuid import UUID

from organizations.domain.models import Campus
from organizations.domain.models import Organization


class OrganizationRepository(Protocol):
    """Persist organizations through separate platform and tenant query paths."""

    async def add(
        self,
        organization: Organization,
    ) -> None:
        """Create one organization through the privileged platform path."""
        ...

    async def get_platform(
        self,
        *,
        organization_id: UUID,
    ) -> Organization | None:
        """Return one organization for an explicit platform operation."""
        ...

    async def list_platform(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[Organization]:
        """List safe organization governance state for platform administration."""
        ...

    async def get_tenant(
        self,
        *,
        organization_id: UUID,
    ) -> Organization | None:
        """Return one organization under a matching PostgreSQL tenant context."""
        ...

    async def save_platform(
        self,
        organization: Organization,
    ) -> None:
        """Persist a lifecycle change through the platform path."""
        ...

    async def save_tenant(
        self,
        organization: Organization,
    ) -> None:
        """Persist configuration under its matching tenant context."""
        ...


class CampusRepository(Protocol):
    """Persist and query campuses only within a supplied organization boundary."""

    async def add(
        self,
        campus: Campus,
    ) -> None:
        """Create one campus under its own tenant context."""
        ...

    async def get(
        self,
        *,
        organization_id: UUID,
        campus_id: UUID,
    ) -> Campus | None:
        """Return a campus only when both tenant and identifier match."""
        ...

    async def list_for_organization(
        self,
        *,
        organization_id: UUID,
    ) -> list[Campus]:
        """List campuses for exactly one trusted tenant."""
        ...


class OrganizationAuditSink(Protocol):
    """Record privacy-minimized organization governance outcomes."""

    async def record_organization_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        correlation_id: str,
        outcome: str,
    ) -> None:
        """Append one organization change without configuration payloads."""
        ...


class CampusDirectory(Protocol):
    """Expose active-campus validation without leaking organization storage."""

    async def campus_exists(
        self,
        *,
        organization_id: UUID,
        campus_id: UUID,
    ) -> bool:
        """Return whether a trusted tenant owns an active campus."""
        ...


__all__ = [
    "CampusDirectory",
    "CampusRepository",
    "OrganizationAuditSink",
    "OrganizationRepository",
]
