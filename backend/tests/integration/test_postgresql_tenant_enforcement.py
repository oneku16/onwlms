"""Real-role PostgreSQL verification for tenant and worker isolation."""

import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from uuid import UUID
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from psycopg import Connection
from psycopg import sql
from psycopg.errors import InsufficientPrivilege
from psycopg.errors import ObjectNotInPrerequisiteState
from sqlalchemy.engine import URL
from sqlalchemy.engine import make_url

from core.context import TenantActorContext
from core.errors import NotFoundError
from core.identifiers import new_uuid7
from core.settings import AppEnvironment
from core.settings import Settings
from people.application.reference_service import PeopleReferenceService
from people.infrastructure.repositories import SQLAlchemyPeopleRepository
from people_adapters import PeopleSchedulingTeacherAdapter
from scheduling.application.availability_service import TeacherAvailabilityService
from scheduling.application.service import SCHEDULING_SESSION_MANAGE
from scheduling.domain.models import TeacherAvailabilityWindow
from scheduling.infrastructure.sqlalchemy_repository import (
    SQLAlchemyTeacherAvailabilityRepository,
)
from shared.database import Database
from shared.model_registry import load_all_models
from shared.models import BaseModel

GLOBAL_TABLES = frozenset(
    {
        "entitlement_features",
        "entitlement_plan_features",
        "entitlement_plans",
        "identity_pending_oidc_flows",
        "identity_sessions",
        "identity_subjects",
        "organizations",
        "platform_administrators",
    }
)

IMMUTABLE_TABLES = frozenset(
    {
        "academic_course_selection_approvals",
        "academic_course_selection_override_violations",
        "academic_course_selection_overrides",
        "admissions_application_documents",
        "admissions_decisions",
        "admissions_review_records",
        "audit_records",
        "grading_grade_revisions",
        "grading_scale_bands",
        "grading_scales",
    }
)


@dataclass(frozen=True, slots=True)
class EphemeralDatabase:
    """Hold disposable database connection strings for each process role."""

    migration_dsn: str
    runtime_dsn: str
    worker_dsn: str


@dataclass(frozen=True, slots=True)
class IsolationRecords:
    """Identify two-tenant fixtures inserted through the runtime role."""

    organization_one: UUID
    organization_two: UUID
    subject_one: UUID
    subject_two: UUID
    membership_one: UUID
    membership_two: UUID
    person_one: UUID
    person_two: UUID
    audit_record: UUID


def _sync_dsn(url: URL, *, database: str) -> str:
    """Render a SQLAlchemy URL for direct psycopg connections."""

    return url.set(
        drivername="postgresql",
        database=database,
    ).render_as_string(hide_password=False)


def _require_local_admin_url() -> URL:
    """Accept explicit test execution only against a local PostgreSQL server."""

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
    """Migrate a uniquely named database and always drop it after verification."""

    migration_url = _require_local_admin_url()
    database_name = f"ownsis_rls_test_{uuid4().hex}"
    admin_dsn = _sync_dsn(migration_url, database="postgres")
    runtime_url = make_url(
        os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://ownsis:ownsis@localhost:5432/ownsis",
        )
    )
    worker_url = make_url(
        os.environ.get(
            "WORKER_DATABASE_URL",
            "postgresql+asyncpg://ownsis_worker:ownsis_worker@localhost:5432/ownsis",
        )
    )
    database = EphemeralDatabase(
        migration_dsn=_sync_dsn(migration_url, database=database_name),
        runtime_dsn=_sync_dsn(runtime_url, database=database_name),
        worker_dsn=_sync_dsn(worker_url, database=database_name),
    )

    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        roles = {
            row[0]: (row[1], row[2])
            for row in admin.execute(
                "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles "
                "WHERE rolname IN ('ownsis', 'ownsis_worker')"
            ).fetchall()
        }
        assert roles == {
            "ownsis": (False, False),
            "ownsis_worker": (False, False),
        }
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


