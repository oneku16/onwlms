"""PostgreSQL implementation of reliable outbox leasing."""

from datetime import timedelta
from uuid import UUID

from sqlalchemy import and_
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from core.time import utc_now
from outbox.application.events import ApplicationEvent
from outbox.infrastructure.models import OutboxEventModel
from shared.database import Database


class SQLAlchemyOutboxRepository:
    """Persist and lease application events using PostgreSQL locking."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database

    async def enqueue(
        self,
        event: ApplicationEvent,
    ) -> bool:
        """Insert an event once and report whether this call accepted it."""

        try:
            async with self._database.session(
                organization_id=event.organization_id,
            ) as session:
                session.add(
                    OutboxEventModel(
                        id=event.id,
                        event_type=event.event_type,
                        contract_version=event.contract_version,
                        organization_id=event.organization_id,
                        actor_subject_id=event.actor_subject_id,
                        correlation_id=event.correlation_id,
                        idempotency_key=event.idempotency_key,
                        payload=event.payload,
                        created_at=event.occurred_at,
                        available_at=event.occurred_at,
                    )
                )
        except IntegrityError:
            return False
        return True

    async def claim_batch(
        self,
        *,
        worker_id: str,
        batch_size: int,
        lease_seconds: int,
    ) -> list[ApplicationEvent]:
        """Lease due or abandoned events with SKIP LOCKED."""

        now = utc_now()
        abandoned_before = now - timedelta(seconds=lease_seconds)
        async with self._database.session() as session:
            statement = (
                select(OutboxEventModel)
                .where(
                    or_(
                        and_(
                            OutboxEventModel.status.in_(("pending", "retry")),
                            OutboxEventModel.available_at <= now,
                        ),
                        and_(
                            OutboxEventModel.status == "processing",
                            OutboxEventModel.locked_at.is_not(None),
                            OutboxEventModel.locked_at <= abandoned_before,
                        ),
                    )
                )
                .order_by(OutboxEventModel.created_at)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
            rows = list(await session.scalars(statement))
            for row in rows:
                row.status = "processing"
                row.locked_at = now
                row.locked_by = worker_id
                row.attempts += 1
            return [self._to_event(row) for row in rows]

    async def mark_processed(
        self,
        *,
        event_id: object,
        worker_id: str,
    ) -> None:
        """Complete a lease only when the caller still owns it."""

        identifier = self._require_uuid(event_id)
        async with self._database.session() as session:
            row = await session.scalar(
                select(OutboxEventModel)
                .where(
                    OutboxEventModel.id == identifier,
                    OutboxEventModel.locked_by == worker_id,
                    OutboxEventModel.status == "processing",
                )
                .with_for_update()
            )
            if row is None:
                return
            row.status = "processed"
            row.processed_at = utc_now()
            row.locked_at = None
            row.locked_by = None

    async def record_failure(
        self,
        *,
        event_id: object,
        worker_id: str,
        error_code: str,
        retry_delay_seconds: int,
        max_attempts: int,
    ) -> None:
        """Release a failed lease for retry or terminal quarantine."""

        identifier = self._require_uuid(event_id)
        async with self._database.session() as session:
            row = await session.scalar(
                select(OutboxEventModel)
                .where(
                    OutboxEventModel.id == identifier,
                    OutboxEventModel.locked_by == worker_id,
                    OutboxEventModel.status == "processing",
                )
                .with_for_update()
            )
            if row is None:
                return
            row.last_error_code = error_code[:120]
            row.locked_at = None
            row.locked_by = None
            if row.attempts >= max_attempts:
                row.status = "quarantined"
                return
            row.status = "retry"
            exponent = min(row.attempts - 1, 8)
            delay = retry_delay_seconds * (2**exponent)
            row.available_at = utc_now() + timedelta(seconds=delay)

    @staticmethod
    def _require_uuid(value: object) -> UUID:
        """Narrow the protocol's opaque event identifier safely."""

        if not isinstance(value, UUID):
            message = "event_id must be a UUID"
            raise TypeError(message)
        return value

    @staticmethod
    def _to_event(model: OutboxEventModel) -> ApplicationEvent:
        """Translate a leased row into its stable public event contract."""

        return ApplicationEvent(
            id=model.id,
            event_type=model.event_type,
            contract_version=model.contract_version,
            occurred_at=model.created_at,
            organization_id=model.organization_id,
            actor_subject_id=model.actor_subject_id,
            correlation_id=model.correlation_id,
            idempotency_key=model.idempotency_key,
            payload=model.payload,
        )


__all__ = ["SQLAlchemyOutboxRepository"]
