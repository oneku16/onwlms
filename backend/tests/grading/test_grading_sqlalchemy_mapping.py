"""Official-grading SQLAlchemy mapping regression tests."""

from datetime import UTC
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from grading.domain.models import FinalGrade
from grading.infrastructure.sqlalchemy_repository import SQLAlchemyGradingRepository


def test_final_grade_mapping_preserves_current_official_state() -> None:
    recorded_at = datetime(2026, 8, 5, 10, tzinfo=UTC)
    updated_at = datetime(2026, 8, 6, 10, tzinfo=UTC)
    grade = FinalGrade(
        id=uuid4(),
        organization_id=uuid4(),
        student_academic_enrollment_id=uuid4(),
        course_enrollment_id=uuid4(),
        course_offering_id=uuid4(),
        course_id=uuid4(),
        term_id=uuid4(),
        grading_scale_id=uuid4(),
        raw_score=Decimal("88.50"),
        symbol="B",
        credits_attempted=Decimal("4"),
        credits_earned=Decimal("4"),
        grade_points=Decimal("3"),
        gpa_contribution=Decimal("12"),
        revision_number=1,
        recorded_by=uuid4(),
        recorded_at=recorded_at,
        updated_at=updated_at,
        recorded_after_term_closure=True,
        recording_explanation="Registrar-approved late finalization.",
    )

    model = SQLAlchemyGradingRepository._grade_to_model(grade)
    restored = SQLAlchemyGradingRepository._grade_from_model(model)

    assert restored == grade
