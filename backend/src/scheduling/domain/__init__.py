"""Public timetable scheduling domain surface."""

from scheduling.domain.constraints import detect_hard_conflicts
from scheduling.domain.constraints import detect_soft_constraint_violations
from scheduling.domain.exceptions import ScheduleVersionConflictError
from scheduling.domain.exceptions import SchedulingConflictError
from scheduling.domain.exceptions import SchedulingRuleError
from scheduling.domain.models import MAX_TEACHER_AVAILABILITY_SPAN
from scheduling.domain.models import ActivityRequest
from scheduling.domain.models import CandidateSlot
from scheduling.domain.models import ConstraintContext
from scheduling.domain.models import DailyWindow
from scheduling.domain.models import HardConflict
from scheduling.domain.models import HardConstraintCode
from scheduling.domain.models import RecurrenceRule
from scheduling.domain.models import RoomSpecification
from scheduling.domain.models import ScheduledSession
from scheduling.domain.models import ScheduleGenerationRequest
from scheduling.domain.models import ScheduleGenerationResult
from scheduling.domain.models import SchedulingPolicy
from scheduling.domain.models import SoftConstraintCode
from scheduling.domain.models import SoftConstraintViolation
from scheduling.domain.models import TeacherAvailability
from scheduling.domain.models import TeacherAvailabilityWindow
from scheduling.domain.models import TimeWindow

__all__ = [
    "MAX_TEACHER_AVAILABILITY_SPAN",
    "ActivityRequest",
    "CandidateSlot",
    "ConstraintContext",
    "DailyWindow",
    "HardConflict",
    "HardConstraintCode",
    "RecurrenceRule",
    "RoomSpecification",
    "ScheduleGenerationRequest",
    "ScheduleGenerationResult",
    "ScheduleVersionConflictError",
    "ScheduledSession",
    "SchedulingConflictError",
    "SchedulingPolicy",
    "SchedulingRuleError",
    "SoftConstraintCode",
    "SoftConstraintViolation",
    "TeacherAvailability",
    "TeacherAvailabilityWindow",
    "TimeWindow",
    "detect_hard_conflicts",
    "detect_soft_constraint_violations",
]
