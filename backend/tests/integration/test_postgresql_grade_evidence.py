"""Real PostgreSQL tenant scoping and single resolution of Moodle grade evidence."""

import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC
from datetime import date
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from psycopg import sql
from psycopg.errors import InsufficientPrivilege
from sqlalchemy.engine import URL
from sqlalchemy.engine import make_url

from academic_adapters import AcademicGradeTargetAdapter
from academics.application.reference_service import AcademicReferenceService
from academics.domain.models import AcademicEnrollmentStatus
from academics.domain.models import AcademicYear
from academics.domain.models import Course
from academics.domain.models import CourseOffering
from academics.domain.models import Department
from academics.domain.models import EducationMode
from academics.domain.models import Faculty
from academics.domain.models import Program
from academics.domain.models import StudentAcademicEnrollment
from academics.domain.models import Term
from academics.infrastructure.sqlalchemy_repository import SQLAlchemyAcademicRepository
from core.errors import ConflictError
from core.errors import NotFoundError
from core.settings import AppEnvironment
from core.settings import Settings
from integrations.domain.moodle import GradeEvidenceStatus
from integrations.domain.moodle import MoodleFinalGradeEvidence
from integrations.domain.moodle import MoodleGradeReconciliationRun
from integrations.domain.moodle import ReconciliationRunStatus
from integrations.infrastructure.repository import SQLAlchemyMoodleIntegrationRepository
from integrations.infrastructure.repository import (
    SQLAlchemyMoodleReconciliationRunRepository,
)
from people.application.reference_service import PeopleReferenceService
from people.infrastructure.repositories import SQLAlchemyPeopleRepository
from shared.database import Database


@dataclass(frozen=True, slots=True)
class EphemeralDatabase:
    """Hold disposable migration and runtime connection strings."""

    migration_dsn: str
    runtime_dsn: str


def _sync_dsn(url: URL, *, database: str) -> str:
    return url.set(
        drivername="postgresql",
        database=database,
    ).render_as_string(hide_password=False)


def _require_local_admin_url() -> URL:
    if os.environ.get("OWNSIS_RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set OWNSIS_RUN_POSTGRES_INTEGRATION=1 to run PostgreSQL tests")
    url = make_url(
        os.environ.get(
            "DATABASE_MIGRATION_URL",
            "postgresql+psycopg://ownsis_migration:ownsis_migration@localhost:5432/ownsis",
        )
    )
    if url.host not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("PostgreSQL integration tests require a local database host")
    return url


@pytest.fixture(scope="module")
def test_database() -> Iterator[EphemeralDatabase]:
    """Migrate a unique local database and always drop it after the module."""

    migration_url = _require_local_admin_url()
    database_name = f"ownsis_grade_evidence_test_{uuid4().hex}"
    admin_dsn = _sync_dsn(migration_url, database="postgres")
    runtime_url = make_url(
        os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://ownsis:ownsis@localhost:5432/ownsis",
        )
    )
    database = EphemeralDatabase(
        migration_dsn=_sync_dsn(migration_url, database=database_name),
        runtime_dsn=_sync_dsn(runtime_url, database=database_name),
    )

    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(
            sql.SQL("CREATE DATABASE {} OWNER ownsis_migration").format(
                sql.Identifier(database_name)
            )
        )

    repository_root = Path(__file__).resolve().parents[3]
    config = Config(str(repository_root / "backend" / "alembic.ini"))
    previous_migration_url = os.environ.get("DATABASE_MIGRATION_URL")
    os.environ["DATABASE_MIGRATION_URL"] = database.migration_dsn.replace(
        "postgresql://",
        "postgresql+psycopg://",
        1,
    )
    try:
        command.upgrade(config, "head")
        command.current(config, check_heads=True)
        command.check(config)
        yield database
    finally:
        if previous_migration_url is None:
            os.environ.pop("DATABASE_MIGRATION_URL", None)
        else:
            os.environ["DATABASE_MIGRATION_URL"] = previous_migration_url
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(database_name)
                )
            )


