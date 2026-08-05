"""Notification preference, safe rendering, and delivery behavior."""

from dataclasses import replace
from uuid import UUID
from uuid import uuid7

import pytest
from fastapi import Request
from fastapi.routing import APIRoute

from core.context import ActorContext
from core.context import TenantActorContext
from core.errors import AuthorizationError
from core.errors import ConflictError
from core.errors import NotFoundError
from notifications.application.service import NOTIFICATIONS_DELIVERY_RETRY_OWN
from notifications.application.service import NOTIFICATIONS_PREFERENCES_MANAGE_OWN
from notifications.application.service import NOTIFICATIONS_READ_OWN
from notifications.application.service import NotificationService
from notifications.domain.messages import DeliveryStatus
from notifications.domain.messages import Notification
from notifications.domain.messages import NotificationChannel
from notifications.domain.messages import NotificationPreference
from notifications.infrastructure.adapters import RecordingChannelAdapter
from notifications.infrastructure.adapters import UnavailableChannelAdapter
from notifications.presentation.router import create_notifications_router


class InMemoryNotificationRepository:
    """Store recipient messages and preferences for behavioral tests."""

    def __init__(self) -> None:
        self.messages: dict[UUID, Notification] = {}
        self.preferences: dict[tuple[UUID, UUID, NotificationChannel], bool] = {}

    async def create(self, notification: Notification) -> None:
        """Persist one message."""

        self.messages[notification.id] = notification

    async def list_for_recipient(
        self,
        *,
        organization_id: UUID,
        recipient_person_id: UUID,
        limit: int,
        offset: int,
    ) -> list[Notification]:
        """Return only matching recipient messages."""

        messages = [
            message
            for message in self.messages.values()
            if message.organization_id == organization_id
            and message.recipient_person_id == recipient_person_id
        ]
        return messages[offset : offset + limit]

    async def mark_read(
        self,
        *,
        organization_id: UUID,
        recipient_person_id: UUID,
        notification_id: UUID,
    ) -> Notification:
        """Mark a matching message read."""

        message = self.messages.get(notification_id)
        if (
            message is None
            or message.organization_id != organization_id
            or message.recipient_person_id != recipient_person_id
        ):
            raise NotFoundError
        updated = replace(message, status=DeliveryStatus.READ)
        self.messages[notification_id] = updated
        return updated

    async def get_for_recipient(
        self,
        *,
        organization_id: UUID,
        recipient_person_id: UUID,
        notification_id: UUID,
    ) -> Notification | None:
        """Return one exact tenant-recipient message."""

        message = self.messages.get(notification_id)
        if (
            message is None
            or message.organization_id != organization_id
            or message.recipient_person_id != recipient_person_id
        ):
            return None
        return message

    async def record_delivery(
        self,
        *,
        organization_id: UUID,
        notification_id: UUID,
        provider_reference: str | None,
    ) -> None:
        """Mark a tenant message delivered."""

        message = self.messages[notification_id]
        assert message.organization_id == organization_id
        self.messages[notification_id] = replace(
            message,
            status=DeliveryStatus.SENT,
            provider_reference=provider_reference,
        )

    async def record_failure(
        self,
        *,
        organization_id: UUID,
        notification_id: UUID,
        error_code: str,
        retryable: bool,
    ) -> None:
        """Mark a tenant message failed safely."""

        message = self.messages[notification_id]
        assert message.organization_id == organization_id
        self.messages[notification_id] = replace(
            message,
            status=DeliveryStatus.RETRY if retryable else DeliveryStatus.FAILED,
            last_error_code=error_code,
        )

    async def channel_enabled(
        self,
        *,
        organization_id: UUID,
        recipient_person_id: UUID,
        channel: NotificationChannel,
    ) -> bool:
        """Return the explicit test preference."""

        return self.preferences.get(
            (organization_id, recipient_person_id, channel),
            channel is NotificationChannel.IN_APP,
        )

    async def list_preferences(
        self,
        *,
        organization_id: UUID,
        recipient_person_id: UUID,
    ) -> tuple[NotificationPreference, ...]:
        """Return explicitly stored preferences for one tenant recipient."""

        return tuple(
            NotificationPreference(
                organization_id=organization_id,
                recipient_person_id=recipient_person_id,
                channel=channel,
                enabled=enabled,
            )
            for (tenant_id, person_id, channel), enabled in self.preferences.items()
            if tenant_id == organization_id and person_id == recipient_person_id
        )

    async def set_channel_enabled(
        self,
        *,
        organization_id: UUID,
        recipient_person_id: UUID,
        channel: NotificationChannel,
        enabled: bool,
    ) -> NotificationPreference:
        """Replace one explicit preference."""

        self.preferences[(organization_id, recipient_person_id, channel)] = enabled
        return NotificationPreference(
            organization_id=organization_id,
            recipient_person_id=recipient_person_id,
            channel=channel,
            enabled=enabled,
        )


