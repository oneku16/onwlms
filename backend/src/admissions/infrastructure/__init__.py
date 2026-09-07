"""Public admissions infrastructure adapters."""

from admissions.infrastructure.models import AdmissionDecisionModel
from admissions.infrastructure.models import AdmissionQuotaModel
from admissions.infrastructure.models import AdmissionsPolicyModel
from admissions.infrastructure.models import AdmissionsPolicyStageModel
from admissions.infrastructure.models import ApplicantProfileModel
from admissions.infrastructure.models import ApplicationDocumentModel
from admissions.infrastructure.models import ApplicationModel
from admissions.infrastructure.models import EnrollmentConversionModel
from admissions.infrastructure.models import ReviewRecordModel
from admissions.infrastructure.models import SeatReservationModel
from admissions.infrastructure.repository import (
    InMemoryAcceptedApplicantEnrollmentRegistrar,
)
from admissions.infrastructure.repository import InMemoryAdmissionsRepository
from admissions.infrastructure.repository import InMemoryAdmissionsTargetDirectory
from admissions.infrastructure.repository import StaticDepositVerifier
from admissions.infrastructure.repository import UnconfiguredDepositVerifier
from admissions.infrastructure.sqlalchemy_repository import (
    SQLAlchemyAdmissionsRepository,
)

__all__ = [
    "AdmissionDecisionModel",
    "AdmissionQuotaModel",
    "AdmissionsPolicyModel",
    "AdmissionsPolicyStageModel",
    "ApplicantProfileModel",
    "ApplicationDocumentModel",
    "ApplicationModel",
    "EnrollmentConversionModel",
    "InMemoryAcceptedApplicantEnrollmentRegistrar",
    "InMemoryAdmissionsRepository",
    "InMemoryAdmissionsTargetDirectory",
    "ReviewRecordModel",
    "SQLAlchemyAdmissionsRepository",
    "SeatReservationModel",
    "StaticDepositVerifier",
    "UnconfiguredDepositVerifier",
]
