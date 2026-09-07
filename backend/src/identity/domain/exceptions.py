"""Identity-specific failures independent of HTTP and provider libraries."""

from core.errors import AuthenticationError
from core.errors import AuthorizationError
from core.errors import ExternalServiceError


class IdentityError(AuthenticationError):
    """Base class for failures that cannot establish a trusted identity."""


class InvalidAuthorizationFlowError(IdentityError):
    """Raised when a pending OIDC flow is absent, expired, or inconsistent."""


class InvalidSessionError(IdentityError):
    """Raised when an application session is absent, expired, or malformed."""


class InvalidCSRFTokenError(AuthorizationError):
    """Raised when a state-changing cookie request fails CSRF validation."""


class OwnIDProviderError(ExternalServiceError):
    """Raised when OwnID cannot provide a safely verified result."""


__all__ = [
    "IdentityError",
    "InvalidAuthorizationFlowError",
    "InvalidCSRFTokenError",
    "InvalidSessionError",
    "OwnIDProviderError",
]
