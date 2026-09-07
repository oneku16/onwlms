"""Real-role PostgreSQL verification for tenant and worker isolation."""

import asyncio
import os
from collections.abc import AsyncIterator
from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from dataclasses import replace
from datetime import UTC
from datetime import date
from datetime import datetime
from datetime import time
from datetime import timedelta
from decimal import Decimal
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
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from academics.application.ports import CourseSelectionDecisionTransaction
from academics.application.reference_service import AcademicReferenceService
from academics.application.service import ACADEMICS_ENROLLMENT_MANAGE
from academics.application.service import ACADEMICS_SELECTION_APPROVE
from academics.application.service import ACADEMICS_STRUCTURE_MANAGE
from academics.application.service import AcademicAdministrationService
from academics.application.service import CourseSelectionService
from academics.domain.exceptions import CourseSelectionDecisionError
from academics.domain.exceptions import CourseSelectionError
from academics.domain.models import AcademicEnrollmentStatus
from academics.domain.models import AcademicYear
from academics.domain.models import Course
from academics.domain.models import CourseEnrollment
from academics.domain.models import CourseEnrollmentStatus
from academics.domain.models import CourseOffering
from academics.domain.models import CourseSelectionPolicy
from academics.domain.models import CourseSelectionRequest
from academics.domain.models import CourseSelectionStatus
from academics.domain.models import CurriculumCourse
from academics.domain.models import CurriculumCourseKind
from academics.domain.models import Department
from academics.domain.models import EducationMode
from academics.domain.models import Faculty
from academics.domain.models import MeetingWindow
from academics.domain.models import Program
from academics.domain.models import ProgramCurriculum
from academics.domain.models import StudentAcademicEnrollment
from academics.domain.models import TeacherAssignment
from academics.domain.models import Term
from academics.infrastructure.sqlalchemy_repository import SQLAlchemyAcademicRepository
from audit.application.service import AuditService
from audit.infrastructure.repository import SQLAlchemyAuditRepository
from audit.infrastructure.sinks import ApplicationAuditSink
from core.context import PlatformActorContext
from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import NotFoundError
from core.identifiers import new_uuid7
from core.settings import AppEnvironment
from core.settings import Settings
from identity.domain.exceptions import FinalPlatformAdministratorError
from identity.domain.exceptions import PlatformAdministratorBootstrapClosedError
from identity.domain.models import PendingAuthorization
from identity.domain.models import PlatformAdministrator
from identity.domain.models import ProviderTokens
from identity.domain.models import StoredSession
from identity.infrastructure.repositories import (
    SQLAlchemyPlatformAdministratorRepository,
)
from identity.infrastructure.repositories import SQLAlchemySessionRepository
from people.application.reference_service import PeopleReferenceService
from people.application.service import APPOINT_OWNER_PERMISSION
from people.application.service import MANAGE_MEMBERSHIPS_PERMISSION
from people.application.service import MANAGE_OWNER_LIFECYCLE_PERMISSION
from people.application.service import MembershipService
from people.domain.exceptions import InvalidMembershipError
from people.domain.models import Membership
from people.domain.models import MembershipRole
from people.domain.models import MembershipStatus
from people.infrastructure.repositories import SQLAlchemyMembershipRepository
from people.infrastructure.repositories import SQLAlchemyPeopleRepository
from people_adapters import PeopleAcademicProfileAdapter
from people_adapters import PeopleSchedulingTeacherAdapter
from scheduling.application.availability_service import TeacherAvailabilityService
from scheduling.application.service import SCHEDULING_SESSION_MANAGE
from scheduling.domain.exceptions import ScheduleVersionConflictError
from scheduling.domain.exceptions import SchedulingConflictError
from scheduling.domain.models import ConstraintContext
from scheduling.domain.models import RoomSpecification
from scheduling.domain.models import ScheduledSession
from scheduling.domain.models import TeacherAvailability
from scheduling.domain.models import TeacherAvailabilityWindow
from scheduling.domain.models import TimeWindow
from scheduling.infrastructure.repository import InMemorySchedulingAuditSink
from scheduling.infrastructure.sqlalchemy_repository import (
    SQLAlchemySchedulingRepository,
)
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


@dataclass(frozen=True, slots=True)
class _FixedAcademicClock:
    """Provide deterministic application time to course-selection tests."""

    current: datetime

    def now(self) -> datetime:
        return self.current


class _RecordingCourseSelectionAudit:
    """Capture selection event ordering without opening another database session."""

    def __init__(self) -> None:
        self.events: list[str] = []

    async def record_course_selection_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        request_id: UUID,
        correlation_id: str,
        outcome: str,
    ) -> None:
        del organization_id, actor_subject_id, request_id, correlation_id, outcome
        self.events.append(action)


class _HoldingPeopleAudit:
    """Pause one audited intent so another membership mutation can commit first."""

    def __init__(self, *, hold_action: str) -> None:
        self._hold_action = hold_action
        self.intent_reached = asyncio.Event()
        self.release_intent = asyncio.Event()
        self.events: list[tuple[str, str]] = []

    async def record_people_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        target_id: UUID,
        correlation_id: str,
        outcome: str,
    ) -> None:
        assert organization_id and actor_subject_id and target_id and correlation_id
        self.events.append((action, outcome))
        if action == self._hold_action and outcome == "intent_recorded":
            self.intent_reached.set()
            await self.release_intent.wait()


class _OwnerRemovalBarrierAudit:
    """Release two owner removals together after both audit intents exist."""

    def __init__(self, *, intent_action: str) -> None:
        self._intent_action = intent_action
        self._intent_count = 0
        self._both_intents = asyncio.Event()

    async def record_people_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        target_id: UUID,
        correlation_id: str,
        outcome: str,
    ) -> None:
        assert organization_id and actor_subject_id and target_id and correlation_id
        if action == self._intent_action and outcome == "intent_recorded":
            self._intent_count += 1
            if self._intent_count == 2:
                self._both_intents.set()
            await self._both_intents.wait()


@dataclass(frozen=True, slots=True)
class _ExactOrganizationAvailability:
    """Expose one active organization to focused membership concurrency tests."""

    organization_id: UUID

    async def is_active(self, *, organization_id: UUID) -> bool:
        return organization_id == self.organization_id


class _UnusedCampusDirectory:
    """Fail if focused profile validation unexpectedly resolves a campus."""

    async def campus_exists(
        self,
        *,
        organization_id: UUID,
        campus_id: UUID,
    ) -> bool:
        del organization_id, campus_id
        raise AssertionError("Profile validation must not resolve a campus.")


class _UnusedTermClosureAudit:
    """Fail if focused profile validation emits a term-closure audit event."""

    async def record_term_closure_intent(
        self,
        *,
        organization_id: UUID,
        actor_subject_id: UUID,
        term_id: UUID,
        correlation_id: str,
        reason: str,
    ) -> None:
        del organization_id, actor_subject_id, term_id, correlation_id, reason
        raise AssertionError("Profile validation must not close a term.")


def _insert_global_test_subject(
    *,
    test_database: EphemeralDatabase,
    subject_id: UUID,
) -> None:
    """Insert one unique global identity for a tenant-membership race fixture."""

    with psycopg.connect(test_database.runtime_dsn) as connection:
        connection.execute(
            """
            INSERT INTO identity_subjects (
                id, issuer, subject, email, display_name, created_at, updated_at
            ) VALUES (
                %s, 'https://id.example.test', %s, NULL, NULL, now(), now()
            )
            """,
            (subject_id, f"membership-race-{subject_id}"),
        )


class _UnusedCourseSelectionOwnership:
    """Fail loudly if an approval unexpectedly enters student ownership logic."""

    async def resolve_actor_student_profile_id(
        self,
        *,
        actor: TenantActorContext,
    ) -> UUID:
        del actor
        raise AssertionError(
            "Approval must not resolve student self-service ownership."
        )

    async def actor_owns_student_profile(
        self,
        *,
        actor: TenantActorContext,
        student_profile_id: UUID,
    ) -> bool:
        del actor, student_profile_id
        raise AssertionError("Approval must not check student self-service ownership.")


class _HoldingCourseSelectionRepository(SQLAlchemyAcademicRepository):
    """Pause the first decision after it owns the exact student row lock."""

    def __init__(self, database: Database) -> None:
        super().__init__(database)
        self.first_decision_locked = asyncio.Event()
        self.release_first_decision = asyncio.Event()
        self._held_first_decision = False

    @asynccontextmanager
    async def decision_transaction(
        self,
        *,
        organization_id: UUID,
        request_id: UUID,
    ) -> AsyncIterator[CourseSelectionDecisionTransaction]:
        async with super().decision_transaction(
            organization_id=organization_id,
            request_id=request_id,
        ) as transaction:
            if not self._held_first_decision:
                self._held_first_decision = True
                self.first_decision_locked.set()
                await self.release_first_decision.wait()
            yield transaction


