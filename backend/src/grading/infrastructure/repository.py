"""Functional in-memory adapters for official grading application ports."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from core.errors import ConflictError
from grading.domain.exceptions import GradeRevisionConflictError
from grading.domain.models import FinalGrade
from grading.domain.models import GradeRevision
from grading.domain.models import GradeTarget
from grading.domain.models import GradingScale

TenantKey = tuple[UUID, UUID]


class InMemoryGradeTargetDirectory:
    """Resolve explicitly registered tenant academic grading targets."""

    def __init__(
        self,
        targets: tuple[GradeTarget, ...] = (),
    ) -> None:
        self._targets = {
            (target.organization_id, target.course_enrollment_id): target
            for target in targets
        }

    async def get_grade_target(
        self,
        *,
        organization_id: UUID,
        course_enrollment_id: UUID,
    ) -> GradeTarget | None:
        """Return a grade target only from the requested tenant."""

        return self._targets.get((organization_id, course_enrollment_id))

    def add(self, target: GradeTarget) -> None:
        """Register an academic grade target for deterministic tests."""

        self._targets[(target.organization_id, target.course_enrollment_id)] = target


class InMemoryTermClosureDirectory:
    """Track explicit tenant term closure state for tests and local composition."""

    def __init__(
        self,
        closed_terms: set[tuple[UUID, UUID]] | None = None,
    ) -> None:
        self._closed_terms = set(closed_terms or set())

    async def is_term_closed(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> bool:
        """Return whether the exact tenant term is closed."""

        return (organization_id, term_id) in self._closed_terms

    def set_closed(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> None:
        """Mark an exact tenant term closed for deterministic tests."""

        self._closed_terms.add((organization_id, term_id))


class InMemoryTermGradeWriteGuard:
    """Serialize local grade writes for one tenant term in deterministic tests."""

    def __init__(self) -> None:
        self._locks: dict[TenantKey, asyncio.Lock] = {}

    @asynccontextmanager
    async def hold_grade_write(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> AsyncIterator[None]:
        """Hold one process-local tenant-term guard for the context lifetime."""

        lock = self._locks.setdefault((organization_id, term_id), asyncio.Lock())
        async with lock:
            yield


class InMemoryGradingRepository:
    """Preserve official-grade uniqueness and revision atomicity in memory."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._scales: dict[TenantKey, GradingScale] = {}
        self._grades: dict[TenantKey, FinalGrade] = {}
        self._course_enrollment_index: dict[TenantKey, UUID] = {}
        self._revisions: dict[TenantKey, GradeRevision] = {}

    async def save_scale(self, scale: GradingScale) -> None:
        """Persist an immutable scale definition with a tenant-unique name."""

        key = (scale.organization_id, scale.id)
        existing = self._scales.get(key)
        if existing is not None and existing != scale:
            raise ConflictError("Published grading scales are immutable.")
        duplicate_name = next(
            (
                candidate
                for candidate in self._scales.values()
                if candidate.organization_id == scale.organization_id
                and candidate.id != scale.id
                and candidate.name.casefold() == scale.name.casefold()
            ),
            None,
        )
        if duplicate_name is not None:
            raise ConflictError("A grading scale with this name already exists.")
        self._scales[key] = scale

    async def get_scale(
        self,
        *,
        organization_id: UUID,
        scale_id: UUID,
    ) -> GradingScale | None:
        """Return a scale only from the requested tenant."""

        return self._scales.get((organization_id, scale_id))

    async def list_scales(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[GradingScale, ...]:
        """Return a bounded stable grading-scale page for one tenant."""

        values = sorted(
            (
                value
                for value in self._scales.values()
                if value.organization_id == organization_id
            ),
            key=lambda value: (value.name.casefold(), str(value.id)),
        )
        return tuple(values[offset : offset + limit])

    async def create_final_grade(self, grade: FinalGrade) -> None:
        """Create one official grade per tenant course enrollment."""

        async with self._lock:
            grade_key = (grade.organization_id, grade.id)
            course_key = (grade.organization_id, grade.course_enrollment_id)
            if grade_key in self._grades or course_key in self._course_enrollment_index:
                raise ConflictError(
                    "An official final grade already exists for this enrollment."
                )
            self._grades[grade_key] = grade
            self._course_enrollment_index[course_key] = grade.id

    async def get_final_grade(
        self,
        *,
        organization_id: UUID,
        final_grade_id: UUID,
    ) -> FinalGrade | None:
        """Return a final grade only from the requested tenant."""

        return self._grades.get((organization_id, final_grade_id))

    async def revise_final_grade(
        self,
        *,
        grade: FinalGrade,
        expected_revision_number: int,
        revision: GradeRevision,
    ) -> None:
        """Atomically append the immutable revision before replacing current state."""

        async with self._lock:
            grade_key = (grade.organization_id, grade.id)
            current = self._grades.get(grade_key)
            if current is None or current.revision_number != expected_revision_number:
                raise GradeRevisionConflictError(
                    "Final grade changed during the requested revision."
                )
            if revision.revision_number != expected_revision_number + 1:
                raise GradeRevisionConflictError(
                    "Grade revision sequence is not contiguous."
                )
            if (
                grade.recorded_by != current.recorded_by
                or grade.recorded_at != current.recorded_at
                or grade.recorded_after_term_closure
                != current.recorded_after_term_closure
                or grade.recording_explanation != current.recording_explanation
            ):
                raise GradeRevisionConflictError(
                    "Initial grade recording evidence is immutable."
                )
            revision_key = (revision.organization_id, revision.id)
            if revision_key in self._revisions:
                raise GradeRevisionConflictError("Grade revision already exists.")
            self._revisions[revision_key] = revision
            self._grades[grade_key] = grade

    async def list_student_final_grades(
        self,
        *,
        organization_id: UUID,
        student_academic_enrollment_id: UUID,
    ) -> tuple[FinalGrade, ...]:
        """Return stable ordered official grades for one student enrollment."""

        grades = (
            grade
            for grade in self._grades.values()
            if grade.organization_id == organization_id
            and grade.student_academic_enrollment_id == student_academic_enrollment_id
        )
        return tuple(
            sorted(
                grades,
                key=lambda grade: (str(grade.term_id), str(grade.course_id)),
            )
        )

    async def list_grade_revisions(
        self,
        *,
        organization_id: UUID,
        final_grade_id: UUID,
    ) -> tuple[GradeRevision, ...]:
        """Return contiguous immutable revision history for one final grade."""

        revisions = (
            revision
            for revision in self._revisions.values()
            if revision.organization_id == organization_id
            and revision.final_grade_id == final_grade_id
        )
        return tuple(sorted(revisions, key=lambda item: item.revision_number))


__all__ = [
    "InMemoryGradeTargetDirectory",
    "InMemoryGradingRepository",
    "InMemoryTermClosureDirectory",
    "InMemoryTermGradeWriteGuard",
]
