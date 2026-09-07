"""Teacher availability domain, application, repository, and API tests."""

from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from uuid import UUID
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport
from httpx import AsyncClient

from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import ConflictError
from core.errors import NotFoundError
from core.http import install_error_handlers
from core.identifiers import new_uuid7
from identity.presentation.dependencies import require_actor
from identity.presentation.dependencies import require_csrf
from scheduling.application.availability_service import TeacherAvailabilityService
from scheduling.application.service import SCHEDULING_READ
from scheduling.application.service import SCHEDULING_SESSION_MANAGE
from scheduling.domain.exceptions import SchedulingRuleError
from scheduling.domain.models import TeacherAvailabilityWindow
from scheduling.infrastructure.repository import InMemorySchedulingAuditSink
from scheduling.infrastructure.repository import InMemoryTeacherAvailabilityRepository
from scheduling.presentation.router import router


@dataclass(frozen=True, slots=True)
class _TeacherReferences:
    """Resolve exact tenant teacher profile fixtures."""

    profiles_by_organization: dict[UUID, frozenset[UUID]]

    async def existing_teacher_profile_ids(
        self,
        *,
        organization_id: UUID,
        teacher_profile_ids: frozenset[UUID],
    ) -> frozenset[UUID]:
        """Return the intersection for exactly one organization."""

        return teacher_profile_ids & self.profiles_by_organization.get(
            organization_id,
            frozenset(),
        )


def _context(
    organization_id: UUID,
    *permissions: str,
) -> TenantActorContext:
    return TenantActorContext(
        subject_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        correlation_id="teacher-availability-test",
        permissions=frozenset(permissions),
    )


def _window(
    *,
    organization_id: UUID,
    teacher_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
) -> TeacherAvailabilityWindow:
    return TeacherAvailabilityWindow(
        id=new_uuid7(),
        organization_id=organization_id,
        teacher_id=teacher_id,
        starts_at=starts_at,
        ends_at=ends_at,
    )


@pytest.mark.parametrize(
    ("starts_at", "ends_at"),
    [
        (
            datetime(2026, 8, 10, 8),
            datetime(2026, 8, 10, 9),
        ),
        (
            datetime(2026, 8, 10, 8, tzinfo=timezone(timedelta(hours=1))),
            datetime(2026, 8, 10, 9, tzinfo=timezone(timedelta(hours=1))),
        ),
        (
            datetime(2026, 8, 10, 8, tzinfo=UTC),
            datetime(2026, 8, 10, 8, tzinfo=UTC),
        ),
        (
            datetime(2026, 8, 10, 8, tzinfo=UTC),
            datetime(2027, 8, 16, 8, tzinfo=UTC),
        ),
    ],
)
def test_window_requires_bounded_increasing_utc_interval(
    starts_at: datetime,
    ends_at: datetime,
) -> None:
    with pytest.raises(SchedulingRuleError):
        _window(
            organization_id=uuid4(),
            teacher_id=uuid4(),
            starts_at=starts_at,
            ends_at=ends_at,
        )


async def test_service_rejects_unknown_and_wrong_tenant_teacher_profiles() -> None:
    organization_id = uuid4()
    other_organization_id = uuid4()
    teacher_id = uuid4()
    wrong_tenant_teacher_id = uuid4()
    unknown_teacher_id = uuid4()
    repository = InMemoryTeacherAvailabilityRepository()
    service = TeacherAvailabilityService(
        repository,
        _TeacherReferences(
            {
                organization_id: frozenset({teacher_id}),
                other_organization_id: frozenset({wrong_tenant_teacher_id}),
            }
        ),
        InMemorySchedulingAuditSink(),
    )
    actor = _context(organization_id, SCHEDULING_SESSION_MANAGE)
    starts_at = datetime(2026, 8, 10, 8, tzinfo=UTC)

    created = await service.create_window(
        context=actor,
        window=_window(
            organization_id=organization_id,
            teacher_id=teacher_id,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=2),
        ),
    )

    assert created.teacher_id == teacher_id
    for invalid_teacher_id in (unknown_teacher_id, wrong_tenant_teacher_id):
        with pytest.raises(NotFoundError, match="Teacher profile"):
            await service.create_window(
                context=actor,
                window=_window(
                    organization_id=organization_id,
                    teacher_id=invalid_teacher_id,
                    starts_at=starts_at,
                    ends_at=starts_at + timedelta(hours=1),
                ),
            )

    stored = await repository.list_constraint_windows(
        organization_id=organization_id,
        teacher_ids=frozenset(
            {teacher_id, unknown_teacher_id, wrong_tenant_teacher_id}
        ),
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=3),
    )
    assert {window.teacher_id for window in stored} == {teacher_id}


