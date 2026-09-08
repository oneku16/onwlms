"""Real PostgreSQL serialization between term closure and official grades."""

import asyncio
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
from psycopg import sql
from sqlalchemy.engine import URL
from sqlalchemy.engine import make_url

from academic_adapters import AcademicTermClosureAdapter
from academics.application.reference_service import AcademicReferenceService
from academics.application.service import ACADEMICS_TERM_CLOSE
from academics.application.service import AcademicAdministrationService
from academics.domain.models import AcademicYear
from academics.domain.models import Term
from academics.infrastructure.repository import InMemoryCampusDirectory
from academics.infrastructure.sqlalchemy_repository import SQLAlchemyAcademicRepository
from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import ConflictError
from core.settings import AppEnvironment
from core.settings import Settings
from grading.application.service import GRADING_CLOSED_TERM_REVISE
from grading.application.service import GRADING_FINAL_RECORD
from grading.application.service import GRADING_FINAL_REVISE
from grading.application.service import OfficialGradingService
from grading.domain.models import FinalGrade
from grading.domain.models import GradeRevision
from grading.domain.models import GradeTarget
from grading.domain.models import GradingScale
from grading.domain.models import GradingScaleTemplate
from grading.domain.models import build_scale_from_template
from grading.infrastructure.repository import InMemoryExternalGradeEvidenceDirectory
from grading.infrastructure.repository import InMemoryGradeTargetDirectory
from grading.infrastructure.sqlalchemy_repository import SQLAlchemyGradingRepository
from grading.infrastructure.term_guard import SQLAlchemyTermGradeWriteGuard
from shared.database import Database


@dataclass(frozen=True, slots=True)
class EphemeralDatabase:
    """Hold disposable migration and runtime connection strings."""

    migration_dsn: str
    runtime_dsn: str


@dataclass(frozen=True, slots=True)
class FixedClock:
    """Return deterministic official-grade timestamps."""

    current: datetime

    def now(self) -> datetime:
        return self.current


class NoOpGradingAuditSink:
    """Keep the race focused on persistence without consuming the app pool."""

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
        del (
            action,
            organization_id,
            actor_subject_id,
            final_grade_id,
            correlation_id,
            after_term_closure,
            outcome,
        )

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
        del (
            action,
            organization_id,
            actor_subject_id,
            evidence_id,
            correlation_id,
            outcome,
            reason,
        )


class NoOpTermClosureAuditSink:
    """Keep Academic intent ordering without adding a second test dependency."""

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


class UnusedAcademicProfileDirectory:
    """Fail if a grading/closure race unexpectedly resolves People profiles."""

    async def teacher_profile_exists(
        self,
        *,
        organization_id: UUID,
        teacher_profile_id: UUID,
    ) -> bool:
        del organization_id, teacher_profile_id
        raise AssertionError("Term closure must not resolve teacher profiles.")

    async def student_profile_exists(
        self,
        *,
        organization_id: UUID,
        student_profile_id: UUID,
    ) -> bool:
        del organization_id, student_profile_id
        raise AssertionError("Term closure must not resolve student profiles.")


class HoldingGradingRepository(SQLAlchemyGradingRepository):
    """Pause grade persistence while the service still owns its shared guard."""

    def __init__(
        self,
        database: Database,
        *,
        held_creates: int = 0,
        hold_revision: bool = False,
    ) -> None:
        super().__init__(database)
        self._held_creates = held_creates
        self._hold_revision = hold_revision
        self._create_entries = 0
        self.all_creates_entered = asyncio.Event()
        self.revision_entered = asyncio.Event()
        self.release_creates = asyncio.Event()
        self.release_revision = asyncio.Event()

    async def create_final_grade(self, grade: FinalGrade) -> None:
        """Pause configured creates before they consume the application pool."""

        if self._create_entries < self._held_creates:
            self._create_entries += 1
            if self._create_entries == self._held_creates:
                self.all_creates_entered.set()
            await self.release_creates.wait()
        await super().create_final_grade(grade)

    async def revise_final_grade(
        self,
        *,
        grade: FinalGrade,
        expected_revision_number: int,
        revision: GradeRevision,
    ) -> None:
        """Pause one revision before it consumes the application pool."""

        if self._hold_revision:
            self._hold_revision = False
            self.revision_entered.set()
            await self.release_revision.wait()
        await super().revise_final_grade(
            grade=grade,
            expected_revision_number=expected_revision_number,
            revision=revision,
        )


