"""Shared portal and MCP reads preserve profile and assignment ownership."""

from typing import cast
from uuid import UUID
from uuid import uuid7

import pytest

from academics.application.read_ports import AcademicSelfServiceReadRepository
from academics.application.read_service import AcademicSelfServiceReadService
from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import NotFoundError
from grading.application.read_service import OfficialGradingReadService
from integrations.application.read_service import IntegrationSelfServiceReadService
from mcp_gateway.application.owned_read_service import ActorOwnedReadService
from people.application.read_models import OwnedProfileSummary
from people.application.read_ports import PeopleOwnershipReadRepository
from people.application.read_service import GUARDIAN_LINKED_READ
from people.application.read_service import TEACHER_ASSIGNED_READ
from people.application.read_service import PeopleOwnershipReadService
from people.domain.models import ProfileKind
from scheduling.application.read_service import OwnedTimetableReadService


class FakeMembershipPersonResolver:
    """Return the person re-read from one active membership."""

    def __init__(
        self,
        person_id: UUID,
    ) -> None:
        self.person_id = person_id

    async def resolve_person_id(
        self,
        *,
        actor: TenantActorContext,
    ) -> UUID:
        assert actor.organization_id
        return self.person_id


class FakePeopleOwnershipRepository:
    """Hold profiles and explicit guardian links for ownership tests."""

    def __init__(self) -> None:
        self.profiles: dict[UUID, OwnedProfileSummary] = {}
        self.guardian_links: dict[UUID, tuple[UUID, ...]] = {}
        self.roster_calls = 0

    async def get_profile_for_person(
        self,
        *,
        organization_id: UUID,
        person_id: UUID,
        kind: ProfileKind,
    ) -> OwnedProfileSummary | None:
        del organization_id
        return next(
            (
                profile
                for profile in self.profiles.values()
                if profile.person_id == person_id and profile.kind is kind
            ),
            None,
        )

    async def list_linked_students(
        self,
        *,
        organization_id: UUID,
        guardian_profile_id: UUID,
    ) -> tuple[OwnedProfileSummary, ...]:
        del organization_id
        return tuple(
            self.profiles[profile_id]
            for profile_id in self.guardian_links.get(guardian_profile_id, ())
        )

    async def list_student_summaries(
        self,
        *,
        organization_id: UUID,
        student_profile_ids: frozenset[UUID],
    ) -> tuple[OwnedProfileSummary, ...]:
        del organization_id
        self.roster_calls += 1
        return tuple(
            self.profiles[profile_id]
            for profile_id in sorted(student_profile_ids, key=str)
            if profile_id in self.profiles
        )


class FakeAcademicReadRepository:
    """Authorize exactly one teacher-section assignment."""

    def __init__(
        self,
        *,
        teacher_profile_id: UUID,
        section_id: UUID,
        student_profile_id: UUID,
    ) -> None:
        self.teacher_profile_id = teacher_profile_id
        self.section_id = section_id
        self.student_profile_id = student_profile_id

    async def list_section_student_profile_ids(
        self,
        *,
        organization_id: UUID,
        teacher_profile_id: UUID,
        section_id: UUID,
    ) -> tuple[UUID, ...] | None:
        del organization_id
        if (
            teacher_profile_id != self.teacher_profile_id
            or section_id != self.section_id
        ):
            return None
        return (self.student_profile_id,)


def _actor(
    organization_id: UUID,
    *permissions: str,
) -> TenantActorContext:
    return TenantActorContext(
        subject_id=uuid7(),
        organization_id=organization_id,
        membership_id=uuid7(),
        correlation_id="test-correlation",
        permissions=frozenset(permissions),
    )


