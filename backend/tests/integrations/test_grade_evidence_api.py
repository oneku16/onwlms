"""HTTP contracts for signed grade-event ingress, evidence reads, and runs."""

import json
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from uuid import UUID
from uuid import uuid7

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi import Request
from httpx import ASGITransport
from httpx import AsyncClient

from core.context import ActorContext
from core.context import PlatformActorContext
from core.context import TenantActorContext
from core.field_encryption import FieldCipher
from core.http import install_error_handlers
from integrations.application.ports import MoodleGateway
from integrations.application.reconciliation_service import GRADE_EVIDENCE_RECONCILE
from integrations.application.reconciliation_service import (
    MoodleGradeReconciliationService,
)
from integrations.application.service import GRADE_EVIDENCE_READ
from integrations.application.service import MoodleIntegrationService
from integrations.domain.grade_events import GRADE_EVENT_SIGNATURE_HEADER
from integrations.domain.grade_events import GRADE_EVENT_TIMESTAMP_HEADER
from integrations.domain.grade_events import compute_grade_event_signature
from integrations.domain.moodle import MoodleCourseGradeObservation
from integrations.domain.moodle import MoodleDeadlineEvidence
from integrations.infrastructure.grade_receiver import (
    ReviewRequiredGradeEvidenceReceiver,
)
from integrations.infrastructure.memory import InMemoryMoodleIntegrationRepository
from integrations.infrastructure.memory import InMemoryMoodleReconciliationRunRepository
from integrations.presentation.router import create_integrations_router

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
SECRET = "tenant-grade-event-secret-with-32-plus-characters"


@dataclass(frozen=True, slots=True)
class FixedClock:
    current: datetime

    def now(self) -> datetime:
        return self.current


class FakeMoodleGateway:
    """Serve one mapped course total for reconciliation routes."""

    async def ensure_user(
        self,
        *,
        external_username: str,
        display_name: str,
        email: str | None,
        idempotency_key: str,
    ) -> str:
        raise AssertionError("not used")

    async def ensure_course(
        self,
        *,
        course_code: str,
        course_title: str,
        idempotency_key: str,
    ) -> str:
        raise AssertionError("not used")

    async def set_enrollment(
        self,
        *,
        external_user_id: str,
        external_course_id: str,
        role: str,
        active: bool,
        idempotency_key: str,
    ) -> None:
        raise AssertionError("not used")

    async def list_deadlines(
        self,
        *,
        external_user_id: str,
    ) -> list[MoodleDeadlineEvidence]:
        raise AssertionError("not used")

    async def list_course_grades(
        self,
        *,
        external_course_id: str,
    ) -> list[MoodleCourseGradeObservation]:
        if external_course_id != "course-11":
            return []
        return [
            MoodleCourseGradeObservation(
                external_user_id="user-7",
                grade_item_id="900",
                grade_raw="91",
                graded_at=NOW,
                observed_at=NOW,
                source_version="moodle-webservice-v1",
            )
        ]


class FakeGatewayFactory:
    async def create_for_organization(
        self,
        organization_id: UUID,
    ) -> MoodleGateway:
        del organization_id
        return FakeMoodleGateway()


class FakeTermOfferings:
    def __init__(self, offerings: dict[tuple[UUID, UUID], frozenset[UUID]]) -> None:
        self._offerings = offerings

    async def list_course_offering_ids(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> frozenset[UUID] | None:
        return self._offerings.get((organization_id, term_id))


class NoOpAuditSink:
    async def record_moodle_configuration_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        correlation_id: str,
        outcome: str,
    ) -> None:
        del action, organization_id, actor_subject_id, correlation_id, outcome

    async def record_grade_evidence_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID | None,
        evidence_reference: str,
        correlation_id: str,
        outcome: str,
    ) -> None:
        del action, organization_id, actor_subject_id, evidence_reference
        del correlation_id, outcome

    async def record_grade_reconciliation_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        run_id: UUID,
        correlation_id: str,
        outcome: str,
    ) -> None:
        del action, organization_id, actor_subject_id, run_id, correlation_id
        del outcome


@dataclass(frozen=True, slots=True)
class ApiFixture:
    organization_id: UUID
    term_id: UUID
    offering_id: UUID
    person_id: UUID
    repository: InMemoryMoodleIntegrationRepository
    moodle: MoodleIntegrationService
    reconciliation: MoodleGradeReconciliationService


