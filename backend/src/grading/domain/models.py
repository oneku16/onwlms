"""Framework-independent official grade, scale, and transcript models."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from grading.domain.exceptions import GradingRuleError


class GradingScaleKind(StrEnum):
    """Classify supported official grading-scale semantics."""

    PERCENTAGE = "percentage"
    LETTER = "letter"
    ECTS = "ects"
    FIVE_POINT = "five_point"
    PASS_FAIL = "pass_fail"  # noqa: S105 - official grading terminology.
    CUSTOM = "custom"


class GradingScaleTemplate(StrEnum):
    """Name conservative built-in scale templates that organizations may copy."""

    PERCENTAGE = "percentage"
    ECTS = "ects"
    FIVE_POINT = "five_point"
    PASS_FAIL = "pass_fail"  # noqa: S105 - official grading terminology.


@dataclass(frozen=True, slots=True)
class GradeBand:
    """Map scores at or above a threshold to an official outcome."""

    minimum_score: Decimal
    symbol: str
    passing: bool
    grade_points: Decimal | None

    def __post_init__(self) -> None:
        """Require a finite threshold, symbol, and non-negative GPA mapping."""

        if not self.minimum_score.is_finite():
            raise GradingRuleError("Grade-band threshold must be finite.")
        if not self.symbol.strip():
            raise GradingRuleError("Grade-band symbol is required.")
        if self.grade_points is not None:
            if not self.grade_points.is_finite() or self.grade_points < Decimal(0):
                raise GradingRuleError("Grade points must be finite and non-negative.")


@dataclass(frozen=True, slots=True)
class GradeOutcome:
    """Return the official outcome resolved from a grading scale."""

    symbol: str
    passing: bool
    grade_points: Decimal | None


@dataclass(frozen=True, slots=True)
class GradingScale:
    """Represent a tenant-owned official grading scale and GPA mapping."""

    id: UUID
    organization_id: UUID
    name: str
    kind: GradingScaleKind
    minimum_score: Decimal
    maximum_score: Decimal
    bands: tuple[GradeBand, ...]

    def __post_init__(self) -> None:
        """Require a complete, ordered, non-ambiguous scale definition."""

        if not self.name.strip():
            raise GradingRuleError("Grading scale name is required.")
        if not self.minimum_score.is_finite() or not self.maximum_score.is_finite():
            raise GradingRuleError("Grading scale bounds must be finite.")
        if self.minimum_score >= self.maximum_score:
            raise GradingRuleError("Grading scale maximum must exceed its minimum.")
        if not self.bands:
            raise GradingRuleError("Grading scale requires at least one band.")
        thresholds = [band.minimum_score for band in self.bands]
        symbols = [band.symbol.casefold() for band in self.bands]
        if len(thresholds) != len(set(thresholds)):
            raise GradingRuleError("Grade-band thresholds must be unique.")
        if len(symbols) != len(set(symbols)):
            raise GradingRuleError("Grade-band symbols must be unique.")
        if min(thresholds) != self.minimum_score:
            raise GradingRuleError(
                "Grading scale bands must cover the configured minimum score."
            )
        if any(
            threshold < self.minimum_score or threshold > self.maximum_score
            for threshold in thresholds
        ):
            raise GradingRuleError("Grade-band threshold is outside scale bounds.")

    def resolve(self, score: Decimal) -> GradeOutcome:
        """Resolve a finite score to the highest matching threshold."""

        if not score.is_finite():
            raise GradingRuleError("Final score must be finite.")
        if score < self.minimum_score or score > self.maximum_score:
            raise GradingRuleError("Final score is outside grading scale bounds.")
        matching = max(
            (band for band in self.bands if score >= band.minimum_score),
            key=lambda band: band.minimum_score,
        )
        return GradeOutcome(
            symbol=matching.symbol,
            passing=matching.passing,
            grade_points=matching.grade_points,
        )


@dataclass(frozen=True, slots=True)
class GradeTarget:
    """Describe the academic enrollment facts grading is allowed to consume."""

    organization_id: UUID
    student_academic_enrollment_id: UUID
    course_enrollment_id: UUID
    course_offering_id: UUID
    term_id: UUID
    course_id: UUID
    credits: Decimal

    def __post_init__(self) -> None:
        """Require positive official course-enrollment credits."""

        if self.credits <= Decimal(0):
            raise GradingRuleError("Grade target credits must be positive.")


@dataclass(frozen=True, slots=True)
class FinalGrade:
    """Represent the current official final result for one course enrollment."""

    id: UUID
    organization_id: UUID
    student_academic_enrollment_id: UUID
    course_enrollment_id: UUID
    course_offering_id: UUID
    course_id: UUID
    term_id: UUID
    grading_scale_id: UUID
    raw_score: Decimal
    symbol: str
    credits_attempted: Decimal
    credits_earned: Decimal
    grade_points: Decimal | None
    gpa_contribution: Decimal | None
    revision_number: int
    recorded_by: UUID
    recorded_at: datetime
    updated_at: datetime
    recorded_after_term_closure: bool = False
    recording_explanation: str | None = None

    def __post_init__(self) -> None:
        """Require coherent credits, GPA values, revision, and aware times."""

        if not self.raw_score.is_finite():
            raise GradingRuleError("Final grade score must be finite.")
        if not self.symbol.strip():
            raise GradingRuleError("Final grade symbol is required.")
        if self.credits_attempted <= Decimal(0):
            raise GradingRuleError("Credits attempted must be positive.")
        if self.credits_earned < Decimal(0):
            raise GradingRuleError("Credits earned cannot be negative.")
        if self.credits_earned > self.credits_attempted:
            raise GradingRuleError("Credits earned cannot exceed credits attempted.")
        if self.grade_points is None and self.gpa_contribution is not None:
            raise GradingRuleError("Non-GPA grades cannot contribute to GPA.")
        if self.grade_points is not None:
            expected = self.grade_points * self.credits_attempted
            if self.gpa_contribution != expected:
                raise GradingRuleError("GPA contribution does not match grade points.")
        if self.revision_number < 0:
            raise GradingRuleError("Grade revision number cannot be negative.")
        _require_aware(self.recorded_at, "Final grade recorded time")
        _require_aware(self.updated_at, "Final grade updated time")
        if self.recorded_after_term_closure:
            if not (self.recording_explanation or "").strip():
                raise GradingRuleError(
                    "A post-closure final grade explanation is required."
                )
        elif self.recording_explanation is not None:
            raise GradingRuleError(
                "An initial grade explanation is reserved for post-closure records."
            )


@dataclass(frozen=True, slots=True)
class GradeRevision:
    """Preserve immutable before-and-after state for one grade amendment."""

    id: UUID
    organization_id: UUID
    final_grade_id: UUID
    revision_number: int
    previous_raw_score: Decimal
    previous_symbol: str
    previous_credits_earned: Decimal
    previous_grade_points: Decimal | None
    previous_gpa_contribution: Decimal | None
    replacement_raw_score: Decimal
    replacement_symbol: str
    replacement_credits_earned: Decimal
    replacement_grade_points: Decimal | None
    replacement_gpa_contribution: Decimal | None
    explanation: str
    revised_by: UUID
    revised_at: datetime
    after_term_closure: bool

    def __post_init__(self) -> None:
        """Require an explanation, positive revision, and aware revision time."""

        if self.revision_number <= 0:
            raise GradingRuleError("Grade revision number must be positive.")
        if not self.explanation.strip():
            raise GradingRuleError("Grade revision explanation is required.")
        _require_aware(self.revised_at, "Grade revision time")


@dataclass(frozen=True, slots=True)
class FinalGradeHistory:
    """Expose immutable initial-record evidence with amendment history."""

    final_grade_id: UUID
    recorded_by: UUID
    recorded_at: datetime
    recorded_after_term_closure: bool
    recording_explanation: str | None
    revisions: tuple[GradeRevision, ...]


@dataclass(frozen=True, slots=True)
class TranscriptRecord:
    """Represent one official transcript line derived from a final grade."""

    final_grade_id: UUID
    course_id: UUID
    course_offering_id: UUID
    term_id: UUID
    symbol: str
    credits_attempted: Decimal
    credits_earned: Decimal
    grade_points: Decimal | None
    gpa_contribution: Decimal | None


@dataclass(frozen=True, slots=True)
class GpaSummary:
    """Summarize attempted, earned, GPA-bearing credits and official GPA."""

    credits_attempted: Decimal
    credits_earned: Decimal
    gpa_credits_attempted: Decimal
    quality_points: Decimal
    gpa: Decimal | None


def build_scale_from_template(
    *,
    scale_id: UUID,
    organization_id: UUID,
    name: str,
    template: GradingScaleTemplate,
) -> GradingScale:
    """Create a tenant-owned copy of one conservative official scale template."""

    if template is GradingScaleTemplate.PERCENTAGE:
        return GradingScale(
            id=scale_id,
            organization_id=organization_id,
            name=name,
            kind=GradingScaleKind.PERCENTAGE,
            minimum_score=Decimal(0),
            maximum_score=Decimal(100),
            bands=(
                GradeBand(Decimal(0), "F", False, Decimal(0)),
                GradeBand(Decimal(60), "D", True, Decimal(1)),
                GradeBand(Decimal(70), "C", True, Decimal(2)),
                GradeBand(Decimal(80), "B", True, Decimal(3)),
                GradeBand(Decimal(90), "A", True, Decimal(4)),
            ),
        )
    if template is GradingScaleTemplate.ECTS:
        return GradingScale(
            id=scale_id,
            organization_id=organization_id,
            name=name,
            kind=GradingScaleKind.ECTS,
            minimum_score=Decimal(0),
            maximum_score=Decimal(100),
            bands=(
                GradeBand(Decimal(0), "F", False, Decimal(0)),
                GradeBand(Decimal(40), "FX", False, Decimal(0)),
                GradeBand(Decimal(50), "E", True, Decimal("2.0")),
                GradeBand(Decimal(60), "D", True, Decimal("2.5")),
                GradeBand(Decimal(70), "C", True, Decimal("3.0")),
                GradeBand(Decimal(80), "B", True, Decimal("3.5")),
                GradeBand(Decimal(90), "A", True, Decimal("4.0")),
            ),
        )
    if template is GradingScaleTemplate.FIVE_POINT:
        return GradingScale(
            id=scale_id,
            organization_id=organization_id,
            name=name,
            kind=GradingScaleKind.FIVE_POINT,
            minimum_score=Decimal(1),
            maximum_score=Decimal(5),
            bands=(
                GradeBand(Decimal(1), "1", False, Decimal(0)),
                GradeBand(Decimal(2), "2", False, Decimal(0)),
                GradeBand(Decimal(3), "3", True, Decimal(2)),
                GradeBand(Decimal(4), "4", True, Decimal(3)),
                GradeBand(Decimal(5), "5", True, Decimal(4)),
            ),
        )
    return GradingScale(
        id=scale_id,
        organization_id=organization_id,
        name=name,
        kind=GradingScaleKind.PASS_FAIL,
        minimum_score=Decimal(0),
        maximum_score=Decimal(1),
        bands=(
            GradeBand(Decimal(0), "Fail", False, None),
            GradeBand(Decimal(1), "Pass", True, None),
        ),
    )


def calculate_gpa_summary(
    grades: tuple[FinalGrade, ...],
) -> GpaSummary:
    """Calculate official GPA from grade-level stored contributions."""

    credits_attempted = sum(
        (grade.credits_attempted for grade in grades),
        start=Decimal(0),
    )
    credits_earned = sum(
        (grade.credits_earned for grade in grades),
        start=Decimal(0),
    )
    gpa_grades = tuple(grade for grade in grades if grade.grade_points is not None)
    gpa_credits = sum(
        (grade.credits_attempted for grade in gpa_grades),
        start=Decimal(0),
    )
    quality_points = sum(
        (grade.gpa_contribution or Decimal(0) for grade in gpa_grades),
        start=Decimal(0),
    )
    return GpaSummary(
        credits_attempted=credits_attempted,
        credits_earned=credits_earned,
        gpa_credits_attempted=gpa_credits,
        quality_points=quality_points,
        gpa=(quality_points / gpa_credits if gpa_credits > Decimal(0) else None),
    )


def transcript_record(grade: FinalGrade) -> TranscriptRecord:
    """Project a supported official transcript record from current grade state."""

    return TranscriptRecord(
        final_grade_id=grade.id,
        course_id=grade.course_id,
        course_offering_id=grade.course_offering_id,
        term_id=grade.term_id,
        symbol=grade.symbol,
        credits_attempted=grade.credits_attempted,
        credits_earned=grade.credits_earned,
        grade_points=grade.grade_points,
        gpa_contribution=grade.gpa_contribution,
    )


def _require_aware(
    value: datetime,
    label: str,
) -> None:
    """Reject timestamps whose UTC offset cannot be determined."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise GradingRuleError(f"{label} must be timezone-aware.")


__all__ = [
    "FinalGrade",
    "FinalGradeHistory",
    "GpaSummary",
    "GradeBand",
    "GradeOutcome",
    "GradeRevision",
    "GradeTarget",
    "GradingScale",
    "GradingScaleKind",
    "GradingScaleTemplate",
    "TranscriptRecord",
    "build_scale_from_template",
    "calculate_gpa_summary",
    "transcript_record",
]
