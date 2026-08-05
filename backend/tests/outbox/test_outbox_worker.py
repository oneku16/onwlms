"""Outbox duplicate-safe dispatch and terminal failure behavior."""

from uuid import UUID
from uuid import uuid7

from core.time import utc_now
from outbox.application.events import ApplicationEvent
from outbox.application.worker import OutboxWorker


class InMemoryOutboxRepository:
    """Provide one leased event and record worker outcomes."""

    def __init__(self, event: ApplicationEvent) -> None:
        self.event = event
        self.processed: list[object] = []
        self.failures: list[tuple[object, str]] = []

    async def enqueue(self, event: ApplicationEvent) -> bool:
        """Accept an event only when its idempotency key differs."""

        if event.idempotency_key == self.event.idempotency_key:
            return False
        self.event = event
        return True

    async def claim_batch(
        self,
        *,
        worker_id: str,
        batch_size: int,
        lease_seconds: int,
    ) -> list[ApplicationEvent]:
        """Return the configured event once per call."""

        del worker_id, batch_size, lease_seconds
        return [self.event]

    async def mark_processed(
        self,
        *,
        event_id: object,
        worker_id: str,
    ) -> None:
        """Record successful completion."""

        del worker_id
        self.processed.append(event_id)

    async def record_failure(
        self,
        *,
        event_id: object,
        worker_id: str,
        error_code: str,
        retry_delay_seconds: int,
        max_attempts: int,
    ) -> None:
        """Record safe failure metadata."""

        del worker_id, retry_delay_seconds, max_attempts
        self.failures.append((event_id, error_code))


class RecordingHandler:
    """Record idempotency keys handled by a successful consumer."""

    event_type = "student.activated.v1"

    def __init__(self) -> None:
        self.keys: list[str] = []

    async def handle(self, event: ApplicationEvent) -> None:
        """Record the event without external effects."""

        self.keys.append(event.idempotency_key)


class FailingHandler:
    """Fail without exposing a sensitive exception message."""

    event_type = "student.activated.v1"

    async def handle(self, event: ApplicationEvent) -> None:
        """Raise a representative provider failure."""

        del event
        raise RuntimeError("sensitive provider detail")


def _event() -> ApplicationEvent:
    """Create a tenant-bound activation fact."""

    return ApplicationEvent(
        id=uuid7(),
        event_type="student.activated.v1",
        contract_version=1,
        occurred_at=utc_now(),
        organization_id=uuid7(),
        actor_subject_id=uuid7(),
        correlation_id="test-correlation",
        idempotency_key="student:activation:one",
        payload={"student_id": str(uuid7())},
    )


async def test_worker_marks_successful_idempotent_handler_processed() -> None:
    event = _event()
    repository = InMemoryOutboxRepository(event)
    handler = RecordingHandler()
    worker = OutboxWorker(
        repository=repository,
        handlers=[handler],
        worker_id="worker-one",
        max_attempts=5,
    )

    count = await worker.process_batch()

    assert count == 1
    assert handler.keys == [event.idempotency_key]
    assert repository.processed == [event.id]


async def test_worker_records_opaque_failure_code_without_exception_text() -> None:
    event = _event()
    repository = InMemoryOutboxRepository(event)
    worker = OutboxWorker(
        repository=repository,
        handlers=[FailingHandler()],
        worker_id="worker-one",
        max_attempts=5,
    )

    await worker.process_batch()

    event_id, error_code = repository.failures[0]
    assert event_id == event.id
    assert error_code.startswith("handler_error_")
    assert "sensitive" not in error_code
    assert isinstance(event_id, UUID)
