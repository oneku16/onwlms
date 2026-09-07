"""Governed bootstrap and lifecycle for global platform administrators."""

import secrets
from uuid import UUID

from core.context import PlatformActorContext
from core.errors import AuthorizationError
from identity.application.ports import PlatformAdministrationAuditSink
from identity.application.ports import PlatformAdministratorRepository
from identity.domain.models import PlatformAdministrator

MANAGE_PLATFORM_ADMINISTRATORS_PERMISSION = "platform_administrators.manage"


class PlatformAdministrationService:
    """Coordinate explicit, auditable global administrator changes."""

    def __init__(
        self,
        *,
        administrators: PlatformAdministratorRepository,
        audit: PlatformAdministrationAuditSink,
        bootstrap_secret: str,
    ) -> None:
        self._administrators = administrators
        self._audit = audit
        self._bootstrap_secret = bootstrap_secret

    async def bootstrap(
        self,
        *,
        subject_id: UUID,
        supplied_secret: str,
        correlation_id: str,
    ) -> PlatformAdministrator:
        """Assign the signed-in subject as the first administrator once."""

        if not self._valid_bootstrap_secret(supplied_secret):
            await self._audit.record_platform_administrator_event(
                action="platform_administrator.bootstrap",
                actor_subject_id=subject_id,
                target_subject_id=subject_id,
                correlation_id=correlation_id,
                outcome="denied",
            )
            raise AuthorizationError
        await self._record_intent(
            action="platform_administrator.bootstrap_intent",
            actor_subject_id=subject_id,
            target_subject_id=subject_id,
            correlation_id=correlation_id,
        )
        administrator = await self._administrators.bootstrap(subject_id=subject_id)
        await self._record_success(
            action="platform_administrator.bootstrapped",
            actor_subject_id=subject_id,
            target_subject_id=subject_id,
            correlation_id=correlation_id,
        )
        return administrator

    async def assign(
        self,
        *,
        actor: PlatformActorContext,
        subject_id: UUID,
    ) -> PlatformAdministrator:
        """Assign or reactivate one administrator under platform authority."""

        self._require_management_permission(actor)
        await self._record_intent(
            action="platform_administrator.assignment_intent",
            actor_subject_id=actor.subject_id,
            target_subject_id=subject_id,
            correlation_id=actor.correlation_id,
        )
        administrator = await self._administrators.assign(subject_id=subject_id)
        await self._record_success(
            action="platform_administrator.assigned",
            actor_subject_id=actor.subject_id,
            target_subject_id=subject_id,
            correlation_id=actor.correlation_id,
        )
        return administrator

    async def revoke(
        self,
        *,
        actor: PlatformActorContext,
        subject_id: UUID,
    ) -> PlatformAdministrator:
        """Revoke an administrator while preserving at least one active admin."""

        self._require_management_permission(actor)
        await self._record_intent(
            action="platform_administrator.revocation_intent",
            actor_subject_id=actor.subject_id,
            target_subject_id=subject_id,
            correlation_id=actor.correlation_id,
        )
        administrator = await self._administrators.revoke(subject_id=subject_id)
        await self._record_success(
            action="platform_administrator.revoked",
            actor_subject_id=actor.subject_id,
            target_subject_id=subject_id,
            correlation_id=actor.correlation_id,
        )
        return administrator

    async def list_administrators(
        self,
        *,
        actor: PlatformActorContext,
        limit: int,
        offset: int,
    ) -> list[PlatformAdministrator]:
        """List administrator assignments under separate platform authority."""

        self._require_management_permission(actor)
        return await self._administrators.list_all(limit=limit, offset=offset)

    def _valid_bootstrap_secret(self, supplied: str) -> bool:
        """Compare a configured one-time bootstrap secret in constant time."""

        if not self._bootstrap_secret or not supplied:
            return False
        try:
            return secrets.compare_digest(self._bootstrap_secret, supplied)
        except TypeError, ValueError:
            return False

    async def _record_intent(
        self,
        *,
        action: str,
        actor_subject_id: UUID,
        target_subject_id: UUID,
        correlation_id: str,
    ) -> None:
        """Persist intent before mutation so audit failure aborts the change."""

        await self._audit.record_platform_administrator_event(
            action=action,
            actor_subject_id=actor_subject_id,
            target_subject_id=target_subject_id,
            correlation_id=correlation_id,
            outcome="intent_recorded",
        )

    async def _record_success(
        self,
        *,
        action: str,
        actor_subject_id: UUID,
        target_subject_id: UUID,
        correlation_id: str,
    ) -> None:
        """Persist the successful global privilege outcome."""

        await self._audit.record_platform_administrator_event(
            action=action,
            actor_subject_id=actor_subject_id,
            target_subject_id=target_subject_id,
            correlation_id=correlation_id,
            outcome="succeeded",
        )

    @staticmethod
    def _require_management_permission(actor: PlatformActorContext) -> None:
        """Require a separately established platform administrator context."""

        if (
            not isinstance(actor, PlatformActorContext)
            or MANAGE_PLATFORM_ADMINISTRATORS_PERMISSION not in actor.permissions
        ):
            raise AuthorizationError


__all__ = [
    "MANAGE_PLATFORM_ADMINISTRATORS_PERMISSION",
    "PlatformAdministrationService",
]
