"""Ports owned by the audit application module."""

from typing import Protocol
from uuid import UUID

from audit.domain.records import AuditRecord


class AuditRepository(Protocol):
    """Persist and read immutable audit evidence."""

    async def append(
        self,
        record: AuditRecord,
    ) -> None:
        """Append evidence without exposing an update or delete operation."""
        ...

    async def list_for_organization(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> list[AuditRecord]:
        """Return safe audit evidence for exactly one organization."""
        ...

    async def list_platform(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[AuditRecord]:
        """Return platform-operation evidence for authorized administrators."""
        ...


__all__ = ["AuditRepository"]
