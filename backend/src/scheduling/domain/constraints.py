"""Immediate hard-conflict detection and deterministic soft scoring."""

from collections import defaultdict
from collections.abc import Callable
from datetime import date
from uuid import UUID

from scheduling.domain.exceptions import SchedulingRuleError
from scheduling.domain.models import ConstraintContext
from scheduling.domain.models import HardConflict
from scheduling.domain.models import HardConstraintCode
from scheduling.domain.models import ScheduledSession
from scheduling.domain.models import SchedulingPolicy
from scheduling.domain.models import SoftConstraintCode
from scheduling.domain.models import SoftConstraintViolation
from scheduling.domain.models import TimeWindow


def detect_hard_conflicts(
    *,
    candidate: ScheduledSession,
    existing_sessions: tuple[ScheduledSession, ...],
    context: ConstraintContext,
) -> tuple[HardConflict, ...]:
    """Return all immediate hard conflicts for a candidate session."""

    if candidate.organization_id != context.organization_id:
        raise SchedulingRuleError("Candidate and constraint tenants differ.")
    if any(
        session.organization_id != candidate.organization_id
        for session in existing_sessions
    ):
        raise SchedulingRuleError("Existing session tenant does not match candidate.")
    conflicts: list[HardConflict] = []
    room = context.room(candidate.room_id)
    if room is None:
        conflicts.append(
            HardConflict(
                code=HardConstraintCode.UNKNOWN_RESOURCE,
                session_ids=(candidate.id,),
                resource_id=candidate.room_id,
                explanation="The requested room is not available to this tenant.",
            )
        )
    else:
        if room.capacity < candidate.expected_attendance:
            conflicts.append(
                HardConflict(
                    code=HardConstraintCode.ROOM_CAPACITY,
                    session_ids=(candidate.id,),
                    resource_id=room.room_id,
                    explanation="Room capacity is below expected attendance.",
                )
            )
        if room.room_type.casefold() != candidate.required_room_type.casefold():
            conflicts.append(
                HardConflict(
                    code=HardConstraintCode.ROOM_TYPE,
                    session_ids=(candidate.id,),
                    resource_id=room.room_id,
                    explanation="Room type does not match the activity requirement.",
                )
            )

    candidate_occurrences = candidate.occurrences()
    if any(
        not any(
            window.contains(occurrence) for window in context.academic_calendar_windows
        )
        for occurrence in candidate_occurrences
    ):
        conflicts.append(
            HardConflict(
                code=HardConstraintCode.ACADEMIC_CALENDAR,
                session_ids=(candidate.id,),
                resource_id=None,
                explanation="Session falls outside the academic calendar.",
            )
        )

    for teacher_id in candidate.teacher_ids:
        availability = context.teacher_windows(teacher_id)
        if any(
            not any(window.contains(occurrence) for window in availability)
            for occurrence in candidate_occurrences
        ):
            conflicts.append(
                HardConflict(
                    code=HardConstraintCode.TEACHER_UNAVAILABLE,
                    session_ids=(candidate.id,),
                    resource_id=teacher_id,
                    explanation="Teacher availability does not cover the session.",
                )
            )

    for existing in existing_sessions:
        if existing.id == candidate.id:
            continue
        if not _sessions_overlap(candidate, existing):
            continue
        if existing.room_id == candidate.room_id:
            conflicts.append(
                HardConflict(
                    code=HardConstraintCode.ROOM_OVERLAP,
                    session_ids=(candidate.id, existing.id),
                    resource_id=candidate.room_id,
                    explanation="Room is already booked for an overlapping session.",
                )
            )
        for teacher_id in sorted(
            set(candidate.teacher_ids) & set(existing.teacher_ids),
            key=str,
        ):
            conflicts.append(
                HardConflict(
                    code=HardConstraintCode.TEACHER_OVERLAP,
                    session_ids=(candidate.id, existing.id),
                    resource_id=teacher_id,
                    explanation="Teacher is assigned to overlapping sessions.",
                )
            )
        for group_id in sorted(
            set(candidate.required_group_ids) & set(existing.required_group_ids),
            key=str,
        ):
            conflicts.append(
                HardConflict(
                    code=HardConstraintCode.REQUIRED_GROUP_OVERLAP,
                    session_ids=(candidate.id, existing.id),
                    resource_id=group_id,
                    explanation="Required student group has overlapping sessions.",
                )
            )
    return tuple(conflicts)