class _HoldingSchedulingRepository(SQLAlchemySchedulingRepository):
    """Pause a normal write after its transaction owns booking locks."""

    def __init__(self, database: Database) -> None:
        super().__init__(database)
        self.write_locked = asyncio.Event()
        self.release_write = asyncio.Event()

    async def _save_session(
        self,
        *,
        database_session: AsyncSession,
        value: ScheduledSession,
        expected_version: int | None,
    ) -> None:
        self.write_locked.set()
        await self.release_write.wait()
        await super()._save_session(
            database_session=database_session,
            value=value,
            expected_version=expected_version,
        )


class _HoldingReplacementRepository(SQLAlchemySchedulingRepository):
    """Pause generated replacement while its exclusive tenant lock is held."""

    def __init__(self, database: Database) -> None:
        super().__init__(database)
        self.replacement_locked = asyncio.Event()
        self.release_replacement = asyncio.Event()

    async def _acquire_tenant_write_lock(
        self,
        *,
        database_session: AsyncSession,
        organization_id: UUID,
        shared: bool,
    ) -> None:
        await super()._acquire_tenant_write_lock(
            database_session=database_session,
            organization_id=organization_id,
            shared=shared,
        )
        if not shared:
            self.replacement_locked.set()
            await self.release_replacement.wait()


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
async def test_runtime_role_atomically_consumes_pending_oidc_flow(
    test_database: EphemeralDatabase,
) -> None:
    """Consume pending state once without requiring runtime UPDATE privilege."""

    database = Database(
        Settings(APP_ENV=AppEnvironment.TEST),
        database_url=test_database.runtime_dsn.replace(
            "postgresql://",
            "postgresql+asyncpg://",
            1,
        ),
    )
    repository = SQLAlchemySessionRepository(
        database=database,
        encryption_key=Fernet.generate_key().decode("ascii"),
    )
    pending = PendingAuthorization(
        key_digest="a" * 64,
        state_digest="b" * 64,
        nonce="pending-nonce",
        code_verifier="pending-code-verifier",
        return_path="/dashboard",
        expires_at=datetime(2026, 8, 5, 12, tzinfo=UTC),
    )

    try:
        await repository.save_pending(pending)
        results = await asyncio.gather(
            repository.consume_pending(key_digest=pending.key_digest),
            repository.consume_pending(key_digest=pending.key_digest),
        )
    finally:
        await database.close()

    assert results.count(pending) == 1
    assert results.count(None) == 1


@pytest.mark.integration
async def test_postgresql_session_refresh_lock_serializes_token_versions(
    test_database: EphemeralDatabase,
    isolation_records: IsolationRecords,
) -> None:
    """Expose the newer token version only after the first refresh commits."""

    database = _async_runtime_database(test_database)
    repository = SQLAlchemySessionRepository(
        database=database,
        encryption_key=Fernet.generate_key().decode("ascii"),
    )
    stored = StoredSession(
        key_digest=uuid4().hex + uuid4().hex,
        subject_id=isolation_records.subject_one,
        csrf_digest=uuid4().hex + uuid4().hex,
        tokens=ProviderTokens(
            access_token="access-before",
            id_token="id-before",
            refresh_token="refresh-before",
            expires_at=datetime(2026, 8, 7, 11, tzinfo=UTC),
        ),
        expires_at=datetime(2026, 8, 7, 12, tzinfo=UTC),
    )
    first_locked = asyncio.Event()
    release_first = asyncio.Event()
    queued_started = asyncio.Event()

    async def first_refresh() -> None:
        async with repository.lock_for_refresh(
            key_digest=stored.key_digest,
        ) as claim:
            assert claim is not None
            assert claim.stored.version == 1
            first_locked.set()
            await release_first.wait()
            await claim.replace_tokens(
                ProviderTokens(
                    access_token="access-after",
                    id_token="id-after",
                    refresh_token="refresh-after",
                    expires_at=datetime(2026, 8, 7, 11, 30, tzinfo=UTC),
                )
            )

    async def queued_refresh_version() -> int:
        queued_started.set()
        async with repository.lock_for_refresh(
            key_digest=stored.key_digest,
        ) as claim:
            assert claim is not None
            return claim.stored.version

    try:
        await repository.save_session(stored)
        first = asyncio.create_task(first_refresh())
        await asyncio.wait_for(first_locked.wait(), timeout=5)
        queued = asyncio.create_task(queued_refresh_version())
        await asyncio.wait_for(queued_started.wait(), timeout=5)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(queued), timeout=0.2)
        release_first.set()
        await asyncio.wait_for(first, timeout=5)
        observed_version = await asyncio.wait_for(queued, timeout=5)
    finally:
        release_first.set()
        await database.close()

    assert observed_version == 2


@pytest.mark.integration
@pytest.mark.parametrize(
    ("contender", "hold_action"),
    (
        ("reactivate", "membership.reactivation_intent"),
        ("replace_roles", "membership.roles_replace_intent"),
    ),
)
async def test_postgresql_revocation_cannot_be_undone_by_stale_membership_mutation(
    contender: str,
    hold_action: str,
    test_database: EphemeralDatabase,
    isolation_records: IsolationRecords,
) -> None:
    """Revalidate terminal revocation after a contender's stale preflight read."""

    organization_id = isolation_records.organization_one
    target_subject_id = uuid4()
    target = Membership(
        id=uuid4(),
        organization_id=organization_id,
        identity_subject_id=target_subject_id,
        person_id=None,
        roles=frozenset({MembershipRole.STAFF}),
        status=MembershipStatus.SUSPENDED,
    )
    _insert_global_test_subject(
        test_database=test_database,
        subject_id=target_subject_id,
    )
    database = _async_runtime_database(test_database)
    memberships = SQLAlchemyMembershipRepository(database)
    audit = _HoldingPeopleAudit(hold_action=hold_action)
    service = MembershipService(
        memberships=memberships,
        people=SQLAlchemyPeopleRepository(
            database=database,
            encryption_key=Fernet.generate_key().decode("ascii"),
        ),
        organizations=_ExactOrganizationAvailability(organization_id),
        audit=audit,
    )
    actor = TenantActorContext(
        subject_id=isolation_records.subject_one,
        organization_id=organization_id,
        membership_id=isolation_records.membership_one,
        correlation_id=f"membership-revoke-{contender}",
        permissions=frozenset({MANAGE_MEMBERSHIPS_PERMISSION}),
    )

    async def stale_mutation() -> Membership:
        if contender == "reactivate":
            return await service.reactivate(actor=actor, membership_id=target.id)
        return await service.replace_roles(
            actor=actor,
            membership_id=target.id,
            roles=frozenset({MembershipRole.STUDENT}),
        )

    stale_task: asyncio.Task[Membership] | None = None
    try:
        await memberships.add(target)
        stale_task = asyncio.create_task(stale_mutation())
        await asyncio.wait_for(audit.intent_reached.wait(), timeout=5)

        revoked = await asyncio.wait_for(
            service.revoke(actor=actor, membership_id=target.id),
            timeout=5,
        )
        assert revoked.status is MembershipStatus.REVOKED
        audit.release_intent.set()

        with pytest.raises(InvalidMembershipError):
            await asyncio.wait_for(stale_task, timeout=5)
        stored = await memberships.get(
            organization_id=organization_id,
            membership_id=target.id,
        )
        assert stored is not None
        assert stored.status is MembershipStatus.REVOKED
        assert stored.roles == frozenset({MembershipRole.STAFF})
    finally:
        audit.release_intent.set()
        if stale_task is not None and not stale_task.done():
            await asyncio.gather(stale_task, return_exceptions=True)
        await database.close()


