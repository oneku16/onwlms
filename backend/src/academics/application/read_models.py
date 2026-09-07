"""Minimum academic projections for ownership-safe self-service reads."""

from dataclasses import dataclass
from datetime import date
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from academics.domain.models import MeetingWindow


@dataclass(frozen=True, slots=True)
class StudentAcademicSnapshot:
    """Describe a student's official enrollment identifiers and current program."""

    student_profile_id: UUID
    enrollment_ids: tuple[UUID, ...]
    active_course_offering_ids: tuple[UUID, ...]
    current_program: str | None


@dataclass(frozen=True, slots=True)
class AcademicSectionSummary:
    """Describe one offering without enrollment or grading internals."""

    id: UUID
    course_id: UUID
    course_code: str
    course_title: str
    section_name: str
    term_name: str


@dataclass(frozen=True, slots=True)
class AcademicCourseSummary:
    """Describe one official course for transcript presentation."""

    id: UUID
    code: str
    title: str


@dataclass(frozen=True, slots=True)
class AcademicRoomSummary:
    """Describe one room using its organization-owned display code."""

    id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class CourseSelectionOfferingOption:
    """Describe one curriculum offering available for student selection."""

    id: UUID
    course_id: UUID
    course_code: str
    course_title: str
    section_code: str
    credits: Decimal
    capacity: int
    meeting_windows: tuple[MeetingWindow, ...]


@dataclass(frozen=True, slots=True)
class CourseSelectionTermOption:
    """Describe one open policy-backed term and its selectable offerings."""

    id: UUID
    name: str
    starts_on: date
    ends_on: date
    deadline: datetime
    maximum_credits: Decimal
    approval_required: bool
    offerings: tuple[CourseSelectionOfferingOption, ...]


@dataclass(frozen=True, slots=True)
class CourseSelectionEnrollmentOption:
    """Bind selectable terms to one exact actor-owned active enrollment."""

    id: UUID
    program_id: UUID
    program_name: str
    academic_year_id: UUID
    terms: tuple[CourseSelectionTermOption, ...]


@dataclass(frozen=True, slots=True)
class StudentCourseSelectionContext:
    """Contain all bounded selection choices for the current student actor."""

    student_profile_id: UUID
    enrollments: tuple[CourseSelectionEnrollmentOption, ...]


__all__ = [
    "AcademicCourseSummary",
    "AcademicRoomSummary",
    "AcademicSectionSummary",
    "CourseSelectionEnrollmentOption",
    "CourseSelectionOfferingOption",
    "CourseSelectionTermOption",
    "StudentAcademicSnapshot",
    "StudentCourseSelectionContext",
]
