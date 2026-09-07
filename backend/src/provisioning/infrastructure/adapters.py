"""Explicit safe provisioning adapters for tests and missing configuration."""

from uuid import UUID

from core.errors import ExternalServiceError
from provisioning.domain.jobs import ProvisioningTarget


class RecordingProvisioningAdapter:
    """Record effects for local/test use without claiming provider verification."""

    def __init__(
        self,
        target: ProvisioningTarget,
    ) -> None:
        self._target = target
        self.operations: dict[str, str] = {}

    @property
    def target(self) -> ProvisioningTarget:
        """Return the configured test destination."""

        return self._target

    async def provision(
        self,
        *,
        organization_id: UUID,
        subject_type: str,
        subject_id: UUID,
        idempotency_key: str,
    ) -> str:
        """Record one idempotent operation and return a synthetic reference."""

        del organization_id, subject_type, subject_id
        reference = self.operations.get(idempotency_key)
        if reference is None:
            reference = f"test-{self._target.value}-{len(self.operations) + 1}"
            self.operations[idempotency_key] = reference
        return reference


class UnavailableProvisioningAdapter:
    """Fail explicitly when a production destination lacks configuration."""

    def __init__(
        self,
        target: ProvisioningTarget,
    ) -> None:
        self._target = target

    @property
    def target(self) -> ProvisioningTarget:
        """Return the unavailable destination."""

        return self._target

    async def provision(
        self,
        *,
        organization_id: UUID,
        subject_type: str,
        subject_id: UUID,
        idempotency_key: str,
    ) -> None:
        """Reject the effect without leaking configuration detail."""

        del organization_id, subject_type, subject_id, idempotency_key
        raise ExternalServiceError("Provisioning provider is unavailable")


__all__ = ["RecordingProvisioningAdapter", "UnavailableProvisioningAdapter"]
