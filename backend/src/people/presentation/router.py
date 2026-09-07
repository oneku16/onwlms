"""Thin FastAPI routes and safe serializers for people and memberships."""

from datetime import date
from typing import Annotated
from typing import cast
from uuid import UUID

from fastapi import APIRouter
from fastapi import Query
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic import Field

from core.context import PlatformActorContext
from core.context import TenantActorContext
from core.errors import AuthorizationError
from identity import ActorDep
from identity import CSRFDep
from identity import CurrentSessionDep
from people.application.service import ContactInput
from people.application.service import MembershipService
from people.application.service import PeopleService
from people.domain.models import ContactKind
from people.domain.models import ContactMethod
from people.domain.models import GuardianRelationship
from people.domain.models import Membership
from people.domain.models import MembershipRole
from people.domain.models import Person
from people.domain.models import PersonProfile
from people.domain.models import ProfileKind

router = APIRouter(prefix="/api/v1", tags=["people"])


class ContactRequest(BaseModel):
    """Validate one sensitive contact method input."""

    kind: ContactKind
    value: str = Field(min_length=1, max_length=320)
    label: str | None = Field(default=None, max_length=80)
    is_primary: bool = False
    whatsapp_capable: bool = False


class CreatePersonRequest(BaseModel):
    """Validate a tenant-owned person creation request."""

    given_name: str = Field(min_length=1, max_length=120)
    family_name: str = Field(min_length=1, max_length=120)
    preferred_name: str | None = Field(default=None, max_length=120)
    national_identifier: str | None = Field(default=None, min_length=3, max_length=64)
    date_of_birth: date | None = None
    contacts: list[ContactRequest] = Field(default_factory=list, max_length=20)


class CreateProfileRequest(BaseModel):
    """Validate a student, staff, teacher, or guardian profile request."""

    kind: ProfileKind
    reference_number: str | None = Field(default=None, max_length=80)
    title: str | None = Field(default=None, max_length=120)


class CreateGuardianRelationshipRequest(BaseModel):
    """Validate a guardian-to-student profile relationship request."""

    guardian_profile_id: UUID
    student_profile_id: UUID
    relationship_label: str = Field(min_length=1, max_length=80)


class CreateMembershipRequest(BaseModel):
    """Validate a multi-role organization membership request."""

    identity_subject_id: UUID
    person_id: UUID | None = None
    roles: frozenset[MembershipRole] = Field(min_length=1)


class ReplaceRolesRequest(BaseModel):
    """Validate complete replacement of a membership role set."""

    roles: frozenset[MembershipRole] = Field(min_length=1)


class AppointOwnerRequest(BaseModel):
    """Validate platform appointment of an organization owner."""

    identity_subject_id: UUID
    person_id: UUID | None = None


def _people(request: Request) -> PeopleService:
    """Return the explicitly composed people service."""

    return cast(PeopleService, request.app.state.people_service)


def _memberships(request: Request) -> MembershipService:
    """Return the explicitly composed membership service."""

    return cast(MembershipService, request.app.state.membership_service)


def _tenant_actor(
    actor: PlatformActorContext | TenantActorContext,
) -> TenantActorContext:
    """Require a verified tenant membership context."""

    if not isinstance(actor, TenantActorContext):
        raise AuthorizationError
    return actor


def _platform_actor(
    actor: PlatformActorContext | TenantActorContext,
) -> PlatformActorContext:
    """Require separately established platform actor context."""

    if not isinstance(actor, PlatformActorContext):
        raise AuthorizationError
    return actor


def _masked_contact(contact: ContactMethod) -> str:
    """Mask a contact value so list responses do not disclose raw PII."""

    if contact.kind is ContactKind.EMAIL:
        local, domain = contact.value.split("@", maxsplit=1)
        return f"{local[:1]}***@{domain}"
    if contact.kind is ContactKind.PHONE:
        return f"***{contact.value[-4:]}"
    return f"@{contact.value.removeprefix('@')[:1]}***"