@pytest.mark.integration
@pytest.mark.parametrize("winner", ("owner_appointment", "revocation"))
async def test_postgresql_owner_appointment_and_revocation_revalidate_locked_state(
    winner: str,
    test_database: EphemeralDatabase,
    isolation_records: IsolationRecords,
) -> None:
    """Keep both owner protection and terminal revocation true under stale reads."""

    organization_id = isolation_records.organization_one
    target_subject_id = uuid4()
    target = Membership(
        id=uuid4(),
        organization_id=organization_id,
        identity_subject_id=target_subject_id,
        person_id=None,
        roles=frozenset({MembershipRole.STAFF}),
    )
    _insert_global_test_subject(
        test_database=test_database,
        subject_id=target_subject_id,
    )
    database = _async_runtime_database(test_database)
    memberships = SQLAlchemyMembershipRepository(database)
    hold_action = (
        "membership.revocation_intent"
        if winner == "owner_appointment"
        else "membership.owner_recovery_intent"
    )
    audit = _HoldingPeopleAudit(hold_action=hold_action)
    service = MembershipService(
        memberships=memberships,
        people=SQLAlchemyPeopleRepository(
            database=database,
            encryption_key=Fernet.generate_key().decode("ascii"),
        ),
        organizations=_ExactOrganizationAvailability(organization_id),
        audit=audit,
    )
    tenant_actor = TenantActorContext(
        subject_id=isolation_records.subject_one,
        organization_id=organization_id,
        membership_id=isolation_records.membership_one,
        correlation_id=f"membership-owner-race-{winner}",
        permissions=frozenset({MANAGE_MEMBERSHIPS_PERMISSION}),
    )
    platform_actor = PlatformActorContext(
        subject_id=isolation_records.subject_one,
        correlation_id=f"membership-owner-race-{winner}",
        permissions=frozenset({APPOINT_OWNER_PERMISSION}),
    )

    async def appoint_owner() -> Membership:
        return await service.appoint_organization_owner(
            actor=platform_actor,
            organization_id=organization_id,
            identity_subject_id=target_subject_id,
            person_id=None,
        )

    async def revoke() -> Membership:
        return await service.revoke(
            actor=tenant_actor,
            membership_id=target.id,
        )

    stale_task: asyncio.Task[Membership] | None = None
    try:
        await memberships.add(target)
        stale_task = asyncio.create_task(
            revoke() if winner == "owner_appointment" else appoint_owner()
        )
        await asyncio.wait_for(audit.intent_reached.wait(), timeout=5)

        committed = await asyncio.wait_for(
            appoint_owner() if winner == "owner_appointment" else revoke(),
            timeout=5,
        )
        audit.release_intent.set()

        expected_error = (
            AuthorizationError
            if winner == "owner_appointment"
            else InvalidMembershipError
        )
        with pytest.raises(expected_error):
            await asyncio.wait_for(stale_task, timeout=5)
        stored = await memberships.get(
            organization_id=organization_id,
            membership_id=target.id,
        )
        assert stored is not None
        assert stored == committed
        if winner == "owner_appointment":
            assert stored.status is MembershipStatus.ACTIVE
            assert stored.roles == frozenset(
                {MembershipRole.STAFF, MembershipRole.ORGANIZATION_OWNER}
            )
        else:
            assert stored.status is MembershipStatus.REVOKED
            assert stored.roles == frozenset({MembershipRole.STAFF})
    finally:
        audit.release_intent.set()
        if stale_task is not None and not stale_task.done():
            await asyncio.gather(stale_task, return_exceptions=True)
        await database.close()


@pytest.mark.integration
@pytest.mark.parametrize(
    ("operation", "intent_action", "removed_status"),
    (
        (
            "suspend",
            "membership.owner_suspension_intent",
            MembershipStatus.SUSPENDED,
        ),
        (
            "revoke",
            "membership.owner_revocation_intent",
            MembershipStatus.REVOKED,
        ),
    ),
)
async def test_postgresql_concurrent_owner_removals_keep_one_active_owner(
    operation: str,
    intent_action: str,
    removed_status: MembershipStatus,
    test_database: EphemeralDatabase,
    isolation_records: IsolationRecords,
) -> None:
    """Serialize two removals so exactly one active organization owner remains."""

    organization_id = uuid4()
    with psycopg.connect(test_database.runtime_dsn) as connection:
        connection.execute(
            """
            INSERT INTO organizations (
                id, slug, organization_type, status, display_name,
                primary_color, secondary_color, locale, timezone,
                education_mode, created_at, updated_at
            ) VALUES (
                %s, %s, 'school', 'active', 'Owner Concurrency Test',
                '#112233', '#445566', 'en', 'UTC', 'school', now(), now()
            )
            """,
            (organization_id, f"owner-concurrency-{organization_id.hex}"),
        )
    subject_ids = (uuid4(), uuid4())
    for subject_id in subject_ids:
        _insert_global_test_subject(
            test_database=test_database,
            subject_id=subject_id,
        )
    owners = tuple(
        Membership(
            id=uuid4(),
            organization_id=organization_id,
            identity_subject_id=subject_id,
            person_id=None,
            roles=frozenset({MembershipRole.ORGANIZATION_OWNER}),
        )
        for subject_id in subject_ids
    )
    database = _async_runtime_database(test_database)
    memberships = SQLAlchemyMembershipRepository(database)
    audit = _OwnerRemovalBarrierAudit(intent_action=intent_action)
    service = MembershipService(
        memberships=memberships,
        people=SQLAlchemyPeopleRepository(
            database=database,
            encryption_key=Fernet.generate_key().decode("ascii"),
        ),
        organizations=_ExactOrganizationAvailability(organization_id),
        audit=audit,
    )
    actor = PlatformActorContext(
        subject_id=isolation_records.subject_one,
        correlation_id=f"owner-removal-{operation}",
        permissions=frozenset({MANAGE_OWNER_LIFECYCLE_PERMISSION}),
    )

    async def remove(owner: Membership) -> Membership:
        if operation == "suspend":
            return await service.suspend_organization_owner(
                actor=actor,
                organization_id=organization_id,
                membership_id=owner.id,
            )
        return await service.revoke_organization_owner(
            actor=actor,
            organization_id=organization_id,
            membership_id=owner.id,
        )

    try:
        for owner in owners:
            await memberships.add(owner)
        results = await asyncio.wait_for(
            asyncio.gather(
                *(remove(owner) for owner in owners),
                return_exceptions=True,
            ),
            timeout=5,
        )
        stored = tuple(
            [
                await memberships.get(
                    organization_id=organization_id,
                    membership_id=owner.id,
                )
                for owner in owners
            ]
        )
    finally:
        await database.close()

    assert sum(isinstance(result, Membership) for result in results) == 1
    assert sum(isinstance(result, InvalidMembershipError) for result in results) == 1
    assert all(membership is not None for membership in stored)
    statuses = [membership.status for membership in stored if membership is not None]
    assert statuses.count(MembershipStatus.ACTIVE) == 1
    assert statuses.count(removed_status) == 1


