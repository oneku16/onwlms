"""Explicit public contracts for the academic bounded context."""

from academics.application import ACADEMICS_CURRICULUM_MANAGE
from academics.application import ACADEMICS_ENROLLMENT_MANAGE
from academics.application import ACADEMICS_SELECTION_APPROVE
from academics.application import ACADEMICS_SELECTION_OVERRIDE
from academics.application import ACADEMICS_SELECTION_SUBMIT
from academics.application import ACADEMICS_STRUCTURE_MANAGE
from academics.application import MAX_SCHEDULING_REFERENCE_HORIZON
from academics.application import AcademicAdministrationService
from academics.application import AcademicCatalogRepository
from academics.application import AcademicGradeTarget
from academics.application import AcademicInstructionWindow
from academics.application import AcademicReferenceRepository
from academics.application import AcademicReferenceService
from academics.application import AcademicSchedulingReferences
from academics.application import AcademicSchedulingRoom
from academics.application import CampusDirectory
from academics.application import CourseSelectionRepository
from academics.application import CourseSelectionService
from academics.domain import CourseEnrollment
from academics.domain import CourseOffering
from academics.domain import CourseSelectionRequest
from academics.domain import ProgramCurriculum
from academics.domain import StudentAcademicEnrollment

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
    "AcademicGradeTarget",
    "AcademicInstructionWindow",
    "AcademicReferenceRepository",
    "AcademicReferenceService",
    "AcademicSchedulingReferences",
    "AcademicSchedulingRoom",
    "CampusDirectory",
    "CourseEnrollment",
    "CourseOffering",
    "CourseSelectionRepository",
    "CourseSelectionRequest",
    "CourseSelectionService",
    "ProgramCurriculum",
    "StudentAcademicEnrollment",
]
