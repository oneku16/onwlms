"""Explicit provisioning module construction for API and worker processes."""

from core.settings import AppEnvironment
from core.settings import Settings
from provisioning.application.ports import ProvisioningAdapter
from provisioning.application.ports import ProvisioningAuditSink
from provisioning.application.service import ProvisioningService
from provisioning.domain.jobs import ProvisioningTarget
from provisioning.infrastructure.adapters import RecordingProvisioningAdapter
from provisioning.infrastructure.adapters import UnavailableProvisioningAdapter
from provisioning.infrastructure.repository import SQLAlchemyProvisioningRepository
from shared.database import Database


def create_provisioning_service(
    *,
    settings: Settings,
    database: Database,
    audit: ProvisioningAuditSink,
) -> ProvisioningService:
    """Construct persistent provisioning with environment-safe adapters."""

    return ProvisioningService(
        repository=SQLAlchemyProvisioningRepository(database),
        adapters=_adapters(settings),
        max_attempts=settings.WORKER_MAX_ATTEMPTS,
        audit=audit,
        lease_seconds=settings.WORKER_LEASE_SECONDS,
    )


def _adapters(settings: Settings) -> list[ProvisioningAdapter]:
    """Use local recorders and explicit unavailable production providers."""

    if settings.APP_ENV is AppEnvironment.PRODUCTION:
        return [UnavailableProvisioningAdapter(target) for target in ProvisioningTarget]
    return [RecordingProvisioningAdapter(target) for target in ProvisioningTarget]


__all__ = ["create_provisioning_service"]