def _tenant_actor(organization_id: UUID) -> TenantActorContext:
    return TenantActorContext(
        subject_id=uuid7(),
        organization_id=organization_id,
        membership_id=uuid7(),
        correlation_id="api-test",
        permissions=frozenset(
            {
                "integrations.configure",
                "integrations.read",
                GRADE_EVIDENCE_READ,
                GRADE_EVIDENCE_RECONCILE,
            }
        ),
    )


def _fixture() -> ApiFixture:
    organization_id = uuid7()
    term_id = uuid7()
    offering_id = uuid7()
    person_id = uuid7()
    repository = InMemoryMoodleIntegrationRepository()
    clock = FixedClock(NOW)
    audit = NoOpAuditSink()
    moodle = MoodleIntegrationService(
        repository=repository,
        gateway_factory=FakeGatewayFactory(),
        grade_receiver=ReviewRequiredGradeEvidenceReceiver(),
        cipher=FieldCipher(Fernet.generate_key().decode("ascii")),
        audit=audit,
        clock=clock,
    )
    reconciliation = MoodleGradeReconciliationService(
        repository=repository,
        runs=InMemoryMoodleReconciliationRunRepository(),
        intake=moodle,
        gateway_factory=FakeGatewayFactory(),
        offerings=FakeTermOfferings(
            {(organization_id, term_id): frozenset({offering_id})}
        ),
        clock=clock,
        audit=audit,
    )
    return ApiFixture(
        organization_id=organization_id,
        term_id=term_id,
        offering_id=offering_id,
        person_id=person_id,
        repository=repository,
        moodle=moodle,
        reconciliation=reconciliation,
    )


def _application(fixture: ApiFixture, actor: ActorContext) -> FastAPI:
    async def actor_dependency(request: Request) -> ActorContext:
        del request
        return actor

    async def csrf_dependency() -> None:
        return None

    app = FastAPI()
    install_error_handlers(app)
    app.state.moodle_service = fixture.moodle
    app.state.moodle_reconciliation_service = fixture.reconciliation
    app.include_router(
        create_integrations_router(
            actor_dependency=actor_dependency,
            csrf_dependency=csrf_dependency,
        )
    )
    return app


def _event_body(fixture: ApiFixture) -> bytes:
    return json.dumps(
        {
            "external_event_id": "moodle:grade:77",
            "course_offering_id": str(fixture.offering_id),
            "student_person_id": str(fixture.person_id),
            "grade_value": "87.5",
            "observed_at": NOW.isoformat(),
        }
    ).encode("utf-8")


def _headers(
    body: bytes, *, secret: str = SECRET, at: datetime = NOW
) -> dict[str, str]:
    timestamp = str(int(at.timestamp()))
    return {
        GRADE_EVENT_TIMESTAMP_HEADER: timestamp,
        GRADE_EVENT_SIGNATURE_HEADER: compute_grade_event_signature(
            secret=secret,
            timestamp=timestamp,
            body=body,
        ),
        "content-type": "application/json",
    }


