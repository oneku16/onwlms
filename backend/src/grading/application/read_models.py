"""Official grading projections for ownership-safe self-service reads."""

from dataclasses import dataclass

from grading.domain.models import FinalGrade
from grading.domain.models import GpaSummary


@dataclass(frozen=True, slots=True)
class OfficialStudentReport:
    """Contain current official grades and their deterministic GPA summary."""

    grades: tuple[FinalGrade, ...]
    gpa: GpaSummary


__all__ = ["OfficialStudentReport"]
