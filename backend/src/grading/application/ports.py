"""Application-owned official grading persistence and collaboration ports."""

from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Protocol
from uuid import UUID

from grading.domain.models import ExternalGradeEvidence
from grading.domain.models import FinalGrade
from grading.domain.models import GradeRevision
from grading.domain.models import GradeTarget
from grading.domain.models import GradingScale


class GradingRepository(Protocol):
    """Persist official scales, current grades, and immutable revision history."""

    async def save_scale(self, scale: GradingScale) -> None:
        """Persist one tenant-owned grading scale."""
        ...

    async def get_scale(
        self,
        *,
        organization_id: UUID,
        scale_id: UUID,
    ) -> GradingScale | None:
        """Return a grading scale only from the requested tenant."""
        ...

    async def list_scales(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[GradingScale, ...]:
        """Return a bounded stable page of tenant grading scales."""
        ...

    async def create_final_grade(self, grade: FinalGrade) -> None:
        """Create the sole official grade for one course enrollment."""
        ...

    async def get_final_grade(
        self,
        *,
        organization_id: UUID,
        final_grade_id: UUID,
    ) -> FinalGrade | None:
        """Return a final grade only from the requested tenant."""
        ...

    async def get_final_grade_for_course_enrollment(
        self,
        *,
        organization_id: UUID,
        course_enrollment_id: UUID,
    ) -> FinalGrade | None:
        """Return the current official grade of one tenant course enrollment."""
        ...

    async def revise_final_grade(
        self,
        *,
        grade: FinalGrade,
        expected_revision_number: int,
        revision: GradeRevision,
    ) -> None:
        """Atomically append history before replacing current grade state."""
        ...

    async def list_student_final_grades(
        self,
        *,
        organization_id: UUID,
        student_academic_enrollment_id: UUID,
    ) -> tuple[FinalGrade, ...]:
        """Return official final grades for one tenant student enrollment."""
        ...

    async def list_grade_revisions(
        self,
        *,
        organization_id: UUID,
        final_grade_id: UUID,
    ) -> tuple[GradeRevision, ...]:
        """Return immutable revision history for one tenant final grade."""
        ...


class GradeTargetDirectory(Protocol):
    """Resolve an academic course enrollment through a stable public contract."""

    async def get_grade_target(
        self,
        *,
        organization_id: UUID,
        course_enrollment_id: UUID,
    ) -> GradeTarget | None:
        """Return grading facts only when the target belongs to the tenant."""
        ...

    async def get_grade_target_for_participant(
        self,
        *,
        organization_id: UUID,
        course_offering_id: UUID,
        student_person_id: UUID,
    ) -> GradeTarget | None:
        """Return the one active participation of a person in an offering."""
        ...


class ExternalGradeEvidenceDirectory(Protocol):
    """Read and resolve pending external evidence owned by an integration."""

    async def get_pending_evidence(
        self,
        *,
        organization_id: UUID,
        evidence_id: UUID,
    ) -> ExternalGradeEvidence | None:
        """Return evidence only while it awaits an official decision."""
        ...

    async def record_acceptance(
        self,
        *,
        organization_id: UUID,
        evidence_id: UUID,
        final_grade_id: UUID,
        actor_subject_id: UUID,
        correlation_id: str,
    ) -> None:
        """Link the evidence to the official grade it produced."""
        ...

    async def record_rejection(
        self,
        *,
        organization_id: UUID,
        evidence_id: UUID,
        reason_code: str,
        actor_subject_id: UUID,
        correlation_id: str,
    ) -> None:
        """Mark the evidence rejected without discarding it."""
        ...


class TermClosureDirectory(Protocol):
    """Resolve official term closure without importing academic internals."""

    async def is_term_closed(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> bool:
        """Return whether official result amendment is post-closure."""
        ...


class TermGradeWriteGuard(Protocol):
    """Serialize official-grade writes with Academic term closure."""

    def hold_grade_write(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> AbstractAsyncContextManager[None]:
        """Hold shared tenant-term protection through closure check and commit."""
        ...


class GradingClock(Protocol):
    """Supply explicit timezone-aware grading application time."""

    def now(self) -> datetime:
        """Return the current timezone-aware UTC time."""
        ...


class GradingAuditSink(Protocol):
    """Append privacy-minimized evidence for official grade mutations."""

    async def record_final_grade_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        final_grade_id: UUID,
        correlation_id: str,
        after_term_closure: bool,
        outcome: str,
    ) -> None:
        """Record one grade-mutation intent or outcome without grade values."""
        ...

    async def record_external_evidence_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        evidence_id: UUID,
        correlation_id: str,
        outcome: str,
        reason: str | None,
    ) -> None:
        """Record official acceptance or rejection of external evidence."""
        ...


__all__ = [
    "ExternalGradeEvidenceDirectory",
    "GradeTargetDirectory",
    "GradingAuditSink",
    "GradingClock",
    "GradingRepository",
    "TermClosureDirectory",
    "TermGradeWriteGuard",
]
