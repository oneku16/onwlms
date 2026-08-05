"""Academic curriculum and course-selection policies."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from academics.domain.models import CourseEnrollment
from academics.domain.models import CourseEnrollmentStatus
from academics.domain.models import CourseOffering
from academics.domain.models import CourseSelectionPolicy
from academics.domain.models import EducationMode
from academics.domain.models import ProgramCurriculum
from academics.domain.models import SelectionEvaluation
from academics.domain.models import SelectionRuleCode
from academics.domain.models import SelectionRuleViolation


def evaluate_course_selection(
    *,
    policy: CourseSelectionPolicy,
    curriculum: ProgramCurriculum,
    selected_offerings: tuple[CourseOffering, ...],
    existing_enrollments: tuple[CourseEnrollment, ...],
    existing_offerings: tuple[CourseOffering, ...],
    completed_course_ids: frozenset[UUID],
    submitted_at: datetime,
) -> SelectionEvaluation:
    """Evaluate deadline, credit, prerequisite, and meeting-conflict rules."""

    credits = Decimal(0)
    violations: list[SelectionRuleViolation] = []
    if policy.education_mode is EducationMode.FIXED_CURRICULUM:
        violations.append(
            SelectionRuleViolation(code=SelectionRuleCode.FIXED_CURRICULUM)
        )
    if submitted_at > policy.deadline:
        violations.append(
            SelectionRuleViolation(code=SelectionRuleCode.DEADLINE_PASSED)
        )

    for offering in selected_offerings:
        curriculum_course = curriculum.course(offering.course_id)
        if curriculum_course is None:
            violations.append(
                SelectionRuleViolation(
                    code=SelectionRuleCode.PREREQUISITE_MISSING,
                    related_ids=(offering.course_id,),
                )
            )
            continue
        credits += curriculum_course.credits
        missing = sorted(
            curriculum_course.prerequisite_course_ids - completed_course_ids,
            key=str,
        )
        if missing:
            violations.append(
                SelectionRuleViolation(
                    code=SelectionRuleCode.PREREQUISITE_MISSING,
                    related_ids=(offering.course_id, *missing),
                )
            )

    active_credits = sum(
        (
            enrollment.credits
            for enrollment in existing_enrollments
            if enrollment.status is CourseEnrollmentStatus.ENROLLED
        ),
        start=Decimal(0),
    )
    if active_credits + credits > policy.maximum_credits:
        violations.append(
            SelectionRuleViolation(code=SelectionRuleCode.MAXIMUM_CREDITS)
        )

    all_pairs: list[tuple[CourseOffering, CourseOffering]] = []
    for index, left in enumerate(selected_offerings):
        all_pairs.extend((left, right) for right in selected_offerings[index + 1 :])
        all_pairs.extend((left, right) for right in existing_offerings)
    for left, right in all_pairs:
        if _offerings_overlap(left, right):
            violations.append(
                SelectionRuleViolation(
                    code=SelectionRuleCode.SCHEDULE_CONFLICT,
                    related_ids=(left.id, right.id),
                )
            )

    return SelectionEvaluation(
        offerings=selected_offerings,
        requested_credits=credits,
        violations=tuple(violations),
    )


def _offerings_overlap(
    left: CourseOffering,
    right: CourseOffering,
) -> bool:
    """Return whether any weekly meeting windows overlap."""

    return any(
        left_window.overlaps(right_window)
        for left_window in left.meeting_windows
        for right_window in right.meeting_windows
    )


__all__ = ["evaluate_course_selection"]