def detect_soft_constraint_violations(
    *,
    sessions: tuple[ScheduledSession, ...],
    policy: SchedulingPolicy,
) -> tuple[SoftConstraintViolation, ...]:
    """Return deterministic teacher, student, preference, and balance penalties."""

    violations: list[SoftConstraintViolation] = []
    if policy.preferred_hours:
        for session in sessions:
            if any(
                not any(
                    window.contains(occurrence) for window in policy.preferred_hours
                )
                for occurrence in session.occurrences()
            ):
                violations.append(
                    SoftConstraintViolation(
                        code=SoftConstraintCode.PREFERRED_HOURS,
                        session_ids=(session.id,),
                        resource_id=None,
                        penalty=policy.penalty_per_violation,
                        explanation="Session is outside preferred instructional hours.",
                    )
                )

    violations.extend(
        _resource_timing_violations(
            sessions=sessions,
            resource_ids=lambda session: session.teacher_ids,
            policy=policy,
            gap_code=SoftConstraintCode.TEACHER_GAP,
        )
    )
    violations.extend(
        _resource_timing_violations(
            sessions=sessions,
            resource_ids=lambda session: session.group_ids,
            policy=policy,
            gap_code=SoftConstraintCode.STUDENT_GAP,
        )
    )
    violations.extend(_weekly_balance_violations(sessions=sessions, policy=policy))
    return tuple(violations)


def _sessions_overlap(
    left: ScheduledSession,
    right: ScheduledSession,
) -> bool:
    """Return whether any bounded concrete occurrences overlap."""

    return any(
        left_occurrence.overlaps(right_occurrence)
        for left_occurrence in left.occurrences()
        for right_occurrence in right.occurrences()
    )


def _resource_timing_violations(
    *,
    sessions: tuple[ScheduledSession, ...],
    resource_ids: Callable[[ScheduledSession], tuple[UUID, ...]],
    policy: SchedulingPolicy,
    gap_code: SoftConstraintCode,
) -> list[SoftConstraintViolation]:
    """Detect excessive gaps and consecutive sequences for a resource class."""

    grouped: dict[tuple[UUID, date], list[tuple[ScheduledSession, TimeWindow]]] = (
        defaultdict(list)
    )
    for session in sessions:
        for occurrence in session.occurrences():
            for resource_id in resource_ids(session):
                grouped[(resource_id, occurrence.starts_at.date())].append(
                    (session, occurrence)
                )

    violations: list[SoftConstraintViolation] = []
    for (resource_id, _day), values in grouped.items():
        ordered = sorted(values, key=lambda value: value[1].starts_at)
        consecutive_ids: list[UUID] = []
        previous_occurrence: TimeWindow | None = None
        previous_session: ScheduledSession | None = None
        for session, occurrence in ordered:
            if previous_occurrence is None:
                consecutive_ids = [session.id]
            else:
                gap = occurrence.starts_at - previous_occurrence.ends_at
                if gap <= policy.consecutive_break_threshold:
                    consecutive_ids.append(session.id)
                else:
                    consecutive_ids = [session.id]
                if gap > policy.preferred_gap_limit and previous_session is not None:
                    violations.append(
                        SoftConstraintViolation(
                            code=gap_code,
                            session_ids=(previous_session.id, session.id),
                            resource_id=resource_id,
                            penalty=policy.penalty_per_violation,
                            explanation="Gap between sessions exceeds the preference.",
                        )
                    )
            if len(consecutive_ids) == policy.maximum_consecutive_sessions + 1:
                violations.append(
                    SoftConstraintViolation(
                        code=SoftConstraintCode.MAXIMUM_CONSECUTIVE,
                        session_ids=tuple(consecutive_ids),
                        resource_id=resource_id,
                        penalty=policy.penalty_per_violation,
                        explanation="Consecutive-session preference was exceeded.",
                    )
                )
            previous_occurrence = occurrence
            previous_session = session
    return violations


def _weekly_balance_violations(
    *,
    sessions: tuple[ScheduledSession, ...],
    policy: SchedulingPolicy,
) -> list[SoftConstraintViolation]:
    """Penalize required-group weekday distributions differing by over one."""

    counts: dict[UUID, dict[int, list[UUID]]] = defaultdict(lambda: defaultdict(list))
    for session in sessions:
        for occurrence in session.occurrences():
            weekday = occurrence.starts_at.isoweekday()
            if weekday > 5:
                continue
            for group_id in session.required_group_ids:
                counts[group_id][weekday].append(session.id)

    violations: list[SoftConstraintViolation] = []
    for group_id, by_weekday in counts.items():
        weekday_counts = [len(by_weekday.get(weekday, [])) for weekday in range(1, 6)]
        if max(weekday_counts, default=0) - min(weekday_counts, default=0) <= 1:
            continue
        session_ids = tuple(
            sorted(
                {
                    session_id
                    for identifiers in by_weekday.values()
                    for session_id in identifiers
                },
                key=str,
            )
        )
        violations.append(
            SoftConstraintViolation(
                code=SoftConstraintCode.WEEKLY_BALANCE,
                session_ids=session_ids,
                resource_id=group_id,
                penalty=policy.penalty_per_violation,
                explanation="Required sessions are unevenly distributed by weekday.",
            )
        )
    return violations


__all__ = [
    "detect_hard_conflicts",
    "detect_soft_constraint_violations",
]
