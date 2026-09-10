"""PostgreSQL adapters for encrypted people data and tenant memberships."""

import base64
import hashlib
import hmac
from collections.abc import Callable
from uuid import UUID

from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken
from sqlalchemy import Select
from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from people.domain.exceptions import InvalidMembershipError
from people.domain.exceptions import MembershipNotFoundError
from people.domain.exceptions import PeopleConflictError
from people.domain.exceptions import PeopleDataProtectionError
from people.domain.models import ContactKind
from people.domain.models import ContactMethod
from people.domain.models import GuardianRelationship
from people.domain.models import Membership
from people.domain.models import MembershipRole
from people.domain.models import MembershipStatus
from people.domain.models import Person
from people.domain.models import PersonProfile
from people.domain.models import ProfileKind
from people.infrastructure.models import ContactMethodModel
from people.infrastructure.models import GuardianRelationshipModel
from people.infrastructure.models import MembershipModel
from people.infrastructure.models import MembershipRoleModel
from people.infrastructure.models import PersonModel
from people.infrastructure.models import PersonProfileModel
from shared.database import Database

_NATIONAL_IDENTIFIER_DIGEST_DOMAIN = b"ownsis:people:national-identifier:v1"


class SQLAlchemyPeopleRepository:
    """Encrypt and tenant-scope person, contact, profile, and guardian state."""

    def __init__(
        self,
        *,
        database: Database,
        encryption_key: str,
    ) -> None:
        self._database = database
        self._fernet = Fernet(encryption_key.encode("ascii"))
        self._legacy_digest_key = base64.urlsafe_b64decode(
            encryption_key.encode("ascii")
        )
        self._digest_key = hmac.new(
            self._legacy_digest_key,
            _NATIONAL_IDENTIFIER_DIGEST_DOMAIN,
            hashlib.sha256,
        ).digest()

    async def add_person(
        self,
        person: Person,
    ) -> None:
        """Create a person while encrypting PIN and every contact value."""

        national_identifier = person.national_identifier
        national_identifier_digest = (
            self._digest(person.organization_id, national_identifier)
            if national_identifier is not None
            else None
        )
        try:
            async with self._database.session(
                organization_id=person.organization_id,
            ) as session:
                if national_identifier is not None:
                    existing_identifier = await session.scalar(
                        select(PersonModel.id)
                        .where(
                            PersonModel.organization_id == person.organization_id,
                            PersonModel.national_identifier_digest.in_(
                                (
                                    national_identifier_digest,
                                    self._legacy_digest(national_identifier),
                                )
                            ),
                        )
                        .limit(1)
                    )
                    if existing_identifier is not None:
                        raise PeopleConflictError(
                            "Person or national identifier already exists"
                        )
                session.add(
                    PersonModel(
                        id=person.id,
                        organization_id=person.organization_id,
                        given_name=person.given_name,
                        family_name=person.family_name,
                        preferred_name=person.preferred_name,
                        encrypted_national_identifier=(
                            self._encrypt(national_identifier)
                            if national_identifier is not None
                            else None
                        ),
                        national_identifier_digest=national_identifier_digest,
                        date_of_birth=person.date_of_birth,
                    )
                )
                for contact in person.contacts:
                    session.add(
                        ContactMethodModel(
                            id=contact.id,
                            organization_id=person.organization_id,
                            person_id=person.id,
                            kind=contact.kind.value,
                            encrypted_value=self._encrypt(contact.value),
                            label=contact.label,
                            is_primary=contact.is_primary,
                            whatsapp_capable=contact.whatsapp_capable,
                        )
                    )
        except IntegrityError as exc:
            raise PeopleConflictError(
                "Person or national identifier already exists"
            ) from exc

    async def get_person(
        self,
        *,
        organization_id: UUID,
        person_id: UUID,
    ) -> Person | None:
        """Return decrypted person state only after exact tenant matching."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(PersonModel).where(
                    PersonModel.id == person_id,
                    PersonModel.organization_id == organization_id,
                )
            )
            if model is None:
                return None
            contact_models = await session.scalars(
                select(ContactMethodModel)
                .where(
                    ContactMethodModel.person_id == person_id,
                    ContactMethodModel.organization_id == organization_id,
                )
                .order_by(ContactMethodModel.created_at)
            )
            try:
                contacts = tuple(
                    ContactMethod(
                        id=contact.id,
                        kind=ContactKind(contact.kind),
                        value=self._decrypt(contact.encrypted_value),
                        label=contact.label,
                        is_primary=contact.is_primary,
                        whatsapp_capable=contact.whatsapp_capable,
                    )
                    for contact in contact_models
                )
                national_identifier = (
                    self._decrypt(model.encrypted_national_identifier)
                    if model.encrypted_national_identifier is not None
                    else None
                )
            except InvalidToken as exc:
                raise PeopleDataProtectionError from exc
            return Person(
                id=model.id,
                organization_id=model.organization_id,
                given_name=model.given_name,
                family_name=model.family_name,
                preferred_name=model.preferred_name,
                national_identifier=national_identifier,
                date_of_birth=model.date_of_birth,
                contacts=contacts,
            )

    async def list_people(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> list[Person]:
        """List bounded people through exact tenant predicates and context."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            identifiers = await session.scalars(
                select(PersonModel.id)
                .where(PersonModel.organization_id == organization_id)
                .order_by(
                    PersonModel.family_name, PersonModel.given_name, PersonModel.id
                )
                .limit(limit)
                .offset(offset)
            )
            people: list[Person] = []
            for person_id in identifiers:
                person = await self._get_person_in_session(
                    session=session,
                    organization_id=organization_id,
                    person_id=person_id,
                )
                if person is not None:
                    people.append(person)
            return people

    async def person_exists(
        self,
        *,
        organization_id: UUID,
        person_id: UUID,
    ) -> bool:
        """Check a tenant person reference without decrypting personal data."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            identifier = await session.scalar(
                select(PersonModel.id).where(
                    PersonModel.id == person_id,
                    PersonModel.organization_id == organization_id,
                )
            )
            return identifier is not None

    async def add_profile(
        self,
        profile: PersonProfile,
    ) -> None:
        """Create one profile while encrypting its local reference number."""

        try:
            async with self._database.session(
                organization_id=profile.organization_id,
            ) as session:
                session.add(
                    PersonProfileModel(
                        id=profile.id,
                        organization_id=profile.organization_id,
                        person_id=profile.person_id,
                        kind=profile.kind.value,
                        encrypted_reference_number=(
                            self._encrypt(profile.reference_number)
                            if profile.reference_number is not None
                            else None
                        ),
                        title=profile.title,
                    )
                )
        except IntegrityError as exc:
            raise PeopleConflictError("Person profile already exists") from exc

    async def existing_teacher_profile_ids(
        self,
        *,
        organization_id: UUID,
        teacher_profile_ids: frozenset[UUID],
    ) -> frozenset[UUID]:
        """Return tenant-matching teacher profile IDs without decrypting data."""

        return await self._existing_profile_ids(
            organization_id=organization_id,
            profile_ids=teacher_profile_ids,
            kind=ProfileKind.TEACHER,
        )

    async def existing_student_profile_ids(
        self,
        *,
        organization_id: UUID,
        student_profile_ids: frozenset[UUID],
    ) -> frozenset[UUID]:
        """Return tenant-matching student profile IDs without decrypting data."""

        return await self._existing_profile_ids(
            organization_id=organization_id,
            profile_ids=student_profile_ids,
            kind=ProfileKind.STUDENT,
        )

    async def resolve_student_profile_id(
        self,
        *,
        organization_id: UUID,
        person_id: UUID,
    ) -> UUID | None:
        """Return the tenant person's student profile ID without decrypting data."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            value: object = await session.scalar(
                select(PersonProfileModel.id).where(
                    PersonProfileModel.organization_id == organization_id,
                    PersonProfileModel.person_id == person_id,
                    PersonProfileModel.kind == ProfileKind.STUDENT.value,
                )
            )
            return value if isinstance(value, UUID) else None

    async def _existing_profile_ids(
        self,
        *,
        organization_id: UUID,
        profile_ids: frozenset[UUID],
        kind: ProfileKind,
    ) -> frozenset[UUID]:
        """Resolve requested profile IDs for one tenant and exact profile kind."""

        if not profile_ids:
            return frozenset()
        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            identifiers = await session.scalars(
                select(PersonProfileModel.id).where(
                    PersonProfileModel.organization_id == organization_id,
                    PersonProfileModel.id.in_(profile_ids),
                    PersonProfileModel.kind == kind.value,
                )
            )
            return frozenset(identifiers)

    async def get_profile(
        self,
        *,
        organization_id: UUID,
        profile_id: UUID,
        kind: ProfileKind,
    ) -> PersonProfile | None:
        """Return a profile only when tenant, identifier, and profile kind match."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(PersonProfileModel).where(
                    PersonProfileModel.id == profile_id,
                    PersonProfileModel.organization_id == organization_id,
                    PersonProfileModel.kind == kind.value,
                )
            )
            if model is None:
                return None
            try:
                reference_number = (
                    self._decrypt(model.encrypted_reference_number)
                    if model.encrypted_reference_number is not None
                    else None
                )
            except InvalidToken as exc:
                raise PeopleDataProtectionError from exc
            return PersonProfile(
                id=model.id,
                organization_id=model.organization_id,
                person_id=model.person_id,
                kind=ProfileKind(model.kind),
                reference_number=reference_number,
                title=model.title,
            )

    async def list_profiles(
        self,
        *,
        organization_id: UUID,
        kind: ProfileKind,
        limit: int,
        offset: int,
    ) -> list[PersonProfile]:
        """List one profile kind through an exact tenant predicate and context."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            models = await session.scalars(
                select(PersonProfileModel)
                .where(
                    PersonProfileModel.organization_id == organization_id,
                    PersonProfileModel.kind == kind.value,
                )
                .order_by(PersonProfileModel.created_at, PersonProfileModel.id)
                .limit(limit)
                .offset(offset)
            )
            profiles: list[PersonProfile] = []
            try:
                for model in models:
                    reference_number = (
                        self._decrypt(model.encrypted_reference_number)
                        if model.encrypted_reference_number is not None
                        else None
                    )
                    profiles.append(
                        PersonProfile(
                            id=model.id,
                            organization_id=model.organization_id,
                            person_id=model.person_id,
                            kind=ProfileKind(model.kind),
                            reference_number=reference_number,
                            title=model.title,
                        )
                    )
            except InvalidToken as exc:
                raise PeopleDataProtectionError from exc
            return profiles

    async def add_guardian_relationship(
        self,
        relationship: GuardianRelationship,
    ) -> None:
        """Persist a validated same-tenant guardian-to-student relationship."""

        try:
            async with self._database.session(
                organization_id=relationship.organization_id,
            ) as session:
                session.add(
                    GuardianRelationshipModel(
                        id=relationship.id,
                        organization_id=relationship.organization_id,
                        guardian_profile_id=relationship.guardian_profile_id,
                        student_profile_id=relationship.student_profile_id,
                        relationship_label=relationship.relationship_label,
                    )
                )
        except IntegrityError as exc:
            raise PeopleConflictError(
                "Guardian relationship already exists or crosses tenants"
            ) from exc

    def _encrypt(
        self,
        value: str,
    ) -> str:
        """Encrypt one personal-data string at the infrastructure boundary."""

        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    async def _get_person_in_session(
        self,
        *,
        session: AsyncSession,
        organization_id: UUID,
        person_id: UUID,
    ) -> Person | None:
        """Load one decrypted person inside an existing tenant transaction."""

        model = await session.scalar(
            select(PersonModel).where(
                PersonModel.id == person_id,
                PersonModel.organization_id == organization_id,
            )
        )
        if model is None:
            return None
        contact_models = await session.scalars(
            select(ContactMethodModel)
            .where(
                ContactMethodModel.person_id == person_id,
                ContactMethodModel.organization_id == organization_id,
            )
            .order_by(ContactMethodModel.created_at)
        )
        try:
            contacts = tuple(
                ContactMethod(
                    id=contact.id,
                    kind=ContactKind(contact.kind),
                    value=self._decrypt(contact.encrypted_value),
                    label=contact.label,
                    is_primary=contact.is_primary,
                    whatsapp_capable=contact.whatsapp_capable,
                )
                for contact in contact_models
            )
            national_identifier = (
                self._decrypt(model.encrypted_national_identifier)
                if model.encrypted_national_identifier is not None
                else None
            )
        except InvalidToken as exc:
            raise PeopleDataProtectionError from exc
        return Person(
            id=model.id,
            organization_id=model.organization_id,
            given_name=model.given_name,
            family_name=model.family_name,
            preferred_name=model.preferred_name,
            national_identifier=national_identifier,
            date_of_birth=model.date_of_birth,
            contacts=contacts,
        )

    def _decrypt(
        self,
        value: str,
    ) -> str:
        """Decrypt one personal-data string only for an authorized repository read."""

        return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")

    def _digest(
        self,
        organization_id: UUID,
        value: str,
    ) -> str:
        """Create a tenant- and domain-separated keyed lookup digest."""

        return hmac.new(
            self._digest_key,
            organization_id.bytes + b"\x00" + value.strip().encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _legacy_digest(self, value: str) -> str:
        """Recognize pre-domain-separation values during duplicate checks."""

        return hmac.new(
            self._legacy_digest_key,
            value.strip().encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()


class SQLAlchemyMembershipRepository:
    """Persist multi-role memberships with tenant predicates on every path."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database

    async def add(
        self,
        membership: Membership,
    ) -> None:
        """Create membership and its complete role set in one transaction."""

        try:
            async with self._database.session(
                organization_id=membership.organization_id,
            ) as session:
                session.add(
                    MembershipModel(
                        id=membership.id,
                        organization_id=membership.organization_id,
                        identity_subject_id=membership.identity_subject_id,
                        person_id=membership.person_id,
                        status=membership.status.value,
                    )
                )
                for role in membership.roles:
                    session.add(
                        MembershipRoleModel(
                            membership_id=membership.id,
                            organization_id=membership.organization_id,
                            role=role.value,
                        )
                    )
        except IntegrityError as exc:
            raise PeopleConflictError(
                "Membership already exists or references another tenant"
            ) from exc

    async def mutate_existing(
        self,
        *,
        organization_id: UUID,
        membership_id: UUID,
        mutation: Callable[[Membership], Membership],
    ) -> Membership:
        """Apply one domain mutation while holding the tenant membership row lock."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(MembershipModel)
                .where(
                    MembershipModel.id == membership_id,
                    MembershipModel.organization_id == organization_id,
                )
                .with_for_update()
            )
            if model is None:
                raise MembershipNotFoundError
            current = await self._to_domain(session=session, model=model)
            updated = mutation(current)
            await self._persist_mutation(
                session=session,
                model=model,
                current=current,
                updated=updated,
            )
            return updated

    async def mutate_owner(
        self,
        *,
        organization_id: UUID,
        membership_id: UUID,
        mutation: Callable[[Membership, tuple[Membership, ...]], Membership],
    ) -> Membership:
        """Serialize one owner mutation against every owner row in the tenant."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            models = list(
                await session.scalars(
                    self._owner_membership_query(
                        organization_id=organization_id,
                    ).with_for_update(of=MembershipModel)
                )
            )
            owner_memberships = tuple(
                [
                    await self._to_domain(session=session, model=model)
                    for model in models
                ]
            )
            target_index = next(
                (
                    index
                    for index, model in enumerate(models)
                    if model.id == membership_id
                ),
                None,
            )
            if target_index is None:
                raise MembershipNotFoundError
            current = owner_memberships[target_index]
            updated = mutation(current, owner_memberships)
            await self._persist_mutation(
                session=session,
                model=models[target_index],
                current=current,
                updated=updated,
            )
            return updated

    async def get(
        self,
        *,
        organization_id: UUID,
        membership_id: UUID,
    ) -> Membership | None:
        """Return a membership only when identifier and tenant both match."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(MembershipModel).where(
                    MembershipModel.id == membership_id,
                    MembershipModel.organization_id == organization_id,
                )
            )
            if model is None:
                return None
            return await self._to_domain(session=session, model=model)

    async def get_for_identity(
        self,
        *,
        organization_id: UUID,
        identity_subject_id: UUID,
    ) -> Membership | None:
        """Return one identity's membership only in the supplied organization."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(MembershipModel).where(
                    MembershipModel.organization_id == organization_id,
                    MembershipModel.identity_subject_id == identity_subject_id,
                )
            )
            if model is None:
                return None
            return await self._to_domain(session=session, model=model)

    async def list_for_identity(
        self,
        *,
        identity_subject_id: UUID,
    ) -> list[Membership]:
        """List active memberships under verified-subject PostgreSQL context."""

        async with self._database.session(
            identity_subject_id=identity_subject_id,
        ) as session:
            models = await session.scalars(
                select(MembershipModel)
                .where(
                    MembershipModel.identity_subject_id == identity_subject_id,
                    MembershipModel.status == MembershipStatus.ACTIVE.value,
                )
                .order_by(MembershipModel.organization_id)
            )
            return [
                await self._to_domain(session=session, model=model) for model in models
            ]

    async def list_for_organization(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> list[Membership]:
        """List all lifecycle states through exact tenant context and predicates."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            models = await session.scalars(
                select(MembershipModel)
                .where(MembershipModel.organization_id == organization_id)
                .order_by(MembershipModel.created_at, MembershipModel.id)
                .limit(limit)
                .offset(offset)
            )
            return [
                await self._to_domain(session=session, model=model) for model in models
            ]

    async def list_owners_for_organization(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> list[Membership]:
        """List owner lifecycle state under exact tenant context and predicates."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            models = await session.scalars(
                self._owner_membership_query(organization_id=organization_id)
                .limit(limit)
                .offset(offset)
            )
            return [
                await self._to_domain(session=session, model=model) for model in models
            ]

    @staticmethod
    def _owner_membership_query(
        *,
        organization_id: UUID,
    ) -> Select[tuple[MembershipModel]]:
        """Build the deterministic exact-tenant owner membership query."""

        return (
            select(MembershipModel)
            .join(
                MembershipRoleModel,
                (MembershipRoleModel.membership_id == MembershipModel.id)
                & (
                    MembershipRoleModel.organization_id
                    == MembershipModel.organization_id
                ),
            )
            .where(
                MembershipModel.organization_id == organization_id,
                MembershipRoleModel.organization_id == organization_id,
                MembershipRoleModel.role == MembershipRole.ORGANIZATION_OWNER.value,
            )
            .order_by(MembershipModel.id)
        )

    @staticmethod
    async def _persist_mutation(
        *,
        session: AsyncSession,
        model: MembershipModel,
        current: Membership,
        updated: Membership,
    ) -> None:
        """Persist one validated membership mutation in the owning transaction."""

        if (
            updated.id != current.id
            or updated.organization_id != current.organization_id
            or updated.identity_subject_id != current.identity_subject_id
        ):
            raise InvalidMembershipError(
                "Membership mutation cannot change its identity or tenant"
            )
        model.person_id = updated.person_id
        model.status = updated.status.value
        await session.execute(
            delete(MembershipRoleModel).where(
                MembershipRoleModel.membership_id == current.id,
                MembershipRoleModel.organization_id == current.organization_id,
            )
        )
        for role in updated.roles:
            session.add(
                MembershipRoleModel(
                    membership_id=updated.id,
                    organization_id=updated.organization_id,
                    role=role.value,
                )
            )

    @staticmethod
    async def _to_domain(
        *,
        session: AsyncSession,
        model: MembershipModel,
    ) -> Membership:
        """Translate one membership row and its role rows into a domain value."""

        roles = await session.scalars(
            select(MembershipRoleModel.role).where(
                MembershipRoleModel.membership_id == model.id,
                MembershipRoleModel.organization_id == model.organization_id,
            )
        )
        return Membership(
            id=model.id,
            organization_id=model.organization_id,
            identity_subject_id=model.identity_subject_id,
            person_id=model.person_id,
            roles=frozenset(MembershipRole(role) for role in roles),
            status=MembershipStatus(model.status),
        )


__all__ = ["SQLAlchemyMembershipRepository", "SQLAlchemyPeopleRepository"]
