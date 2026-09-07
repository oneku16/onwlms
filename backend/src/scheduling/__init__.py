"""Explicit public contracts for the timetable scheduling bounded context."""

from scheduling.application import SCHEDULING_APPLY_GENERATION
from scheduling.application import SCHEDULING_GENERATE
from scheduling.application import SCHEDULING_READ
from scheduling.application import SCHEDULING_SESSION_MANAGE
from scheduling.application import DeterministicHeuristicSchedulingGenerator
from scheduling.application import ExistingSchedulingReferences
from scheduling.application import SchedulingAuditSink
from scheduling.application import SchedulingGenerator
from scheduling.application import SchedulingReferenceDirectory
from scheduling.application import SchedulingRepository
from scheduling.application import SchedulingResourceDirectory
from scheduling.application import TimetableService
from scheduling.domain import ConstraintContext
from scheduling.domain import HardConflict
from scheduling.domain import ScheduledSession
from scheduling.domain import ScheduleGenerationRequest
from scheduling.domain import ScheduleGenerationResult

__all__ = [
    "SCHEDULING_APPLY_GENERATION",
    "SCHEDULING_GENERATE",
    "SCHEDULING_READ",
    "SCHEDULING_SESSION_MANAGE",
    "ConstraintContext",
    "DeterministicHeuristicSchedulingGenerator",
    "ExistingSchedulingReferences",
    "HardConflict",
    "ScheduleGenerationRequest",
    "ScheduleGenerationResult",
    "ScheduledSession",
    "SchedulingAuditSink",
    "SchedulingGenerator",
    "SchedulingReferenceDirectory",
    "SchedulingRepository",
    "SchedulingResourceDirectory",
    "TimetableService",
]
