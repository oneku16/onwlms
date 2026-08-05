"""Trusted actor and tenant context passed to application capabilities."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PlatformActorContext:
    """Describe a verified actor performing an explicit platform operation."""

    subject_id: UUID
    correlation_id: str
    permissions: frozenset[str]


@dataclass(frozen=True, slots=True)
class TenantActorContext:
    """Describe a verified actor bound to exactly one organization membership."""

    subject_id: UUID
    organization_id: UUID
    membership_id: UUID
    correlation_id: str
    permissions: frozenset[str]


ActorContext = PlatformActorContext | TenantActorContext

__all__ = [
    "ActorContext",
    "PlatformActorContext",
    "TenantActorContext",
]
