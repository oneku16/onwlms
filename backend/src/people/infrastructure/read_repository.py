"""Encrypted PostgreSQL ownership projections for people self-service reads."""

from uuid import UUID

from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken
from sqlalchemy import select

from people.application.read_models import OwnedProfileSummary
from people.domain.exceptions import PeopleDataProtectionError
from people.domain.models import ProfileKind
from people.infrastructure.models import GuardianRelationshipModel
from people.infrastructure.models import PersonModel
from people.infrastructure.models import PersonProfileModel
from shared.database import Database


class SQLAlchemyPeopleOwnershipReadRepository:
    """Read minimum identity projections under exact PostgreSQL tenant context."""

    def __init__(
        self,
        *,
        database: Database,
        encryption_key: str,
    ) -> None:
        self._database = database
        self._fernet = Fernet(encryption_key.encode("ascii"))

    async def get_profile_for_person(
        self,
        *,
        organization_id: UUID,
        person_id: UUID,
        kind: ProfileKind,
    ) -> OwnedProfileSummary | None:
        """Return one profile only through tenant, person, and kind predicates."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            row = (
                await session.execute(
                    select(PersonProfileModel, PersonModel)
                    .join(
                        PersonModel,
                        (
                            PersonModel.organization_id
                            == PersonProfileModel.organization_id
                        )
                        & (PersonModel.id == PersonProfileModel.person_id),
                    )
                    .where(
                        PersonProfileModel.organization_id == organization_id,
                        PersonProfileModel.person_id == person_id,
                        PersonProfileModel.kind == kind.value,
                    )
                )
            ).one_or_none()
        if row is None:
            return None
        return self._summary(profile=row[0], person=row[1])

    async def list_linked_students(
        self,
        *,
        organization_id: UUID,
        guardian_profile_id: UUID,
    ) -> tuple[OwnedProfileSummary, ...]:
        """Return student profiles behind explicit guardian links only."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            rows = tuple(
                (
                    await session.execute(
                        select(PersonProfileModel, PersonModel)
                        .join(
                            GuardianRelationshipModel,
                            (
                                GuardianRelationshipModel.organization_id
                                == PersonProfileModel.organization_id
                            )
                            & (
                                GuardianRelationshipModel.student_profile_id
                                == PersonProfileModel.id
                            ),
                        )
                        .join(
                            PersonModel,
                            (
                                PersonModel.organization_id
                                == PersonProfileModel.organization_id
                            )
                            & (PersonModel.id == PersonProfileModel.person_id),
                        )
                        .where(
                            GuardianRelationshipModel.organization_id
                            == organization_id,
                            GuardianRelationshipModel.guardian_profile_id
                            == guardian_profile_id,
                            PersonProfileModel.kind == ProfileKind.STUDENT.value,
                        )
                        .order_by(PersonProfileModel.id)
                    )
                ).all()
            )
        return tuple(self._summary(profile=row[0], person=row[1]) for row in rows)

    async def list_student_summaries(
        self,
        *,
        organization_id: UUID,
        student_profile_ids: frozenset[UUID],
    ) -> tuple[OwnedProfileSummary, ...]:
        """Return the exact requested tenant student projection set."""

        if not student_profile_ids:
            return ()
        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            rows = tuple(
                (
                    await session.execute(
                        select(PersonProfileModel, PersonModel)
                        .join(
                            PersonModel,
                            (
                                PersonModel.organization_id
                                == PersonProfileModel.organization_id
                            )
                            & (PersonModel.id == PersonProfileModel.person_id),
                        )
                        .where(
                            PersonProfileModel.organization_id == organization_id,
                            PersonProfileModel.id.in_(student_profile_ids),
                            PersonProfileModel.kind == ProfileKind.STUDENT.value,
                        )
                        .order_by(PersonProfileModel.id)
                    )
                ).all()
            )
        return tuple(self._summary(profile=row[0], person=row[1]) for row in rows)

    def _summary(
        self,
        *,
        profile: PersonProfileModel,
        person: PersonModel,
    ) -> OwnedProfileSummary:
        """Decrypt only the institutional reference needed by safe read models."""

        try:
            reference = (
                self._fernet.decrypt(
                    profile.encrypted_reference_number.encode("ascii")
                ).decode("utf-8")
                if profile.encrypted_reference_number is not None
                else None
            )
        except InvalidToken as exc:
            raise PeopleDataProtectionError from exc
        display_name = (
            person.preferred_name.strip()
            if person.preferred_name and person.preferred_name.strip()
            else f"{person.given_name} {person.family_name}".strip()
        )
        return OwnedProfileSummary(
            profile_id=profile.id,
            person_id=person.id,
            kind=ProfileKind(profile.kind),
            display_name=display_name,
            institutional_reference=reference,
        )


__all__ = ["SQLAlchemyPeopleOwnershipReadRepository"]
