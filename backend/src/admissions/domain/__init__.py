"""Public admissions domain surface."""

from admissions.domain.exceptions import AdmissionsRuleError
from admissions.domain.exceptions import ApplicationTransitionError
from admissions.domain.exceptions import EnrollmentConversionError
from admissions.domain.exceptions import QuotaUnavailableError
from admissions.domain.models import AdmissionDecision
from admissions.domain.models import AdmissionDecisionOutcome
from admissions.domain.models import AdmissionQuota
from admissions.domain.models import AdmissionsPolicy
from admissions.domain.models import ApplicantProfile
from admissions.domain.models import Application
from admissions.domain.models import ApplicationDocument
from admissions.domain.models import ApplicationSource
from admissions.domain.models import ApplicationStatus
from admissions.domain.models import DepositRequirement
from admissions.domain.models import DepositStatus
from admissions.domain.models import EnrollmentConversion
from admissions.domain.models import EnrollmentConversionStatus
from admissions.domain.models import ReservationStatus
from admissions.domain.models import ReviewOutcome
from admissions.domain.models import ReviewRecord
from admissions.domain.models import ReviewStage
from admissions.domain.models import SeatReservation
from admissions.domain.models import transition_application

__all__ = [
    "AdmissionDecision",
    "AdmissionDecisionOutcome",
    "AdmissionQuota",
    "AdmissionsPolicy",
    "AdmissionsRuleError",
    "ApplicantProfile",
    "Application",
    "ApplicationDocument",
    "ApplicationSource",
    "ApplicationStatus",
    "ApplicationTransitionError",
    "DepositRequirement",
    "DepositStatus",
    "EnrollmentConversion",
    "EnrollmentConversionError",
    "EnrollmentConversionStatus",
    "QuotaUnavailableError",
    "ReservationStatus",
    "ReviewOutcome",
    "ReviewRecord",
    "ReviewStage",
    "SeatReservation",
    "transition_application",
]
