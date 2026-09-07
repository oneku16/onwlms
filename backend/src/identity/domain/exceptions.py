"""Identity-specific failures independent of HTTP and provider libraries."""

from core.errors import AuthenticationError
from core.errors import AuthorizationError
from core.errors import ConflictError
from core.errors import ExternalServiceError
from core.errors import NotFoundError


class IdentityError(AuthenticationError):
    """Base class for failures that cannot establish a trusted identity."""


class InvalidAuthorizationFlowError(IdentityError):
    """Raised when a pending OIDC flow is absent, expired, or inconsistent."""


class InvalidSessionError(IdentityError):
    """Raised when an application session is absent, expired, or malformed."""


class SessionRefreshConflictError(ConflictError):
    """Raised when another request already refreshed the same session."""


class InvalidCSRFTokenError(AuthorizationError):
    """Raised when a state-changing cookie request fails CSRF validation."""


class OwnIDProviderError(ExternalServiceError):
    """Raised when OwnID cannot provide a safely verified result."""


class PlatformAdministratorNotFoundError(NotFoundError):
    """Raised when a platform-administrator target does not exist."""


class PlatformAdministratorBootstrapClosedError(ConflictError):
    """Raised once ordinary platform administration has been established."""


class FinalPlatformAdministratorError(ConflictError):
    """Raised when revocation would leave no active platform administrator."""


__all__ = [
    "FinalPlatformAdministratorError",
    "IdentityError",
    "InvalidAuthorizationFlowError",
    "InvalidCSRFTokenError",
    "InvalidSessionError",
    "OwnIDProviderError",
    "PlatformAdministratorBootstrapClosedError",
    "PlatformAdministratorNotFoundError",
    "SessionRefreshConflictError",
]
