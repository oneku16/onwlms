"""Cookie-session self-service routes expose typed ownership-safe reads."""

from datetime import UTC
from datetime import datetime
from typing import cast
from uuid import uuid7

from fastapi import FastAPI
from fastapi import Request
from httpx import ASGITransport
from httpx import AsyncClient

from core.context import ActorContext
from core.context import TenantActorContext
from core.http import install_error_handlers
from mcp_gateway.application.owned_read_service import ActorOwnedReadService
from mcp_gateway.domain.read_models import ScheduleItem
from mcp_gateway.presentation.self_service_router import create_self_service_router

NOW = datetime(2026, 8, 5, 12, tzinfo=UTC)


class FakeOwnedReads:
    """Return a fixed safe projection through the router seam."""

    async def student_schedule(
        self,
        *,
        actor: TenantActorContext,
    ) -> list[ScheduleItem]:
        assert actor.organization_id
        return [
            ScheduleItem(
                id=uuid7(),
                title="CS101 A",
                starts_at=NOW,
                ends_at=NOW.replace(hour=13),
                room_name="R-1",
            )
        ]

    async def teacher_schedule(
        self,
        *,
        actor: TenantActorContext,
    ) -> list[ScheduleItem]:
        """Return one already ownership-filtered teaching session."""

        assert actor.organization_id
        return [
            ScheduleItem(
                id=uuid7(),
                title="CS201 B",
                starts_at=NOW.replace(hour=14),
                ends_at=NOW.replace(hour=15),
                room_name="R-2",
            )
        ]


def _app() -> FastAPI:
    actor = TenantActorContext(
        subject_id=uuid7(),
        organization_id=uuid7(),
        membership_id=uuid7(),
        correlation_id="http-correlation",
        permissions=frozenset({"academics.student.read_own"}),
    )

    async def actor_dependency(request: Request) -> ActorContext:
        del request
        return actor

    app = FastAPI()
    install_error_handlers(app)
    app.include_router(
        create_self_service_router(
            service=cast(ActorOwnedReadService, FakeOwnedReads()),
            actor_dependency=actor_dependency,
        )
    )
    return app


async def test_student_schedule_route_serializes_the_explicit_read_model() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_app()),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/self-service/student/schedule")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["title"] == "CS101 A"
    assert payload[0]["room_name"] == "R-1"
    assert payload[0]["starts_at"] == "2026-08-05T12:00:00Z"


async def test_teacher_schedule_route_serializes_only_safe_session_fields() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_app()),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/self-service/teacher/schedule")

    assert response.status_code == 200
    payload = response.json()
    assert payload == [
        {
            "id": payload[0]["id"],
            "title": "CS201 B",
            "starts_at": "2026-08-05T14:00:00Z",
            "ends_at": "2026-08-05T15:00:00Z",
            "room_name": "R-2",
        }
    ]


def test_router_exposes_only_canonical_read_paths() -> None:
    paths = set(_app().openapi()["paths"])

    assert paths == {
        "/api/v1/self-service/student/schedule",
        "/api/v1/self-service/student/profile",
        "/api/v1/self-service/student/official-grades",
        "/api/v1/self-service/student/gpa",
        "/api/v1/self-service/student/upcoming-events",
        "/api/v1/self-service/student/moodle-deadlines",
        "/api/v1/self-service/teacher/schedule",
        "/api/v1/self-service/teacher/assigned-sections",
        "/api/v1/self-service/teacher/assigned-sections/{section_id}/students",
        "/api/v1/self-service/teacher/grade-synchronization",
        "/api/v1/self-service/teacher/moodle-deadlines",
        "/api/v1/self-service/guardian/upcoming-events",
        "/api/v1/self-service/guardian/linked-students",
    }