def _insert_organization(test_database: EphemeralDatabase) -> UUID:
    organization_id = uuid4()
    with psycopg.connect(test_database.runtime_dsn) as connection:
        connection.execute(
            """
            INSERT INTO organizations (
                id, slug, organization_type, status, display_name,
                primary_color, secondary_color, locale, timezone,
                education_mode, created_at, updated_at
            ) VALUES (
                %s, %s, 'school', 'active', 'Grade Evidence Test',
                '#112233', '#445566', 'en', 'UTC', 'school', now(), now()
            )
            """,
            (organization_id, f"grade-evidence-{organization_id.hex}"),
        )
    return organization_id


def _runtime_database(test_database: EphemeralDatabase) -> Database:
    return Database(
        Settings(APP_ENV=AppEnvironment.TEST),
        database_url=test_database.runtime_dsn.replace(
            "postgresql://",
            "postgresql+asyncpg://",
            1,
        ),
    )


def _evidence(*, external_event_id: str) -> MoodleFinalGradeEvidence:
    return MoodleFinalGradeEvidence(
        external_event_id=external_event_id,
        course_offering_id=uuid4(),
        student_person_id=uuid4(),
        grade_value="87.5",
        observed_at=datetime(2026, 9, 8, 12, tzinfo=UTC),
        source_version="moodle-webservice-v1",
    )


