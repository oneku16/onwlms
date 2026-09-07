"""Functional in-memory scheduling persistence and resource adapters."""

import asyncio
from datetime import datetime
from uuid import UUID

from core.errors import ConflictError
from scheduling.application.contracts import ExistingSchedulingReferences
from scheduling.domain.constraints import detect_hard_conflicts
from scheduling.domain.exceptions import ScheduleVersionConflictError
from scheduling.domain.exceptions import SchedulingConflictError
from scheduling.domain.exceptions import SchedulingRuleError
from scheduling.domain.models import ConstraintContext
from scheduling.domain.models import ScheduledSession
from scheduling.domain.models import TeacherAvailability
from scheduling.domain.models import TeacherAvailabilityWindow
from scheduling.domain.replacement import prepare_generated_replacement

TenantKey = tuple[UUID, UUID]


class InMemorySchedulingResourceDirectory:
    """Return explicitly configured tenant scheduling constraint snapshots."""

    def __init__(
        self,
        contexts: tuple[ConstraintContext, ...] = (),
    ) -> None:
        self._contexts = {context.organization_id: context for context in contexts}

    async def constraint_context(
        self,
        *,
        organization_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        teacher_ids: frozenset[UUID],
    ) -> ConstraintContext:
        """Return tenant context covering the requested bounded horizon."""

        if starts_at >= ends_at:
            raise SchedulingRuleError("Constraint horizon must be increasing.")
        context = self._contexts.get(organization_id)
        if context is None:
            raise SchedulingRuleError(
                "Scheduling constraints are not configured for the tenant."
            )
        availability_by_teacher = {
            availability.teacher_id: availability
            for availability in context.teacher_availability
        }
        return ConstraintContext(
            organization_id=context.organization_id,
            rooms=context.rooms,
            teacher_availability=tuple(
                availability_by_teacher.get(
                    teacher_id,
                    TeacherAvailability(
                        organization_id=organization_id,
                        teacher_id=teacher_id,
                        windows=(),
                    ),
                )
                for teacher_id in sorted(teacher_ids, key=str)
            ),
            academic_calendar_windows=context.academic_calendar_windows,
        )

    def set_context(self, context: ConstraintContext) -> None:
        """Replace one tenant constraint snapshot for deterministic tests."""

        self._contexts[context.organization_id] = context


class InMemorySchedulingReferenceDirectory:
    """Resolve explicitly configured tenant scheduling reference snapshots."""

    def __init__(
        self,
        references: tuple[ExistingSchedulingReferences, ...] = (),
    ) -> None:
        self._references = {
            reference.organization_id: reference for reference in references
        }

    async def existing_references(
        self,
        *,
        organization_id: UUID,
        room_ids: frozenset[UUID],
        course_offering_ids: frozenset[UUID],
        group_ids: frozenset[UUID],
        teacher_ids: frozenset[UUID],
    ) -> ExistingSchedulingReferences:
        """Return the requested intersection for one exact configured tenant."""

        configured = self._references.get(
            organization_id,
            ExistingSchedulingReferences(
                organization_id=organization_id,
                room_ids=frozenset(),
                course_offering_ids=frozenset(),
                group_ids=frozenset(),
                teacher_ids=frozenset(),
            ),
        )
        return ExistingSchedulingReferences(
            organization_id=organization_id,
            room_ids=room_ids & configured.room_ids,
            course_offering_ids=(course_offering_ids & configured.course_offering_ids),
            group_ids=group_ids & configured.group_ids,
            teacher_ids=teacher_ids & configured.teacher_ids,
        )


class InMemorySchedulingAuditSink:
    """Record ordered scheduling audit calls for local and test composition."""

    def __init__(self) -> None:
        self.events: list[tuple[str, UUID, UUID, UUID, str, str]] = []

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
        """Record one privacy-minimized scheduling event in call order."""

        self.events.append(
            (
                action,
                organization_id,
                actor_subject_id,
                target_id,
                correlation_id,
                outcome,
            )
        )


