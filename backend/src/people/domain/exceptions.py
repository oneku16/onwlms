"""People and membership domain failures."""

from core.errors import AppError
from core.errors import ConflictError
from core.errors import NotFoundError
from core.errors import ValidationError


class InvalidPersonError(ValidationError):
    """Raised when person-owned values violate their invariants."""


class InvalidMembershipError(ValidationError):
    """Raised when a tenant membership is absent, inactive, or invalid."""


class PersonNotFoundError(NotFoundError):
    """Raised when an authorized tenant lookup cannot find a person."""


class MembershipNotFoundError(NotFoundError):
    """Raised when no active matching tenant membership exists."""


class PeopleConflictError(ConflictError):
    """Raised when tenant-owned people state conflicts with an invariant."""


class PeopleDataProtectionError(AppError):
    """Raised when encrypted personal data cannot be processed safely."""


__all__ = [
    "InvalidMembershipError",
    "InvalidPersonError",
    "MembershipNotFoundError",
    "PeopleConflictError",
    "PeopleDataProtectionError",
    "PersonNotFoundError",
]