@pytest.mark.integration
async def test_evidence_secrets_mappings_and_runs_are_tenant_scoped(
    test_database: EphemeralDatabase,
) -> None:
    """Keep every new integration row invisible and immutable across tenants."""

    organization_a = _insert_organization(test_database)
    organization_b = _insert_organization(test_database)
    database = _runtime_database(test_database)
    repository = SQLAlchemyMoodleIntegrationRepository(database)
    runs = SQLAlchemyMoodleReconciliationRunRepository(database)
    try:
        configuration = await repository.configure(
            organization_id=organization_a,
            base_url="https://moodle.example.edu",
            encrypted_token="protected-token",
        )
        assert configuration.grade_events_configured is False
        with_secret = await repository.set_grade_event_secret(
            organization_id=organization_a,
            encrypted_secret="protected-secret",
        )
        assert with_secret.grade_events_configured is True
        assert (
            await repository.get_encrypted_grade_event_secret(organization_a)
            == "protected-secret"
        )
        assert await repository.get_encrypted_grade_event_secret(organization_b) is None
        with pytest.raises(NotFoundError):
            await repository.set_grade_event_secret(
                organization_id=organization_b,
                encrypted_secret="protected-secret",
            )

        person_id = uuid4()
        await repository.put_mapping(
            organization_id=organization_a,
            entity_type="person",
            entity_id=person_id,
            external_id="user-7",
        )
        assert (
            await repository.get_entity_id(
                organization_id=organization_a,
                entity_type="person",
                external_id="user-7",
            )
            == person_id
        )
        assert (
            await repository.get_entity_id(
                organization_id=organization_b,
                entity_type="person",
                external_id="user-7",
            )
            is None
        )

        evidence = _evidence(external_event_id="moodle:grade:1")
        assert (
            await repository.accept_grade_event_once(
                organization_id=organization_a,
                evidence=evidence,
            )
            is True
        )
        assert (
            await repository.accept_grade_event_once(
                organization_id=organization_a,
                evidence=evidence,
            )
            is False
        )
        # The same external key in another tenant is a distinct, independent event.
        assert (
            await repository.accept_grade_event_once(
                organization_id=organization_b,
                evidence=evidence,
            )
            is True
        )
        await repository.mark_grade_event_outcome(
            organization_id=organization_a,
            external_event_id="moodle:grade:1",
            status=GradeEvidenceStatus.PENDING,
            reason_code="review_required",
        )
        stored = await repository.get_grade_evidence_by_event(
            organization_id=organization_a,
            external_event_id="moodle:grade:1",
        )
        assert stored is not None
        assert stored.reason_code == "review_required"
        listed = await repository.list_grade_evidence(
            organization_id=organization_a,
            status=GradeEvidenceStatus.PENDING,
            course_offering_id=None,
            limit=10,
            offset=0,
        )
        assert [record.id for record in listed] == [stored.id]
        assert (
            await repository.get_grade_evidence(
                organization_id=organization_b,
                evidence_id=stored.id,
            )
            is None
        )
        with pytest.raises(NotFoundError):
            await repository.resolve_grade_evidence(
                organization_id=organization_b,
                evidence_id=stored.id,
                status=GradeEvidenceStatus.ACCEPTED,
                reason_code=None,
                final_grade_id=uuid4(),
                resolved_by=uuid4(),
                resolved_at=datetime(2026, 9, 8, 13, tzinfo=UTC),
            )
        final_grade_id = uuid4()
        resolved = await repository.resolve_grade_evidence(
            organization_id=organization_a,
            evidence_id=stored.id,
            status=GradeEvidenceStatus.ACCEPTED,
            reason_code=None,
            final_grade_id=final_grade_id,
            resolved_by=uuid4(),
            resolved_at=datetime(2026, 9, 8, 13, tzinfo=UTC),
        )
        assert resolved.status is GradeEvidenceStatus.ACCEPTED
        assert resolved.accepted_final_grade_id == final_grade_id
        with pytest.raises(ConflictError):
            await repository.resolve_grade_evidence(
                organization_id=organization_a,
                evidence_id=stored.id,
                status=GradeEvidenceStatus.REJECTED,
                reason_code="rejected_by_reviewer",
                final_grade_id=None,
                resolved_by=uuid4(),
                resolved_at=datetime(2026, 9, 8, 14, tzinfo=UTC),
            )

        run = MoodleGradeReconciliationRun(
            id=uuid4(),
            organization_id=organization_a,
            term_id=uuid4(),
            requested_by=uuid4(),
            status=ReconciliationRunStatus.RUNNING,
            started_at=datetime(2026, 9, 8, 12, tzinfo=UTC),
            offering_count=2,
        )
        await runs.create_run(run)
        completed = MoodleGradeReconciliationRun(
            id=run.id,
            organization_id=organization_a,
            term_id=run.term_id,
            requested_by=run.requested_by,
            status=ReconciliationRunStatus.SUCCEEDED,
            started_at=run.started_at,
            finished_at=datetime(2026, 9, 8, 12, 1, tzinfo=UTC),
            offering_count=2,
            unmapped_offering_count=1,
            observed_count=3,
            new_evidence_count=2,
            duplicate_count=1,
            unmapped_user_count=0,
        )
        await runs.complete_run(completed)
        assert await runs.get_run(organization_id=organization_a, run_id=run.id) == (
            completed
        )
        assert await runs.get_run(organization_id=organization_b, run_id=run.id) is None
        assert (
            await runs.list_runs(organization_id=organization_b, limit=5, offset=0)
            == ()
        )
        with pytest.raises(NotFoundError):
            await runs.complete_run(
                MoodleGradeReconciliationRun(
                    id=run.id,
                    organization_id=organization_b,
                    term_id=run.term_id,
                    requested_by=run.requested_by,
                    status=ReconciliationRunStatus.FAILED,
                    started_at=run.started_at,
                )
            )
    finally:
        await database.close()

    with psycopg.connect(test_database.runtime_dsn) as connection:
        connection.execute(
            "SELECT set_config('app.organization_id', %s, false)",
            (str(organization_a),),
        )
        visible = connection.execute(
            "SELECT count(*) FROM moodle_grade_reconciliation_runs"
        ).fetchone()
        assert visible == (1,)
        with pytest.raises(InsufficientPrivilege):
            connection.execute("DELETE FROM moodle_grade_reconciliation_runs")
        connection.rollback()
        with pytest.raises(InsufficientPrivilege):
            connection.execute("DELETE FROM moodle_grade_evidence")


def _set_tenant(connection: psycopg.Connection, organization_id: UUID) -> None:
    connection.execute(
        "SELECT set_config('app.organization_id', %s, false)",
        (str(organization_id),),
    )


