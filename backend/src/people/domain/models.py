"""Tenant-owned people, contacts, memberships, profiles, and relationships."""

import re
from dataclasses import dataclass
from dataclasses import field
from datetime import date
from enum import StrEnum
from uuid import UUID

from core.context import TenantActorContext
from people.domain.exceptions import InvalidMembershipError
from people.domain.exceptions import InvalidPersonError


class ContactKind(StrEnum):
    """Supported contact channels stored as sensitive personal information."""

    EMAIL = "email"
    PHONE = "phone"
    TELEGRAM = "telegram"


class MembershipRole(StrEnum):
    """Built-in tenant roles that may be combined on one membership."""

    ORGANIZATION_OWNER = "organization_owner"
    ORGANIZATION_ADMIN = "organization_admin"
    STUDENT = "student"
    TEACHER = "teacher"
    GUARDIAN = "guardian"
    STAFF = "staff"
    GUEST = "guest"


class MembershipStatus(StrEnum):
    """Govern whether a subject may establish organization context."""

    ACTIVE = "active"
    SUSPENDED = "suspended"


class ProfileKind(StrEnum):
    """Supported simultaneous organization-specific person profiles."""

    STUDENT = "student"
    STAFF = "staff"
    TEACHER = "teacher"
    GUARDIAN = "guardian"


_SELF_NOTIFICATION_PERMISSIONS = frozenset(
    {
        "notifications.read_own",
        "notifications.preferences.manage_own",
        "notifications.delivery.retry_own",
    }
)


_TENANT_ADMIN_PERMISSIONS = (
    frozenset(
        {
            "organizations.read",
            "organizations.configure",
            "organizations.campuses.manage",
            "people.read",
            "people.manage",
            "people.memberships.manage",
            "people.guardians.manage",
            "academics.structure.manage",
            "academics.curriculum.manage",
            "academics.enrollment.manage",
            "academics.term.close",
            "academics.course_selection.submit",
            "academics.course_selection.approve",
            "academics.course_selection.override",
            "admissions.application.create",
            "admissions.application.submit",
            "admissions.document.manage",
            "admissions.review",
            "admissions.decision.manage",
            "admissions.policy.manage",
            "admissions.application.enroll",
            "grading.scale.manage",
            "grading.final_grade.record",
            "grading.final_grade.revise",
            "grading.transcript.read",
            "scheduling.session.manage",
            "scheduling.generate",
            "scheduling.generation.apply",
            "scheduling.read",
            "integrations.configure",
            "integrations.read",
            "provisioning.read",
            "provisioning.retry",
            "entitlements.read",
            "audit.read",
        }
    )
    | _SELF_NOTIFICATION_PERMISSIONS
)

# Self-service permissions are deliberately narrow and are usable only through
# application queries that also revalidate the addressed profile or assignment.
ROLE_PERMISSIONS: dict[MembershipRole, frozenset[str]] = {
    MembershipRole.ORGANIZATION_OWNER: _TENANT_ADMIN_PERMISSIONS
    | {"grading.final_grade.revise_closed_term"},
    MembershipRole.ORGANIZATION_ADMIN: _TENANT_ADMIN_PERMISSIONS,
    MembershipRole.STUDENT: frozenset(
        {
            "organizations.read",
            "academics.student.read_own",
            "academics.course_selection.submit",
            "grading.student.read_own",
            "scheduling.student.read_own",
            "integrations.moodle_deadlines.read_own",
            "entitlements.read",
        }
    )
    | _SELF_NOTIFICATION_PERMISSIONS,
    MembershipRole.TEACHER: frozenset(
        {
            "organizations.read",
            "academics.teacher.read_assigned",
            "scheduling.teacher.read_own",
            "integrations.grade_sync.read_assigned",
            "integrations.moodle_deadlines.read_own",
            "entitlements.read",
        }
    )
    | _SELF_NOTIFICATION_PERMISSIONS,
    MembershipRole.GUARDIAN: frozenset(
        {
            "organizations.read",
            "academics.guardian.read_linked",
            "grading.guardian.read_linked",
            "entitlements.read",
        }
    )
    | _SELF_NOTIFICATION_PERMISSIONS,
    MembershipRole.STAFF: frozenset(
        {
            "organizations.read",
            "people.read",
            "scheduling.read",
            "entitlements.read",
        }
    )
    | _SELF_NOTIFICATION_PERMISSIONS,
    MembershipRole.GUEST: frozenset(
        {
            "organizations.read",
            "entitlements.read",
        }
    )
    | _SELF_NOTIFICATION_PERMISSIONS,
}


