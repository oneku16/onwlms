"""Minimum-data ownership projections exposed by the people module."""

from dataclasses import dataclass
from uuid import UUID

from people.domain.models import ProfileKind


@dataclass(frozen=True, slots=True)
class OwnedProfileSummary:
    """Identify one actor-owned or explicitly related tenant profile."""

    profile_id: UUID
    person_id: UUID
    kind: ProfileKind
    display_name: str
    institutional_reference: str | None


__all__ = ["OwnedProfileSummary"]
