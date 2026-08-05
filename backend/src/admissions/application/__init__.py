"""Public admissions application contracts."""

from admissions.application.contracts import AcceptedApplicantEnrollmentCommand
from admissions.application.contracts import AcceptedApplicantEnrollmentResult
from admissions.application.ports import AcceptedApplicantEnrollmentRegistrar
from admissions.application.ports import AdmissionsClock
from admissions.application.ports import AdmissionsRepository
from admissions.application.ports import AdmissionsTargetDirectory
from admissions.application.ports import DepositVerifier
from admissions.application.service import ADMISSIONS_APPLICATION_CREATE
from admissions.application.service import ADMISSIONS_APPLICATION_SUBMIT
from admissions.application.service import ADMISSIONS_DECIDE
from admissions.application.service import ADMISSIONS_DOCUMENT_MANAGE
from admissions.application.service import ADMISSIONS_ENROLL
from admissions.application.service import ADMISSIONS_POLICY_MANAGE
from admissions.application.service import ADMISSIONS_REVIEW
from admissions.application.service import AdmissionsService

__all__ = [
    "ADMISSIONS_APPLICATION_CREATE",
    "ADMISSIONS_APPLICATION_SUBMIT",
    "ADMISSIONS_DECIDE",
    "ADMISSIONS_DOCUMENT_MANAGE",
    "ADMISSIONS_ENROLL",
    "ADMISSIONS_POLICY_MANAGE",
    "ADMISSIONS_REVIEW",
    "AcceptedApplicantEnrollmentCommand",
    "AcceptedApplicantEnrollmentRegistrar",
    "AcceptedApplicantEnrollmentResult",
    "AdmissionsClock",
    "AdmissionsRepository",
    "AdmissionsService",
    "AdmissionsTargetDirectory",
    "DepositVerifier",
]