@dataclass(frozen=True, slots=True)
class ContactMethod:
    """Represent one sensitive contact channel with explicit metadata."""

    id: UUID
    kind: ContactKind
    value: str = field(repr=False)
    label: str | None = None
    is_primary: bool = False
    whatsapp_capable: bool = False

    def __post_init__(self) -> None:
        """Validate contact shape without normalizing away user intent."""

        if self.label is not None and len(self.label) > 80:
            raise InvalidPersonError("Contact label is too long")
        if self.kind is ContactKind.EMAIL:
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", self.value):
                raise InvalidPersonError("Invalid email address")
            if self.whatsapp_capable:
                raise InvalidPersonError("Only phone contacts may support WhatsApp")
        elif self.kind is ContactKind.PHONE:
            if not re.fullmatch(r"\+[1-9][0-9]{6,14}", self.value):
                raise InvalidPersonError("Phone must use E.164 format")
        elif not re.fullmatch(r"@[A-Za-z0-9_]{5,32}", self.value):
            raise InvalidPersonError("Invalid Telegram username")


@dataclass(frozen=True, slots=True)
class Person:
    """Represent one organization-owned person while minimizing unsafe repr output."""

    id: UUID
    organization_id: UUID
    given_name: str
    family_name: str
    preferred_name: str | None = None
    national_identifier: str | None = field(default=None, repr=False)
    date_of_birth: date | None = field(default=None, repr=False)
    contacts: tuple[ContactMethod, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        """Validate names, sensitive identifiers, and contact uniqueness."""

        if not self.given_name.strip() or len(self.given_name) > 120:
            raise InvalidPersonError("Invalid given name")
        if not self.family_name.strip() or len(self.family_name) > 120:
            raise InvalidPersonError("Invalid family name")
        if self.preferred_name is not None and len(self.preferred_name) > 120:
            raise InvalidPersonError("Preferred name is too long")
        if self.national_identifier is not None:
            normalized_identifier = self.national_identifier.strip()
            if not 3 <= len(normalized_identifier) <= 64:
                raise InvalidPersonError("Invalid national identifier")
        if self.date_of_birth is not None and self.date_of_birth > date.today():
            raise InvalidPersonError("Date of birth cannot be in the future")
        contact_ids = {contact.id for contact in self.contacts}
        if len(contact_ids) != len(self.contacts):
            raise InvalidPersonError("Duplicate contact identifier")


@dataclass(frozen=True, slots=True)
class Membership:
    """Bind one global identity to one tenant with multiple authorization roles."""

    id: UUID
    organization_id: UUID
    identity_subject_id: UUID
    person_id: UUID | None
    roles: frozenset[MembershipRole]
    status: MembershipStatus = MembershipStatus.ACTIVE

    def __post_init__(self) -> None:
        """Require at least one tenant role and prohibit platform-role conflation."""

        if not self.roles:
            raise InvalidMembershipError("Membership requires at least one role")

    @property
    def permissions(self) -> frozenset[str]:
        """Return the union of permissions granted by all current built-in roles."""

        permissions: set[str] = set()
        for role in self.roles:
            permissions.update(ROLE_PERMISSIONS[role])
        return frozenset(permissions)

    def actor_context(
        self,
        *,
        correlation_id: str,
    ) -> TenantActorContext:
        """Bind an active membership to one immutable tenant actor context."""

        if self.status is not MembershipStatus.ACTIVE:
            raise InvalidMembershipError("Membership is not active")
        return TenantActorContext(
            subject_id=self.identity_subject_id,
            organization_id=self.organization_id,
            membership_id=self.id,
            correlation_id=correlation_id,
            permissions=self.permissions,
        )


@dataclass(frozen=True, slots=True)
class PersonProfile:
    """Represent one simultaneous tenant profile attached to a person."""

    id: UUID
    organization_id: UUID
    person_id: UUID
    kind: ProfileKind
    reference_number: str | None = field(default=None, repr=False)
    title: str | None = None

    def __post_init__(self) -> None:
        """Validate profile reference and display metadata."""

        if (
            self.reference_number is not None
            and not 1 <= len(self.reference_number) <= 80
        ):
            raise InvalidPersonError("Invalid profile reference")
        if self.title is not None and len(self.title) > 120:
            raise InvalidPersonError("Profile title is too long")


@dataclass(frozen=True, slots=True)
class GuardianRelationship:
    """Link a guardian profile to a student profile within one organization."""

    id: UUID
    organization_id: UUID
    guardian_profile_id: UUID
    student_profile_id: UUID
    relationship_label: str

    def __post_init__(self) -> None:
        """Validate a concise relationship label."""

        if not self.relationship_label.strip() or len(self.relationship_label) > 80:
            raise InvalidPersonError("Invalid guardian relationship label")


__all__ = [
    "ROLE_PERMISSIONS",
    "ContactKind",
    "ContactMethod",
    "GuardianRelationship",
    "Membership",
    "MembershipRole",
    "MembershipStatus",
    "Person",
    "PersonProfile",
    "ProfileKind",
]
