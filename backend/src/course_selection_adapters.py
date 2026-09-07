"""Cross-module adapter for student-owned course-selection submission."""

from uuid import UUID

from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import NotFoundError
from people.application.read_service import PeopleOwnershipReadService
from people.domain.models import ProfileKind


class CourseSelectionStudentOwnershipAdapter:
    """Resolve the actor's student profile through People's public read service."""

    def __init__(self, people: PeopleOwnershipReadService) -> None:
        self._people = people

    async def actor_owns_student_profile(
        self,
        *,
        actor: TenantActorContext,
        student_profile_id: UUID,
    ) -> bool:
        """Fail closed unless the active membership owns the exact profile."""

        try:
            profile = await self._people.resolve_actor_profile(
                actor=actor,
                kind=ProfileKind.STUDENT,
            )
        except AuthorizationError, NotFoundError:
            return False
        return profile.profile_id == student_profile_id


__all__ = ["CourseSelectionStudentOwnershipAdapter"]