def serialize_person_safe(person: Person) -> dict[str, object]:
    """Serialize person identity while excluding PIN, birth date, and raw contacts."""

    return {
        "id": str(person.id),
        "organization_id": str(person.organization_id),
        "display_name": person.preferred_name
        or f"{person.given_name} {person.family_name}",
        "given_name": person.given_name,
        "family_name": person.family_name,
        "preferred_name": person.preferred_name,
        "contacts": [
            {
                "id": str(contact.id),
                "kind": contact.kind.value,
                "masked_value": _masked_contact(contact),
                "label": contact.label,
                "is_primary": contact.is_primary,
                "whatsapp_capable": contact.whatsapp_capable,
            }
            for contact in person.contacts
        ],
    }


def serialize_profile_safe(profile: PersonProfile) -> dict[str, object]:
    """Serialize profile metadata without local reference numbers."""

    return {
        "id": str(profile.id),
        "organization_id": str(profile.organization_id),
        "person_id": str(profile.person_id),
        "kind": profile.kind.value,
        "title": profile.title,
    }


def serialize_profile_directory_entry(profile: PersonProfile) -> dict[str, object]:
    """Serialize a profile collection entry without its local reference number."""

    return {
        **serialize_profile_safe(profile),
        "display_name": profile.title or f"{profile.kind.value.title()} profile",
    }


def serialize_membership_safe(membership: Membership) -> dict[str, object]:
    """Serialize membership authorization state without OwnID claims."""

    return {
        "id": str(membership.id),
        "organization_id": str(membership.organization_id),
        "identity_subject_id": str(membership.identity_subject_id),
        "person_id": str(membership.person_id) if membership.person_id else None,
        "roles": sorted(role.value for role in membership.roles),
        "status": membership.status.value,
    }


def serialize_membership_discovery(membership: Membership) -> dict[str, object]:
    """Serialize active tenant access without subject, person, or PII fields."""

    return {
        "id": str(membership.id),
        "organization_id": str(membership.organization_id),
        "roles": sorted(role.value for role in membership.roles),
        "status": membership.status.value,
    }


def serialize_guardian_relationship_safe(
    relationship: GuardianRelationship,
) -> dict[str, object]:
    """Serialize guardian relationship identifiers without person details."""

    return {
        "id": str(relationship.id),
        "organization_id": str(relationship.organization_id),
        "guardian_profile_id": str(relationship.guardian_profile_id),
        "student_profile_id": str(relationship.student_profile_id),
        "relationship_label": relationship.relationship_label,
    }


