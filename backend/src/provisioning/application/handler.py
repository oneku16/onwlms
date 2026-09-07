"""Outbox consumer for activation-driven provisioning."""

from uuid import UUID

from core.errors import ValidationError
from outbox.application.events import ApplicationEvent
from provisioning.application.service import ProvisioningService


class ActivationProvisioningHandler:
    """Translate an accepted activation fact into idempotent provisioning work."""

    event_type = "person.activated.v1"

    def __init__(
        self,
        service: ProvisioningService,
    ) -> None:
        self._service = service

    async def handle(
        self,
        event: ApplicationEvent,
    ) -> None:
        """Create and execute destination jobs under the event's tenant context.

        A retry reuses the repository's tenant-aware idempotency keys. Completed
        destinations are left untouched while pending or retryable destinations
        are attempted again, which makes partial provider failure observable and
        safe to resume from the same outbox event.
        """

        if event.organization_id is None:
            raise ValidationError("Activation event requires organization context")
        subject_id_value = event.payload.get("subject_id")
        subject_type_value = event.payload.get("subject_type")
        if not isinstance(subject_id_value, str) or not isinstance(
            subject_type_value,
            str,
        ):
            raise ValidationError("Activation event payload is invalid")
        jobs = await self._service.create_activation_jobs(
            organization_id=event.organization_id,
            subject_type=subject_type_value,
            subject_id=UUID(subject_id_value),
        )
        for job in jobs:
            if not self._service.can_retry(job):
                continue
            await self._service.execute(
                organization_id=event.organization_id,
                job_id=job.id,
                actor_subject_id=event.actor_subject_id,
                correlation_id=event.correlation_id,
                worker_initiated=True,
            )


__all__ = ["ActivationProvisioningHandler"]
