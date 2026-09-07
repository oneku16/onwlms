"""Minimum academic projections for ownership-safe self-service reads."""

from dataclasses import dataclass
from uuid import UUID


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


__all__ = [
    "AcademicCourseSummary",
    "AcademicRoomSummary",
    "AcademicSectionSummary",
    "StudentAcademicSnapshot",
]
