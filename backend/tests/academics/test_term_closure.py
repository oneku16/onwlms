"""One-way academic term closure behavior across owned boundaries."""

from dataclasses import dataclass
from datetime import UTC
from datetime import date
from datetime import datetime
from uuid import UUID
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport
from httpx import AsyncClient

from academics.application.service import ACADEMICS_TERM_CLOSE
from academics.application.service import AcademicAdministrationService
from academics.domain.exceptions import AcademicRuleError
from academics.domain.models import Term
from academics.infrastructure.repository import InMemoryAcademicRepository
from academics.infrastructure.repository import InMemoryCampusDirectory
from academics.presentation.router import router
from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import NotFoundError
from core.http import install_error_handlers
from identity.presentation.dependencies import require_actor
from identity.presentation.dependencies import require_csrf


@dataclass(frozen=True, slots=True)
class RecordedTermClosureIntent:
    organization_id: UUID
    actor_subject_id: UUID
    term_id: UUID
    correlation_id: str
    reason: str


class RecordingTermClosureAuditSink:
    """Capture closure intent or simulate an unavailable audit boundary."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[RecordedTermClosureIntent] = []

    async def record_term_closure_intent(
        self,
        *,
        organization_id: UUID,
        actor_subject_id: UUID,
        term_id: UUID,
        correlation_id: str,
        reason: str,
    ) -> None:
        if self.fail:
            raise RuntimeError("Audit is unavailable.")
        self.events.append(
            RecordedTermClosureIntent(
                organization_id=organization_id,
                actor_subject_id=actor_subject_id,
                term_id=term_id,
                correlation_id=correlation_id,
                reason=reason,
            )
        )


class UnusedAcademicProfileDirectory:
    """Fail loudly if term closure unexpectedly resolves a People profile."""

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


class FailingCloseAcademicRepository(InMemoryAcademicRepository):
    """Fail the catalog transaction after closure intent is recorded."""

    async def close_term(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> Term | None:
        del organization_id, term_id
        raise RuntimeError("Catalog write failed.")


@dataclass(frozen=True, slots=True)
class TermClosureFixture:
    organization_id: UUID
    repository: InMemoryAcademicRepository
    audit: RecordingTermClosureAuditSink
    service: AcademicAdministrationService
    term: Term
    actor: TenantActorContext


def _term(*, organization_id: UUID, term_id: UUID | None = None) -> Term:
    return Term(
        id=term_id or uuid4(),
        organization_id=organization_id,
        academic_year_id=uuid4(),
        name="Fall 2026",
        starts_on=date(2026, 8, 10),
        ends_on=date(2026, 12, 20),
        enrollment_deadline=datetime(2026, 8, 20, tzinfo=UTC),
    )


def _actor(
    *,
    organization_id: UUID,
    permissions: frozenset[str] = frozenset({ACADEMICS_TERM_CLOSE}),
) -> TenantActorContext:
    return TenantActorContext(
        subject_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        correlation_id="term-close-correlation",
        permissions=permissions,
    )


async def _fixture(
    *,
    repository: InMemoryAcademicRepository | None = None,
    audit: RecordingTermClosureAuditSink | None = None,
) -> TermClosureFixture:
    organization_id = uuid4()
    repository = repository or InMemoryAcademicRepository()
    audit = audit or RecordingTermClosureAuditSink()
    term = _term(organization_id=organization_id)
    await repository.save_term(term)
    return TermClosureFixture(
        organization_id=organization_id,
        repository=repository,
        audit=audit,
        service=AcademicAdministrationService(
            catalog=repository,
            campuses=InMemoryCampusDirectory(),
            profiles=UnusedAcademicProfileDirectory(),
            audit=audit,
        ),
        term=term,
        actor=_actor(organization_id=organization_id),
    )


def test_term_close_is_one_way_and_idempotent() -> None:
    term = _term(organization_id=uuid4())

    closed = term.close()

    assert closed.is_closed is True
    assert term.is_closed is False
    assert closed.close() is closed


async def test_in_memory_repository_closes_only_the_exact_tenant_term() -> None:
    repository = InMemoryAcademicRepository()
    organization_id = uuid4()
    term = _term(organization_id=organization_id)
    await repository.save_term(term)

    assert (
        await repository.close_term(
            organization_id=uuid4(),
            term_id=term.id,
        )
        is None
    )
    assert (
        await repository.get_term(
            organization_id=organization_id,
            term_id=term.id,
        )
        == term
    )

    first = await repository.close_term(
        organization_id=organization_id,
        term_id=term.id,
    )
    second = await repository.close_term(
        organization_id=organization_id,
        term_id=term.id,
    )

    assert first is not None and first.is_closed is True
    assert second is first


async def test_service_records_minimized_intent_before_closing_term() -> None:
    fixture = await _fixture()

    result = await fixture.service.close_term(
        context=fixture.actor,
        term_id=fixture.term.id,
        explanation="  Final grades have been approved.  ",
    )

    assert result.is_closed is True
    assert fixture.audit.events == [
        RecordedTermClosureIntent(
            organization_id=fixture.organization_id,
            actor_subject_id=fixture.actor.subject_id,
            term_id=fixture.term.id,
            correlation_id=fixture.actor.correlation_id,
            reason="Final grades have been approved.",
        )
    ]


async def test_service_requires_explicit_term_close_permission() -> None:
    fixture = await _fixture()
    unauthorized = _actor(
        organization_id=fixture.organization_id,
        permissions=frozenset(),
    )

    with pytest.raises(AuthorizationError):
        await fixture.service.close_term(
            context=unauthorized,
            term_id=fixture.term.id,
            explanation="Attempted closure",
        )

    assert fixture.audit.events == []
    assert (
        await fixture.repository.get_term(
            organization_id=fixture.organization_id,
            term_id=fixture.term.id,
        )
        == fixture.term
    )


@pytest.mark.parametrize("explanation", ["   ", "x" * 501])
async def test_service_requires_a_bounded_explanation(explanation: str) -> None:
    fixture = await _fixture()

    with pytest.raises(AcademicRuleError):
        await fixture.service.close_term(
            context=fixture.actor,
            term_id=fixture.term.id,
            explanation=explanation,
        )

    assert fixture.audit.events == []
    assert (
        await fixture.repository.get_term(
            organization_id=fixture.organization_id,
            term_id=fixture.term.id,
        )
        == fixture.term
    )


async def test_service_does_not_reveal_a_cross_tenant_term() -> None:
    fixture = await _fixture()
    other_tenant_actor = _actor(organization_id=uuid4())

    with pytest.raises(NotFoundError):
        await fixture.service.close_term(
            context=other_tenant_actor,
            term_id=fixture.term.id,
            explanation="Close another tenant's term",
        )

    assert fixture.audit.events == []
    assert (
        await fixture.repository.get_term(
            organization_id=fixture.organization_id,
            term_id=fixture.term.id,
        )
        == fixture.term
    )


async def test_repeated_close_returns_current_state_without_duplicate_intent() -> None:
    fixture = await _fixture()

    first = await fixture.service.close_term(
        context=fixture.actor,
        term_id=fixture.term.id,
        explanation="Approved first closure",
    )
    second = await fixture.service.close_term(
        context=fixture.actor,
        term_id=fixture.term.id,
        explanation="Safe retry",
    )

    assert first.is_closed is True
    assert second == first
    assert len(fixture.audit.events) == 1


async def test_audit_failure_prevents_catalog_closure() -> None:
    fixture = await _fixture(audit=RecordingTermClosureAuditSink(fail=True))

    with pytest.raises(RuntimeError, match="Audit is unavailable"):
        await fixture.service.close_term(
            context=fixture.actor,
            term_id=fixture.term.id,
            explanation="Approved closure",
        )

    assert (
        await fixture.repository.get_term(
            organization_id=fixture.organization_id,
            term_id=fixture.term.id,
        )
        == fixture.term
    )


async def test_catalog_failure_leaves_intent_without_claiming_closure() -> None:
    repository = FailingCloseAcademicRepository()
    fixture = await _fixture(repository=repository)

    with pytest.raises(RuntimeError, match="Catalog write failed"):
        await fixture.service.close_term(
            context=fixture.actor,
            term_id=fixture.term.id,
            explanation="Approved closure",
        )

    assert len(fixture.audit.events) == 1
    assert (
        await repository.get_term(
            organization_id=fixture.organization_id,
            term_id=fixture.term.id,
        )
        == fixture.term
    )


async def test_close_term_api_is_typed_and_csrf_protected() -> None:
    fixture = await _fixture()
    csrf_calls = 0

    async def actor_dependency() -> TenantActorContext:
        return fixture.actor

    async def csrf_dependency() -> None:
        nonlocal csrf_calls
        csrf_calls += 1

    app = FastAPI()
    app.state.academic_administration_service = fixture.service
    install_error_handlers(app)
    app.include_router(router)
    app.dependency_overrides[require_actor] = actor_dependency
    app.dependency_overrides[require_csrf] = csrf_dependency

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            f"/api/v1/academics/terms/{fixture.term.id}/close",
            json={"explanation": "  Registrar approval  "},
        )

    assert response.status_code == 200
    assert response.json()["id"] == str(fixture.term.id)
    assert response.json()["is_closed"] is True
    assert csrf_calls == 1
    assert fixture.audit.events[0].reason == "Registrar approval"


async def test_close_term_api_rejects_an_overlong_explanation() -> None:
    fixture = await _fixture()

    async def actor_dependency() -> TenantActorContext:
        return fixture.actor

    async def csrf_dependency() -> None:
        return None

    app = FastAPI()
    app.state.academic_administration_service = fixture.service
    install_error_handlers(app)
    app.include_router(router)
    app.dependency_overrides[require_actor] = actor_dependency
    app.dependency_overrides[require_csrf] = csrf_dependency

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            f"/api/v1/academics/terms/{fixture.term.id}/close",
            json={"explanation": "x" * 501},
        )

    assert response.status_code == 422
    assert fixture.audit.events == []
    assert (
        await fixture.repository.get_term(
            organization_id=fixture.organization_id,
            term_id=fixture.term.id,
        )
        == fixture.term
    )
