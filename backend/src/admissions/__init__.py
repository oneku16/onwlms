"""Explicit public contracts for the admissions bounded context."""

from admissions.application import ADMISSIONS_APPLICATION_CREATE
from admissions.application import ADMISSIONS_APPLICATION_SUBMIT
from admissions.application import ADMISSIONS_DECIDE
from admissions.application import ADMISSIONS_DOCUMENT_MANAGE
from admissions.application import ADMISSIONS_ENROLL
from admissions.application import ADMISSIONS_POLICY_MANAGE
from admissions.application import ADMISSIONS_REVIEW
from admissions.application import AcceptedApplicantEnrollmentCommand
from admissions.application import AcceptedApplicantEnrollmentRegistrar
from admissions.application import AcceptedApplicantEnrollmentResult
from admissions.application import AdmissionsRepository
from admissions.application import AdmissionsService
from admissions.application import AdmissionsTargetDirectory
from admissions.application import DepositVerifier
from admissions.domain import AdmissionDecision
from admissions.domain import AdmissionQuota
from admissions.domain import AdmissionsPolicy
from admissions.domain import ApplicantProfile
from admissions.domain import Application
from admissions.domain import SeatReservation

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
    "AdmissionDecision",
    "AdmissionQuota",
    "AdmissionsPolicy",
    "AdmissionsRepository",
    "AdmissionsService",
    "AdmissionsTargetDirectory",
    "ApplicantProfile",
    "Application",
    "DepositVerifier",
    "SeatReservation",
]
