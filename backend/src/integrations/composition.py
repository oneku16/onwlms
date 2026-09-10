"""Explicit Moodle integration construction and route registration."""

from collections.abc import Awaitable
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from fastapi import FastAPI
from fastapi import Request

from core.context import ActorContext
from core.field_encryption import FieldCipher
from core.time import utc_now
from integrations.application.ports import MoodleGatewayFactory
from integrations.application.ports import MoodleIntegrationAuditSink
from integrations.application.ports import MoodleIntegrationRepository
from integrations.application.ports import TermOfferingDirectory
from integrations.application.reconciliation_service import (
    MoodleGradeReconciliationService,
)
from integrations.application.service import MoodleIntegrationService
from integrations.infrastructure.factory import MoodleGatewayFactoryAdapter
from integrations.infrastructure.grade_receiver import (
    ReviewRequiredGradeEvidenceReceiver,
)
from integrations.infrastructure.repository import SQLAlchemyMoodleIntegrationRepository
from integrations.infrastructure.repository import (
    SQLAlchemyMoodleReconciliationRunRepository,
)
from integrations.presentation.router import create_integrations_router
from shared.database import Database


class SystemIntegrationClock:
    """Supply timezone-aware UTC time to integration use cases."""

    def now(self) -> datetime:
        """Return current UTC time."""

        return utc_now()


@dataclass(frozen=True, slots=True)
class MoodleResources:
    """Expose the separately addressable Moodle application boundaries."""

    service: MoodleIntegrationService
    reconciliation: MoodleGradeReconciliationService
    repository: MoodleIntegrationRepository
    gateway_factory: MoodleGatewayFactory


def create_moodle_resources(
    *,
    database: Database,
    integration_encryption_key: str,
    request_timeout_seconds: float,
    offerings: TermOfferingDirectory,
    audit: MoodleIntegrationAuditSink,
) -> MoodleResources:
    """Construct PostgreSQL Moodle adapters and explicit application services."""

    cipher = FieldCipher(integration_encryption_key)
    repository = SQLAlchemyMoodleIntegrationRepository(database)
    gateway_factory = MoodleGatewayFactoryAdapter(
        repository=repository,
        cipher=cipher,
        timeout_seconds=request_timeout_seconds,
    )
    clock = SystemIntegrationClock()
    service = MoodleIntegrationService(
        repository=repository,
        gateway_factory=gateway_factory,
        grade_receiver=ReviewRequiredGradeEvidenceReceiver(),
        cipher=cipher,
        audit=audit,
        clock=clock,
    )
    reconciliation = MoodleGradeReconciliationService(
        repository=repository,
        runs=SQLAlchemyMoodleReconciliationRunRepository(database),
        intake=service,
        gateway_factory=gateway_factory,
        offerings=offerings,
        clock=clock,
        audit=audit,
    )
    return MoodleResources(
        service=service,
        reconciliation=reconciliation,
        repository=repository,
        gateway_factory=gateway_factory,
    )


def install_integration_routes(
    *,
    app: FastAPI,
    resources: MoodleResources,
    actor_dependency: Callable[[Request], Awaitable[ActorContext]],
    csrf_dependency: Callable[..., Awaitable[None]],
) -> None:
    """Register the explicitly composed Moodle services and thin router."""

    app.state.moodle_service = resources.service
    app.state.moodle_reconciliation_service = resources.reconciliation
    app.include_router(
        create_integrations_router(
            actor_dependency=actor_dependency,
            csrf_dependency=csrf_dependency,
        )
    )


__all__ = [
    "MoodleResources",
    "SystemIntegrationClock",
    "create_moodle_resources",
    "install_integration_routes",
]
