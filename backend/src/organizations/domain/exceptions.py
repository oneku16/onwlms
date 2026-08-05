"""Organization domain and persistence failures."""

from core.errors import ConflictError
from core.errors import NotFoundError
from core.errors import ValidationError


class InvalidOrganizationError(ValidationError):
    """Raised when organization-owned values violate their invariants."""


class OrganizationLifecycleError(ConflictError):
    """Raised when a lifecycle transition conflicts with current state."""


class OrganizationNotFoundError(NotFoundError):
    """Raised when an authorized organization lookup finds no tenant."""


class OrganizationSlugConflictError(ConflictError):
    """Raised when a requested global organization slug already exists."""


__all__ = [
    "InvalidOrganizationError",
    "OrganizationLifecycleError",
    "OrganizationNotFoundError",
    "OrganizationSlugConflictError",
]
