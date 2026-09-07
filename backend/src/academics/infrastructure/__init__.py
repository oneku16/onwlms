"""Public academic infrastructure adapters."""

from academics.infrastructure.models import AcademicCalendarEventModel
from academics.infrastructure.models import AcademicYearModel
from academics.infrastructure.models import AdmissionsEnrollmentRegistrationModel
from academics.infrastructure.models import CohortModel
from academics.infrastructure.models import CourseEnrollmentModel
from academics.infrastructure.models import CourseModel
from academics.infrastructure.models import CourseOfferingMeetingModel
from academics.infrastructure.models import CourseOfferingModel
from academics.infrastructure.models import CourseSelectionApprovalModel
from academics.infrastructure.models import CourseSelectionOverrideModel
from academics.infrastructure.models import CourseSelectionOverrideViolationModel
from academics.infrastructure.models import CourseSelectionPolicyModel
from academics.infrastructure.models import CourseSelectionRequestModel
from academics.infrastructure.models import CourseSelectionRequestOfferingModel
from academics.infrastructure.models import CurriculumCourseModel
from academics.infrastructure.models import CurriculumPrerequisiteModel
from academics.infrastructure.models import DepartmentModel
from academics.infrastructure.models import FacultyModel
from academics.infrastructure.models import ProgramCurriculumModel
from academics.infrastructure.models import ProgramModel
from academics.infrastructure.models import RoomModel
from academics.infrastructure.models import StudentAcademicEnrollmentModel
from academics.infrastructure.models import TeacherAssignmentModel
from academics.infrastructure.models import TermModel
from academics.infrastructure.repository import InMemoryAcademicRepository
from academics.infrastructure.repository import InMemoryCampusDirectory
from academics.infrastructure.sqlalchemy_repository import SQLAlchemyAcademicRepository

__all__ = [
    "AcademicCalendarEventModel",
    "AcademicYearModel",
    "AdmissionsEnrollmentRegistrationModel",
    "CohortModel",
    "CourseEnrollmentModel",
    "CourseModel",
    "CourseOfferingMeetingModel",
    "CourseOfferingModel",
    "CourseSelectionApprovalModel",
    "CourseSelectionOverrideModel",
    "CourseSelectionOverrideViolationModel",
    "CourseSelectionPolicyModel",
    "CourseSelectionRequestModel",
    "CourseSelectionRequestOfferingModel",
    "CurriculumCourseModel",
    "CurriculumPrerequisiteModel",
    "DepartmentModel",
    "FacultyModel",
    "InMemoryAcademicRepository",
    "InMemoryCampusDirectory",
    "ProgramCurriculumModel",
    "ProgramModel",
    "RoomModel",
    "SQLAlchemyAcademicRepository",
    "StudentAcademicEnrollmentModel",
    "TeacherAssignmentModel",
    "TermModel",
]
