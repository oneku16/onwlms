"""Application-owned timetable persistence and generation contracts."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from scheduling.application.contracts import ExistingSchedulingReferences
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
        """Create or compare-and-swap session state without changing its booking."""
        ...

    async def save_conflict_free_session(
        self,
        *,
        session: ScheduledSession,
        expected_version: int | None,
        constraints: ConstraintContext,
    ) -> None:
        """Atomically reject stored booking conflicts and save one session."""
        ...

    async def replace_generated_schedule(
        self,
        *,
        organization_id: UUID,
        proposed_sessions: tuple[ScheduledSession, ...],
        locked_session_ids: frozenset[UUID],
        expected_versions: dict[UUID, int],
        constraints: ConstraintContext,
    ) -> tuple[ScheduledSession, ...]:
        """Atomically replace and return sessions with authoritative versions."""
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


class SchedulingReferenceDirectory(Protocol):
    """Validate external scheduling identifiers through public module contracts."""

    async def existing_references(
        self,
        *,
        organization_id: UUID,
        room_ids: frozenset[UUID],
        course_offering_ids: frozenset[UUID],
        group_ids: frozenset[UUID],
        teacher_ids: frozenset[UUID],
    ) -> ExistingSchedulingReferences:
        """Return only requested references owned by the exact tenant."""
        ...


class SchedulingAuditSink(Protocol):
    """Append privacy-minimized scheduling mutation evidence."""

    async def record_scheduling_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        target_id: UUID,
        correlation_id: str,
        outcome: str,
    ) -> None:
        """Record one mutation intent or completed mutation outcome."""
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
    "SchedulingAuditSink",
    "SchedulingGenerator",
    "SchedulingReferenceDirectory",
    "SchedulingRepository",
    "SchedulingResourceDirectory",
    "TeacherAvailabilityDirectory",
    "TeacherAvailabilityRepository",
    "TeacherReferenceDirectory",
    "TimetableGenerationEntitlement",
]
