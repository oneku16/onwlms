"""Academic SQLAlchemy mapping regression tests."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC
from datetime import date
from datetime import datetime
from decimal import Decimal
from typing import cast
from uuid import UUID
from uuid import uuid4

from academics.domain.models import CourseEnrollment
from academics.domain.models import CourseEnrollmentStatus
from academics.domain.models import CourseSelectionStatus
from academics.domain.models import Term
from academics.infrastructure.models import TermModel
from academics.infrastructure.sqlalchemy_repository import SQLAlchemyAcademicRepository
from shared.database import Database


class RecordingTermSession:
    """Capture the locked term update performed inside one transaction."""

    def __init__(self, term: TermModel | None) -> None:
        self.term = term
        self.statements: list[object] = []
        self.flush_count = 0

    async def scalar(self, statement: object) -> TermModel | None:
        self.statements.append(statement)
        return self.term

    async def flush(self) -> None:
        self.flush_count += 1


class RecordingTermDatabase:
    """Expose a repeatable synthetic tenant transaction."""

    def __init__(self, term: TermModel | None) -> None:
        self.session_value = RecordingTermSession(term)
        self.organization_ids: list[UUID | None] = []

    @asynccontextmanager
    async def session(
        self,
        *,
        organization_id: UUID | None = None,
        identity_subject_id: UUID | None = None,
    ) -> AsyncIterator[RecordingTermSession]:
        del identity_subject_id
        self.organization_ids.append(organization_id)
        yield self.session_value


class EmptyScalarRows:
    """Expose the result shape used by SQLAlchemy scalar collections."""

    def all(self) -> tuple[object, ...]:
        return ()


class RecordingSelectionSession:
    """Capture the bounded selection-request statement without returning rows."""

    def __init__(self) -> None:
        self.statements: list[object] = []

    async def scalars(self, statement: object) -> EmptyScalarRows:
        self.statements.append(statement)
        return EmptyScalarRows()


class RecordingSelectionDatabase:
    """Expose one synthetic tenant read transaction for query-shape assertions."""

    def __init__(self) -> None:
        self.session_value = RecordingSelectionSession()
        self.organization_ids: list[UUID | None] = []

    @asynccontextmanager
    async def session(
        self,
        *,
        organization_id: UUID | None = None,
        identity_subject_id: UUID | None = None,
    ) -> AsyncIterator[RecordingSelectionSession]:
        del identity_subject_id
        self.organization_ids.append(organization_id)
        yield self.session_value


def test_course_enrollment_mapping_preserves_official_selection_fields() -> None:
    enrollment = CourseEnrollment(
        id=uuid4(),
        organization_id=uuid4(),
        student_academic_enrollment_id=uuid4(),
        course_offering_id=uuid4(),
        credits=Decimal("4.50"),
        status=CourseEnrollmentStatus.ENROLLED,
        enrolled_at=datetime(2026, 8, 5, 10, tzinfo=UTC),
        selection_request_id=uuid4(),
    )

    model = SQLAlchemyAcademicRepository._course_enrollment_to_model(enrollment)
    restored = SQLAlchemyAcademicRepository._course_enrollment_from_model(model)

    assert restored == enrollment


async def test_term_closure_uses_a_tenant_transaction_and_row_lock() -> None:
    organization_id = uuid4()
    model = TermModel(
        id=uuid4(),
        organization_id=organization_id,
        academic_year_id=uuid4(),
        name="Fall 2026",
        starts_on=date(2026, 8, 10),
        ends_on=date(2026, 12, 20),
        enrollment_deadline=datetime(2026, 8, 20, tzinfo=UTC),
        is_closed=False,
    )
    database = RecordingTermDatabase(model)
    repository = SQLAlchemyAcademicRepository(cast(Database, database))

    first = await repository.close_term(
        organization_id=organization_id,
        term_id=model.id,
    )
    second = await repository.close_term(
        organization_id=organization_id,
        term_id=model.id,
    )

    assert first == Term(
        id=model.id,
        organization_id=organization_id,
        academic_year_id=model.academic_year_id,
        name=model.name,
        starts_on=model.starts_on,
        ends_on=model.ends_on,
        enrollment_deadline=model.enrollment_deadline,
        is_closed=True,
    )
    assert second == first
    assert model.is_closed is True
    assert database.organization_ids == [organization_id, organization_id]
    assert database.session_value.flush_count == 1
    assert all(
        "FOR UPDATE" in str(statement)
        for statement in database.session_value.statements
    )


async def test_selection_request_page_query_is_tenant_filtered_and_stable() -> None:
    organization_id = uuid4()
    database = RecordingSelectionDatabase()
    repository = SQLAlchemyAcademicRepository(cast(Database, database))

    values = await repository.list_selection_requests(
        organization_id=organization_id,
        status=CourseSelectionStatus.PENDING,
        limit=25,
        offset=5,
    )

    assert values == ()
    assert database.organization_ids == [organization_id]
    assert len(database.session_value.statements) == 1
    statement = str(database.session_value.statements[0])
    assert "academic_course_selection_requests.organization_id =" in statement
    assert "academic_course_selection_requests.status =" in statement
    assert (
        "ORDER BY academic_course_selection_requests.submitted_at DESC, "
        "academic_course_selection_requests.id" in statement
    )
    assert "LIMIT" in statement
    assert "OFFSET" in statement
