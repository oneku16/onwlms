"""Safe immutable audit evidence values."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class AuditSource(StrEnum):
    """Trusted origin category for an audited capability invocation."""

    WEB = "web"
    API = "api"
    WORKER = "worker"
    INTEGRATION = "integration"
    MCP = "mcp"
    SUPPORT = "support"


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """Represent append-only, privacy-minimized evidence of an action."""

    id: UUID
    organization_id: UUID | None
    actor_subject_id: UUID | None
    action: str
    entity_type: str
    entity_id: str
    occurred_at: datetime
    source: AuditSource
    outcome: str
    correlation_id: str
    reason: str | None = None
    metadata: dict[str, str | int | bool] | None = None


__all__ = ["AuditRecord", "AuditSource"]