@pytest.mark.integration
async def test_platform_admin_bootstrap_and_final_revoke_are_serialized(
    test_database: EphemeralDatabase,
) -> None:
    """Prove concurrent first/final administrator checks cannot both succeed."""

    subject_ids = (uuid4(), uuid4())
    with psycopg.connect(test_database.runtime_dsn) as connection:
        for index, subject_id in enumerate(subject_ids):
            connection.execute(
                """
                INSERT INTO identity_subjects (
                    id, issuer, subject, email, display_name, created_at, updated_at
                ) VALUES (%s, %s, %s, NULL, NULL, now(), now())
                """,
                (
                    subject_id,
                    "urn:ownsis:test:platform-admin",
                    f"platform-admin-{index}",
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
    repository = SQLAlchemyPlatformAdministratorRepository(database)
    try:
        bootstrap_results = await asyncio.gather(
            *(repository.bootstrap(subject_id=value) for value in subject_ids),
            return_exceptions=True,
        )
        assert (
            sum(
                isinstance(result, PlatformAdministrator)
                for result in bootstrap_results
            )
            == 1
        )
        assert (
            sum(
                isinstance(result, PlatformAdministratorBootstrapClosedError)
                for result in bootstrap_results
            )
            == 1
        )

        inactive_subject = next(
            subject_id
            for subject_id, result in zip(
                subject_ids,
                bootstrap_results,
                strict=True,
            )
            if isinstance(result, PlatformAdministratorBootstrapClosedError)
        )
        await repository.assign(subject_id=inactive_subject)

        revoke_results = await asyncio.gather(
            *(repository.revoke(subject_id=value) for value in subject_ids),
            return_exceptions=True,
        )
    finally:
        await database.close()

    assert (
        sum(
            isinstance(result, PlatformAdministrator) and not result.active
            for result in revoke_results
        )
        == 1
    )
    assert (
        sum(
            isinstance(result, FinalPlatformAdministratorError)
            for result in revoke_results
        )
        == 1
    )


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
            InMemorySchedulingAuditSink(),
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


def _async_runtime_database(test_database: EphemeralDatabase) -> Database:
    return Database(
        Settings(APP_ENV=AppEnvironment.TEST),
        database_url=test_database.runtime_dsn.replace(
            "postgresql://",
            "postgresql+asyncpg://",
            1,
        ),
    )


def _booking_session(
    *,
    organization_id: UUID,
    room_id: UUID,
    teacher_id: UUID,
    group_id: UUID,
    starts_at: datetime,
) -> ScheduledSession:
    return ScheduledSession(
        id=uuid4(),
        organization_id=organization_id,
        activity_id=uuid4(),
        course_offering_id=uuid4(),
        room_id=room_id,
        teacher_ids=(teacher_id,),
        group_ids=(group_id,),
        required_group_ids=(group_id,),
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        activity_type="lecture",
        required_room_type="lecture",
        expected_attendance=20,
    )


def _booking_constraints(
    *,
    organization_id: UUID,
    room_ids: frozenset[UUID],
    teacher_ids: frozenset[UUID],
    starts_at: datetime,
) -> ConstraintContext:
    horizon = TimeWindow(
        starts_at=starts_at - timedelta(hours=1),
        ends_at=starts_at + timedelta(hours=2),
    )
    return ConstraintContext(
        organization_id=organization_id,
        rooms=tuple(
            RoomSpecification(
                organization_id=organization_id,
                room_id=room_id,
                room_type="lecture",
                capacity=40,
            )
            for room_id in sorted(room_ids, key=str)
        ),
        teacher_availability=tuple(
            TeacherAvailability(
                organization_id=organization_id,
                teacher_id=teacher_id,
                windows=(horizon,),
            )
            for teacher_id in sorted(teacher_ids, key=str)
        ),
        academic_calendar_windows=(horizon,),
    )


@pytest.mark.integration
@pytest.mark.parametrize("shared_resource", ["room", "teacher", "required_group"])
async def test_postgresql_concurrent_booking_rejects_each_shared_resource(
    test_database: EphemeralDatabase,
    isolation_records: IsolationRecords,
    shared_resource: str,
) -> None:
    """Hold one real transaction and reject a colliding booking immediately."""

    organization_id = isolation_records.organization_one
    shared_id = uuid4()
    first_room_id = shared_id if shared_resource == "room" else uuid4()
    second_room_id = shared_id if shared_resource == "room" else uuid4()
    first_teacher_id = shared_id if shared_resource == "teacher" else uuid4()
    second_teacher_id = shared_id if shared_resource == "teacher" else uuid4()
    first_group_id = shared_id if shared_resource == "required_group" else uuid4()
    second_group_id = shared_id if shared_resource == "required_group" else uuid4()
    starts_at = datetime(2026, 9, 7, 9, tzinfo=UTC)
    first = _booking_session(
        organization_id=organization_id,
        room_id=first_room_id,
        teacher_id=first_teacher_id,
        group_id=first_group_id,
        starts_at=starts_at,
    )
    second = _booking_session(
        organization_id=organization_id,
        room_id=second_room_id,
        teacher_id=second_teacher_id,
        group_id=second_group_id,
        starts_at=starts_at,
    )
    constraints = _booking_constraints(
        organization_id=organization_id,
        room_ids=frozenset({first_room_id, second_room_id}),
        teacher_ids=frozenset({first_teacher_id, second_teacher_id}),
        starts_at=starts_at,
    )
    database = _async_runtime_database(test_database)
    holding_repository = _HoldingSchedulingRepository(database)
    competing_repository = SQLAlchemySchedulingRepository(database)
    first_write = asyncio.create_task(
        holding_repository.save_conflict_free_session(
            session=first,
            expected_version=None,
            constraints=constraints,
        )
    )
    try:
        await asyncio.wait_for(holding_repository.write_locked.wait(), timeout=5)
        with pytest.raises(SchedulingConflictError, match="being updated"):
            await asyncio.wait_for(
                competing_repository.save_conflict_free_session(
                    session=second,
                    expected_version=None,
                    constraints=constraints,
                ),
                timeout=5,
            )
    finally:
        holding_repository.release_write.set()
        await asyncio.wait_for(first_write, timeout=5)

    try:
        assert (
            await competing_repository.get_session(
                organization_id=organization_id,
                session_id=first.id,
            )
            == first
        )
        assert (
            await competing_repository.get_session(
                organization_id=organization_id,
                session_id=second.id,
            )
            is None
        )
    finally:
        await database.close()


@pytest.mark.integration
async def test_postgresql_booking_locks_are_tenant_scoped(
    test_database: EphemeralDatabase,
    isolation_records: IsolationRecords,
) -> None:
    """Permit identical resource identifiers in two tenant transactions."""

    shared_room_id = uuid4()
    shared_teacher_id = uuid4()
    shared_group_id = uuid4()
    starts_at = datetime(2026, 9, 8, 9, tzinfo=UTC)
    first = _booking_session(
        organization_id=isolation_records.organization_one,
        room_id=shared_room_id,
        teacher_id=shared_teacher_id,
        group_id=shared_group_id,
        starts_at=starts_at,
    )
    second = _booking_session(
        organization_id=isolation_records.organization_two,
        room_id=shared_room_id,
        teacher_id=shared_teacher_id,
        group_id=shared_group_id,
        starts_at=starts_at,
    )
    first_constraints = _booking_constraints(
        organization_id=isolation_records.organization_one,
        room_ids=frozenset({shared_room_id}),
        teacher_ids=frozenset({shared_teacher_id}),
        starts_at=starts_at,
    )
    second_constraints = _booking_constraints(
        organization_id=isolation_records.organization_two,
        room_ids=frozenset({shared_room_id}),
        teacher_ids=frozenset({shared_teacher_id}),
        starts_at=starts_at,
    )
    database = _async_runtime_database(test_database)
    holding_repository = _HoldingSchedulingRepository(database)
    competing_repository = SQLAlchemySchedulingRepository(database)
    first_write = asyncio.create_task(
        holding_repository.save_conflict_free_session(
            session=first,
            expected_version=None,
            constraints=first_constraints,
        )
    )
    try:
        await asyncio.wait_for(holding_repository.write_locked.wait(), timeout=5)
        await asyncio.wait_for(
            competing_repository.save_conflict_free_session(
                session=second,
                expected_version=None,
                constraints=second_constraints,
            ),
            timeout=5,
        )
    finally:
        holding_repository.release_write.set()
        await asyncio.wait_for(first_write, timeout=5)

    try:
        assert (
            await competing_repository.get_session(
                organization_id=first.organization_id,
                session_id=first.id,
            )
            == first
        )
        assert (
            await competing_repository.get_session(
                organization_id=second.organization_id,
                session_id=second.id,
            )
            == second
        )
    finally:
        await database.close()


@pytest.mark.integration
async def test_postgresql_generated_replacement_preserves_locks_and_versions_members(
    test_database: EphemeralDatabase,
) -> None:
    """Enforce persisted locks and server-owned versions on a real replacement."""

    organization_id = uuid4()
    with psycopg.connect(test_database.runtime_dsn) as connection:
        connection.execute(
            """
            INSERT INTO organizations (
                id, slug, organization_type, status, display_name,
                primary_color, secondary_color, locale, timezone,
                education_mode, created_at, updated_at
            ) VALUES (
                %s, %s, 'school', 'active', 'Scheduling Replacement Test',
                '#112233', '#445566', 'en', 'UTC', 'school', now(), now()
            )
            """,
            (organization_id, f"scheduling-replacement-{organization_id.hex}"),
        )
    starts_at = datetime(2026, 9, 9, 9, tzinfo=UTC)
    locked = replace(
        _booking_session(
            organization_id=organization_id,
            room_id=uuid4(),
            teacher_id=uuid4(),
            group_id=uuid4(),
            starts_at=starts_at,
        ),
        locked=True,
    )
    first_mutable_teacher_id = uuid4()
    removed_mutable_teacher_id = uuid4()
    first_mutable_group_id = uuid4()
    removed_mutable_group_id = uuid4()
    mutable = replace(
        _booking_session(
            organization_id=organization_id,
            room_id=uuid4(),
            teacher_id=first_mutable_teacher_id,
            group_id=first_mutable_group_id,
            starts_at=starts_at,
        ),
        teacher_ids=(first_mutable_teacher_id, removed_mutable_teacher_id),
        group_ids=(first_mutable_group_id, removed_mutable_group_id),
        required_group_ids=(first_mutable_group_id, removed_mutable_group_id),
    )
    replacement_room_id = uuid4()
    replacement_teacher_id = uuid4()
    replacement_group_id = uuid4()
    retained_mutable = replace(
        mutable,
        room_id=replacement_room_id,
        teacher_ids=(replacement_teacher_id,),
        group_ids=(replacement_group_id,),
        required_group_ids=(replacement_group_id,),
    )
    new_session = _booking_session(
        organization_id=organization_id,
        room_id=uuid4(),
        teacher_id=uuid4(),
        group_id=uuid4(),
        starts_at=starts_at,
    )
    constraints = _booking_constraints(
        organization_id=organization_id,
        room_ids=frozenset(
            {
                locked.room_id,
                mutable.room_id,
                replacement_room_id,
                new_session.room_id,
            }
        ),
        teacher_ids=frozenset(
            {
                *locked.teacher_ids,
                *mutable.teacher_ids,
                replacement_teacher_id,
                *new_session.teacher_ids,
            }
        ),
        starts_at=starts_at,
    )
    database = _async_runtime_database(test_database)
    repository = SQLAlchemySchedulingRepository(database)
    try:
        await repository.save_conflict_free_session(
            session=locked,
            expected_version=None,
            constraints=constraints,
        )
        await repository.save_conflict_free_session(
            session=mutable,
            expected_version=None,
            constraints=constraints,
        )

        with pytest.raises(ScheduleVersionConflictError, match="changed a locked"):
            await repository.replace_generated_schedule(
                organization_id=organization_id,
                proposed_sessions=(retained_mutable,),
                locked_session_ids=frozenset(),
                expected_versions={locked.id: 0, mutable.id: 0},
                constraints=constraints,
            )

        first = await repository.replace_generated_schedule(
            organization_id=organization_id,
            proposed_sessions=(locked, retained_mutable, new_session),
            locked_session_ids=frozenset(),
            expected_versions={locked.id: 0, mutable.id: 0},
            constraints=constraints,
        )
        first_by_id = {session.id: session for session in first}
        assert first_by_id[locked.id] == locked
        assert first_by_id[mutable.id] == replace(retained_mutable, version=1)
        assert first_by_id[new_session.id] == new_session

        second = await repository.replace_generated_schedule(
            organization_id=organization_id,
            proposed_sessions=first,
            locked_session_ids=frozenset(),
            expected_versions={locked.id: 0, mutable.id: 1, new_session.id: 0},
            constraints=constraints,
        )
        second_by_id = {session.id: session for session in second}
        assert second_by_id[locked.id].version == 0
        assert second_by_id[mutable.id] == replace(retained_mutable, version=2)
        assert second_by_id[new_session.id].version == 1
        assert (
            await repository.get_session(
                organization_id=organization_id,
                session_id=mutable.id,
            )
            == second_by_id[mutable.id]
        )
        assert removed_mutable_teacher_id not in second_by_id[mutable.id].teacher_ids
        assert removed_mutable_group_id not in second_by_id[mutable.id].group_ids
    finally:
        await database.close()


@pytest.mark.integration
async def test_postgresql_generated_replacement_excludes_normal_writes(
    test_database: EphemeralDatabase,
) -> None:
    """Reject a normal write while a nonempty replacement owns the tenant lock."""

    organization_id = uuid4()
    with psycopg.connect(test_database.runtime_dsn) as connection:
        connection.execute(
            """
            INSERT INTO organizations (
                id, slug, organization_type, status, display_name,
                primary_color, secondary_color, locale, timezone,
                education_mode, created_at, updated_at
            ) VALUES (
                %s, %s, 'school', 'active', 'Scheduling Lock Test',
                '#112233', '#445566', 'en', 'UTC', 'school', now(), now()
            )
            """,
            (organization_id, f"scheduling-lock-{organization_id.hex}"),
        )
    starts_at = datetime(2026, 9, 9, 9, tzinfo=UTC)
    replacement_session = _booking_session(
        organization_id=organization_id,
        room_id=uuid4(),
        teacher_id=uuid4(),
        group_id=uuid4(),
        starts_at=starts_at,
    )
    session = _booking_session(
        organization_id=organization_id,
        room_id=uuid4(),
        teacher_id=uuid4(),
        group_id=uuid4(),
        starts_at=starts_at,
    )
    constraints = _booking_constraints(
        organization_id=organization_id,
        room_ids=frozenset({replacement_session.room_id, session.room_id}),
        teacher_ids=frozenset({*replacement_session.teacher_ids, *session.teacher_ids}),
        starts_at=starts_at,
    )
    database = _async_runtime_database(test_database)
    holding_repository = _HoldingReplacementRepository(database)
    competing_repository = SQLAlchemySchedulingRepository(database)
    replacement = asyncio.create_task(
        holding_repository.replace_generated_schedule(
            organization_id=organization_id,
            proposed_sessions=(replacement_session,),
            locked_session_ids=frozenset(),
            expected_versions={},
            constraints=constraints,
        )
    )
    try:
        await asyncio.wait_for(
            holding_repository.replacement_locked.wait(),
            timeout=5,
        )
        with pytest.raises(SchedulingConflictError, match="being updated"):
            await asyncio.wait_for(
                competing_repository.save_conflict_free_session(
                    session=session,
                    expected_version=None,
                    constraints=constraints,
                ),
                timeout=5,
            )
    finally:
        holding_repository.release_replacement.set()
        await asyncio.wait_for(replacement, timeout=5)

    try:
        assert (
            await competing_repository.get_session(
                organization_id=organization_id,
                session_id=session.id,
            )
            is None
        )
        assert (
            await competing_repository.get_session(
                organization_id=organization_id,
                session_id=replacement_session.id,
            )
            == replacement_session
        )
    finally:
        await database.close()


@pytest.mark.integration
async def test_postgresql_normal_write_excludes_generated_replacement(
    test_database: EphemeralDatabase,
) -> None:
    """Reject a nonempty replacement while a normal write owns the tenant lock."""

    organization_id = uuid4()
    with psycopg.connect(test_database.runtime_dsn) as connection:
        connection.execute(
            """
            INSERT INTO organizations (
                id, slug, organization_type, status, display_name,
                primary_color, secondary_color, locale, timezone,
                education_mode, created_at, updated_at
            ) VALUES (
                %s, %s, 'school', 'active', 'Scheduling Reverse Lock Test',
                '#112233', '#445566', 'en', 'UTC', 'school', now(), now()
            )
            """,
            (organization_id, f"scheduling-reverse-lock-{organization_id.hex}"),
        )
    starts_at = datetime(2026, 9, 10, 9, tzinfo=UTC)
    normal_session = _booking_session(
        organization_id=organization_id,
        room_id=uuid4(),
        teacher_id=uuid4(),
        group_id=uuid4(),
        starts_at=starts_at,
    )
    replacement_session = _booking_session(
        organization_id=organization_id,
        room_id=uuid4(),
        teacher_id=uuid4(),
        group_id=uuid4(),
        starts_at=starts_at,
    )
    constraints = _booking_constraints(
        organization_id=organization_id,
        room_ids=frozenset({normal_session.room_id, replacement_session.room_id}),
        teacher_ids=frozenset(
            {*normal_session.teacher_ids, *replacement_session.teacher_ids}
        ),
        starts_at=starts_at,
    )
    database = _async_runtime_database(test_database)
    holding_repository = _HoldingSchedulingRepository(database)
    competing_repository = SQLAlchemySchedulingRepository(database)
    normal_write = asyncio.create_task(
        holding_repository.save_conflict_free_session(
            session=normal_session,
            expected_version=None,
            constraints=constraints,
        )
    )
    try:
        await asyncio.wait_for(holding_repository.write_locked.wait(), timeout=5)
        with pytest.raises(SchedulingConflictError, match="being updated"):
            await asyncio.wait_for(
                competing_repository.replace_generated_schedule(
                    organization_id=organization_id,
                    proposed_sessions=(replacement_session,),
                    locked_session_ids=frozenset(),
                    expected_versions={},
                    constraints=constraints,
                ),
                timeout=5,
            )
    finally:
        holding_repository.release_write.set()
        await asyncio.wait_for(normal_write, timeout=5)

    try:
        assert (
            await competing_repository.get_session(
                organization_id=organization_id,
                session_id=normal_session.id,
            )
            == normal_session
        )
        assert (
            await competing_repository.get_session(
                organization_id=organization_id,
                session_id=replacement_session.id,
            )
            is None
        )
    finally:
        await database.close()


@pytest.mark.integration
@pytest.mark.parametrize(
    ("maximum_credits", "overlapping", "expected_rule"),
    (
        (Decimal("3"), False, "maximum_credits"),
        (Decimal("6"), True, "schedule_conflict"),
    ),
)
async def test_postgresql_selection_approvals_serialize_and_pool_one_stays_live(
    test_database: EphemeralDatabase,
    isolation_records: IsolationRecords,
    maximum_credits: Decimal,
    overlapping: bool,
    expected_rule: str,
) -> None:
    """Serialize student rules and avoid nested-session pool starvation."""

    organization_id = isolation_records.organization_one
    suffix = uuid4().hex[:8]
    now = datetime(2026, 8, 5, 8, tzinfo=UTC)
    campus_id = uuid4()
    faculty = Faculty(
        id=uuid4(),
        organization_id=organization_id,
        campus_id=campus_id,
        code=f"SCI-{suffix}",
        name=f"Science {suffix}",
    )
    department = Department(
        id=uuid4(),
        organization_id=organization_id,
        faculty_id=faculty.id,
        code=f"CS-{suffix}",
        name=f"Computer Science {suffix}",
    )
    program = Program(
        id=uuid4(),
        organization_id=organization_id,
        department_id=department.id,
        code=f"BSCS-{suffix}",
        name=f"Computer Science {suffix}",
        education_mode=EducationMode.FLEXIBLE_SELECTION,
        credit_unit_label="credits",
    )
    academic_year = AcademicYear(
        id=uuid4(),
        organization_id=organization_id,
        name=f"2026-2027-{suffix}",
        starts_on=date(2026, 8, 1),
        ends_on=date(2027, 7, 31),
    )
    term = Term(
        id=uuid4(),
        organization_id=organization_id,
        academic_year_id=academic_year.id,
        name=f"Fall-{suffix}",
        starts_on=date(2026, 8, 10),
        ends_on=date(2026, 12, 20),
        enrollment_deadline=datetime(2026, 8, 20, tzinfo=UTC),
    )
    courses = (
        Course(
            id=uuid4(),
            organization_id=organization_id,
            department_id=department.id,
            code=f"CS101-{suffix}",
            title="Foundations",
            credits=Decimal("3"),
        ),
        Course(
            id=uuid4(),
            organization_id=organization_id,
            department_id=department.id,
            code=f"CS102-{suffix}",
            title="Systems",
            credits=Decimal("3"),
        ),
    )
    meeting_windows = (
        (
            (MeetingWindow(1, time(9), time(10)),),
            (MeetingWindow(1, time(9, 30), time(10, 30)),),
        )
        if overlapping
        else ((), ())
    )
    offerings = tuple(
        CourseOffering(
            id=uuid4(),
            organization_id=organization_id,
            course_id=course.id,
            term_id=term.id,
            campus_id=campus_id,
            section_code="A",
            capacity=30,
            meeting_windows=meeting_windows[index],
        )
        for index, course in enumerate(courses)
    )
    curriculum = ProgramCurriculum(
        id=uuid4(),
        organization_id=organization_id,
        program_id=program.id,
        academic_year_id=academic_year.id,
        courses=tuple(
            CurriculumCourse(
                course_id=course.id,
                kind=CurriculumCourseKind.ELECTIVE,
                credits=course.credits,
            )
            for course in courses
        ),
    )
    policy = CourseSelectionPolicy(
        organization_id=organization_id,
        program_id=program.id,
        term_id=term.id,
        education_mode=EducationMode.FLEXIBLE_SELECTION,
        maximum_credits=maximum_credits,
        deadline=datetime(2026, 8, 20, tzinfo=UTC),
        approval_required=True,
    )
    student_enrollment = StudentAcademicEnrollment(
        id=uuid4(),
        organization_id=organization_id,
        student_id=uuid4(),
        program_id=program.id,
        academic_year_id=academic_year.id,
        cohort_id=None,
        status=AcademicEnrollmentStatus.ACTIVE,
        enrolled_at=now,
    )
    requests = tuple(
        CourseSelectionRequest(
            id=uuid4(),
            organization_id=organization_id,
            student_academic_enrollment_id=student_enrollment.id,
            term_id=term.id,
            offering_ids=(offering.id,),
            requested_credits=Decimal("3"),
            status=CourseSelectionStatus.PENDING,
            submitted_at=now,
            submitted_by=isolation_records.subject_one,
        )
        for offering in offerings
    )
    database = _async_runtime_database(test_database)
    repository = _HoldingCourseSelectionRepository(database)
    audit = _RecordingCourseSelectionAudit()
    service = CourseSelectionService(
        catalog=repository,
        selections=repository,
        clock=_FixedAcademicClock(now),
        audit=audit,
        ownership=_UnusedCourseSelectionOwnership(),
    )
    actor = TenantActorContext(
        subject_id=isolation_records.subject_one,
        organization_id=organization_id,
        membership_id=isolation_records.membership_one,
        correlation_id=f"selection-concurrency-{suffix}",
        permissions=frozenset({ACADEMICS_SELECTION_APPROVE}),
    )
    first_task: asyncio.Task[CourseSelectionRequest] | None = None
    second_task: asyncio.Task[CourseSelectionRequest] | None = None
    try:
        await repository.save_faculty(faculty)
        await repository.save_department(department)
        await repository.save_program(program)
        await repository.save_academic_year(academic_year)
        await repository.save_term(term)
        for course in courses:
            await repository.save_course(course)
        for offering in offerings:
            await repository.save_course_offering(offering)
        await repository.save_curriculum(curriculum)
        await repository.save_selection_policy(policy)
        await repository.save_student_enrollment(student_enrollment)
        for request in requests:
            await repository.save_submission(
                request=request,
                enrollments=(),
                offering_capacities={},
            )

        first_task = asyncio.create_task(
            service.decide(
                context=actor,
                request_id=requests[0].id,
                approved=True,
            )
        )
        await asyncio.wait_for(repository.first_decision_locked.wait(), timeout=5)
        second_task = asyncio.create_task(
            service.decide(
                context=actor,
                request_id=requests[1].id,
                approved=True,
            )
        )
        try:
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(second_task), timeout=0.2)
        finally:
            repository.release_first_decision.set()
        results = await asyncio.gather(
            first_task,
            second_task,
            return_exceptions=True,
        )

        stored = tuple(
            await asyncio.gather(
                *(
                    repository.get_selection_request(
                        organization_id=organization_id,
                        request_id=request.id,
                    )
                    for request in requests
                )
            )
        )
        enrollments = await repository.list_course_enrollments(
            organization_id=organization_id,
            student_academic_enrollment_id=student_enrollment.id,
        )
        assert (
            sum(isinstance(result, CourseSelectionRequest) for result in results) == 1
        )
        assert (
            sum(isinstance(result, CourseSelectionDecisionError) for result in results)
            == 1
        )
        decision_errors = tuple(
            result
            for result in results
            if isinstance(result, CourseSelectionDecisionError)
        )
        assert expected_rule in str(decision_errors[0])
        assert {value.status for value in stored if value is not None} == {
            CourseSelectionStatus.APPROVED,
            CourseSelectionStatus.PENDING,
        }
        assert len(enrollments) == 1
        assert audit.events.count("academics.course_selection.approval_requested") == 2
        assert audit.events.count("academics.course_selection.approved") == 1

        pending_request = next(
            value
            for value in stored
            if value is not None and value.status is CourseSelectionStatus.PENDING
        )
        rule_updates: tuple[asyncio.Task[None], ...] = ()
        try:
            async with repository.decision_transaction(
                organization_id=organization_id,
                request_id=pending_request.id,
            ) as rule_snapshot:
                assert (
                    await rule_snapshot.get_term(
                        organization_id=organization_id,
                        term_id=term.id,
                    )
                    is not None
                )
                assert (
                    await rule_snapshot.get_selection_policy(
                        organization_id=organization_id,
                        program_id=program.id,
                        term_id=term.id,
                    )
                    is not None
                )
                assert (
                    await rule_snapshot.get_curriculum(
                        organization_id=organization_id,
                        program_id=program.id,
                        academic_year_id=academic_year.id,
                    )
                    is not None
                )
                rule_updates = (
                    asyncio.create_task(
                        repository.save_selection_policy(
                            replace(
                                policy,
                                deadline=policy.deadline + timedelta(days=1),
                            )
                        )
                    ),
                    asyncio.create_task(repository.save_curriculum(curriculum)),
                )
                for update in rule_updates:
                    with pytest.raises(TimeoutError):
                        await asyncio.wait_for(asyncio.shield(update), timeout=0.2)
        finally:
            if rule_updates:
                await asyncio.gather(*rule_updates)

        liveness_enrollment = StudentAcademicEnrollment(
            id=uuid4(),
            organization_id=organization_id,
            student_id=uuid4(),
            program_id=program.id,
            academic_year_id=academic_year.id,
            cohort_id=None,
            status=AcademicEnrollmentStatus.ACTIVE,
            enrolled_at=now,
        )
        liveness_request = CourseSelectionRequest(
            id=uuid4(),
            organization_id=organization_id,
            student_academic_enrollment_id=liveness_enrollment.id,
            term_id=term.id,
            offering_ids=(offerings[0].id,),
            requested_credits=Decimal("3"),
            status=CourseSelectionStatus.PENDING,
            submitted_at=now,
            submitted_by=isolation_records.subject_one,
        )
        await repository.save_student_enrollment(liveness_enrollment)
        await repository.save_submission(
            request=liveness_request,
            enrollments=(),
            offering_capacities={},
        )
        single_connection_database = Database(
            Settings(
                APP_ENV=AppEnvironment.TEST,
                DATABASE_POOL_SIZE=1,
                DATABASE_MAX_OVERFLOW=0,
            ),
            database_url=test_database.runtime_dsn.replace(
                "postgresql://",
                "postgresql+asyncpg://",
                1,
            ),
        )
        single_connection_repository = SQLAlchemyAcademicRepository(
            single_connection_database
        )
        single_connection_service = CourseSelectionService(
            catalog=single_connection_repository,
            selections=single_connection_repository,
            clock=_FixedAcademicClock(now),
            audit=ApplicationAuditSink(
                AuditService(SQLAlchemyAuditRepository(single_connection_database))
            ),
            ownership=_UnusedCourseSelectionOwnership(),
        )
        try:
            liveness_result = await asyncio.wait_for(
                single_connection_service.decide(
                    context=actor,
                    request_id=liveness_request.id,
                    approved=True,
                ),
                timeout=5,
            )
            assert liveness_result.status is CourseSelectionStatus.APPROVED
        finally:
            await single_connection_database.close()

        close_task: asyncio.Task[Term | None] | None = None
        try:
            async with repository.decision_transaction(
                organization_id=organization_id,
                request_id=pending_request.id,
            ) as term_snapshot:
                assert (
                    await term_snapshot.get_term(
                        organization_id=organization_id,
                        term_id=term.id,
                    )
                    is not None
                )
                close_task = asyncio.create_task(
                    repository.close_term(
                        organization_id=organization_id,
                        term_id=term.id,
                    )
                )
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(asyncio.shield(close_task), timeout=0.2)
        finally:
            if close_task is not None:
                closed_term = await close_task
                assert closed_term is not None and closed_term.is_closed
    finally:
        repository.release_first_decision.set()
        pending_tasks = tuple(
            task
            for task in (first_task, second_task)
            if task is not None and not task.done()
        )
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)
        await database.close()