async def test_constraint_query_merges_windows_and_ignores_orphaned_teacher() -> None:
    organization_id = uuid4()
    teacher_id = uuid4()
    orphaned_teacher_id = uuid4()
    starts_at = datetime(2026, 8, 10, 8, tzinfo=UTC)
    repository = InMemoryTeacherAvailabilityRepository()
    service = TeacherAvailabilityService(
        repository,
        _TeacherReferences({organization_id: frozenset({teacher_id})}),
        InMemorySchedulingAuditSink(),
    )
    for teacher, start_delta, end_delta in (
        (teacher_id, timedelta(), timedelta(hours=1)),
        (teacher_id, timedelta(hours=1), timedelta(hours=2)),
        (teacher_id, timedelta(hours=1, minutes=30), timedelta(hours=3)),
        (orphaned_teacher_id, timedelta(), timedelta(hours=3)),
    ):
        await repository.create_window(
            _window(
                organization_id=organization_id,
                teacher_id=teacher,
                starts_at=starts_at + start_delta,
                ends_at=starts_at + end_delta,
            )
        )

    availability = await service.availability_for_constraints(
        organization_id=organization_id,
        teacher_ids=frozenset({teacher_id, orphaned_teacher_id}),
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=4),
    )
    by_teacher = {entry.teacher_id: entry for entry in availability}

    assert len(by_teacher[teacher_id].windows) == 1
    assert by_teacher[teacher_id].windows[0].starts_at == starts_at
    assert by_teacher[teacher_id].windows[0].ends_at == starts_at + timedelta(hours=3)
    assert by_teacher[orphaned_teacher_id].windows == ()


async def test_repository_pages_by_overlap_and_enforces_exact_uniqueness() -> None:
    organization_id = uuid4()
    other_organization_id = uuid4()
    teacher_id = uuid4()
    starts_at = datetime(2026, 8, 10, 8, tzinfo=UTC)
    repository = InMemoryTeacherAvailabilityRepository()
    first = _window(
        organization_id=organization_id,
        teacher_id=teacher_id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
    )
    second = _window(
        organization_id=organization_id,
        teacher_id=teacher_id,
        starts_at=starts_at + timedelta(hours=2),
        ends_at=starts_at + timedelta(hours=3),
    )
    other_tenant = _window(
        organization_id=other_organization_id,
        teacher_id=teacher_id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=3),
    )
    for window in (second, other_tenant, first):
        await repository.create_window(window)

    page = await repository.list_windows_page(
        organization_id=organization_id,
        teacher_id=teacher_id,
        starts_at=starts_at + timedelta(minutes=30),
        ends_at=starts_at + timedelta(hours=3),
        limit=1,
        offset=1,
    )

    assert page == (second,)
    with pytest.raises(ConflictError):
        await repository.create_window(
            _window(
                organization_id=organization_id,
                teacher_id=teacher_id,
                starts_at=first.starts_at,
                ends_at=first.ends_at,
            )
        )
    assert not await repository.delete_window(
        organization_id=other_organization_id,
        window_id=first.id,
    )
    assert await repository.delete_window(
        organization_id=organization_id,
        window_id=first.id,
    )


