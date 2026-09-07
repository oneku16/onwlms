"""Safe explicit notification channel adapters."""

from uuid import UUID

from core.errors import ExternalServiceError
from notifications.domain.messages import NotificationChannel


class RecordingChannelAdapter:
    """Record external sends for local/test use only."""

    def __init__(
        self,
        channel: NotificationChannel,
    ) -> None:
        if channel is NotificationChannel.IN_APP:
            message = "In-app messages do not use an external adapter"
            raise ValueError(message)
        self._channel = channel
        self.operations: dict[str, str] = {}

    @property
    def channel(self) -> NotificationChannel:
        """Return the recorded external channel."""

        return self._channel

    async def send(
        self,
        *,
        organization_id: UUID,
        recipient_person_id: UUID,
        subject: str,
        body: str,
        idempotency_key: str,
    ) -> str:
        """Record one idempotent send without logging message content."""

        del organization_id, recipient_person_id, subject, body
        reference = self.operations.get(idempotency_key)
        if reference is None:
            reference = f"test-{self._channel.value}-{len(self.operations) + 1}"
            self.operations[idempotency_key] = reference
        return reference


class UnavailableChannelAdapter:
    """Fail explicitly when a production notification provider is absent."""

    def __init__(
        self,
        channel: NotificationChannel,
    ) -> None:
        self._channel = channel

    @property
    def channel(self) -> NotificationChannel:
        """Return the unavailable channel."""

        return self._channel

    async def send(
        self,
        *,
        organization_id: UUID,
        recipient_person_id: UUID,
        subject: str,
        body: str,
        idempotency_key: str,
    ) -> None:
        """Reject delivery without exposing configuration or message content."""

        del organization_id, recipient_person_id, subject, body, idempotency_key
        raise ExternalServiceError("Notification provider is unavailable")


__all__ = ["RecordingChannelAdapter", "UnavailableChannelAdapter"]