@pytest.mark.integration
async def test_postgresql_selection_approvals_serialize_final_offering_seat(
    test_database: EphemeralDatabase,
    isolation_records: IsolationRecords,
) -> None:
    """Allow exactly one concurrent approval to claim one remaining seat."""

    organization_id = isolation_records.organization_one
    suffix = uuid4().hex[:8]
    now = datetime(2026, 8, 5, 8, tzinfo=UTC)
    campus_id = uuid4()
    faculty = Faculty(
        id=uuid4(),
        organization_id=organization_id,
        campus_id=campus_id,
        code=f"SEAT-FAC-{suffix}",
        name=f"Seat Faculty {suffix}",
    )
    department = Department(
        id=uuid4(),
        organization_id=organization_id,
        faculty_id=faculty.id,
        code=f"SEAT-DEP-{suffix}",
        name=f"Seat Department {suffix}",
    )
    programs = tuple(
        Program(
            id=uuid4(),
            organization_id=organization_id,
            department_id=department.id,
            code=f"SEAT-{index}-{suffix}",
            name=f"Seat Program {index} {suffix}",
            education_mode=EducationMode.FLEXIBLE_SELECTION,
            credit_unit_label="credits",
        )
        for index in range(2)
    )
    academic_year = AcademicYear(
        id=uuid4(),
        organization_id=organization_id,
        name=f"Seat Year {suffix}",
        starts_on=date(2026, 8, 1),
        ends_on=date(2027, 7, 31),
    )
    term = Term(
        id=uuid4(),
        organization_id=organization_id,
        academic_year_id=academic_year.id,
        name=f"Seat Term {suffix}",
        starts_on=date(2026, 8, 10),
        ends_on=date(2026, 12, 20),
        enrollment_deadline=datetime(2026, 8, 20, tzinfo=UTC),
    )
    course = Course(
        id=uuid4(),
        organization_id=organization_id,
        department_id=department.id,
        code=f"SEAT-101-{suffix}",
        title=f"Final Seat {suffix}",
        credits=Decimal("3"),
    )
    offering = CourseOffering(
        id=uuid4(),
        organization_id=organization_id,
        course_id=course.id,
        term_id=term.id,
        campus_id=campus_id,
        section_code="A",
        capacity=2,
        meeting_windows=(),
    )
    curricula = tuple(
        ProgramCurriculum(
            id=uuid4(),
            organization_id=organization_id,
            program_id=program.id,
            academic_year_id=academic_year.id,
            courses=(
                CurriculumCourse(
                    course_id=course.id,
                    kind=CurriculumCourseKind.ELECTIVE,
                    credits=course.credits,
                ),
            ),
        )
        for program in programs
    )
    policies = tuple(
        CourseSelectionPolicy(
            organization_id=organization_id,
            program_id=program.id,
            term_id=term.id,
            education_mode=EducationMode.FLEXIBLE_SELECTION,
            maximum_credits=Decimal("6"),
            deadline=datetime(2026, 8, 20, tzinfo=UTC),
            approval_required=True,
        )
        for program in programs
    )
    occupied_student = StudentAcademicEnrollment(
        id=uuid4(),
        organization_id=organization_id,
        student_id=uuid4(),
        program_id=programs[0].id,
        academic_year_id=academic_year.id,
        cohort_id=None,
        status=AcademicEnrollmentStatus.ACTIVE,
        enrolled_at=now,
    )
    racing_students = tuple(
        StudentAcademicEnrollment(
            id=uuid4(),
            organization_id=organization_id,
            student_id=uuid4(),
            program_id=program.id,
            academic_year_id=academic_year.id,
            cohort_id=None,
            status=AcademicEnrollmentStatus.ACTIVE,
            enrolled_at=now,
        )
        for program in programs
    )
    occupied_request = CourseSelectionRequest(
        id=uuid4(),
        organization_id=organization_id,
        student_academic_enrollment_id=occupied_student.id,
        term_id=term.id,
        offering_ids=(offering.id,),
        requested_credits=course.credits,
        status=CourseSelectionStatus.APPROVED,
        submitted_at=now,
        submitted_by=isolation_records.subject_one,
        decided_at=now,
        decided_by=isolation_records.subject_one,
    )
    pending_requests = tuple(
        CourseSelectionRequest(
            id=uuid4(),
            organization_id=organization_id,
            student_academic_enrollment_id=student.id,
            term_id=term.id,
            offering_ids=(offering.id,),
            requested_credits=course.credits,
            status=CourseSelectionStatus.PENDING,
            submitted_at=now,
            submitted_by=isolation_records.subject_one,
        )
        for student in racing_students
    )
    database = _async_runtime_database(test_database)
    repository = SQLAlchemyAcademicRepository(database)
    audit = _RecordingCourseSelectionAudit()
    service = CourseSelectionService(
        catalog=repository,
        selections=repository,
        clock=_FixedAcademicClock(now),
        audit=audit,
        ownership=_UnusedCourseSelectionOwnership(),
    )
    actor = TenantActorContext(
        subject_id=isolation_records.subject_one,
        organization_id=organization_id,
        membership_id=isolation_records.membership_one,
        correlation_id=f"selection-final-seat-{suffix}",
        permissions=frozenset({ACADEMICS_SELECTION_APPROVE}),
    )
    first_task: asyncio.Task[CourseSelectionRequest] | None = None
    second_task: asyncio.Task[CourseSelectionRequest] | None = None
    try:
        await repository.save_faculty(faculty)
        await repository.save_department(department)
        for program in programs:
            await repository.save_program(program)
        await repository.save_academic_year(academic_year)
        await repository.save_term(term)
        await repository.save_course(course)
        await repository.save_course_offering(offering)
        for curriculum in curricula:
            await repository.save_curriculum(curriculum)
        for policy in policies:
            await repository.save_selection_policy(policy)
        await repository.save_student_enrollment(occupied_student)
        for student in racing_students:
            await repository.save_student_enrollment(student)
        await repository.save_submission(
            request=occupied_request,
            enrollments=(
                CourseEnrollment(
                    id=uuid4(),
                    organization_id=organization_id,
                    student_academic_enrollment_id=occupied_student.id,
                    course_offering_id=offering.id,
                    credits=course.credits,
                    status=CourseEnrollmentStatus.ENROLLED,
                    enrolled_at=now,
                    selection_request_id=occupied_request.id,
                ),
            ),
            offering_capacities={offering.id: offering.capacity},
        )
        for request in pending_requests:
            await repository.save_submission(
                request=request,
                enrollments=(),
                offering_capacities={},
            )

        async with database.session(organization_id=organization_id) as lock_session:
            locked_offering_id = await lock_session.scalar(
                text(
                    """
                    SELECT id
                    FROM academic_course_offerings
                    WHERE organization_id = :organization_id
                      AND id = :offering_id
                    FOR UPDATE
                    """
                ),
                {
                    "organization_id": organization_id,
                    "offering_id": offering.id,
                },
            )
            assert locked_offering_id == offering.id
            first_task = asyncio.create_task(
                service.decide(
                    context=actor,
                    request_id=pending_requests[0].id,
                    approved=True,
                )
            )
            second_task = asyncio.create_task(
                service.decide(
                    context=actor,
                    request_id=pending_requests[1].id,
                    approved=True,
                )
            )
            completed, _pending = await asyncio.wait(
                (first_task, second_task),
                timeout=0.2,
            )
            assert completed == set()
            assert (
                audit.events.count("academics.course_selection.approval_requested") == 2
            )
        results = await asyncio.gather(
            first_task,
            second_task,
            return_exceptions=True,
        )

        stored_requests = tuple(
            await asyncio.gather(
                *(
                    repository.get_selection_request(
                        organization_id=organization_id,
                        request_id=request.id,
                    )
                    for request in pending_requests
                )
            )
        )
        enrollment_sets = tuple(
            await asyncio.gather(
                *(
                    repository.list_course_enrollments(
                        organization_id=organization_id,
                        student_academic_enrollment_id=student.id,
                    )
                    for student in (occupied_student, *racing_students)
                )
            )
        )
        racing_enrollments = enrollment_sets[1] + enrollment_sets[2]
        assert (
            sum(isinstance(result, CourseSelectionRequest) for result in results) == 1
        )
        assert sum(isinstance(result, CourseSelectionError) for result in results) == 1
        capacity_error = next(
            result for result in results if isinstance(result, CourseSelectionError)
        )
        assert "capacity was reached" in str(capacity_error)
        assert {
            request.status for request in stored_requests if request is not None
        } == {
            CourseSelectionStatus.APPROVED,
            CourseSelectionStatus.PENDING,
        }
        assert len(racing_enrollments) == 1
        assert (
            sum(len(enrollments) for enrollments in enrollment_sets)
            == offering.capacity
        )
        assert racing_enrollments[0].course_offering_id == offering.id
        approved_request = next(
            request
            for request in stored_requests
            if request is not None and request.status is CourseSelectionStatus.APPROVED
        )
        assert racing_enrollments[0].selection_request_id == approved_request.id
        assert audit.events.count("academics.course_selection.approval_requested") == 2
        assert audit.events.count("academics.course_selection.approved") == 1
    finally:
        pending_tasks = tuple(
            task
            for task in (first_task, second_task)
            if task is not None and not task.done()
        )
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)
        await database.close()