class InMemorySchedulingRepository:
    """Preserve tenant scope, optimistic edits, and generation locks in memory."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._sessions: dict[TenantKey, ScheduledSession] = {}

    async def list_sessions(
        self,
        *,
        organization_id: UUID,
    ) -> tuple[ScheduledSession, ...]:
        """Return stable ordered sessions inside one tenant."""

        sessions = (
            session
            for session in self._sessions.values()
            if session.organization_id == organization_id
        )
        return tuple(
            sorted(
                sessions,
                key=lambda session: (
                    session.starts_at,
                    session.ends_at,
                    str(session.id),
                ),
            )
        )

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

        values = sorted(
            (
                session
                for session in self._sessions.values()
                if session.organization_id == organization_id
                and session.starts_at < ends_at
                and session.ends_at > starts_at
            ),
            key=lambda session: (session.starts_at, session.ends_at, str(session.id)),
        )
        return tuple(values[offset : offset + limit])

    async def get_session(
        self,
        *,
        organization_id: UUID,
        session_id: UUID,
    ) -> ScheduledSession | None:
        """Return a session only from the requested tenant."""

        return self._sessions.get((organization_id, session_id))

    async def save_session(
        self,
        *,
        session: ScheduledSession,
        expected_version: int | None,
    ) -> None:
        """Create or compare-and-swap one timetable session."""

        async with self._lock:
            self._save_session(session=session, expected_version=expected_version)

    async def save_conflict_free_session(
        self,
        *,
        session: ScheduledSession,
        expected_version: int | None,
        constraints: ConstraintContext,
    ) -> None:
        """Check all current tenant sessions and save under one process lock."""

        async with self._lock:
            existing = tuple(
                value
                for value in self._sessions.values()
                if value.organization_id == session.organization_id
                and value.id != session.id
            )
            conflicts = detect_hard_conflicts(
                candidate=session,
                existing_sessions=existing,
                context=constraints,
            )
            if conflicts:
                codes = ", ".join(
                    dict.fromkeys(conflict.code for conflict in conflicts)
                )
                raise SchedulingConflictError(f"Session conflicts with: {codes}.")
            self._save_session(session=session, expected_version=expected_version)

    async def replace_generated_schedule(
        self,
        *,
        organization_id: UUID,
        proposed_sessions: tuple[ScheduledSession, ...],
        locked_session_ids: frozenset[UUID],
        expected_versions: dict[UUID, int],
        constraints: ConstraintContext,
    ) -> tuple[ScheduledSession, ...]:
        """Atomically preserve effective locks and assign replacement versions."""

        async with self._lock:
            current_sessions = tuple(
                session
                for session in self._sessions.values()
                if session.organization_id == organization_id
            )
            prepared_sessions = prepare_generated_replacement(
                organization_id=organization_id,
                current_sessions=current_sessions,
                proposed_sessions=proposed_sessions,
                asserted_locked_session_ids=locked_session_ids,
                expected_versions=expected_versions,
            )
            conflicts = tuple(
                conflict
                for candidate in prepared_sessions
                for conflict in detect_hard_conflicts(
                    candidate=candidate,
                    existing_sessions=prepared_sessions,
                    context=constraints,
                )
            )
            if conflicts:
                codes = ", ".join(
                    dict.fromkeys(conflict.code for conflict in conflicts)
                )
                raise SchedulingConflictError(
                    f"Generated proposal conflicts with: {codes}."
                )
            tenant_keys = [key for key in self._sessions if key[0] == organization_id]
            for key in tenant_keys:
                del self._sessions[key]
            for session in prepared_sessions:
                self._sessions[(organization_id, session.id)] = session
            return prepared_sessions

    def _save_session(
        self,
        *,
        session: ScheduledSession,
        expected_version: int | None,
    ) -> None:
        """Persist one session while the repository process lock is held."""

        key = (session.organization_id, session.id)
        current = self._sessions.get(key)
        if expected_version is None:
            if current is not None:
                raise ConflictError("Timetable session already exists.")
        elif current is None or current.version != expected_version:
            raise ScheduleVersionConflictError(
                "Timetable session changed during the requested edit."
            )
        self._sessions[key] = session


class InMemoryTeacherAvailabilityRepository:
    """Preserve tenant ownership and exact-window uniqueness in memory."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._windows: dict[TenantKey, TeacherAvailabilityWindow] = {}

    async def create_window(self, window: TeacherAvailabilityWindow) -> None:
        """Create one unique ID and exact teacher interval."""

        async with self._lock:
            key = (window.organization_id, window.id)
            if key in self._windows or any(
                existing.organization_id == window.organization_id
                and existing.teacher_id == window.teacher_id
                and existing.starts_at == window.starts_at
                and existing.ends_at == window.ends_at
                for existing in self._windows.values()
            ):
                raise ConflictError("Teacher availability window already exists.")
            self._windows[key] = window

    async def delete_window(
        self,
        *,
        organization_id: UUID,
        window_id: UUID,
    ) -> bool:
        """Delete only an exact tenant-owned window."""

        async with self._lock:
            return self._windows.pop((organization_id, window_id), None) is not None

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
        """Return a stable page filtered by tenant, teacher, and overlap."""

        values = self._matching(
            organization_id=organization_id,
            teacher_ids=(frozenset({teacher_id}) if teacher_id is not None else None),
            starts_at=starts_at,
            ends_at=ends_at,
        )
        return values[offset : offset + limit]

    async def list_constraint_windows(
        self,
        *,
        organization_id: UUID,
        teacher_ids: frozenset[UUID],
        starts_at: datetime,
        ends_at: datetime,
    ) -> tuple[TeacherAvailabilityWindow, ...]:
        """Return every overlapping window for a requested teacher set."""

        if not teacher_ids:
            return ()
        return self._matching(
            organization_id=organization_id,
            teacher_ids=teacher_ids,
            starts_at=starts_at,
            ends_at=ends_at,
        )

    def _matching(
        self,
        *,
        organization_id: UUID,
        teacher_ids: frozenset[UUID] | None,
        starts_at: datetime,
        ends_at: datetime,
    ) -> tuple[TeacherAvailabilityWindow, ...]:
        """Return stable overlap-filtered windows."""

        return tuple(
            sorted(
                (
                    window
                    for window in self._windows.values()
                    if window.organization_id == organization_id
                    and (teacher_ids is None or window.teacher_id in teacher_ids)
                    and window.starts_at < ends_at
                    and window.ends_at > starts_at
                ),
                key=lambda window: (
                    window.starts_at,
                    window.ends_at,
                    str(window.id),
                ),
            )
        )


__all__ = [
    "InMemorySchedulingAuditSink",
    "InMemorySchedulingReferenceDirectory",
    "InMemorySchedulingRepository",
    "InMemorySchedulingResourceDirectory",
    "InMemoryTeacherAvailabilityRepository",
]
