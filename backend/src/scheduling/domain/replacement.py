"""Generated timetable replacement invariants."""

from dataclasses import replace
from uuid import UUID

from scheduling.domain.exceptions import ScheduleVersionConflictError
from scheduling.domain.exceptions import SchedulingRuleError
from scheduling.domain.models import ScheduledSession


def prepare_generated_replacement(
    *,
    organization_id: UUID,
    current_sessions: tuple[ScheduledSession, ...],
    proposed_sessions: tuple[ScheduledSession, ...],
    asserted_locked_session_ids: frozenset[UUID],
    expected_versions: dict[UUID, int],
) -> tuple[ScheduledSession, ...]:
    """Validate one snapshot-bound replacement and assign authoritative versions."""

    proposed_by_id = {session.id: session for session in proposed_sessions}
    if len(proposed_by_id) != len(proposed_sessions):
        raise SchedulingRuleError("Generated schedule has duplicate sessions.")
    if any(session.organization_id != organization_id for session in proposed_sessions):
        raise SchedulingRuleError("Generated schedule tenant does not match.")

    current_by_id = {session.id: session for session in current_sessions}
    current_versions = {
        identifier: session.version for identifier, session in current_by_id.items()
    }
    if current_versions != expected_versions:
        raise ScheduleVersionConflictError(
            "Timetable changed after schedule generation."
        )

    if not asserted_locked_session_ids.issubset(current_by_id):
        raise ScheduleVersionConflictError(
            "An asserted locked timetable session no longer exists."
        )
    persisted_locked_session_ids = frozenset(
        session.id for session in current_sessions if session.locked
    )
    effective_locked_session_ids = (
        persisted_locked_session_ids | asserted_locked_session_ids
    )
    if any(
        proposed_by_id.get(identifier) != current_by_id[identifier]
        for identifier in effective_locked_session_ids
    ):
        raise ScheduleVersionConflictError(
            "Generated schedule changed a locked session."
        )

    prepared: list[ScheduledSession] = []
    for proposed in proposed_sessions:
        current = current_by_id.get(proposed.id)
        if current is None:
            if proposed.version != 0:
                raise ScheduleVersionConflictError(
                    "A new generated session must start at version zero."
                )
            prepared.append(proposed)
            continue
        if proposed.version != current.version:
            raise ScheduleVersionConflictError(
                "Generated proposal used an invalid session version."
            )
        if proposed.id in effective_locked_session_ids:
            prepared.append(current)
        else:
            prepared.append(replace(proposed, version=current.version + 1))
    return tuple(prepared)
