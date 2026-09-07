"""Entitlement domain and persistence failures."""

from core.errors import ConflictError
from core.errors import NotFoundError
from core.errors import ValidationError


class InvalidEntitlementError(ValidationError):
    """Raised when plans, subscriptions, or limits violate invariants."""


class EntitlementNotFoundError(NotFoundError):
    """Raised when an authorized global entitlement lookup finds no record."""


class EntitlementConflictError(ConflictError):
    """Raised when entitlement state conflicts with centralized uniqueness."""


__all__ = [
    "EntitlementConflictError",
    "EntitlementNotFoundError",
    "InvalidEntitlementError",
]