def _teacher_reads() -> tuple[
    ActorOwnedReadService,
    TenantActorContext,
    UUID,
    UUID,
    FakePeopleOwnershipRepository,
]:
    organization_id = uuid7()
    teacher_person_id = uuid7()
    teacher_profile_id = uuid7()
    student_person_id = uuid7()
    student_profile_id = uuid7()
    section_id = uuid7()
    people_repository = FakePeopleOwnershipRepository()
    people_repository.profiles = {
        teacher_profile_id: OwnedProfileSummary(
            profile_id=teacher_profile_id,
            person_id=teacher_person_id,
            kind=ProfileKind.TEACHER,
            display_name="Teacher",
            institutional_reference="T-1",
        ),
        student_profile_id: OwnedProfileSummary(
            profile_id=student_profile_id,
            person_id=student_person_id,
            kind=ProfileKind.STUDENT,
            display_name="Student",
            institutional_reference="S-1",
        ),
    }
    people = PeopleOwnershipReadService(
        repository=cast(PeopleOwnershipReadRepository, people_repository),
        memberships=FakeMembershipPersonResolver(teacher_person_id),
    )
    academics = AcademicSelfServiceReadService(
        cast(
            AcademicSelfServiceReadRepository,
            FakeAcademicReadRepository(
                teacher_profile_id=teacher_profile_id,
                section_id=section_id,
                student_profile_id=student_profile_id,
            ),
        )
    )
    unused = object()
    reads = ActorOwnedReadService(
        people=people,
        academics=academics,
        grading=cast(OfficialGradingReadService, unused),
        scheduling=cast(OwnedTimetableReadService, unused),
        integrations=cast(IntegrationSelfServiceReadService, unused),
        clock=lambda: pytest.fail("clock should not be read"),
    )
    return (
        reads,
        _actor(organization_id, TEACHER_ASSIGNED_READ),
        section_id,
        student_person_id,
        people_repository,
    )


async def test_teacher_roster_requires_the_exact_assigned_section() -> None:
    reads, actor, _, _, people_repository = _teacher_reads()

    with pytest.raises(NotFoundError):
        await reads.section_students(actor=actor, section_id=uuid7())

    assert people_repository.roster_calls == 0


async def test_teacher_roster_returns_only_minimum_assigned_student_identity() -> None:
    reads, actor, section_id, student_person_id, _ = _teacher_reads()

    roster = await reads.section_students(actor=actor, section_id=section_id)

    assert len(roster) == 1
    assert roster[0].person_id == student_person_id
    assert roster[0].display_name == "Student"
    assert roster[0].institutional_reference == "S-1"


async def test_role_mismatch_cannot_resolve_another_profile_kind() -> None:
    reads, actor, _, _, _ = _teacher_reads()
    student_actor = _actor(actor.organization_id, "academics.student.read_own")

    with pytest.raises(AuthorizationError):
        await reads.section_students(actor=student_actor, section_id=uuid7())


async def test_guardian_directory_returns_only_explicit_relationships() -> None:
    organization_id = uuid7()
    guardian_person_id = uuid7()
    guardian_profile_id = uuid7()
    linked_profile_id = uuid7()
    unrelated_profile_id = uuid7()
    repository = FakePeopleOwnershipRepository()
    repository.profiles = {
        guardian_profile_id: OwnedProfileSummary(
            profile_id=guardian_profile_id,
            person_id=guardian_person_id,
            kind=ProfileKind.GUARDIAN,
            display_name="Guardian",
            institutional_reference=None,
        ),
        linked_profile_id: OwnedProfileSummary(
            profile_id=linked_profile_id,
            person_id=uuid7(),
            kind=ProfileKind.STUDENT,
            display_name="Linked",
            institutional_reference="S-1",
        ),
        unrelated_profile_id: OwnedProfileSummary(
            profile_id=unrelated_profile_id,
            person_id=uuid7(),
            kind=ProfileKind.STUDENT,
            display_name="Unrelated",
            institutional_reference="S-2",
        ),
    }
    repository.guardian_links[guardian_profile_id] = (linked_profile_id,)
    people = PeopleOwnershipReadService(
        repository=repository,
        memberships=FakeMembershipPersonResolver(guardian_person_id),
    )

    linked = await people.list_linked_students(
        actor=_actor(organization_id, GUARDIAN_LINKED_READ)
    )

    assert [student.profile_id for student in linked] == [linked_profile_id]
    assert unrelated_profile_id not in {student.profile_id for student in linked}
