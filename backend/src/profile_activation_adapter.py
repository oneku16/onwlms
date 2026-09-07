"""Atomic cross-module adapter for people activation and outbox publication."""

import base64
import hashlib
import hmac
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from core.field_encryption import FieldCipher
from core.identifiers import new_uuid7
from core.time import utc_now
from outbox.infrastructure.models import OutboxEventModel
from people.application.contracts import AcceptedStudentRegistrationCommand
from people.application.contracts import AcceptedStudentRegistrationResult
from people.domain.exceptions import PeopleConflictError
from people.domain.models import Person
from people.domain.models import PersonProfile
from people.domain.models import ProfileKind
from people.infrastructure.models import AcceptedStudentRegistrationModel
from people.infrastructure.models import ContactMethodModel
from people.infrastructure.models import PersonModel
from people.infrastructure.models import PersonProfileModel
from shared.database import Database

_ACTIVATING_PROFILE_KINDS = frozenset(
    {ProfileKind.STUDENT, ProfileKind.STAFF, ProfileKind.TEACHER}
)


class SQLAlchemyProfileActivationWriter:
    """Write a profile and activation event in one PostgreSQL transaction.

    This adapter lives at the application composition boundary because the
    people and outbox modules retain separate persistence ownership. It is the
    only place that coordinates both representations, and it does not expose
    either module's ORM model to application code.
    """

    def __init__(
        self,
        *,
        database: Database,
        pii_encryption_key: str,
    ) -> None:
        self._database = database
        self._cipher = FieldCipher(pii_encryption_key)

    async def add_profile_with_activation(
        self,
        *,
        profile: PersonProfile,
        actor_subject_id: UUID,
        correlation_id: str,
    ) -> None:
        """Commit the activating state and durable publication together."""

        occurred_at = utc_now()
        try:
            async with self._database.session(
                organization_id=profile.organization_id,
                identity_subject_id=actor_subject_id,
            ) as session:
                session.add(
                    PersonProfileModel(
                        id=profile.id,
                        organization_id=profile.organization_id,
                        person_id=profile.person_id,
                        kind=profile.kind.value,
                        encrypted_reference_number=(
                            self._cipher.encrypt(profile.reference_number)
                            if profile.reference_number is not None
                            else None
                        ),
                        title=profile.title,
                    )
                )
                if profile.kind in _ACTIVATING_PROFILE_KINDS:
                    session.add(
                        OutboxEventModel(
                            id=new_uuid7(),
                            event_type="person.activated.v1",
                            contract_version=1,
                            organization_id=profile.organization_id,
                            actor_subject_id=actor_subject_id,
                            correlation_id=correlation_id,
                            idempotency_key=(
                                f"person-profile:{profile.id}:activated:v1"
                            ),
                            payload={
                                "subject_type": profile.kind.value,
                                "subject_id": str(profile.id),
                            },
                            created_at=occurred_at,
                            available_at=occurred_at,
                        )
                    )
        except IntegrityError as exc:
            raise PeopleConflictError("Person profile already exists") from exc


