"""Application-owned timetable persistence and generation contracts."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from scheduling.domain.models import ConstraintContext
from scheduling.domain.models import ScheduledSession
from scheduling.domain.models import ScheduleGenerationRequest
from scheduling.domain.models import ScheduleGenerationResult
from scheduling.domain.models import TeacherAvailability
from scheduling.domain.models import TeacherAvailabilityWindow


class SchedulingRepository(Protocol):
    """Persist tenant timetable sessions with optimistic version guarantees."""

    async def list_sessions(
        self,
        *,
        organization_id: UUID,
    ) -> tuple[ScheduledSession, ...]:
        """Return all timetable sessions inside one tenant."""
        ...

    async def list_sessions_window(
        self,
        *,
        organization_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        limit: int,
        offset: int,
    ) -> tuple[ScheduledSession, ...]:
        """Return a bounded stable page intersecting one tenant time window."""
        ...

    async def get_session(
        self,
        *,
        organization_id: UUID,
        session_id: UUID,
    ) -> ScheduledSession | None:
        """Return a timetable session only from the requested tenant."""
        ...

    async def save_session(
        self,
        *,
        session: ScheduledSession,
        expected_version: int | None,
    ) -> None:
        """Create or compare-and-swap one timetable session."""
        ...

    async def replace_generated_schedule(
        self,
        *,
        organization_id: UUID,
        proposed_sessions: tuple[ScheduledSession, ...],
        locked_session_ids: frozenset[UUID],
        expected_versions: dict[UUID, int],
    ) -> None:
        """Atomically preserve locks and replace all other tenant sessions."""
        ...


class SchedulingGenerator(Protocol):
    """Generate a proposed schedule behind a replaceable deterministic contract."""

    def generate(
        self,
        request: ScheduleGenerationRequest,
    ) -> ScheduleGenerationResult:
        """Return proposals, unresolved hard conflicts, violations, and score."""
        ...


class SchedulingResourceDirectory(Protocol):
    """Resolve academic room, teacher, and calendar facts through a public port."""

    async def constraint_context(
        self,
        *,
        organization_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        teacher_ids: frozenset[UUID],
    ) -> ConstraintContext:
        """Return tenant constraint facts covering a requested schedule horizon."""
        ...


class TimetableGenerationEntitlement(Protocol):
    """Resolve the commercial capability owned outside scheduling."""

    async def is_timetable_generation_enabled(
        self,
        *,
        organization_id: UUID,
    ) -> bool:
        """Return whether one tenant may generate and apply proposals."""
        ...


class TeacherAvailabilityRepository(Protocol):
    """Persist tenant-owned teacher availability windows."""

    async def create_window(self, window: TeacherAvailabilityWindow) -> None:
        """Create one exact availability window."""
        ...

    async def delete_window(
        self,
        *,
        organization_id: UUID,
        window_id: UUID,
    ) -> bool:
        """Delete one exact tenant window and report whether it existed."""
        ...

    async def list_windows_page(
        self,
        *,
        organization_id: UUID,
        teacher_id: UUID | None,
        starts_at: datetime,
        ends_at: datetime,
        limit: int,
        offset: int,
    ) -> tuple[TeacherAvailabilityWindow, ...]:
        """Return a stable bounded page of overlapping tenant windows."""
        ...

    async def list_constraint_windows(
        self,
        *,
        organization_id: UUID,
        teacher_ids: frozenset[UUID],
        starts_at: datetime,
        ends_at: datetime,
    ) -> tuple[TeacherAvailabilityWindow, ...]:
        """Return all overlapping windows for the requested teacher set."""
        ...


class TeacherAvailabilityDirectory(Protocol):
    """Expose Scheduling-owned availability to the constraint composer."""

    async def availability_for_constraints(
        self,
        *,
        organization_id: UUID,
        teacher_ids: frozenset[UUID],
        starts_at: datetime,
        ends_at: datetime,
    ) -> tuple[TeacherAvailability, ...]:
        """Return one availability entry for every requested teacher."""
        ...


class TeacherReferenceDirectory(Protocol):
    """Validate teacher profile references through the People public boundary."""

    async def existing_teacher_profile_ids(
        self,
        *,
        organization_id: UUID,
        teacher_profile_ids: frozenset[UUID],
    ) -> frozenset[UUID]:
        """Return only matching teacher profiles from the requested tenant."""
        ...


__all__ = [
    "SchedulingGenerator",
    "SchedulingRepository",
    "SchedulingResourceDirectory",
    "TeacherAvailabilityDirectory",
    "TeacherAvailabilityRepository",
    "TeacherReferenceDirectory",
    "TimetableGenerationEntitlement",
]
