"""Deterministic first scheduling heuristic with explicit limitations."""

from decimal import Decimal
from uuid import NAMESPACE_URL
from uuid import UUID
from uuid import uuid5

from scheduling.domain.constraints import detect_hard_conflicts
from scheduling.domain.constraints import detect_soft_constraint_violations
from scheduling.domain.models import ActivityRequest
from scheduling.domain.models import CandidateSlot
from scheduling.domain.models import HardConflict
from scheduling.domain.models import HardConstraintCode
from scheduling.domain.models import RoomSpecification
from scheduling.domain.models import ScheduledSession
from scheduling.domain.models import ScheduleGenerationRequest
from scheduling.domain.models import ScheduleGenerationResult


class DeterministicHeuristicSchedulingGenerator:
    """Place scarce activities by hard feasibility and incremental soft cost."""

    def generate(
        self,
        request: ScheduleGenerationRequest,
    ) -> ScheduleGenerationResult:
        """Preserve locks, greedily place activities, then score preferences."""

        locked_sessions = tuple(
            sorted(
                (
                    session
                    for session in request.existing_sessions
                    if session.id in request.locked_session_ids
                ),
                key=_session_order,
            )
        )
        proposed: list[ScheduledSession] = list(locked_sessions)
        unresolved: list[HardConflict] = []
        for index, locked in enumerate(locked_sessions):
            unresolved.extend(
                detect_hard_conflicts(
                    candidate=locked,
                    existing_sessions=locked_sessions[:index],
                    context=request.constraints,
                )
            )

        slots = tuple(sorted(request.candidate_slots, key=_slot_order))
        rooms = tuple(
            sorted(
                request.constraints.rooms,
                key=lambda room: str(room.room_id),
            )
        )
        ordered_activities = sorted(
            request.activities,
            key=lambda activity: (
                self._feasible_placement_count(
                    activity=activity,
                    ordinal=_locked_activity_count(activity, locked_sessions),
                    slots=slots,
                    rooms=rooms,
                    proposed=locked_sessions,
                    request=request,
                ),
                str(activity.id),
            ),
        )
        for activity in ordered_activities:
            already_locked = sum(
                1 for session in locked_sessions if session.activity_id == activity.id
            )
            for ordinal in range(already_locked, activity.sessions_required):
                generated, blocked_conflicts = self._place_activity(
                    activity=activity,
                    ordinal=ordinal,
                    slots=slots,
                    rooms=rooms,
                    proposed=tuple(proposed),
                    request=request,
                )
                if generated is None:
                    detail = _blocked_conflict_detail(blocked_conflicts)
                    unresolved.append(
                        HardConflict(
                            code=HardConstraintCode.UNSCHEDULED_ACTIVITY,
                            session_ids=(),
                            resource_id=activity.id,
                            explanation=(
                                "No candidate slot and room satisfy all hard "
                                f"constraints.{detail}"
                            ),
                        )
                    )
                    continue
                proposed.append(generated)

        ordered_proposal = tuple(sorted(proposed, key=_session_order))
        soft_violations = detect_soft_constraint_violations(
            sessions=ordered_proposal,
            policy=request.policy,
        )
        hard_penalty = Decimal(25) * len(unresolved)
        soft_penalty = sum(
            (violation.penalty for violation in soft_violations),
            start=Decimal(0),
        )
        score = max(Decimal(0), Decimal(100) - hard_penalty - soft_penalty)
        return ScheduleGenerationResult(
            proposed_sessions=ordered_proposal,
            unresolved_hard_conflicts=tuple(unresolved),
            soft_constraint_violations=soft_violations,
            quality_score=score,
            explanation=(
                f"Deterministic heuristic placed {len(ordered_proposal)} sessions; "
                f"{len(unresolved)} hard conflicts remain and "
                f"{len(soft_violations)} preference violations were scored."
            ),
            locked_session_ids=request.locked_session_ids,
            expected_versions=tuple(
                sorted(
                    (
                        (session.id, session.version)
                        for session in request.existing_sessions
                    ),
                    key=lambda item: str(item[0]),
                )
            ),
        )

    @classmethod
    def _place_activity(
        cls,
        *,
        activity: ActivityRequest,
        ordinal: int,
        slots: tuple[CandidateSlot, ...],
        rooms: tuple[RoomSpecification, ...],
        proposed: tuple[ScheduledSession, ...],
        request: ScheduleGenerationRequest,
    ) -> tuple[ScheduledSession | None, tuple[HardConflict, ...]]:
        """Choose the hard-feasible candidate with least incremental soft cost."""

        feasible: list[tuple[Decimal, tuple[object, ...], ScheduledSession]] = []
        blocked: list[HardConflict] = []
        baseline_penalty = _soft_penalty(
            sessions=proposed,
            request=request,
        )
        for slot, room, candidate, conflicts in cls._candidate_attempts(
            activity=activity,
            ordinal=ordinal,
            slots=slots,
            rooms=rooms,
            proposed=proposed,
            request=request,
        ):
            if conflicts:
                blocked.extend(conflicts)
                continue
            incremental_penalty = (
                _soft_penalty(
                    sessions=(*proposed, candidate),
                    request=request,
                )
                - baseline_penalty
            )
            feasible.append(
                (
                    incremental_penalty,
                    (*_slot_order(slot), str(room.room_id), str(candidate.id)),
                    candidate,
                )
            )
        if not feasible:
            return None, tuple(blocked)
        return min(feasible, key=lambda item: (item[0], item[1]))[2], ()

    @classmethod
    def _feasible_placement_count(
        cls,
        *,
        activity: ActivityRequest,
        ordinal: int,
        slots: tuple[CandidateSlot, ...],
        rooms: tuple[RoomSpecification, ...],
        proposed: tuple[ScheduledSession, ...],
        request: ScheduleGenerationRequest,
    ) -> int:
        """Count hard-feasible slot/room placements for activity scarcity."""

        return sum(
            not conflicts
            for _slot, _room, _candidate, conflicts in cls._candidate_attempts(
                activity=activity,
                ordinal=ordinal,
                slots=slots,
                rooms=rooms,
                proposed=proposed,
                request=request,
            )
        )

    @staticmethod
    def _candidate_attempts(
        *,
        activity: ActivityRequest,
        ordinal: int,
        slots: tuple[CandidateSlot, ...],
        rooms: tuple[RoomSpecification, ...],
        proposed: tuple[ScheduledSession, ...],
        request: ScheduleGenerationRequest,
    ) -> tuple[
        tuple[
            CandidateSlot,
            RoomSpecification,
            ScheduledSession,
            tuple[HardConflict, ...],
        ],
        ...,
    ]:
        """Enumerate stable candidate placements with their hard conflicts."""

        attempts: list[
            tuple[
                CandidateSlot,
                RoomSpecification,
                ScheduledSession,
                tuple[HardConflict, ...],
            ]
        ] = []
        for slot in slots:
            session_end = slot.starts_at + activity.duration
            if session_end > slot.ends_at:
                continue
            for room in rooms:
                candidate = ScheduledSession(
                    id=_proposal_id(
                        organization_id=request.organization_id,
                        activity_id=activity.id,
                        ordinal=ordinal,
                        slot_id=slot.id,
                        room_id=room.room_id,
                    ),
                    organization_id=request.organization_id,
                    activity_id=activity.id,
                    course_offering_id=activity.course_offering_id,
                    room_id=room.room_id,
                    teacher_ids=activity.teacher_ids,
                    group_ids=activity.group_ids,
                    required_group_ids=activity.required_group_ids,
                    starts_at=slot.starts_at,
                    ends_at=session_end,
                    activity_type=activity.activity_type,
                    required_room_type=activity.required_room_type,
                    expected_attendance=activity.expected_attendance,
                )
                attempts.append(
                    (
                        slot,
                        room,
                        candidate,
                        detect_hard_conflicts(
                            candidate=candidate,
                            existing_sessions=proposed,
                            context=request.constraints,
                        ),
                    )
                )
        return tuple(attempts)