@dataclass(frozen=True, slots=True)
class GradingRaceFixture:
    """Compose real Academic and Grading persistence around one tenant term."""

    organization_id: UUID
    term: Term
    scale: GradingScale
    targets: tuple[GradeTarget, ...]
    database: Database
    academic_repository: SQLAlchemyAcademicRepository
    grading_repository: HoldingGradingRepository
    academic_service: AcademicAdministrationService
    grading_service: OfficialGradingService


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
    database_name = f"ownsis_term_grading_test_{uuid4().hex}"
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
                %s, %s, 'school', 'active', 'Term Grading Race Test',
                '#112233', '#445566', 'en', 'UTC', 'school', now(), now()
            )
            """,
            (organization_id, f"term-grading-race-{organization_id.hex}"),
        )
    return organization_id


def _application_database(test_database: EphemeralDatabase) -> Database:
    """Use one bounded application connection to expose pool-starvation bugs."""

    return Database(
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


def _actor(
    *,
    organization_id: UUID,
    permissions: frozenset[str],
) -> TenantActorContext:
    return TenantActorContext(
        subject_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        correlation_id=f"term-grading-race-{uuid4()}",
        permissions=permissions,
    )


async def _race_fixture(
    *,
    test_database: EphemeralDatabase,
    target_count: int,
    held_creates: int = 0,
    hold_revision: bool = False,
) -> GradingRaceFixture:
    organization_id = _insert_organization(test_database)
    database = _application_database(test_database)
    academic_repository = SQLAlchemyAcademicRepository(database)
    grading_repository = HoldingGradingRepository(
        database,
        held_creates=held_creates,
        hold_revision=hold_revision,
    )
    academic_year = AcademicYear(
        id=uuid4(),
        organization_id=organization_id,
        name="2026-2027",
        starts_on=date(2026, 8, 1),
        ends_on=date(2027, 7, 31),
    )
    term = Term(
        id=uuid4(),
        organization_id=organization_id,
        academic_year_id=academic_year.id,
        name="Fall 2026",
        starts_on=date(2026, 8, 10),
        ends_on=date(2026, 12, 20),
        enrollment_deadline=datetime(2026, 8, 20, tzinfo=UTC),
    )
    await academic_repository.save_academic_year(academic_year)
    await academic_repository.save_term(term)

    scale = build_scale_from_template(
        scale_id=uuid4(),
        organization_id=organization_id,
        name="Official percentage",
        template=GradingScaleTemplate.PERCENTAGE,
    )
    await grading_repository.save_scale(scale)
    student_enrollment_id = uuid4()
    targets = tuple(
        GradeTarget(
            organization_id=organization_id,
            student_academic_enrollment_id=student_enrollment_id,
            course_enrollment_id=uuid4(),
            course_offering_id=uuid4(),
            term_id=term.id,
            course_id=uuid4(),
            credits=Decimal("3"),
        )
        for _ in range(target_count)
    )
    references = AcademicReferenceService(repository=academic_repository)
    academic_service = AcademicAdministrationService(
        catalog=academic_repository,
        campuses=InMemoryCampusDirectory(),
        profiles=UnusedAcademicProfileDirectory(),
        audit=NoOpTermClosureAuditSink(),
    )
    grading_service = OfficialGradingService(
        repository=grading_repository,
        targets=InMemoryGradeTargetDirectory(targets),
        terms=AcademicTermClosureAdapter(references),
        term_writes=SQLAlchemyTermGradeWriteGuard(database),
        clock=FixedClock(datetime(2026, 8, 7, 10, tzinfo=UTC)),
        audit=NoOpGradingAuditSink(),
        evidence=InMemoryExternalGradeEvidenceDirectory(),
    )
    return GradingRaceFixture(
        organization_id=organization_id,
        term=term,
        scale=scale,
        targets=targets,
        database=database,
        academic_repository=academic_repository,
        grading_repository=grading_repository,
        academic_service=academic_service,
        grading_service=grading_service,
    )


async def _cancel_unfinished(tasks: list[asyncio.Task[FinalGrade]]) -> None:
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.integration
async def test_close_cannot_commit_during_records_with_one_slot_app_pool(
    test_database: EphemeralDatabase,
) -> None:
    """Keep three guards live without exhausting a one-connection app pool."""

    fixture = await _race_fixture(
        test_database=test_database,
        target_count=3,
        held_creates=3,
    )
    grade_actor = _actor(
        organization_id=fixture.organization_id,
        permissions=frozenset({GRADING_FINAL_RECORD}),
    )
    close_actor = _actor(
        organization_id=fixture.organization_id,
        permissions=frozenset({ACADEMICS_TERM_CLOSE}),
    )
    writes = [
        asyncio.create_task(
            fixture.grading_service.record_final_grade(
                context=grade_actor,
                course_enrollment_id=target.course_enrollment_id,
                grading_scale_id=fixture.scale.id,
                raw_score=Decimal("80"),
            )
        )
        for target in fixture.targets
    ]

    try:
        await asyncio.wait_for(
            fixture.grading_repository.all_creates_entered.wait(),
            timeout=5,
        )
        with pytest.raises(ConflictError, match="being updated"):
            await asyncio.wait_for(
                fixture.academic_service.close_term(
                    context=close_actor,
                    term_id=fixture.term.id,
                    explanation="End-of-term close raced with grade recording.",
                ),
                timeout=5,
            )
        open_term = await fixture.academic_repository.get_term(
            organization_id=fixture.organization_id,
            term_id=fixture.term.id,
        )
        assert open_term is not None
        assert open_term.is_closed is False

        fixture.grading_repository.release_creates.set()
        grades = await asyncio.wait_for(asyncio.gather(*writes), timeout=5)
        closed = await asyncio.wait_for(
            fixture.academic_service.close_term(
                context=close_actor,
                term_id=fixture.term.id,
                explanation="All official grade writes completed.",
            ),
            timeout=5,
        )
        assert closed.is_closed is True
        assert len(grades) == 3
        stored = await fixture.grading_repository.list_student_final_grades(
            organization_id=fixture.organization_id,
            student_academic_enrollment_id=(
                fixture.targets[0].student_academic_enrollment_id
            ),
        )
        assert {grade.id for grade in stored} == {grade.id for grade in grades}
    finally:
        fixture.grading_repository.release_creates.set()
        await _cancel_unfinished(writes)
        await fixture.database.close()


@pytest.mark.integration
async def test_close_cannot_commit_during_revision_and_closed_rules_reapply(
    test_database: EphemeralDatabase,
) -> None:
    """Preserve revision history and reject ordinary post-close amendments."""

    fixture = await _race_fixture(
        test_database=test_database,
        target_count=1,
        hold_revision=True,
    )
    grade_actor = _actor(
        organization_id=fixture.organization_id,
        permissions=frozenset({GRADING_FINAL_RECORD, GRADING_FINAL_REVISE}),
    )
    close_actor = _actor(
        organization_id=fixture.organization_id,
        permissions=frozenset({ACADEMICS_TERM_CLOSE}),
    )
    original = await fixture.grading_service.record_final_grade(
        context=grade_actor,
        course_enrollment_id=fixture.targets[0].course_enrollment_id,
        grading_scale_id=fixture.scale.id,
        raw_score=Decimal("75"),
    )
    revision_task = asyncio.create_task(
        fixture.grading_service.revise_final_grade(
            context=grade_actor,
            final_grade_id=original.id,
            raw_score=Decimal("85"),
            explanation="Approved correction before term closure.",
            expected_revision_number=0,
        )
    )

    try:
        await asyncio.wait_for(
            fixture.grading_repository.revision_entered.wait(),
            timeout=5,
        )
        with pytest.raises(ConflictError, match="being updated"):
            await asyncio.wait_for(
                fixture.academic_service.close_term(
                    context=close_actor,
                    term_id=fixture.term.id,
                    explanation="End-of-term close raced with a correction.",
                ),
                timeout=5,
            )

        fixture.grading_repository.release_revision.set()
        revised = await asyncio.wait_for(revision_task, timeout=5)
        assert revised.revision_number == 1
        closed = await asyncio.wait_for(
            fixture.academic_service.close_term(
                context=close_actor,
                term_id=fixture.term.id,
                explanation="The protected correction completed.",
            ),
            timeout=5,
        )
        assert closed.is_closed is True

        with pytest.raises(AuthorizationError):
            await fixture.grading_service.revise_final_grade(
                context=grade_actor,
                final_grade_id=original.id,
                raw_score=Decimal("90"),
                explanation="Ordinary correction after closure.",
                expected_revision_number=1,
            )
        history = await fixture.grading_repository.list_grade_revisions(
            organization_id=fixture.organization_id,
            final_grade_id=original.id,
        )
        assert len(history) == 1
        assert history[0].after_term_closure is False

        closed_term_actor = _actor(
            organization_id=fixture.organization_id,
            permissions=frozenset({GRADING_FINAL_REVISE, GRADING_CLOSED_TERM_REVISE}),
        )
        post_close = await fixture.grading_service.revise_final_grade(
            context=closed_term_actor,
            final_grade_id=original.id,
            raw_score=Decimal("90"),
            explanation="Registrar-approved correction after closure.",
            expected_revision_number=1,
        )
        final_history = await fixture.grading_repository.list_grade_revisions(
            organization_id=fixture.organization_id,
            final_grade_id=original.id,
        )
        assert post_close.revision_number == 2
        assert [item.after_term_closure for item in final_history] == [False, True]
    finally:
        fixture.grading_repository.release_revision.set()
        if not revision_task.done():
            revision_task.cancel()
        await asyncio.gather(revision_task, return_exceptions=True)
        await fixture.database.close()


@pytest.mark.integration
async def test_postgresql_closed_initial_grade_preserves_explanation_in_history(
    test_database: EphemeralDatabase,
) -> None:
    """Persist post-closure recording evidence through later amendments."""

    fixture = await _race_fixture(
        test_database=test_database,
        target_count=1,
    )
    close_actor = _actor(
        organization_id=fixture.organization_id,
        permissions=frozenset({ACADEMICS_TERM_CLOSE}),
    )
    grade_actor = _actor(
        organization_id=fixture.organization_id,
        permissions=frozenset(
            {
                GRADING_FINAL_RECORD,
                GRADING_FINAL_REVISE,
                GRADING_CLOSED_TERM_REVISE,
            }
        ),
    )
    try:
        await fixture.academic_service.close_term(
            context=close_actor,
            term_id=fixture.term.id,
            explanation="The term is ready for controlled late finalization.",
        )
        grade = await fixture.grading_service.record_final_grade(
            context=grade_actor,
            course_enrollment_id=fixture.targets[0].course_enrollment_id,
            grading_scale_id=fixture.scale.id,
            raw_score=Decimal("80"),
            explanation="  Registrar-approved late finalization.  ",
        )
        await fixture.grading_service.revise_final_grade(
            context=grade_actor,
            final_grade_id=grade.id,
            raw_score=Decimal("90"),
            explanation="Registrar-approved correction after late finalization.",
            expected_revision_number=0,
        )

        stored = await fixture.grading_repository.get_final_grade(
            organization_id=fixture.organization_id,
            final_grade_id=grade.id,
        )
        history = await fixture.grading_service.grade_history(
            context=grade_actor,
            final_grade_id=grade.id,
        )

        assert stored is not None
        assert stored.recorded_after_term_closure is True
        assert stored.recording_explanation == ("Registrar-approved late finalization.")
        assert history.recorded_after_term_closure is True
        assert history.recording_explanation == (
            "Registrar-approved late finalization."
        )
        assert len(history.revisions) == 1
        assert history.revisions[0].after_term_closure is True
    finally:
        await fixture.database.close()


@pytest.mark.integration
async def test_cancelled_shared_guard_releases_the_term_for_closure(
    test_database: EphemeralDatabase,
) -> None:
    """Rollback and close the dedicated guard connection on cancellation."""

    fixture = await _race_fixture(
        test_database=test_database,
        target_count=1,
    )
    guard = SQLAlchemyTermGradeWriteGuard(fixture.database)
    entered = asyncio.Event()
    remain_held = asyncio.Event()

    async def hold_until_cancelled() -> None:
        async with guard.hold_grade_write(
            organization_id=fixture.organization_id,
            term_id=fixture.term.id,
        ):
            entered.set()
            await remain_held.wait()

    guard_task = asyncio.create_task(hold_until_cancelled())
    close_actor = _actor(
        organization_id=fixture.organization_id,
        permissions=frozenset({ACADEMICS_TERM_CLOSE}),
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        guard_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await guard_task
        closed = await asyncio.wait_for(
            fixture.academic_service.close_term(
                context=close_actor,
                term_id=fixture.term.id,
                explanation="Cancellation released the grading guard.",
            ),
            timeout=5,
        )
        assert closed.is_closed is True
    finally:
        if not guard_task.done():
            guard_task.cancel()
        await asyncio.gather(guard_task, return_exceptions=True)
        await fixture.database.close()


@pytest.mark.integration
async def test_same_term_lock_input_in_different_tenants_does_not_contend(
    test_database: EphemeralDatabase,
) -> None:
    """Include organization identity in both sides of the advisory-lock key."""

    first = await _race_fixture(
        test_database=test_database,
        target_count=1,
    )
    second = await _race_fixture(
        test_database=test_database,
        target_count=1,
    )
    first_guard = SQLAlchemyTermGradeWriteGuard(first.database)
    second_close_actor = _actor(
        organization_id=second.organization_id,
        permissions=frozenset({ACADEMICS_TERM_CLOSE}),
    )
    try:
        async with first_guard.hold_grade_write(
            organization_id=first.organization_id,
            term_id=second.term.id,
        ):
            second_closed = await asyncio.wait_for(
                second.academic_service.close_term(
                    context=second_close_actor,
                    term_id=second.term.id,
                    explanation="The other tenant's guard must not interfere.",
                ),
                timeout=5,
            )
        first_term = await first.academic_repository.get_term(
            organization_id=first.organization_id,
            term_id=first.term.id,
        )
        assert second_closed.is_closed is True
        assert first_term is not None
        assert first_term.is_closed is False
    finally:
        await first.database.close()
        await second.database.close()
