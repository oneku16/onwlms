"""Bounded, observable outbox dispatch loop behavior."""

import hashlib
from uuid import UUID

import structlog

from outbox.application.ports import EventHandler
from outbox.application.ports import OutboxRepository


class OutboxWorker:
    """Dispatch leased events to explicitly registered idempotent handlers."""

    def __init__(
        self,
        *,
        repository: OutboxRepository,
        handlers: list[EventHandler],
        worker_id: str,
        max_attempts: int,
        lease_seconds: int = 300,
    ) -> None:
        self._repository = repository
        self._handlers = {handler.event_type: handler for handler in handlers}
        self._worker_id = worker_id
        self._max_attempts = max_attempts
        self._lease_seconds = lease_seconds
        self._logger = structlog.get_logger("outbox_worker")

    async def process_batch(
        self,
        *,
        batch_size: int = 25,
    ) -> int:
        """Process one leased batch and return the number of events examined."""

        events = await self._repository.claim_batch(
            worker_id=self._worker_id,
            batch_size=batch_size,
            lease_seconds=self._lease_seconds,
        )
        for event in events:
            handler = self._handlers.get(event.event_type)
            if handler is None:
                await self._record_failure(
                    event_id=event.id,
                    error_code="handler_not_registered",
                )
                continue
            try:
                await handler.handle(event)
            except Exception as exc:
                error_code = self._safe_error_code(exc)
                self._logger.warning(
                    "event_handler_failed",
                    event_id=str(event.id),
                    event_type=event.event_type,
                    organization_id=(
                        str(event.organization_id) if event.organization_id else None
                    ),
                    error_code=error_code,
                )
                await self._record_failure(
                    event_id=event.id,
                    error_code=error_code,
                )
                continue
            await self._repository.mark_processed(
                event_id=event.id,
                worker_id=self._worker_id,
            )
        return len(events)

    async def _record_failure(
        self,
        *,
        event_id: UUID,
        error_code: str,
    ) -> None:
        """Record a bounded retry with exponential delay delegated to storage."""

        await self._repository.record_failure(
            event_id=event_id,
            worker_id=self._worker_id,
            error_code=error_code,
            retry_delay_seconds=2,
            max_attempts=self._max_attempts,
        )

    @staticmethod
    def _safe_error_code(exc: Exception) -> str:
        """Return a stable opaque error class marker without exception text."""

        name = type(exc).__name__.encode("utf-8")
        digest = hashlib.sha256(name).hexdigest()[:12]
        return f"handler_error_{digest}"


__all__ = ["OutboxWorker"]
