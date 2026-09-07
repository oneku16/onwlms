"""Observable idempotent provisioning job state."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ProvisioningTarget(StrEnum):
    """Approved replaceable provisioning destinations."""

    OWNID = "ownid"
    MOODLE = "moodle"
    MICROSOFT_365 = "microsoft_365"
    WELCOME_NOTIFICATION = "welcome_notification"


class ProvisioningStatus(StrEnum):
    """Operable lifecycle of one destination-specific provisioning effect."""

    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    RETRY = "retry"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ProvisioningJob:
    """Represent one idempotent external effect for an activated person."""

    id: UUID
    organization_id: UUID
    subject_type: str
    subject_id: UUID
    target: ProvisioningTarget
    status: ProvisioningStatus
    idempotency_key: str
    attempts: int
    created_at: datetime
    updated_at: datetime
    external_reference: str | None = None
    last_error_code: str | None = None


__all__ = ["ProvisioningJob", "ProvisioningStatus", "ProvisioningTarget"]