def _insert_person_with_profile(
    test_database: EphemeralDatabase,
    *,
    organization_id: UUID,
    kind: str,
) -> tuple[UUID, UUID]:
    person_id = uuid4()
    profile_id = uuid4()
    with psycopg.connect(test_database.runtime_dsn) as connection:
        _set_tenant(connection, organization_id)
        connection.execute(
            """
            INSERT INTO people (
                id, organization_id, given_name, family_name, created_at, updated_at
            ) VALUES (%s, %s, 'Evidence', 'Fixture', now(), now())
            """,
            (person_id, organization_id),
        )
        connection.execute(
            """
            INSERT INTO person_profiles (
                id, organization_id, person_id, kind,
                encrypted_reference_number, title, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, NULL, NULL, now(), now())
            """,
            (profile_id, organization_id, person_id, kind),
        )
    return person_id, profile_id


def _insert_course_enrollment(
    test_database: EphemeralDatabase,
    *,
    organization_id: UUID,
    student_enrollment_id: UUID,
    offering_id: UUID,
    status: str = "enrolled",
) -> UUID:
    course_enrollment_id = uuid4()
    with psycopg.connect(test_database.runtime_dsn) as connection:
        _set_tenant(connection, organization_id)
        connection.execute(
            """
            INSERT INTO academic_course_enrollments (
                id, organization_id, student_academic_enrollment_id,
                course_offering_id, credits, status, enrolled_at,
                selection_request_id, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, 3, %s, now(), NULL, now(), now())
            """,
            (
                course_enrollment_id,
                organization_id,
                student_enrollment_id,
                offering_id,
                status,
            ),
        )
    return course_enrollment_id


