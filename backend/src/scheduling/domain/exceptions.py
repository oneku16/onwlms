"""Scheduling domain failures."""

from core.errors import ConflictError
from core.errors import ValidationError


class SchedulingRuleError(ValidationError):
    """Raised when timetable data violates an owned invariant."""


class SchedulingConflictError(ConflictError):
    """Raised when a manual or generated timetable has hard conflicts."""


class ScheduleVersionConflictError(ConflictError):
    """Raised when a timetable session changed during an edit."""


__all__ = [
    "ScheduleVersionConflictError",
    "SchedulingConflictError",
    "SchedulingRuleError",
]
