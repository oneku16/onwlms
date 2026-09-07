"""Stable application failures translated at delivery boundaries."""


class AppError(Exception):
    """Base class for expected OwnSIS application failures."""


class AuthenticationError(AppError):
    """Raised when a caller cannot establish a trusted identity session."""


class AuthorizationError(AppError):
    """Raised when an actor is not allowed to invoke a capability."""


class NotFoundError(AppError):
    """Raised when an authorized lookup cannot find the requested resource."""


class ConflictError(AppError):
    """Raised when current state conflicts with a requested transition."""


class ValidationError(AppError):
    """Raised when input is well shaped but violates an application rule."""


class ExternalServiceError(AppError):
    """Raised when an integration cannot complete an owned operation safely."""


__all__ = [
    "AppError",
    "AuthenticationError",
    "AuthorizationError",
    "ConflictError",
    "ExternalServiceError",
    "NotFoundError",
    "ValidationError",
]