@pytest.mark.integration
async def test_participant_lookup_resolves_only_one_active_participation(
    test_database: EphemeralDatabase,
) -> None:
    """Resolve person to profile to participation with real tenant rows."""

    organization_id = _insert_organization(test_database)
    other_organization_id = _insert_organization(test_database)
    person_id, student_profile_id = _insert_person_with_profile(
        test_database,
        organization_id=organization_id,
        kind="student",
    )
    teacher_person_id, _ = _insert_person_with_profile(
        test_database,
        organization_id=organization_id,
        kind="teacher",
    )
    suffix = uuid4().hex[:8]
    database = _runtime_database(test_database)
    academics = SQLAlchemyAcademicRepository(database)
    references = AcademicReferenceService(repository=academics)
    people = PeopleReferenceService(
        SQLAlchemyPeopleRepository(
            database=database,
            encryption_key=Fernet.generate_key().decode("ascii"),
        )
    )
    adapter = AcademicGradeTargetAdapter(references, people=people)
    faculty = Faculty(
        id=uuid4(),
        organization_id=organization_id,
        campus_id=uuid4(),
        code=f"EVI-FAC-{suffix}",
        name="Evidence Faculty",
    )
    department = Department(
        id=uuid4(),
        organization_id=organization_id,
        faculty_id=faculty.id,
        code=f"EVI-DEP-{suffix}",
        name="Evidence Department",
    )
    program = Program(
        id=uuid4(),
        organization_id=organization_id,
        department_id=department.id,
        code=f"EVI-PROG-{suffix}",
        name="Evidence Program",
        education_mode=EducationMode.FLEXIBLE_SELECTION,
        credit_unit_label="credits",
    )
    academic_year = AcademicYear(
        id=uuid4(),
        organization_id=organization_id,
        name=f"Evidence Year {suffix}",
        starts_on=date(2026, 8, 1),
        ends_on=date(2027, 7, 31),
    )
    second_year = AcademicYear(
        id=uuid4(),
        organization_id=organization_id,
        name=f"Evidence Year Two {suffix}",
        starts_on=date(2027, 8, 1),
        ends_on=date(2028, 7, 31),
    )
    term = Term(
        id=uuid4(),
        organization_id=organization_id,
        academic_year_id=academic_year.id,
        name=f"Evidence Term {suffix}",
        starts_on=date(2026, 8, 10),
        ends_on=date(2026, 12, 20),
        enrollment_deadline=datetime(2026, 8, 20, tzinfo=UTC),
    )
    course = Course(
        id=uuid4(),
        organization_id=organization_id,
        department_id=department.id,
        code=f"EVI-101-{suffix}",
        title="Evidence Integrity",
        credits=Decimal("3"),
    )
    offering = CourseOffering(
        id=uuid4(),
        organization_id=organization_id,
        course_id=course.id,
        term_id=term.id,
        campus_id=faculty.campus_id,
        section_code="A",
        capacity=30,
    )
    student_enrollment = StudentAcademicEnrollment(
        id=uuid4(),
        organization_id=organization_id,
        student_id=student_profile_id,
        program_id=program.id,
        academic_year_id=academic_year.id,
        cohort_id=None,
        status=AcademicEnrollmentStatus.ACTIVE,
        enrolled_at=datetime(2026, 8, 7, 10, tzinfo=UTC),
    )
    try:
        await academics.save_faculty(faculty)
        await academics.save_department(department)
        await academics.save_program(program)
        await academics.save_academic_year(academic_year)
        await academics.save_academic_year(second_year)
        await academics.save_term(term)
        await academics.save_course(course)
        await academics.save_course_offering(offering)
        await academics.save_student_enrollment(student_enrollment)
        course_enrollment_id = _insert_course_enrollment(
            test_database,
            organization_id=organization_id,
            student_enrollment_id=student_enrollment.id,
            offering_id=offering.id,
        )

        assert (
            await people.resolve_student_profile_id(
                organization_id=organization_id,
                person_id=person_id,
            )
            == student_profile_id
        )
        assert (
            await people.resolve_student_profile_id(
                organization_id=other_organization_id,
                person_id=person_id,
            )
            is None
        )
        assert (
            await people.resolve_student_profile_id(
                organization_id=organization_id,
                person_id=teacher_person_id,
            )
            is None
        )

        target = await adapter.get_grade_target_for_participant(
            organization_id=organization_id,
            course_offering_id=offering.id,
            student_person_id=person_id,
        )
        assert target is not None
        assert target.course_enrollment_id == course_enrollment_id
        assert target.student_academic_enrollment_id == student_enrollment.id
        assert target.term_id == term.id
        assert target.credits == Decimal("3")
        assert (
            await adapter.get_grade_target_for_participant(
                organization_id=other_organization_id,
                course_offering_id=offering.id,
                student_person_id=person_id,
            )
            is None
        )
        assert (
            await adapter.get_grade_target_for_participant(
                organization_id=organization_id,
                course_offering_id=offering.id,
                student_person_id=teacher_person_id,
            )
            is None
        )
        assert await references.list_course_offering_ids_for_term(
            organization_id=organization_id,
            term_id=term.id,
        ) == frozenset({offering.id})
        assert (
            await references.list_course_offering_ids_for_term(
                organization_id=other_organization_id,
                term_id=term.id,
            )
            is None
        )
        assert (
            await references.list_course_offering_ids_for_term(
                organization_id=organization_id,
                term_id=uuid4(),
            )
            is None
        )

        # A second active participation of the same student in the same offering
        # is ambiguous and must resolve to nothing rather than a guess.
        second_enrollment = StudentAcademicEnrollment(
            id=uuid4(),
            organization_id=organization_id,
            student_id=student_profile_id,
            program_id=program.id,
            academic_year_id=second_year.id,
            cohort_id=None,
            status=AcademicEnrollmentStatus.ACTIVE,
            enrolled_at=datetime(2027, 8, 7, 10, tzinfo=UTC),
        )
        await academics.save_student_enrollment(second_enrollment)
        _insert_course_enrollment(
            test_database,
            organization_id=organization_id,
            student_enrollment_id=second_enrollment.id,
            offering_id=offering.id,
        )
        assert (
            await references.get_grade_target_for_participant(
                organization_id=organization_id,
                course_offering_id=offering.id,
                student_profile_id=student_profile_id,
            )
            is None
        )

        with psycopg.connect(test_database.runtime_dsn) as connection:
            _set_tenant(connection, organization_id)
            connection.execute(
                """
                UPDATE academic_course_enrollments
                SET status = 'withdrawn', updated_at = now()
                WHERE organization_id = %s
                  AND student_academic_enrollment_id = %s
                """,
                (organization_id, second_enrollment.id),
            )
        resolved_again = await references.get_grade_target_for_participant(
            organization_id=organization_id,
            course_offering_id=offering.id,
            student_profile_id=student_profile_id,
        )
        assert resolved_again is not None
        assert resolved_again.course_enrollment_id == course_enrollment_id
    finally:
        await database.close()