class FixedNotificationRecipientResolver:
    """Resolve one membership-linked person for service tests."""

    def __init__(self, person_id: UUID) -> None:
        self.person_id = person_id

    async def resolve_person_id(
        self,
        *,
        actor: TenantActorContext,
    ) -> UUID:
        assert actor.organization_id
        return self.person_id


def _actor(
    organization_id: UUID,
    *permissions: str,
) -> TenantActorContext:
    """Build one tenant actor with an explicit notification permission set."""

    return TenantActorContext(
        subject_id=uuid7(),
        organization_id=organization_id,
        membership_id=uuid7(),
        correlation_id="notification-test",
        permissions=frozenset(permissions),
    )


async def test_disabled_external_channel_creates_no_message_or_side_effect() -> None:
    repository = InMemoryNotificationRepository()
    adapter = RecordingChannelAdapter(NotificationChannel.EMAIL)
    service = NotificationService(
        repository=repository,
        adapters=[adapter],
        recipients=FixedNotificationRecipientResolver(uuid7()),
    )

    result = await service.create(
        organization_id=uuid7(),
        recipient_person_id=uuid7(),
        channel=NotificationChannel.EMAIL,
        subject_template="Welcome {{name}}",
        body_template="Your account is ready.",
        variables={"name": "Student"},
    )

    assert result is None
    assert repository.messages == {}
    assert adapter.operations == {}


async def test_enabled_channel_renders_and_delivers_without_password_content() -> None:
    repository = InMemoryNotificationRepository()
    adapter = RecordingChannelAdapter(NotificationChannel.EMAIL)
    organization_id = uuid7()
    person_id = uuid7()
    service = NotificationService(
        repository=repository,
        adapters=[adapter],
        recipients=FixedNotificationRecipientResolver(person_id),
    )
    repository.preferences[(organization_id, person_id, NotificationChannel.EMAIL)] = (
        True
    )

    created = await service.create(
        organization_id=organization_id,
        recipient_person_id=person_id,
        channel=NotificationChannel.EMAIL,
        subject_template="Welcome to {{organization}}",
        body_template="Use OwnID to sign in.",
        variables={"organization": "North Campus"},
    )

    assert created is not None
    persisted = repository.messages[created.id]
    assert persisted.status is DeliveryStatus.SENT
    assert "password" not in persisted.body.lower()
    assert persisted.provider_reference == "test-email-1"


async def test_unavailable_provider_records_retry_without_false_success() -> None:
    repository = InMemoryNotificationRepository()
    service = NotificationService(
        repository=repository,
        adapters=[UnavailableChannelAdapter(NotificationChannel.SMS)],
        recipients=FixedNotificationRecipientResolver(uuid7()),
    )
    organization_id = uuid7()
    person_id = uuid7()
    repository.preferences[(organization_id, person_id, NotificationChannel.SMS)] = True

    with pytest.raises(ConflictError, match="failed safely"):
        await service.create(
            organization_id=organization_id,
            recipient_person_id=person_id,
            channel=NotificationChannel.SMS,
            subject_template="Notice",
            body_template="A new notice is available in OwnSIS.",
            variables={},
        )

    persisted = next(iter(repository.messages.values()))
    assert persisted.status is DeliveryStatus.RETRY
    assert "provider" not in (persisted.last_error_code or "")


