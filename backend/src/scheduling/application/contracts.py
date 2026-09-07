"""Scheduling-owned contracts for cross-module reference validation."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ExistingSchedulingReferences:
    """Identify requested resources that exist in one exact tenant."""

    organization_id: UUID
    room_ids: frozenset[UUID]
    course_offering_ids: frozenset[UUID]
    group_ids: frozenset[UUID]
    teacher_ids: frozenset[UUID]


__all__ = ["ExistingSchedulingReferences"]