class SQLAlchemyAcceptedStudentRegistrationWriter:
    """Atomically create accepted-student People state and activation evidence."""

    def __init__(
        self,
        *,
        database: Database,
        pii_encryption_key: str,
    ) -> None:
        self._database = database
        self._cipher = FieldCipher(pii_encryption_key)
        self._digest_key = base64.urlsafe_b64decode(pii_encryption_key.encode("ascii"))

    async def register_accepted_student(
        self,
        *,
        command: AcceptedStudentRegistrationCommand,
        person: Person,
        profile: PersonProfile,
    ) -> AcceptedStudentRegistrationResult:
        """Commit person, contacts, profile, binding, and outbox as one unit."""

        self._require_exact_models(command=command, person=person, profile=profile)
        command_digest = self._command_digest(command)
        occurred_at = utc_now()
        try:
            async with self._database.session(
                organization_id=command.organization_id,
                identity_subject_id=command.actor_subject_id,
            ) as session:
                existing = await session.scalar(
                    select(AcceptedStudentRegistrationModel).where(
                        AcceptedStudentRegistrationModel.organization_id
                        == command.organization_id,
                        AcceptedStudentRegistrationModel.conversion_id
                        == command.idempotency_key,
                    )
                )
                if existing is not None:
                    return self._resolve_existing(
                        existing=existing,
                        command=command,
                        command_digest=command_digest,
                    )
                session.add(
                    PersonModel(
                        id=person.id,
                        organization_id=person.organization_id,
                        given_name=person.given_name,
                        family_name=person.family_name,
                        preferred_name=person.preferred_name,
                        encrypted_national_identifier=None,
                        national_identifier_digest=None,
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
                            encrypted_value=self._cipher.encrypt(contact.value),
                            label=contact.label,
                            is_primary=contact.is_primary,
                            whatsapp_capable=contact.whatsapp_capable,
                        )
                    )
                session.add(
                    PersonProfileModel(
                        id=profile.id,
                        organization_id=profile.organization_id,
                        person_id=profile.person_id,
                        kind=profile.kind.value,
                        encrypted_reference_number=None,
                        title=profile.title,
                    )
                )
                session.add(
                    AcceptedStudentRegistrationModel(
                        id=new_uuid7(),
                        organization_id=command.organization_id,
                        conversion_id=command.idempotency_key,
                        person_id=person.id,
                        student_profile_id=profile.id,
                        command_digest=command_digest,
                    )
                )
                session.add(
                    OutboxEventModel(
                        id=new_uuid7(),
                        event_type="person.activated.v1",
                        contract_version=1,
                        organization_id=command.organization_id,
                        actor_subject_id=command.actor_subject_id,
                        correlation_id=command.correlation_id,
                        idempotency_key=(
                            "accepted-student:"
                            f"{command.organization_id}:{command.idempotency_key}:v1"
                        ),
                        payload={
                            "subject_type": ProfileKind.STUDENT.value,
                            "subject_id": str(profile.id),
                        },
                        created_at=occurred_at,
                        available_at=occurred_at,
                    )
                )
            return AcceptedStudentRegistrationResult(
                person_id=person.id,
                student_profile_id=profile.id,
            )
        except IntegrityError as exc:
            existing = await self._get_registration(command)
            if existing is not None:
                return self._resolve_existing(
                    existing=existing,
                    command=command,
                    command_digest=command_digest,
                )
            raise PeopleConflictError(
                "Accepted-student registration conflicts with stored People state"
            ) from exc

    async def _get_registration(
        self,
        command: AcceptedStudentRegistrationCommand,
    ) -> AcceptedStudentRegistrationModel | None:
        """Reload a winning concurrent idempotency binding after rollback."""

        async with self._database.session(
            organization_id=command.organization_id,
            identity_subject_id=command.actor_subject_id,
        ) as session:
            model: AcceptedStudentRegistrationModel | None = await session.scalar(
                select(AcceptedStudentRegistrationModel).where(
                    AcceptedStudentRegistrationModel.organization_id
                    == command.organization_id,
                    AcceptedStudentRegistrationModel.conversion_id
                    == command.idempotency_key,
                )
            )
            return model

    def _command_digest(
        self,
        command: AcceptedStudentRegistrationCommand,
    ) -> str:
        """Bind replay semantics without persisting copied applicant contacts."""

        payload = json.dumps(
            {
                "email": command.email,
                "family_name": command.family_name,
                "given_name": command.given_name,
                "organization_id": str(command.organization_id),
                "phone": command.phone,
                "student_profile_id": str(command.student_profile_id),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hmac.new(self._digest_key, payload, hashlib.sha256).hexdigest()

    @staticmethod
    def _require_exact_models(
        *,
        command: AcceptedStudentRegistrationCommand,
        person: Person,
        profile: PersonProfile,
    ) -> None:
        """Reject cross-tenant or substituted domain objects before persistence."""

        if (
            person.organization_id != command.organization_id
            or profile.organization_id != command.organization_id
            or profile.id != command.student_profile_id
            or profile.person_id != person.id
            or profile.kind is not ProfileKind.STUDENT
        ):
            raise PeopleConflictError(
                "Accepted-student records do not match the conversion command"
            )

    @staticmethod
    def _resolve_existing(
        *,
        existing: AcceptedStudentRegistrationModel,
        command: AcceptedStudentRegistrationCommand,
        command_digest: str,
    ) -> AcceptedStudentRegistrationResult:
        """Return an exact prior binding or reject a changed replay."""

        if (
            existing.organization_id != command.organization_id
            or existing.command_digest != command_digest
            or existing.student_profile_id != command.student_profile_id
        ):
            raise PeopleConflictError(
                "Conversion key is already bound to different People data"
            )
        return AcceptedStudentRegistrationResult(
            person_id=existing.person_id,
            student_profile_id=existing.student_profile_id,
        )


__all__ = [
    "SQLAlchemyAcceptedStudentRegistrationWriter",
    "SQLAlchemyProfileActivationWriter",
]
