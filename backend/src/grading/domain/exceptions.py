"""Official grading domain failures."""

from core.errors import ConflictError
from core.errors import ValidationError


class GradingRuleError(ValidationError):
    """Raised when an official grading invariant is violated."""


class GradeRevisionConflictError(ConflictError):
    """Raised when a final grade changed during a requested revision."""


__all__ = ["GradeRevisionConflictError", "GradingRuleError"]
