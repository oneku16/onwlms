"""PostgreSQL notification persistence adapter."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from core.errors import ConflictError
from core.errors import NotFoundError
from core.identifiers import new_uuid7
from core.time import utc_now
from notifications.domain.messages import DeliveryStatus
from notifications.domain.messages import Notification
from notifications.domain.messages import NotificationChannel
from notifications.domain.messages import NotificationPreference
from notifications.infrastructure.models import NotificationModel
from notifications.infrastructure.models import NotificationPreferenceModel
from shared.database import Database


class SQLAlchemyNotificationRepository:
    """Persist notification content under recipient and tenant constraints."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database

    async def create(
        self,
        notification: Notification,
    ) -> None:
        """Persist explicitly rendered safe notification fields."""

        async with self._database.session(
            organization_id=notification.organization_id,
        ) as session:
            session.add(
                NotificationModel(
                    id=notification.id,
                    organization_id=notification.organization_id,
                    recipient_person_id=notification.recipient_person_id,
                    channel=notification.channel.value,
                    subject=notification.subject,
                    body=notification.body,
                    status=notification.status.value,
                    created_at=notification.created_at,
                )
            )

    async def list_for_recipient(
        self,
        *,
        organization_id: UUID,
        recipient_person_id: UUID,
        limit: int,
        offset: int,
    ) -> list[Notification]:
        """Return only the verified tenant recipient's messages."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            rows = await session.scalars(
                select(NotificationModel)
                .where(
                    NotificationModel.organization_id == organization_id,
                    NotificationModel.recipient_person_id == recipient_person_id,
                )
                .order_by(NotificationModel.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return [self._to_domain(model) for model in rows]

    async def mark_read(
        self,
        *,
        organization_id: UUID,
        recipient_person_id: UUID,
        notification_id: UUID,
    ) -> Notification:
        """Update only a matching tenant, recipient, and notification."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(NotificationModel)
                .where(
                    NotificationModel.id == notification_id,
                    NotificationModel.organization_id == organization_id,
                    NotificationModel.recipient_person_id == recipient_person_id,
                    NotificationModel.channel == NotificationChannel.IN_APP.value,
                )
                .with_for_update()
            )
            if model is None:
                raise NotFoundError
            model.status = DeliveryStatus.READ.value
            model.read_at = utc_now()
            await session.flush()
            return self._to_domain(model)

    async def get_for_recipient(
        self,
        *,
        organization_id: UUID,
        recipient_person_id: UUID,
        notification_id: UUID,
    ) -> Notification | None:
        """Return one message only when tenant and recipient both match."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(NotificationModel).where(
                    NotificationModel.id == notification_id,
                    NotificationModel.organization_id == organization_id,
                    NotificationModel.recipient_person_id == recipient_person_id,
                )
            )
            return self._to_domain(model) if model is not None else None

    async def record_delivery(
        self,
        *,
        organization_id: UUID,
        notification_id: UUID,
        provider_reference: str | None,
    ) -> None:
        """Record successful delivery under tenant scope."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await self._get_locked(
                session=session,
                organization_id=organization_id,
                notification_id=notification_id,
            )
            model.status = DeliveryStatus.SENT.value
            model.provider_reference = provider_reference
            model.last_error_code = None

    async def record_failure(
        self,
        *,
        organization_id: UUID,
        notification_id: UUID,
        error_code: str,
        retryable: bool,
    ) -> None:
        """Record a safe retryable or terminal external failure."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await self._get_locked(
                session=session,
                organization_id=organization_id,
                notification_id=notification_id,
            )
            model.status = (
                DeliveryStatus.RETRY.value if retryable else DeliveryStatus.FAILED.value
            )
            model.last_error_code = error_code[:120]

    async def channel_enabled(
        self,
        *,
        organization_id: UUID,
        recipient_person_id: UUID,
        channel: NotificationChannel,
    ) -> bool:
        """Resolve preference, defaulting in-app on and external channels off."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            preference = await session.scalar(
                select(NotificationPreferenceModel).where(
                    NotificationPreferenceModel.organization_id == organization_id,
                    NotificationPreferenceModel.person_id == recipient_person_id,
                    NotificationPreferenceModel.channel == channel.value,
                )
            )
            if preference is not None:
                return preference.enabled
        return channel is NotificationChannel.IN_APP

    async def list_preferences(
        self,
        *,
        organization_id: UUID,
        recipient_person_id: UUID,
    ) -> tuple[NotificationPreference, ...]:
        """Return stored preferences only for the exact tenant recipient."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            rows = await session.scalars(
                select(NotificationPreferenceModel).where(
                    NotificationPreferenceModel.organization_id == organization_id,
                    NotificationPreferenceModel.person_id == recipient_person_id,
                )
            )
            return tuple(self._preference_to_domain(model) for model in rows)

    async def set_channel_enabled(
        self,
        *,
        organization_id: UUID,
        recipient_person_id: UUID,
        channel: NotificationChannel,
        enabled: bool,
    ) -> NotificationPreference:
        """Upsert one preference under its existing unique tenant key."""

        statement = (
            insert(NotificationPreferenceModel)
            .values(
                id=new_uuid7(),
                organization_id=organization_id,
                person_id=recipient_person_id,
                channel=channel.value,
                enabled=enabled,
            )
            .on_conflict_do_update(
                constraint=("uq_notification_preferences_organization_person_channel"),
                set_={"enabled": enabled},
            )
            .returning(NotificationPreferenceModel)
        )
        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(statement)
            if model is None:
                raise ConflictError("Notification preference could not be saved.")
            return self._preference_to_domain(model)

    @staticmethod
    async def _get_locked(
        *,
        session: object,
        organization_id: UUID,
        notification_id: UUID,
    ) -> NotificationModel:
        """Load one notification under a caller-owned transaction."""

        from sqlalchemy.ext.asyncio import AsyncSession

        if not isinstance(session, AsyncSession):
            message = "session must be an AsyncSession"
            raise TypeError(message)
        model = await session.scalar(
            select(NotificationModel)
            .where(
                NotificationModel.id == notification_id,
                NotificationModel.organization_id == organization_id,
            )
            .with_for_update()
        )
        if model is None:
            raise NotFoundError
        return model

    @staticmethod
    def _to_domain(model: NotificationModel) -> Notification:
        """Translate persistence state to an explicit safe notification value."""

        return Notification(
            id=model.id,
            organization_id=model.organization_id,
            recipient_person_id=model.recipient_person_id,
            channel=NotificationChannel(model.channel),
            subject=model.subject,
            body=model.body,
            status=DeliveryStatus(model.status),
            created_at=model.created_at,
            read_at=model.read_at,
            provider_reference=model.provider_reference,
            last_error_code=model.last_error_code,
        )

    @staticmethod
    def _preference_to_domain(
        model: NotificationPreferenceModel,
    ) -> NotificationPreference:
        """Translate one explicitly stored channel preference."""

        return NotificationPreference(
            organization_id=model.organization_id,
            recipient_person_id=model.person_id,
            channel=NotificationChannel(model.channel),
            enabled=model.enabled,
        )


__all__ = ["SQLAlchemyNotificationRepository"]