def _set_tenant(
    connection: Connection[tuple[object, ...]],
    organization_id: UUID,
) -> None:
    """Establish the same transaction-local tenant context as the application."""

    connection.execute(
        "SELECT set_config('app.organization_id', %s, true)",
        (str(organization_id),),
    )


def _set_subject(
    connection: Connection[tuple[object, ...]],
    subject_id: UUID,
) -> None:
    """Establish the discovery-only identity context used before tenant choice."""

    connection.execute(
        "SELECT set_config('app.identity_subject_id', %s, true)",
        (str(subject_id),),
    )


@pytest.fixture(scope="module")
def isolation_records(test_database: EphemeralDatabase) -> IsolationRecords:
    """Insert two complete policy fixtures through allowed runtime operations."""

    records = IsolationRecords(
        organization_one=uuid4(),
        organization_two=uuid4(),
        subject_one=uuid4(),
        subject_two=uuid4(),
        membership_one=uuid4(),
        membership_two=uuid4(),
        person_one=uuid4(),
        person_two=uuid4(),
        audit_record=uuid4(),
    )
    with psycopg.connect(test_database.runtime_dsn) as connection:
        connection.cursor().executemany(
            """
            INSERT INTO organizations (
                id, slug, organization_type, status, display_name,
                primary_color, secondary_color, locale, timezone,
                education_mode, created_at, updated_at
            ) VALUES (
                %s, %s, 'school', 'active', %s,
                '#112233', '#445566', 'en', 'UTC', 'school', now(), now()
            )
            """,
            (
                (
                    records.organization_one,
                    f"rls-one-{records.organization_one.hex}",
                    "RLS One",
                ),
                (
                    records.organization_two,
                    f"rls-two-{records.organization_two.hex}",
                    "RLS Two",
                ),
            ),
        )
        connection.cursor().executemany(
            """
            INSERT INTO identity_subjects (
                id, issuer, subject, email, display_name, created_at, updated_at
            ) VALUES (%s, 'https://id.example.test', %s, NULL, NULL, now(), now())
            """,
            (
                (records.subject_one, f"subject-{records.subject_one}"),
                (records.subject_two, f"subject-{records.subject_two}"),
            ),
        )

    fixture_rows = (
        (
            records.organization_one,
            records.subject_one,
            records.membership_one,
            records.person_one,
            "owner",
            "one",
        ),
        (
            records.organization_two,
            records.subject_two,
            records.membership_two,
            records.person_two,
            "organization_admin",
            "two",
        ),
    )
    for (
        organization_id,
        subject_id,
        membership_id,
        person_id,
        role,
        suffix,
    ) in fixture_rows:
        with psycopg.connect(test_database.runtime_dsn) as connection:
            _set_tenant(connection, organization_id)
            connection.execute(
                """
                INSERT INTO people (
                    id, organization_id, given_name, family_name,
                    created_at, updated_at
                ) VALUES (%s, %s, %s, 'Tenant', now(), now())
                """,
                (person_id, organization_id, f"Person {suffix}"),
            )
            connection.execute(
                """
                INSERT INTO organization_memberships (
                    id, organization_id, identity_subject_id, person_id,
                    status, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, 'active', now(), now())
                """,
                (membership_id, organization_id, subject_id, person_id),
            )
            connection.execute(
                """
                INSERT INTO organization_membership_roles (
                    membership_id, organization_id, role
                ) VALUES (%s, %s, %s)
                """,
                (membership_id, organization_id, role),
            )
            connection.execute(
                """
                INSERT INTO outbox_events (
                    id, event_type, contract_version, organization_id,
                    actor_subject_id, correlation_id, idempotency_key, payload,
                    status, attempts, available_at, created_at
                ) VALUES (
                    %s, 'test.event.v1', 1, %s, %s, %s, %s, '{}'::jsonb,
                    'pending', 0, now(), now()
                )
                """,
                (
                    uuid4(),
                    organization_id,
                    subject_id,
                    f"correlation-{suffix}",
                    f"rls-test-{organization_id}",
                ),
            )
            connection.execute(
                """
                INSERT INTO provisioning_jobs (
                    id, organization_id, subject_type, subject_id, target,
                    status, idempotency_key, attempts, created_at, updated_at
                ) VALUES (
                    %s, %s, 'person', %s, 'moodle', 'pending', %s, 0,
                    now(), now()
                )
                """,
                (
                    uuid4(),
                    organization_id,
                    person_id,
                    f"provisioning-{organization_id}",
                ),
            )

    with psycopg.connect(test_database.runtime_dsn) as connection:
        _set_tenant(connection, records.organization_one)
        connection.execute(
            """
            INSERT INTO audit_records (
                id, organization_id, actor_subject_id, action, entity_type,
                entity_id, occurred_at, source, outcome, correlation_id
            ) VALUES (
                %s, %s, %s, 'test.created', 'person', %s,
                now(), 'application', 'success', 'audit-immutability-test'
            )
            """,
            (
                records.audit_record,
                records.organization_one,
                records.subject_one,
                str(records.person_one),
            ),
        )
    return records


