"""Integration application capabilities and ports."""

from integrations.application.ports import FinalGradeEvidenceReceiver
from integrations.application.ports import MoodleGateway
from integrations.application.ports import MoodleIntegrationRepository
from integrations.application.service import MoodleIntegrationService

__all__ = [
    "FinalGradeEvidenceReceiver",
    "MoodleGateway",
    "MoodleIntegrationRepository",
    "MoodleIntegrationService",
]