@pytest.mark.integration
async def test_postgresql_academic_references_enforce_profile_type_tenant_and_state(
    test_database: EphemeralDatabase,
    isolation_records: IsolationRecords,
) -> None:
    """Verify People types and Academic lifecycle facts through real tenant roles."""

    organization_id = isolation_records.organization_one
    other_organization_id = isolation_records.organization_two
    suffix = uuid4().hex[:8]
    now = datetime(2026, 8, 7, 10, tzinfo=UTC)
    teacher_profile_id = uuid4()
    student_profile_id = uuid4()
    foreign_teacher_profile_id = uuid4()
    foreign_student_profile_id = uuid4()
    profile_rows = (
        (organization_id, teacher_profile_id, "teacher"),
        (organization_id, student_profile_id, "student"),
        (other_organization_id, foreign_teacher_profile_id, "teacher"),
        (other_organization_id, foreign_student_profile_id, "student"),
    )
    for tenant_id, profile_id, kind in profile_rows:
        person_id = uuid4()
        with psycopg.connect(test_database.runtime_dsn) as connection:
            _set_tenant(connection, tenant_id)
            connection.execute(
                """
                INSERT INTO people (
                    id, organization_id, given_name, family_name,
                    created_at, updated_at
                ) VALUES (%s, %s, 'Reference', 'Fixture', now(), now())
                """,
                (person_id, tenant_id),
            )
            connection.execute(
                """
                INSERT INTO person_profiles (
                    id, organization_id, person_id, kind,
                    encrypted_reference_number, title, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, NULL, NULL, now(), now())
                """,
                (profile_id, tenant_id, person_id, kind),
            )

    campus_id = uuid4()
    faculty = Faculty(
        id=uuid4(),
        organization_id=organization_id,
        campus_id=campus_id,
        code=f"REF-FAC-{suffix}",
        name=f"Reference Faculty {suffix}",
    )
    department = Department(
        id=uuid4(),
        organization_id=organization_id,
        faculty_id=faculty.id,
        code=f"REF-DEP-{suffix}",
        name=f"Reference Department {suffix}",
    )
    program = Program(
        id=uuid4(),
        organization_id=organization_id,
        department_id=department.id,
        code=f"REF-PROG-{suffix}",
        name=f"Reference Program {suffix}",
        education_mode=EducationMode.FLEXIBLE_SELECTION,
        credit_unit_label="credits",
    )
    academic_year = AcademicYear(
        id=uuid4(),
        organization_id=organization_id,
        name=f"Reference Year {suffix}",
        starts_on=date(2026, 8, 1),
        ends_on=date(2027, 7, 31),
    )
    term = Term(
        id=uuid4(),
        organization_id=organization_id,
        academic_year_id=academic_year.id,
        name=f"Reference Term {suffix}",
        starts_on=date(2026, 8, 10),
        ends_on=date(2026, 12, 20),
        enrollment_deadline=datetime(2026, 8, 20, tzinfo=UTC),
    )
    course = Course(
        id=uuid4(),
        organization_id=organization_id,
        department_id=department.id,
        code=f"REF-101-{suffix}",
        title="Reference Integrity",
        credits=Decimal("3"),
    )
    offering = CourseOffering(
        id=uuid4(),
        organization_id=organization_id,
        course_id=course.id,
        term_id=term.id,
        campus_id=campus_id,
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
        enrolled_at=now,
    )
    database = _async_runtime_database(test_database)
    academics = SQLAlchemyAcademicRepository(database)
    people = PeopleReferenceService(
        SQLAlchemyPeopleRepository(
            database=database,
            encryption_key=Fernet.generate_key().decode("ascii"),
        )
    )
    administration = AcademicAdministrationService(
        catalog=academics,
        campuses=_UnusedCampusDirectory(),
        profiles=PeopleAcademicProfileAdapter(people),
        audit=_UnusedTermClosureAudit(),
    )
    references = AcademicReferenceService(repository=academics)
    actor = TenantActorContext(
        subject_id=isolation_records.subject_one,
        organization_id=organization_id,
        membership_id=isolation_records.membership_one,
        correlation_id=f"academic-reference-{suffix}",
        permissions=frozenset(
            {ACADEMICS_STRUCTURE_MANAGE, ACADEMICS_ENROLLMENT_MANAGE}
        ),
    )
    course_enrollment_id = uuid4()
    try:
        await academics.save_faculty(faculty)
        await academics.save_department(department)
        await academics.save_program(program)
        await academics.save_academic_year(academic_year)
        await academics.save_term(term)
        await academics.save_course(course)
        await academics.save_course_offering(offering)

        await administration.assign_teacher(
            context=actor,
            assignment=TeacherAssignment(
                id=uuid4(),
                organization_id=organization_id,
                course_offering_id=offering.id,
                teacher_id=teacher_profile_id,
                role="lead",
            ),
        )
        for invalid_teacher_id in (student_profile_id, foreign_teacher_profile_id):
            with pytest.raises(NotFoundError):
                await administration.assign_teacher(
                    context=actor,
                    assignment=TeacherAssignment(
                        id=uuid4(),
                        organization_id=organization_id,
                        course_offering_id=offering.id,
                        teacher_id=invalid_teacher_id,
                        role="assistant",
                    ),
                )

        await administration.enroll_student(
            context=actor,
            enrollment=student_enrollment,
        )
        for invalid_student_id in (teacher_profile_id, foreign_student_profile_id):
            with pytest.raises(NotFoundError):
                await administration.enroll_student(
                    context=actor,
                    enrollment=replace(
                        student_enrollment,
                        id=uuid4(),
                        student_id=invalid_student_id,
                    ),
                )

        with psycopg.connect(test_database.runtime_dsn) as connection:
            _set_tenant(connection, organization_id)
            connection.execute(
                """
                INSERT INTO academic_course_enrollments (
                    id, organization_id, student_academic_enrollment_id,
                    course_offering_id, credits, status, enrolled_at,
                    selection_request_id, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, 3, 'enrolled', %s, NULL, now(), now()
                )
                """,
                (
                    course_enrollment_id,
                    organization_id,
                    student_enrollment.id,
                    offering.id,
                    now,
                ),
            )

        assert (
            await references.get_grade_target(
                organization_id=organization_id,
                course_enrollment_id=course_enrollment_id,
            )
            is not None
        )
        assert (
            await references.get_grade_target(
                organization_id=other_organization_id,
                course_enrollment_id=course_enrollment_id,
            )
            is None
        )

        with psycopg.connect(test_database.runtime_dsn) as connection:
            _set_tenant(connection, organization_id)
            connection.execute(
                """
                UPDATE academic_course_enrollments
                SET status = %s, updated_at = now()
                WHERE organization_id = %s AND id = %s
                """,
                (
                    CourseEnrollmentStatus.COMPLETED.value,
                    organization_id,
                    course_enrollment_id,
                ),
            )
        assert (
            await references.get_grade_target(
                organization_id=organization_id,
                course_enrollment_id=course_enrollment_id,
            )
            is not None
        )

        with psycopg.connect(test_database.runtime_dsn) as connection:
            _set_tenant(connection, organization_id)
            connection.execute(
                """
                UPDATE academic_course_enrollments
                SET status = %s, updated_at = now()
                WHERE organization_id = %s AND id = %s
                """,
                (
                    CourseEnrollmentStatus.WITHDRAWN.value,
                    organization_id,
                    course_enrollment_id,
                ),
            )
        assert (
            await references.get_grade_target(
                organization_id=organization_id,
                course_enrollment_id=course_enrollment_id,
            )
            is None
        )

        with psycopg.connect(test_database.runtime_dsn) as connection:
            _set_tenant(connection, organization_id)
            connection.execute(
                """
                UPDATE academic_course_enrollments
                SET status = %s, updated_at = now()
                WHERE organization_id = %s AND id = %s
                """,
                (
                    CourseEnrollmentStatus.ENROLLED.value,
                    organization_id,
                    course_enrollment_id,
                ),
            )
            connection.execute(
                """
                UPDATE academic_student_enrollments
                SET status = %s, updated_at = now()
                WHERE organization_id = %s AND id = %s
                """,
                (
                    AcademicEnrollmentStatus.WITHDRAWN.value,
                    organization_id,
                    student_enrollment.id,
                ),
            )
        assert (
            await references.get_grade_target(
                organization_id=organization_id,
                course_enrollment_id=course_enrollment_id,
            )
            is None
        )

        assert await references.admissions_target_is_open(
            organization_id=organization_id,
            program_id=program.id,
            intake_id=term.id,
        )
        assert not await references.admissions_target_is_open(
            organization_id=other_organization_id,
            program_id=program.id,
            intake_id=term.id,
        )
        closed_term = await academics.close_term(
            organization_id=organization_id,
            term_id=term.id,
        )
        assert closed_term is not None and closed_term.is_closed
        assert not await references.admissions_target_is_open(
            organization_id=organization_id,
            program_id=program.id,
            intake_id=term.id,
        )
    finally:
        await database.close()