@pytest.mark.integration
def test_migration_classifies_every_table_and_forces_tenant_rls(
    test_database: EphemeralDatabase,
) -> None:
    """Keep global classification explicit and force RLS on every tenant table."""

    load_all_models()
    model_tables = frozenset(BaseModel.metadata.tables)
    tenant_tables = frozenset(
        table.name
        for table in BaseModel.metadata.tables.values()
        if "organization_id" in table.c
    )
    assert model_tables - tenant_tables == GLOBAL_TABLES
    constraint_identifiers = {
        str(constraint.name)
        for table in BaseModel.metadata.tables.values()
        for constraint in table.constraints
        if constraint.name is not None
    }
    index_identifiers = {
        str(index.name)
        for table in BaseModel.metadata.tables.values()
        for index in table.indexes
        if index.name is not None
    }
    declared_identifiers = constraint_identifiers | index_identifiers
    assert all(len(name.encode("utf-8")) <= 63 for name in declared_identifiers)

    with psycopg.connect(test_database.migration_dsn) as connection:
        rows = connection.execute(
            """
            SELECT relname, relrowsecurity, relforcerowsecurity
            FROM pg_class
            WHERE relnamespace = 'public'::regnamespace
              AND relkind = 'r'
              AND relname <> 'alembic_version'
            """
        ).fetchall()
        database_rls = {
            str(name): (bool(enabled), bool(forced)) for name, enabled, forced in rows
        }
        assert frozenset(database_rls) == model_tables
        assert all(database_rls[table] == (True, True) for table in tenant_tables)
        assert all(database_rls[table] == (False, False) for table in GLOBAL_TABLES)
        assert connection.execute(
            """
            SELECT count(*)
            FROM pg_trigger
            WHERE tgname = 'reject_immutable_mutation'
              AND NOT tgisinternal
            """
        ).fetchone() == (len(IMMUTABLE_TABLES),)


