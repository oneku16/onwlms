"""Public academic application surface."""

from academics.application.admissions_enrollment_service import (
    AcceptedStudentAcademicEnrollmentService,
)
from academics.application.contracts import AcademicGradeTarget
from academics.application.contracts import AcademicInstructionWindow
from academics.application.contracts import AcademicSchedulingReferences
from academics.application.contracts import AcademicSchedulingRoom
from academics.application.contracts import AcceptedStudentAcademicEnrollmentCommand
from academics.application.contracts import AcceptedStudentAcademicEnrollmentResult
from academics.application.ports import AcademicCatalogRepository
from academics.application.ports import AcademicClock
from academics.application.ports import AcademicReferenceRepository
from academics.application.ports import AcceptedStudentAcademicEnrollmentRegistrar
from academics.application.ports import AdmissionsAcademicEnrollmentRepository
from academics.application.ports import CampusDirectory
from academics.application.ports import CourseSelectionRepository
from academics.application.reference_service import MAX_SCHEDULING_REFERENCE_HORIZON
from academics.application.reference_service import AcademicReferenceService
from academics.application.service import ACADEMICS_CURRICULUM_MANAGE
from academics.application.service import ACADEMICS_ENROLLMENT_MANAGE
from academics.application.service import ACADEMICS_SELECTION_APPROVE
from academics.application.service import ACADEMICS_SELECTION_OVERRIDE
from academics.application.service import ACADEMICS_SELECTION_SUBMIT
from academics.application.service import ACADEMICS_STRUCTURE_MANAGE
from academics.application.service import AcademicAdministrationService
from academics.application.service import CourseSelectionService

__all__ = [
    "ACADEMICS_CURRICULUM_MANAGE",
    "ACADEMICS_ENROLLMENT_MANAGE",
    "ACADEMICS_SELECTION_APPROVE",
    "ACADEMICS_SELECTION_OVERRIDE",
    "ACADEMICS_SELECTION_SUBMIT",
    "ACADEMICS_STRUCTURE_MANAGE",
    "MAX_SCHEDULING_REFERENCE_HORIZON",
    "AcademicAdministrationService",
    "AcademicCatalogRepository",
    "AcademicClock",
    "AcademicGradeTarget",
    "AcademicInstructionWindow",
    "AcademicReferenceRepository",
    "AcademicReferenceService",
    "AcademicSchedulingReferences",
    "AcademicSchedulingRoom",
    "AcceptedStudentAcademicEnrollmentCommand",
    "AcceptedStudentAcademicEnrollmentRegistrar",
    "AcceptedStudentAcademicEnrollmentResult",
    "AcceptedStudentAcademicEnrollmentService",
    "AdmissionsAcademicEnrollmentRepository",
    "CampusDirectory",
    "CourseSelectionRepository",
    "CourseSelectionService",
]
