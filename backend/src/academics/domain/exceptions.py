"""Academic domain failures with stable application meaning."""

from core.errors import ConflictError
from core.errors import ValidationError


class AcademicRuleError(ValidationError):
    """Raised when an academic record violates an owned invariant."""


class CourseSelectionError(ConflictError):
    """Raised when a course-selection request cannot proceed."""


class CourseSelectionDecisionError(ConflictError):
    """Raised when a selection request cannot accept the requested decision."""


class EnrollmentTransitionError(ConflictError):
    """Raised when current state forbids a requested one-way enrollment transition."""


__all__ = [
    "AcademicRuleError",
    "CourseSelectionDecisionError",
    "CourseSelectionError",
    "EnrollmentTransitionError",
]
