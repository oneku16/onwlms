"""Reliable event storage and consumer ports."""

from typing import Protocol

from outbox.application.events import ApplicationEvent


class OutboxRepository(Protocol):
    """Store and claim application events with at-least-once semantics."""

    async def enqueue(
        self,
        event: ApplicationEvent,
    ) -> bool:
        """Persist an event once by its stable idempotency key."""
        ...

    async def claim_batch(
        self,
        *,
        worker_id: str,
        batch_size: int,
        lease_seconds: int,
    ) -> list[ApplicationEvent]:
        """Lease due or abandoned events without blocking healthy peers."""
        ...

    async def mark_processed(
        self,
        *,
        event_id: object,
        worker_id: str,
    ) -> None:
        """Mark a leased event as completed by its owning worker."""
        ...

    async def record_failure(
        self,
        *,
        event_id: object,
        worker_id: str,
        error_code: str,
        retry_delay_seconds: int,
        max_attempts: int,
    ) -> None:
        """Retry or quarantine a failed event without storing payload details."""
        ...


class EventHandler(Protocol):
    """Handle one named application event idempotently."""

    @property
    def event_type(self) -> str:
        """Return the one event type accepted by this handler."""
        ...

    async def handle(
        self,
        event: ApplicationEvent,
    ) -> None:
        """Apply the event under its immutable tenant context."""
        ...


__all__ = ["EventHandler", "OutboxRepository"]
