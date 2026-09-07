"""PostgreSQL audit evidence adapter."""

from uuid import UUID

from sqlalchemy import Select
from sqlalchemy import select

from audit.domain.records import AuditRecord
from audit.domain.records import AuditSource
from audit.infrastructure.models import AuditRecordModel
from shared.database import Database


class SQLAlchemyAuditRepository:
    """Append and query audit evidence through scoped transactions."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database

    async def append(
        self,
        record: AuditRecord,
    ) -> None:
        """Append one record; mutation is intentionally unsupported."""

        async with self._database.session(
            organization_id=record.organization_id,
        ) as session:
            session.add(
                AuditRecordModel(
                    id=record.id,
                    organization_id=record.organization_id,
                    actor_subject_id=record.actor_subject_id,
                    action=record.action,
                    entity_type=record.entity_type,
                    entity_id=record.entity_id,
                    occurred_at=record.occurred_at,
                    source=record.source.value,
                    outcome=record.outcome,
                    correlation_id=record.correlation_id,
                    reason=record.reason,
                    safe_metadata=record.metadata,
                )
            )

    async def list_for_organization(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> list[AuditRecord]:
        """Read one organization's evidence under its PostgreSQL context."""

        statement = self._base_query().where(
            AuditRecordModel.organization_id == organization_id
        )
        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            rows = await session.scalars(statement.limit(limit).offset(offset))
            return [self._to_domain(model) for model in rows]

    async def list_platform(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[AuditRecord]:
        """Read only platform-global audit evidence."""

        statement = self._base_query().where(AuditRecordModel.organization_id.is_(None))
        async with self._database.session() as session:
            rows = await session.scalars(statement.limit(limit).offset(offset))
            return [self._to_domain(model) for model in rows]

    @staticmethod
    def _base_query() -> Select[tuple[AuditRecordModel]]:
        """Build the stable newest-first audit query."""

        return select(AuditRecordModel).order_by(AuditRecordModel.occurred_at.desc())

    @staticmethod
    def _to_domain(model: AuditRecordModel) -> AuditRecord:
        """Translate persistence state into the safe public audit value."""

        return AuditRecord(
            id=model.id,
            organization_id=model.organization_id,
            actor_subject_id=model.actor_subject_id,
            action=model.action,
            entity_type=model.entity_type,
            entity_id=model.entity_id,
            occurred_at=model.occurred_at,
            source=AuditSource(model.source),
            outcome=model.outcome,
            correlation_id=model.correlation_id,
            reason=model.reason,
            metadata=model.safe_metadata,
        )


__all__ = ["SQLAlchemyAuditRepository"]
