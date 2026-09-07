"""Ports owned by people and membership application capabilities."""

from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from people.application.contracts import AcceptedStudentRegistrationCommand
from people.application.contracts import AcceptedStudentRegistrationResult
from people.domain.models import GuardianRelationship
from people.domain.models import Membership
from people.domain.models import Person
from people.domain.models import PersonProfile
from people.domain.models import ProfileKind


class PeopleRepository(Protocol):
    """Persist sensitive people state behind tenant-scoped operations."""

    async def add_person(
        self,
        person: Person,
    ) -> None:
        """Create one person and their encrypted contact methods."""
        ...

    async def get_person(
        self,
        *,
        organization_id: UUID,
        person_id: UUID,
    ) -> Person | None:
        """Return a person only when both tenant and identifier match."""
        ...

    async def list_people(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> list[Person]:
        """List bounded people summaries under one exact tenant context."""
        ...

    async def person_exists(
        self,
        *,
        organization_id: UUID,
        person_id: UUID,
    ) -> bool:
        """Check a person reference without disclosing sensitive state."""
        ...

    async def add_profile(
        self,
        profile: PersonProfile,
    ) -> None:
        """Create one simultaneous person profile inside its tenant."""
        ...

    async def get_profile(
        self,
        *,
        organization_id: UUID,
        profile_id: UUID,
        kind: ProfileKind,
    ) -> PersonProfile | None:
        """Return a matching tenant profile of the required kind."""
        ...

    async def list_profiles(
        self,
        *,
        organization_id: UUID,
        kind: ProfileKind,
        limit: int,
        offset: int,
    ) -> list[PersonProfile]:
        """List one profile kind only within the supplied organization."""
        ...

    async def add_guardian_relationship(
        self,
        relationship: GuardianRelationship,
    ) -> None:
        """Create one same-tenant guardian-to-student relationship."""
        ...


class PeopleReferenceRepository(Protocol):
    """Resolve narrow, non-sensitive People references for other modules."""

    async def existing_teacher_profile_ids(
        self,
        *,
        organization_id: UUID,
        teacher_profile_ids: frozenset[UUID],
    ) -> frozenset[UUID]:
        """Return matching teacher profile IDs without exposing profile data."""
        ...

    async def existing_student_profile_ids(
        self,
        *,
        organization_id: UUID,
        student_profile_ids: frozenset[UUID],
    ) -> frozenset[UUID]:
        """Return matching student profile IDs without exposing profile data."""
        ...


class ProfileActivationWriter(Protocol):
    """Atomically persist an activating profile and its publication fact."""

    async def add_profile_with_activation(
        self,
        *,
        profile: PersonProfile,
        actor_subject_id: UUID,
        correlation_id: str,
    ) -> None:
        """Persist one profile and any required activation event atomically."""
        ...


class AcceptedStudentRegistrationWriter(Protocol):
    """Persist one accepted student and its idempotency binding atomically."""

    async def register_accepted_student(
        self,
        *,
        command: AcceptedStudentRegistrationCommand,
        person: Person,
        profile: PersonProfile,
    ) -> AcceptedStudentRegistrationResult:
        """Create or resolve the exact People records for a conversion key."""
        ...


class AcceptedStudentRegistrar(Protocol):
    """Expose the public People accepted-student application capability."""

    async def register_accepted_student(
        self,
        command: AcceptedStudentRegistrationCommand,
    ) -> AcceptedStudentRegistrationResult:
        """Create or resolve one student activation idempotently."""
        ...


class MembershipRepository(Protocol):
    """Persist identity-to-tenant relationships and their role sets."""

    async def add(
        self,
        membership: Membership,
    ) -> None:
        """Create one membership with all roles atomically."""
        ...

    async def mutate_existing(
        self,
        *,
        organization_id: UUID,
        membership_id: UUID,
        mutation: Callable[[Membership], Membership],
    ) -> Membership:
        """Lock, revalidate, and mutate one existing tenant membership atomically."""
        ...

    async def mutate_owner(
        self,
        *,
        organization_id: UUID,
        membership_id: UUID,
        mutation: Callable[[Membership, tuple[Membership, ...]], Membership],
    ) -> Membership:
        """Serialize one owner mutation against the tenant's complete owner set."""
        ...

    async def get(
        self,
        *,
        organization_id: UUID,
        membership_id: UUID,
    ) -> Membership | None:
        """Return a membership only when its tenant and identifier match."""
        ...

    async def get_for_identity(
        self,
        *,
        organization_id: UUID,
        identity_subject_id: UUID,
    ) -> Membership | None:
        """Return one identity's membership in exactly one organization."""
        ...

    async def list_for_identity(
        self,
        *,
        identity_subject_id: UUID,
    ) -> list[Membership]:
        """List active memberships under verified-subject PostgreSQL context."""
        ...

    async def list_for_organization(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> list[Membership]:
        """List bounded membership governance state for exactly one tenant."""
        ...

    async def list_owners_for_organization(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> list[Membership]:
        """List bounded owner lifecycle state for one exact organization."""
        ...


class OrganizationAvailability(Protocol):
    """Expose lifecycle availability without organization persistence access."""

    async def is_active(
        self,
        *,
        organization_id: UUID,
    ) -> bool:
        """Return whether ordinary membership context may be established."""
        ...


class PeopleAuditSink(Protocol):
    """Record privacy-minimized people and access governance outcomes."""

    async def record_people_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        target_id: UUID,
        correlation_id: str,
        outcome: str,
    ) -> None:
        """Append one event without contact, PIN, date, or profile values."""
        ...


__all__ = [
    "AcceptedStudentRegistrar",
    "AcceptedStudentRegistrationWriter",
    "MembershipRepository",
    "OrganizationAvailability",
    "PeopleAuditSink",
    "PeopleReferenceRepository",
    "PeopleRepository",
    "ProfileActivationWriter",
]