async def test_service_enforces_existing_permissions_and_tenant_scope() -> None:
    organization_id = uuid4()
    other_organization_id = uuid4()
    teacher_id = uuid4()
    starts_at = datetime(2026, 8, 10, 8, tzinfo=UTC)
    repository = InMemoryTeacherAvailabilityRepository()
    service = TeacherAvailabilityService(
        repository,
        _TeacherReferences({organization_id: frozenset({teacher_id})}),
        InMemorySchedulingAuditSink(),
    )
    window = _window(
        organization_id=organization_id,
        teacher_id=teacher_id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
    )

    with pytest.raises(AuthorizationError):
        await service.create_window(
            context=_context(organization_id, SCHEDULING_READ),
            window=window,
        )
    with pytest.raises(NotFoundError):
        await service.create_window(
            context=_context(other_organization_id, SCHEDULING_SESSION_MANAGE),
            window=window,
        )
    await service.create_window(
        context=_context(organization_id, SCHEDULING_SESSION_MANAGE),
        window=window,
    )
    listed = await service.list_windows(
        context=_context(organization_id, SCHEDULING_READ),
        teacher_id=None,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=2),
        limit=100,
        offset=0,
    )
    assert listed == (window,)
    with pytest.raises(NotFoundError):
        await service.delete_window(
            context=_context(other_organization_id, SCHEDULING_SESSION_MANAGE),
            window_id=window.id,
        )


async def test_availability_mutations_record_intent_then_success() -> None:
    organization_id = uuid4()
    teacher_id = uuid4()
    starts_at = datetime(2026, 8, 10, 8, tzinfo=UTC)
    repository = InMemoryTeacherAvailabilityRepository()
    audit = InMemorySchedulingAuditSink()
    service = TeacherAvailabilityService(
        repository,
        _TeacherReferences({organization_id: frozenset({teacher_id})}),
        audit,
    )
    actor = _context(organization_id, SCHEDULING_SESSION_MANAGE)
    window = _window(
        organization_id=organization_id,
        teacher_id=teacher_id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
    )

    await service.create_window(context=actor, window=window)
    await service.delete_window(context=actor, window_id=window.id)

    assert [(event[0], event[-1]) for event in audit.events] == [
        ("scheduling.teacher_availability.create.intent", "intent_recorded"),
        ("scheduling.teacher_availability.create.succeeded", "succeeded"),
        ("scheduling.teacher_availability.delete.intent", "intent_recorded"),
        ("scheduling.teacher_availability.delete.succeeded", "succeeded"),
    ]


async def test_api_uses_uuidv7_permissions_and_csrf_for_mutations() -> None:
    organization_id = uuid4()
    teacher_id = uuid4()
    starts_at = datetime(2026, 8, 10, 8, tzinfo=UTC)
    service = TeacherAvailabilityService(
        InMemoryTeacherAvailabilityRepository(),
        _TeacherReferences({organization_id: frozenset({teacher_id})}),
        InMemorySchedulingAuditSink(),
    )
    actor = _context(
        organization_id,
        SCHEDULING_READ,
        SCHEDULING_SESSION_MANAGE,
    )
    csrf_calls = 0

    async def actor_dependency() -> TenantActorContext:
        return actor

    async def csrf_dependency() -> None:
        nonlocal csrf_calls
        csrf_calls += 1

    app = FastAPI()
    app.state.teacher_availability_service = service
    install_error_handlers(app)
    app.include_router(router)
    app.dependency_overrides[require_actor] = actor_dependency
    app.dependency_overrides[require_csrf] = csrf_dependency

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        created = await client.post(
            "/api/v1/scheduling/teacher-availability",
            json={
                "teacher_id": str(teacher_id),
                "starts_at": starts_at.isoformat(),
                "ends_at": (starts_at + timedelta(hours=2)).isoformat(),
            },
        )
        listed = await client.get(
            "/api/v1/scheduling/teacher-availability",
            params={
                "starts_at": starts_at.isoformat(),
                "ends_at": (starts_at + timedelta(hours=3)).isoformat(),
            },
        )
        deleted = await client.delete(
            f"/api/v1/scheduling/teacher-availability/{created.json()['id']}",
        )

    assert created.status_code == 201
    assert UUID(created.json()["id"]).version == 7
    assert created.json()["teacher_id"] == str(teacher_id)
    assert listed.status_code == 200
    assert listed.json() == [created.json()]
    assert deleted.status_code == 204
    assert csrf_calls == 2
