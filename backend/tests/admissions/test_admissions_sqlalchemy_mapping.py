"""Admissions SQLAlchemy mapping regression tests."""

from datetime import UTC
from datetime import datetime
from decimal import Decimal
from typing import cast
from uuid import uuid4

from cryptography.fernet import Fernet

from admissions.domain.models import ApplicantProfile
from admissions.domain.models import Application
from admissions.domain.models import ApplicationSource
from admissions.domain.models import ApplicationStatus
from admissions.domain.models import DepositRequirement
from admissions.domain.models import DepositStatus
from admissions.infrastructure.models import ApplicantProfileModel
from admissions.infrastructure.sqlalchemy_repository import (
    SQLAlchemyAdmissionsRepository,
)
from shared.database import Database


def test_application_mapping_preserves_lifecycle_and_deposit_metadata() -> None:
    due_at = datetime(2026, 8, 12, 10, tzinfo=UTC)
    application = Application(
        id=uuid4(),
        organization_id=uuid4(),
        applicant_profile_id=uuid4(),
        program_id=uuid4(),
        intake_id=uuid4(),
        seat_category="general",
        source=ApplicationSource.ADMINISTRATOR_ENTERED,
        status=ApplicationStatus.ACCEPTED,
        created_at=datetime(2026, 8, 5, 10, tzinfo=UTC),
        status_changed_at=datetime(2026, 8, 6, 10, tzinfo=UTC),
        deposit=DepositRequirement(
            required=True,
            amount=Decimal("250.00"),
            currency="USD",
            due_at=due_at,
            external_reference="deposit-evidence-1",
            status=DepositStatus.SATISFIED,
        ),
    )

    model = SQLAlchemyAdmissionsRepository._application_to_model(application)
    restored = SQLAlchemyAdmissionsRepository._application_from_model(model)

    assert restored == application


def test_applicant_contact_mapping_encrypts_values_and_has_no_plaintext_columns() -> (
    None
):
    key = Fernet.generate_key().decode("ascii")
    repository = SQLAlchemyAdmissionsRepository(
        database=cast(Database, object()),
        pii_encryption_key=key,
    )
    profile = ApplicantProfile(
        id=uuid4(),
        organization_id=uuid4(),
        given_name="Aizada",
        family_name="Asanova",
        email="aizada@example.test",
        phone="+996700123456",
    )

    model = repository._profile_to_model(profile)
    restored = repository._profile_from_model(model)

    assert restored == profile
    assert model.encrypted_email != profile.email
    assert model.encrypted_phone != profile.phone
    columns = set(ApplicantProfileModel.__table__.c.keys())
    assert "email" not in columns
    assert "phone" not in columns
    assert {"encrypted_email", "encrypted_phone"} <= columns
