"""Stable application-event envelope."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ApplicationEvent:
    """Carry a versioned fact and immutable execution context."""

    id: UUID
    event_type: str
    contract_version: int
    occurred_at: datetime
    organization_id: UUID | None
    actor_subject_id: UUID | None
    correlation_id: str
    idempotency_key: str
    payload: dict[str, str | int | bool | None]


__all__ = ["ApplicationEvent"]