@router.post("/people", status_code=status.HTTP_201_CREATED)
async def create_person(
    payload: CreatePersonRequest,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> JSONResponse:
    """Create one person in the verified tenant context."""

    person = await _people(request).create_person(
        actor=_tenant_actor(actor),
        given_name=payload.given_name,
        family_name=payload.family_name,
        preferred_name=payload.preferred_name,
        national_identifier=payload.national_identifier,
        date_of_birth=payload.date_of_birth,
        contacts=tuple(
            ContactInput(
                kind=contact.kind,
                value=contact.value,
                label=contact.label,
                is_primary=contact.is_primary,
                whatsapp_capable=contact.whatsapp_capable,
            )
            for contact in payload.contacts
        ),
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=serialize_person_safe(person),
    )


@router.get("/people/{person_id}")
async def get_person(
    person_id: UUID,
    request: Request,
    actor: ActorDep,
) -> JSONResponse:
    """Return one safely serialized person through tenant-scoped lookup."""

    person = await _people(request).get_person(
        actor=_tenant_actor(actor),
        person_id=person_id,
    )
    return JSONResponse(serialize_person_safe(person))


@router.get("/organizations/current/people")
async def list_people(
    request: Request,
    actor: ActorDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    """List safely serialized people inside the current organization."""

    people = await _people(request).list_people(
        actor=_tenant_actor(actor),
        limit=limit,
        offset=offset,
    )
    return JSONResponse([serialize_person_safe(person) for person in people])


async def _list_profiles_by_kind(
    *,
    request: Request,
    actor: PlatformActorContext | TenantActorContext,
    kind: ProfileKind,
    limit: int,
    offset: int,
) -> JSONResponse:
    """List one safely serialized profile kind for a tenant collection route."""

    profiles = await _people(request).list_profiles(
        actor=_tenant_actor(actor),
        kind=kind,
        limit=limit,
        offset=offset,
    )
    return JSONResponse(
        [serialize_profile_directory_entry(profile) for profile in profiles]
    )


@router.get("/organizations/current/students")
async def list_students(
    request: Request,
    actor: ActorDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    """List student profiles in the current organization."""

    return await _list_profiles_by_kind(
        request=request,
        actor=actor,
        kind=ProfileKind.STUDENT,
        limit=limit,
        offset=offset,
    )


@router.get("/organizations/current/teachers")
async def list_teachers(
    request: Request,
    actor: ActorDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    """List teacher profiles in the current organization."""

    return await _list_profiles_by_kind(
        request=request,
        actor=actor,
        kind=ProfileKind.TEACHER,
        limit=limit,
        offset=offset,
    )


@router.get("/organizations/current/staff")
async def list_staff(
    request: Request,
    actor: ActorDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    """List staff profiles in the current organization."""

    return await _list_profiles_by_kind(
        request=request,
        actor=actor,
        kind=ProfileKind.STAFF,
        limit=limit,
        offset=offset,
    )


@router.get("/organizations/current/guardians")
async def list_guardians(
    request: Request,
    actor: ActorDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    """List guardian profiles in the current organization."""

    return await _list_profiles_by_kind(
        request=request,
        actor=actor,
        kind=ProfileKind.GUARDIAN,
        limit=limit,
        offset=offset,
    )


@router.post("/people/{person_id}/profiles", status_code=status.HTTP_201_CREATED)
async def create_profile(
    person_id: UUID,
    payload: CreateProfileRequest,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> JSONResponse:
    """Create one simultaneous profile for a tenant person."""

    profile = await _people(request).add_profile(
        actor=_tenant_actor(actor),
        person_id=person_id,
        kind=payload.kind,
        reference_number=payload.reference_number,
        title=payload.title,
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=serialize_profile_safe(profile),
    )


@router.post("/guardian-relationships", status_code=status.HTTP_201_CREATED)
async def create_guardian_relationship(
    payload: CreateGuardianRelationshipRequest,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> JSONResponse:
    """Create one same-tenant guardian-to-student relationship."""

    relationship = await _people(request).link_guardian(
        actor=_tenant_actor(actor),
        guardian_profile_id=payload.guardian_profile_id,
        student_profile_id=payload.student_profile_id,
        relationship_label=payload.relationship_label,
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=serialize_guardian_relationship_safe(relationship),
    )


@router.post("/memberships", status_code=status.HTTP_201_CREATED)
async def create_membership(
    payload: CreateMembershipRequest,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> JSONResponse:
    """Create one multi-role membership inside the verified tenant."""

    membership = await _memberships(request).create_membership(
        actor=_tenant_actor(actor),
        identity_subject_id=payload.identity_subject_id,
        person_id=payload.person_id,
        roles=payload.roles,
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=serialize_membership_safe(membership),
    )


@router.put("/memberships/{membership_id}/roles")
async def replace_membership_roles(
    membership_id: UUID,
    payload: ReplaceRolesRequest,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> JSONResponse:
    """Replace one membership's complete built-in role set."""

    membership = await _memberships(request).replace_roles(
        actor=_tenant_actor(actor),
        membership_id=membership_id,
        roles=payload.roles,
    )
    return JSONResponse(serialize_membership_safe(membership))


@router.post(
    "/platform/organizations/{organization_id}/owner",
    status_code=status.HTTP_201_CREATED,
)
async def appoint_organization_owner(
    organization_id: UUID,
    payload: AppointOwnerRequest,
    request: Request,
    actor: ActorDep,
    _csrf: CSRFDep,
) -> JSONResponse:
    """Appoint one owner through separately authorized platform context."""

    membership = await _memberships(request).appoint_organization_owner(
        actor=_platform_actor(actor),
        organization_id=organization_id,
        identity_subject_id=payload.identity_subject_id,
        person_id=payload.person_id,
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=serialize_membership_safe(membership),
    )


@router.get("/auth/memberships")
async def list_current_memberships(
    request: Request,
    current: CurrentSessionDep,
) -> JSONResponse:
    """List only the signed-in subject's active memberships without PII."""

    memberships = await _memberships(request).list_active_memberships(
        identity_subject_id=current.subject.id,
    )
    return JSONResponse(
        [serialize_membership_discovery(membership) for membership in memberships]
    )


__all__ = [
    "router",
    "serialize_guardian_relationship_safe",
    "serialize_membership_discovery",
    "serialize_membership_safe",
    "serialize_person_safe",
    "serialize_profile_directory_entry",
    "serialize_profile_safe",
]
