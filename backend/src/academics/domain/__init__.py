"""Public academic domain surface."""

from academics.domain.exceptions import AcademicRuleError
from academics.domain.exceptions import CourseSelectionDecisionError
from academics.domain.exceptions import CourseSelectionError
from academics.domain.exceptions import EnrollmentTransitionError
from academics.domain.models import AcademicCalendarEvent
from academics.domain.models import AcademicEnrollmentStatus
from academics.domain.models import AcademicYear
from academics.domain.models import AdministrativeOverride
from academics.domain.models import Cohort
from academics.domain.models import Course
from academics.domain.models import CourseEnrollment
from academics.domain.models import CourseEnrollmentStatus
from academics.domain.models import CourseOffering
from academics.domain.models import CourseSelectionApproval
from academics.domain.models import CourseSelectionPolicy
from academics.domain.models import CourseSelectionRequest
from academics.domain.models import CourseSelectionStatus
from academics.domain.models import CurriculumCourse
from academics.domain.models import CurriculumCourseKind
from academics.domain.models import Department
from academics.domain.models import EducationMode
from academics.domain.models import Faculty
from academics.domain.models import MeetingWindow
from academics.domain.models import Program
from academics.domain.models import ProgramCurriculum
from academics.domain.models import Room
from academics.domain.models import SelectionEvaluation
from academics.domain.models import SelectionRuleCode
from academics.domain.models import SelectionRuleViolation
from academics.domain.models import StudentAcademicEnrollment
from academics.domain.models import TeacherAssignment
from academics.domain.models import Term
from academics.domain.policies import evaluate_course_selection

__all__ = [
    "AcademicCalendarEvent",
    "AcademicEnrollmentStatus",
    "AcademicRuleError",
    "AcademicYear",
    "AdministrativeOverride",
    "Cohort",
    "Course",
    "CourseEnrollment",
    "CourseEnrollmentStatus",
    "CourseOffering",
    "CourseSelectionApproval",
    "CourseSelectionDecisionError",
    "CourseSelectionError",
    "CourseSelectionPolicy",
    "CourseSelectionRequest",
    "CourseSelectionStatus",
    "CurriculumCourse",
    "CurriculumCourseKind",
    "Department",
    "EducationMode",
    "EnrollmentTransitionError",
    "Faculty",
    "MeetingWindow",
    "Program",
    "ProgramCurriculum",
    "Room",
    "SelectionEvaluation",
    "SelectionRuleCode",
    "SelectionRuleViolation",
    "StudentAcademicEnrollment",
    "TeacherAssignment",
    "Term",
    "evaluate_course_selection",
]
