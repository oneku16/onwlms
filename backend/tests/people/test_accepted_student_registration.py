"""Accepted-student People transaction and idempotency tests."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast
from uuid import UUID
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from outbox.infrastructure.models import OutboxEventModel
from people.application.accepted_student_service import (
    AcceptedStudentRegistrationService,
)
from people.application.contracts import AcceptedStudentRegistrationCommand
from people.domain.exceptions import PeopleConflictError
from people.infrastructure.models import AcceptedStudentRegistrationModel
from people.infrastructure.models import ContactMethodModel
from people.infrastructure.models import PersonModel
from people.infrastructure.models import PersonProfileModel
from profile_activation_adapter import SQLAlchemyAcceptedStudentRegistrationWriter
from shared.database import Database


class RecordingSession:
    """Capture models added inside one synthetic database transaction."""

    def __init__(
        self,
        existing: AcceptedStudentRegistrationModel | None,
    ) -> None:
        self.existing = existing
        self.added: list[object] = []

    async def scalar(self, statement: object) -> object | None:
        del statement
        return self.existing

    def add(self, model: object) -> None:
        self.added.append(model)


class RecordingDatabase:
    """Expose one transaction context per writer invocation."""

    def __init__(self) -> None:
        self.existing: AcceptedStudentRegistrationModel | None = None
        self.calls: list[tuple[UUID | None, UUID | None, RecordingSession]] = []

    @asynccontextmanager
    async def session(
        self,
        *,
        organization_id: UUID | None = None,
        identity_subject_id: UUID | None = None,
    ) -> AsyncIterator[RecordingSession]:
        session = RecordingSession(self.existing)
        self.calls.append((organization_id, identity_subject_id, session))
        yield session


def _command(
    *,
    organization_id: UUID,
    conversion_id: UUID,
    student_profile_id: UUID,
    family_name: str = "Asanova",
) -> AcceptedStudentRegistrationCommand:
    return AcceptedStudentRegistrationCommand(
        idempotency_key=conversion_id,
        organization_id=organization_id,
        student_profile_id=student_profile_id,
        actor_subject_id=uuid4(),
        correlation_id="accepted-student-test",
        given_name="Aizada",
        family_name=family_name,
        email="aizada@example.test",
        phone="+996700123456",
    )


async def test_registration_is_atomic_and_idempotent() -> None:
    database = RecordingDatabase()
    writer = SQLAlchemyAcceptedStudentRegistrationWriter(
        database=cast(Database, database),
        pii_encryption_key=Fernet.generate_key().decode("ascii"),
    )
    service = AcceptedStudentRegistrationService(writer=writer)
    organization_id = uuid4()
    conversion_id = uuid4()
    student_profile_id = uuid4()
    command = _command(
        organization_id=organization_id,
        conversion_id=conversion_id,
        student_profile_id=student_profile_id,
    )

    first = await service.register_accepted_student(command)

    assert len(database.calls) == 1
    transaction_org, transaction_actor, session = database.calls[0]
    assert transaction_org == organization_id
    assert transaction_actor == command.actor_subject_id
    person = next(model for model in session.added if isinstance(model, PersonModel))
    contacts = [
        model for model in session.added if isinstance(model, ContactMethodModel)
    ]
    profile = next(
        model for model in session.added if isinstance(model, PersonProfileModel)
    )
    binding = next(
        model
        for model in session.added
        if isinstance(model, AcceptedStudentRegistrationModel)
    )
    event = next(
        model for model in session.added if isinstance(model, OutboxEventModel)
    )
    assert first.person_id == person.id
    assert first.student_profile_id == student_profile_id == profile.id
    assert profile.person_id == person.id
    assert binding.conversion_id == conversion_id
    assert binding.person_id == person.id
    assert binding.student_profile_id == student_profile_id
    assert len(contacts) == 2
    assert {contact.encrypted_value for contact in contacts}.isdisjoint(
        {"aizada@example.test", "+996700123456"}
    )
    assert event.idempotency_key.endswith(f"{conversion_id}:v1")
    assert event.payload == {
        "subject_type": "student",
        "subject_id": str(student_profile_id),
    }

    database.existing = binding
    second = await service.register_accepted_student(command)

    assert second == first
    assert database.calls[1][2].added == []


async def test_registration_rejects_changed_or_cross_tenant_replay() -> None:
    database = RecordingDatabase()
    writer = SQLAlchemyAcceptedStudentRegistrationWriter(
        database=cast(Database, database),
        pii_encryption_key=Fernet.generate_key().decode("ascii"),
    )
    service = AcceptedStudentRegistrationService(writer=writer)
    organization_id = uuid4()
    conversion_id = uuid4()
    student_profile_id = uuid4()
    original = _command(
        organization_id=organization_id,
        conversion_id=conversion_id,
        student_profile_id=student_profile_id,
    )
    await service.register_accepted_student(original)
    database.existing = next(
        model
        for model in database.calls[0][2].added
        if isinstance(model, AcceptedStudentRegistrationModel)
    )

    with pytest.raises(PeopleConflictError, match="different People data"):
        await service.register_accepted_student(
            _command(
                organization_id=organization_id,
                conversion_id=conversion_id,
                student_profile_id=student_profile_id,
                family_name="Changed",
            )
        )

    with pytest.raises(PeopleConflictError, match="different People data"):
        await service.register_accepted_student(
            _command(
                organization_id=uuid4(),
                conversion_id=conversion_id,
                student_profile_id=student_profile_id,
            )
        )