async def test_signed_event_ingress_then_authorized_evidence_reads() -> None:
    fixture = _fixture()
    app = _application(fixture, _tenant_actor(fixture.organization_id))
    ingress = f"/api/v1/integrations/moodle/grade-events/{fixture.organization_id}"
    body = _event_body(fixture)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        before_secret = await client.post(ingress, content=body, headers=_headers(body))
        configured = await client.put(
            "/api/v1/integrations/moodle/configuration",
            json={"base_url": "https://moodle.example.edu", "token": "secret"},
        )
        secret_set = await client.put(
            "/api/v1/integrations/moodle/grade-event-secret",
            json={"secret": SECRET},
        )
        accepted = await client.post(ingress, content=body, headers=_headers(body))
        replay = await client.post(ingress, content=body, headers=_headers(body))
        unsigned = await client.post(ingress, content=body)
        forged = await client.post(
            ingress,
            content=body,
            headers=_headers(body, secret="another-secret-with-at-least-32-chars!!"),
        )
        stale = await client.post(
            ingress,
            content=body,
            headers=_headers(body, at=NOW - timedelta(minutes=10)),
        )
        bad_payload = b'{"external_event_id": "x", "surprise": 1}'
        malformed = await client.post(
            ingress,
            content=bad_payload,
            headers=_headers(bad_payload),
        )
        listed = await client.get(
            "/api/v1/integrations/moodle/grade-evidence",
            params={"status": "pending"},
        )
        evidence_id = listed.json()[0]["id"]
        single = await client.get(
            f"/api/v1/integrations/moodle/grade-evidence/{evidence_id}"
        )
        missing = await client.get(
            f"/api/v1/integrations/moodle/grade-evidence/{uuid7()}"
        )
        status = await client.get("/api/v1/integrations/moodle/status")

    assert before_secret.status_code == 401
    assert configured.status_code == 200
    assert configured.json()["grade_events_configured"] is False
    assert secret_set.status_code == 200
    assert secret_set.json()["grade_events_configured"] is True
    assert accepted.status_code == 202
    assert accepted.json() == {
        "external_event_id": "moodle:grade:77",
        "duplicate": False,
        "status": "pending",
    }
    assert replay.status_code == 202
    assert replay.json()["duplicate"] is True
    assert unsigned.status_code == 401
    assert forged.status_code == 401
    assert stale.status_code == 401
    assert malformed.status_code == 422
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["status"] == "pending"
    assert listed.json()[0]["reason_code"] == "review_required"
    assert listed.json()[0]["grade_value"] == "87.5"
    assert listed.json()[0]["course_offering_id"] == str(fixture.offering_id)
    assert "resolved_by" not in listed.json()[0]
    assert single.status_code == 200
    assert single.json()["id"] == evidence_id
    assert missing.status_code == 404
    assert status.json()["grade_events_configured"] is True


async def test_reconciliation_routes_report_bounded_counts() -> None:
    fixture = _fixture()
    await fixture.repository.configure(
        organization_id=fixture.organization_id,
        base_url="https://moodle.example.edu",
        encrypted_token="protected",
    )
    await fixture.repository.put_mapping(
        organization_id=fixture.organization_id,
        entity_type="course_offering",
        entity_id=fixture.offering_id,
        external_id="course-11",
    )
    await fixture.repository.put_mapping(
        organization_id=fixture.organization_id,
        entity_type="person",
        entity_id=fixture.person_id,
        external_id="user-7",
    )
    app = _application(fixture, _tenant_actor(fixture.organization_id))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        started = await client.post(
            "/api/v1/integrations/moodle/grade-reconciliations",
            json={"term_id": str(fixture.term_id)},
        )
        unknown_term = await client.post(
            "/api/v1/integrations/moodle/grade-reconciliations",
            json={"term_id": str(uuid7())},
        )
        listed = await client.get("/api/v1/integrations/moodle/grade-reconciliations")
        single = await client.get(
            f"/api/v1/integrations/moodle/grade-reconciliations/{started.json()['id']}"
        )
        missing = await client.get(
            f"/api/v1/integrations/moodle/grade-reconciliations/{uuid7()}"
        )
        evidence = await client.get("/api/v1/integrations/moodle/grade-evidence")

    assert started.status_code == 201
    assert started.json()["status"] == "succeeded"
    assert started.json()["offering_count"] == 1
    assert started.json()["observed_count"] == 1
    assert started.json()["new_evidence_count"] == 1
    assert started.json()["unmapped_user_count"] == 0
    assert started.json()["term_id"] == str(fixture.term_id)
    assert unknown_term.status_code == 404
    assert listed.status_code == 200
    assert [run["id"] for run in listed.json()] == [started.json()["id"]]
    assert single.status_code == 200
    assert missing.status_code == 404
    assert len(evidence.json()) == 1
    assert evidence.json()[0]["grade_value"] == "91"


async def test_platform_actor_is_rejected_on_tenant_integration_routes() -> None:
    fixture = _fixture()
    platform = PlatformActorContext(
        subject_id=uuid7(),
        correlation_id="api-test",
        permissions=frozenset({"audit.platform.read"}),
    )
    app = _application(fixture, platform)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        status = await client.get("/api/v1/integrations/moodle/status")
        evidence = await client.get("/api/v1/integrations/moodle/grade-evidence")
        reconcile = await client.post(
            "/api/v1/integrations/moodle/grade-reconciliations",
            json={"term_id": str(fixture.term_id)},
        )

    assert status.status_code == 403
    assert evidence.status_code == 403
    assert reconcile.status_code == 403