@pytest.mark.integration
def test_runtime_role_blocks_cross_tenant_reads_and_writes(
    test_database: EphemeralDatabase,
    isolation_records: IsolationRecords,
) -> None:
    """Prove tenant-local visibility, missing-context denial, and write checks."""

    with psycopg.connect(test_database.runtime_dsn) as connection:
        _set_tenant(connection, isolation_records.organization_one)
        visible_people = connection.execute(
            "SELECT id, organization_id FROM people ORDER BY id"
        ).fetchall()
        assert visible_people == [
            (
                isolation_records.person_one,
                isolation_records.organization_one,
            )
        ]

    with psycopg.connect(test_database.runtime_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM people").fetchone() == (0,)

    with (
        pytest.raises(InsufficientPrivilege),
        psycopg.connect(test_database.runtime_dsn) as connection,
    ):
        _set_tenant(connection, isolation_records.organization_one)
        connection.execute(
            """
            INSERT INTO people (
                id, organization_id, given_name, family_name,
                created_at, updated_at
            ) VALUES (%s, %s, 'Cross', 'Tenant', now(), now())
            """,
            (uuid4(), isolation_records.organization_two),
        )


@pytest.mark.integration
def test_teacher_availability_rls_and_least_privilege_grants(
    test_database: EphemeralDatabase,
    isolation_records: IsolationRecords,
) -> None:
    """Force tenant visibility and deny update or worker access to windows."""

    starts_at = datetime(2026, 8, 10, 8, tzinfo=UTC)
    first_id = uuid4()
    second_id = uuid4()
    for organization_id, window_id in (
        (isolation_records.organization_one, first_id),
        (isolation_records.organization_two, second_id),
    ):
        with psycopg.connect(test_database.runtime_dsn) as connection:
            _set_tenant(connection, organization_id)
            connection.execute(
                """
                INSERT INTO scheduling_teacher_availability_windows (
                    id, organization_id, teacher_id, starts_at, ends_at,
                    created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, now(), now())
                """,
                (
                    window_id,
                    organization_id,
                    uuid4(),
                    starts_at,
                    starts_at + timedelta(hours=2),
                ),
            )

    with psycopg.connect(test_database.runtime_dsn) as connection:
        _set_tenant(connection, isolation_records.organization_one)
        assert connection.execute(
            "SELECT id FROM scheduling_teacher_availability_windows"
        ).fetchall() == [(first_id,)]

    with psycopg.connect(test_database.runtime_dsn) as connection:
        assert connection.execute(
            "SELECT count(*) FROM scheduling_teacher_availability_windows"
        ).fetchone() == (0,)

    with (
        pytest.raises(InsufficientPrivilege),
        psycopg.connect(test_database.runtime_dsn) as connection,
    ):
        _set_tenant(connection, isolation_records.organization_one)
        connection.execute(
            """
            INSERT INTO scheduling_teacher_availability_windows (
                id, organization_id, teacher_id, starts_at, ends_at,
                created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, now(), now())
            """,
            (
                uuid4(),
                isolation_records.organization_two,
                uuid4(),
                starts_at,
                starts_at + timedelta(hours=1),
            ),
        )

    with (
        pytest.raises(InsufficientPrivilege),
        psycopg.connect(test_database.runtime_dsn) as connection,
    ):
        _set_tenant(connection, isolation_records.organization_one)
        connection.execute(
            "UPDATE scheduling_teacher_availability_windows "
            "SET ends_at = ends_at + interval '1 hour'"
        )

    with (
        pytest.raises(InsufficientPrivilege),
        psycopg.connect(test_database.worker_dsn) as connection,
    ):
        _set_tenant(connection, isolation_records.organization_one)
        connection.execute(
            "SELECT count(*) FROM scheduling_teacher_availability_windows"
        )


@pytest.mark.integration
async def test_people_teacher_reference_prevents_invalid_availability_constraints(
    test_database: EphemeralDatabase,
    isolation_records: IsolationRecords,
) -> None:
    """Reject non-teacher and cross-tenant profile IDs through public services."""

    teacher_one = uuid4()
    staff_one = uuid4()
    teacher_two = uuid4()
    orphaned_id = uuid4()
    starts_at = datetime(2026, 8, 12, 8, tzinfo=UTC)
    profile_rows = (
        (
            isolation_records.organization_one,
            isolation_records.person_one,
            teacher_one,
            "teacher",
        ),
        (
            isolation_records.organization_one,
            isolation_records.person_one,
            staff_one,
            "staff",
        ),
        (
            isolation_records.organization_two,
            isolation_records.person_two,
            teacher_two,
            "teacher",
        ),
    )
    for organization_id, person_id, profile_id, kind in profile_rows:
        with psycopg.connect(test_database.runtime_dsn) as connection:
            _set_tenant(connection, organization_id)
            connection.execute(
                """
                INSERT INTO person_profiles (
                    id, organization_id, person_id, kind, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, now(), now())
                """,
                (profile_id, organization_id, person_id, kind),
            )
    with psycopg.connect(test_database.runtime_dsn) as connection:
        _set_tenant(connection, isolation_records.organization_one)
        connection.execute(
            """
            INSERT INTO scheduling_teacher_availability_windows (
                id, organization_id, teacher_id, starts_at, ends_at,
                created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, now(), now())
            """,
            (
                uuid4(),
                isolation_records.organization_one,
                orphaned_id,
                starts_at,
                starts_at + timedelta(hours=3),
            ),
        )

    database = Database(
        Settings(APP_ENV=AppEnvironment.TEST),
        database_url=test_database.runtime_dsn.replace(
            "postgresql://",
            "postgresql+asyncpg://",
            1,
        ),
    )
    try:
        people_repository = SQLAlchemyPeopleRepository(
            database=database,
            encryption_key=Fernet.generate_key().decode("ascii"),
        )
        teachers = PeopleSchedulingTeacherAdapter(
            PeopleReferenceService(people_repository)
        )
        service = TeacherAvailabilityService(
            SQLAlchemyTeacherAvailabilityRepository(database),
            teachers,
        )
        context = TenantActorContext(
            subject_id=isolation_records.subject_one,
            organization_id=isolation_records.organization_one,
            membership_id=isolation_records.membership_one,
            correlation_id="availability-integration-test",
            permissions=frozenset({SCHEDULING_SESSION_MANAGE}),
        )
        await service.create_window(
            context=context,
            window=TeacherAvailabilityWindow(
                id=new_uuid7(),
                organization_id=isolation_records.organization_one,
                teacher_id=teacher_one,
                starts_at=starts_at,
                ends_at=starts_at + timedelta(hours=3),
            ),
        )
        for invalid_teacher_id in (staff_one, teacher_two, orphaned_id):
            with pytest.raises(NotFoundError):
                await service.create_window(
                    context=context,
                    window=TeacherAvailabilityWindow(
                        id=new_uuid7(),
                        organization_id=isolation_records.organization_one,
                        teacher_id=invalid_teacher_id,
                        starts_at=starts_at,
                        ends_at=starts_at + timedelta(hours=1),
                    ),
                )
        availability = await service.availability_for_constraints(
            organization_id=isolation_records.organization_one,
            teacher_ids=frozenset({teacher_one, staff_one, teacher_two, orphaned_id}),
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=4),
        )
        by_teacher = {entry.teacher_id: entry for entry in availability}
        assert len(by_teacher[teacher_one].windows) == 1
        assert all(
            not by_teacher[teacher_id].windows
            for teacher_id in (staff_one, teacher_two, orphaned_id)
        )
    finally:
        await database.close()


