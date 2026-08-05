"""Privacy-safe Moodle synchronization status projections."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class GradeSynchronizationStatus:
    """Summarize observed Moodle grade evidence for one assigned section."""

    course_offering_id: UUID
    status: str
    last_observed_at: datetime | None
    unresolved_count: int


__all__ = ["GradeSynchronizationStatus"]
