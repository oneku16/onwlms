"""Admissions domain failures with stable application meaning."""

from core.errors import ConflictError
from core.errors import ValidationError


class AdmissionsRuleError(ValidationError):
    """Raised when admissions data violates an owned invariant."""


class ApplicationTransitionError(ConflictError):
    """Raised when an application status transition is not permitted."""


class QuotaUnavailableError(ConflictError):
    """Raised when an admissions quota has no reservable seat."""


class EnrollmentConversionError(ConflictError):
    """Raised when an accepted application cannot become an enrollment."""


__all__ = [
    "AdmissionsRuleError",
    "ApplicationTransitionError",
    "EnrollmentConversionError",
    "QuotaUnavailableError",
]