@pytest.mark.integration
def test_identity_subject_can_discover_only_its_memberships_and_roles(
    test_database: EphemeralDatabase,
    isolation_records: IsolationRecords,
) -> None:
    """Allow pre-tenant discovery reads while keeping every write tenant-only."""

    with psycopg.connect(test_database.runtime_dsn) as connection:
        _set_subject(connection, isolation_records.subject_one)
        memberships = connection.execute(
            "SELECT id, organization_id FROM organization_memberships"
        ).fetchall()
        roles = connection.execute(
            """
            SELECT membership_id, organization_id, role
            FROM organization_membership_roles
            """
        ).fetchall()
        assert memberships == [
            (
                isolation_records.membership_one,
                isolation_records.organization_one,
            )
        ]
        assert roles == [
            (
                isolation_records.membership_one,
                isolation_records.organization_one,
                "owner",
            )
        ]
        updated = connection.execute(
            "UPDATE organization_memberships SET status = 'suspended'"
        )
        assert updated.rowcount == 0

    with (
        pytest.raises(InsufficientPrivilege),
        psycopg.connect(test_database.runtime_dsn) as connection,
    ):
        _set_subject(connection, isolation_records.subject_one)
        connection.execute(
            """
            INSERT INTO organization_memberships (
                id, organization_id, identity_subject_id, status,
                created_at, updated_at
            ) VALUES (%s, %s, %s, 'active', now(), now())
            """,
            (
                uuid4(),
                isolation_records.organization_two,
                isolation_records.subject_one,
            ),
        )


