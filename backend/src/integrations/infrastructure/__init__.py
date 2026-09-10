"""Moodle HTTP and PostgreSQL adapters."""

from integrations.infrastructure.factory import MoodleGatewayFactoryAdapter
from integrations.infrastructure.gateway import MoodleWebServiceGateway
from integrations.infrastructure.grade_receiver import (
    ReviewRequiredGradeEvidenceReceiver,
)
from integrations.infrastructure.memory import InMemoryMoodleIntegrationRepository
from integrations.infrastructure.memory import InMemoryMoodleReconciliationRunRepository
from integrations.infrastructure.repository import SQLAlchemyMoodleIntegrationRepository
from integrations.infrastructure.repository import (
    SQLAlchemyMoodleReconciliationRunRepository,
)

__all__ = [
    "InMemoryMoodleIntegrationRepository",
    "InMemoryMoodleReconciliationRunRepository",
    "MoodleGatewayFactoryAdapter",
    "MoodleWebServiceGateway",
    "ReviewRequiredGradeEvidenceReceiver",
    "SQLAlchemyMoodleIntegrationRepository",
    "SQLAlchemyMoodleReconciliationRunRepository",
]
