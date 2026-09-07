"""Tenant-specific Moodle gateway construction from encrypted configuration."""

from uuid import UUID

from core.errors import ExternalServiceError
from core.field_encryption import FieldCipher
from integrations.application.ports import MoodleIntegrationRepository
from integrations.infrastructure.gateway import MoodleWebServiceGateway


class MoodleGatewayFactoryAdapter:
    """Build gateways only after resolving tenant-scoped protected settings."""

    def __init__(
        self,
        *,
        repository: MoodleIntegrationRepository,
        cipher: FieldCipher,
        timeout_seconds: float,
    ) -> None:
        self._repository = repository
        self._cipher = cipher
        self._timeout_seconds = timeout_seconds

    async def create_for_organization(
        self,
        organization_id: UUID,
    ) -> MoodleWebServiceGateway:
        """Return a configured tenant gateway or fail explicitly."""

        configuration = await self._repository.get_configuration(organization_id)
        encrypted_token = await self._repository.get_encrypted_token(organization_id)
        if configuration is None or encrypted_token is None:
            raise ExternalServiceError("Moodle integration is not configured")
        return MoodleWebServiceGateway(
            base_url=configuration.base_url,
            token=self._cipher.decrypt(encrypted_token),
            timeout_seconds=self._timeout_seconds,
        )


__all__ = ["MoodleGatewayFactoryAdapter"]