@pytest.mark.integration
def test_worker_has_cross_tenant_outbox_claim_and_tenant_jobs_only(
    test_database: EphemeralDatabase,
    isolation_records: IsolationRecords,
) -> None:
    """Constrain the worker to delivery columns and tenant-scoped job changes."""

    with psycopg.connect(test_database.worker_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM outbox_events").fetchone() == (
            2,
        )
        updated = connection.execute(
            """
            UPDATE outbox_events
            SET status = 'processing', attempts = attempts + 1,
                locked_by = 'rls-test-worker', locked_at = now()
            """
        )
        assert updated.rowcount == 2

    with (
        pytest.raises(InsufficientPrivilege),
        psycopg.connect(test_database.worker_dsn) as connection,
    ):
        connection.execute(
            "UPDATE outbox_events SET organization_id = %s",
            (isolation_records.organization_one,),
        )

    with (
        pytest.raises(InsufficientPrivilege),
        psycopg.connect(test_database.worker_dsn) as connection,
    ):
        connection.execute(
            """
            INSERT INTO outbox_events (
                id, event_type, contract_version, organization_id,
                correlation_id, idempotency_key, payload, status, attempts,
                available_at, created_at
            ) VALUES (
                %s, 'worker.must.not.publish.v1', 1, %s, 'worker-insert',
                %s, '{}'::jsonb, 'pending', 0, now(), now()
            )
            """,
            (
                uuid4(),
                isolation_records.organization_one,
                f"worker-insert-{uuid4()}",
            ),
        )

    with (
        pytest.raises(InsufficientPrivilege),
        psycopg.connect(test_database.worker_dsn) as connection,
    ):
        connection.execute("SELECT count(*) FROM people")

    with psycopg.connect(test_database.worker_dsn) as connection:
        assert connection.execute(
            "SELECT count(*) FROM provisioning_jobs"
        ).fetchone() == (0,)

    with psycopg.connect(test_database.worker_dsn) as connection:
        _set_tenant(connection, isolation_records.organization_one)
        assert connection.execute(
            "SELECT count(*) FROM provisioning_jobs"
        ).fetchone() == (1,)
        updated = connection.execute(
            "UPDATE provisioning_jobs SET status = 'succeeded', updated_at = now()"
        )
        assert updated.rowcount == 1

    with (
        pytest.raises(InsufficientPrivilege),
        psycopg.connect(test_database.worker_dsn) as connection,
    ):
        _set_tenant(connection, isolation_records.organization_one)
        connection.execute(
            """
            INSERT INTO provisioning_jobs (
                id, organization_id, subject_type, subject_id, target,
                status, idempotency_key, attempts, created_at, updated_at
            ) VALUES (
                %s, %s, 'person', %s, 'moodle', 'pending', %s, 0,
                now(), now()
            )
            """,
            (
                uuid4(),
                isolation_records.organization_two,
                isolation_records.person_two,
                f"cross-tenant-{uuid4()}",
            ),
        )