async def test_preferences_are_effective_tenant_scoped_and_permissioned() -> None:
    repository = InMemoryNotificationRepository()
    organization_id = uuid7()
    person_id = uuid7()
    service = NotificationService(
        repository=repository,
        adapters=[],
        recipients=FixedNotificationRecipientResolver(person_id),
    )
    reader = _actor(organization_id, NOTIFICATIONS_READ_OWN)

    defaults = await service.list_preferences(
        actor=reader,
    )
    assert {preference.channel: preference.enabled for preference in defaults} == {
        NotificationChannel.IN_APP: True,
        NotificationChannel.EMAIL: False,
        NotificationChannel.SMS: False,
        NotificationChannel.WHATSAPP: False,
        NotificationChannel.TELEGRAM: False,
    }

    manager = _actor(organization_id, NOTIFICATIONS_PREFERENCES_MANAGE_OWN)
    updated = await service.set_preference(
        actor=manager,
        channel=NotificationChannel.EMAIL,
        enabled=True,
    )
    assert updated.enabled is True
    assert await repository.channel_enabled(
        organization_id=organization_id,
        recipient_person_id=person_id,
        channel=NotificationChannel.EMAIL,
    )

    with pytest.raises(AuthorizationError):
        await service.set_preference(
            actor=_actor(organization_id),
            channel=NotificationChannel.SMS,
            enabled=True,
        )


async def test_recipient_can_retry_only_owned_retryable_external_delivery() -> None:
    repository = InMemoryNotificationRepository()
    organization_id = uuid7()
    person_id = uuid7()
    repository.preferences[(organization_id, person_id, NotificationChannel.EMAIL)] = (
        True
    )
    failing_service = NotificationService(
        repository=repository,
        adapters=[UnavailableChannelAdapter(NotificationChannel.EMAIL)],
        recipients=FixedNotificationRecipientResolver(person_id),
    )
    with pytest.raises(ConflictError):
        await failing_service.create(
            organization_id=organization_id,
            recipient_person_id=person_id,
            channel=NotificationChannel.EMAIL,
            subject_template="Notice",
            body_template="One tenant-safe message.",
            variables={},
        )
    retryable = next(iter(repository.messages.values()))
    adapter = RecordingChannelAdapter(NotificationChannel.EMAIL)
    retry_service = NotificationService(
        repository=repository,
        adapters=[adapter],
        recipients=FixedNotificationRecipientResolver(person_id),
    )
    actor = _actor(organization_id, NOTIFICATIONS_DELIVERY_RETRY_OWN)

    completed = await retry_service.retry_external_delivery(
        actor=actor,
        notification_id=retryable.id,
    )

    assert completed.status is DeliveryStatus.SENT
    assert adapter.operations == {str(retryable.id): "test-email-1"}
    foreign = replace(
        retryable,
        id=uuid7(),
        recipient_person_id=uuid7(),
    )
    repository.messages[foreign.id] = foreign
    with pytest.raises(NotFoundError):
        await retry_service.retry_external_delivery(
            actor=actor,
            notification_id=foreign.id,
        )


def test_preference_and_retry_routes_require_csrf_on_mutation() -> None:
    async def actor_dependency(request: Request) -> ActorContext:
        del request
        return _actor(uuid7(), NOTIFICATIONS_READ_OWN)

    async def csrf_dependency() -> None:
        return None

    router = create_notifications_router(
        actor_dependency=actor_dependency,
        csrf_dependency=csrf_dependency,
    )
    routes = {
        (route.path, method): route
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods or set()
    }
    preference_update = routes[("/api/v1/notifications/preferences/{channel}", "PUT")]
    retry = routes[("/api/v1/notifications/{notification_id}/retry", "POST")]

    assert any(
        dependency.call is csrf_dependency
        for dependency in preference_update.dependant.dependencies
    )
    assert any(
        dependency.call is csrf_dependency
        for dependency in retry.dependant.dependencies
    )