def _locked_activity_count(
    activity: ActivityRequest,
    locked_sessions: tuple[ScheduledSession, ...],
) -> int:
    """Return how many required sessions are already represented by locks."""

    return sum(1 for session in locked_sessions if session.activity_id == activity.id)


def _soft_penalty(
    *,
    sessions: tuple[ScheduledSession, ...],
    request: ScheduleGenerationRequest,
) -> Decimal:
    """Return total named soft penalty for one partial proposal."""

    return sum(
        (
            violation.penalty
            for violation in detect_soft_constraint_violations(
                sessions=tuple(sorted(sessions, key=_session_order)),
                policy=request.policy,
            )
        ),
        start=Decimal(0),
    )


def _blocked_conflict_detail(conflicts: tuple[HardConflict, ...]) -> str:
    """Summarize deterministic observed conflict facts without losing their names."""

    facts = tuple(
        dict.fromkeys(
            (
                conflict.code.value,
                str(conflict.resource_id) if conflict.resource_id is not None else None,
                conflict.explanation,
            )
            for conflict in conflicts
        )
    )
    if not facts:
        return ""
    rendered = "; ".join(
        f"{code}"
        + (f" for {resource_id}" if resource_id is not None else "")
        + f": {explanation}"
        for code, resource_id, explanation in facts
    )
    return f" Observed conflicts: {rendered}"


def _proposal_id(
    *,
    organization_id: UUID,
    activity_id: UUID,
    ordinal: int,
    slot_id: UUID,
    room_id: UUID,
) -> UUID:
    """Create a stable non-persistent identifier for a deterministic proposal."""

    value = ":".join(
        (
            str(organization_id),
            str(activity_id),
            str(ordinal),
            str(slot_id),
            str(room_id),
        )
    )
    return uuid5(NAMESPACE_URL, value)


def _slot_order(slot: CandidateSlot) -> tuple[object, ...]:
    """Return stable ordering keys for candidate slots."""

    return (slot.starts_at, slot.ends_at, str(slot.id))


def _session_order(session: ScheduledSession) -> tuple[object, ...]:
    """Return stable ordering keys for proposed and locked sessions."""

    return (session.starts_at, session.ends_at, str(session.id))


__all__ = ["DeterministicHeuristicSchedulingGenerator"]