@pytest.mark.integration
def test_worker_can_append_only_tenant_bound_audit_evidence(
    test_database: EphemeralDatabase,
    isolation_records: IsolationRecords,
) -> None:
    """Allow worker attempt evidence without granting audit reads or broad writes."""

    insert_statement = """
        INSERT INTO audit_records (
            id, organization_id, actor_subject_id, action, entity_type,
            entity_id, occurred_at, source, outcome, correlation_id
        ) VALUES (
            %s, %s, NULL, 'provisioning.attempted', 'provisioning_job',
            %s, now(), 'worker', 'succeeded', %s
        )
    """
    with (
        pytest.raises(InsufficientPrivilege),
        psycopg.connect(test_database.worker_dsn) as connection,
    ):
        connection.execute(
            insert_statement,
            (
                uuid4(),
                isolation_records.organization_one,
                str(uuid4()),
                f"worker-audit-missing-context-{uuid4()}",
            ),
        )

    with psycopg.connect(test_database.worker_dsn) as connection:
        _set_tenant(connection, isolation_records.organization_one)
        connection.execute(
            insert_statement,
            (
                uuid4(),
                isolation_records.organization_one,
                str(uuid4()),
                f"worker-audit-success-{uuid4()}",
            ),
        )

    with (
        pytest.raises(InsufficientPrivilege),
        psycopg.connect(test_database.worker_dsn) as connection,
    ):
        _set_tenant(connection, isolation_records.organization_one)
        connection.execute(
            insert_statement,
            (
                uuid4(),
                isolation_records.organization_two,
                str(uuid4()),
                f"worker-audit-cross-tenant-{uuid4()}",
            ),
        )

    with (
        pytest.raises(InsufficientPrivilege),
        psycopg.connect(test_database.worker_dsn) as connection,
    ):
        _set_tenant(connection, isolation_records.organization_one)
        connection.execute("SELECT count(*) FROM audit_records")


@pytest.mark.integration
def test_audit_records_are_tenant_scoped_and_unconditionally_immutable(
    test_database: EphemeralDatabase,
    isolation_records: IsolationRecords,
) -> None:
    """Protect append-only evidence with grants, RLS, and an owner-level trigger."""

    with psycopg.connect(test_database.runtime_dsn) as connection:
        _set_tenant(connection, isolation_records.organization_one)
        assert connection.execute("SELECT id FROM audit_records").fetchone() == (
            isolation_records.audit_record,
        )

    with (
        pytest.raises(InsufficientPrivilege),
        psycopg.connect(test_database.runtime_dsn) as connection,
    ):
        _set_tenant(connection, isolation_records.organization_one)
        connection.execute(
            "UPDATE audit_records SET outcome = 'failure' WHERE id = %s",
            (isolation_records.audit_record,),
        )

    for statement in (
        "UPDATE audit_records SET outcome = 'failure' WHERE id = %s",
        "DELETE FROM audit_records WHERE id = %s",
    ):
        with (
            pytest.raises(ObjectNotInPrerequisiteState),
            psycopg.connect(test_database.migration_dsn) as connection,
        ):
            connection.execute(statement, (isolation_records.audit_record,))


@pytest.mark.integration
def test_availability_downgrade_refuses_destructive_schema_erasure(
    test_database: EphemeralDatabase,
) -> None:
    """Require backup restoration instead of pretending the baseline is reversible."""

    repository_root = Path(__file__).resolve().parents[3]
    config = Config(str(repository_root / "backend" / "alembic.ini"))
    previous_migration_url = os.environ.get("DATABASE_MIGRATION_URL")
    os.environ["DATABASE_MIGRATION_URL"] = test_database.migration_dsn.replace(
        "postgresql://",
        "postgresql+psycopg://",
        1,
    )
    try:
        with pytest.raises(
            RuntimeError,
            match="forward repair or restore a verified backup",
        ):
            command.downgrade(config, "d4c2a9e7b6f1")
        command.upgrade(config, "head")
        command.current(config, check_heads=True)
    finally:
        if previous_migration_url is None:
            os.environ.pop("DATABASE_MIGRATION_URL", None)
        else:
            os.environ["DATABASE_MIGRATION_URL"] = previous_migration_url
