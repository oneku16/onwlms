"""Privacy-minimized audit sink shared by explicitly composed modules."""

from collections.abc import Mapping
from uuid import UUID

from audit.application.service import AuditService
from audit.domain.records import AuditRecord
from audit.domain.records import AuditSource
from core.identifiers import new_uuid7
from core.time import utc_now


class ApplicationAuditSink:
    """Translate module audit ports into the canonical append-only contract."""

    def __init__(self, service: AuditService) -> None:
        self._service = service

    async def record_identity_event(
        self,
        *,
        action: str,
        subject_id: UUID | None,
        correlation_id: str,
        outcome: str,
    ) -> None:
        """Record a global authentication event without provider claims."""

        await self._record(
            organization_id=None,
            actor_subject_id=subject_id,
            action=action,
            entity_type="identity_subject",
            entity_id=str(subject_id) if subject_id is not None else "anonymous",
            correlation_id=correlation_id,
            outcome=outcome,
            source=AuditSource.WEB,
        )

    async def record_organization_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        correlation_id: str,
        outcome: str,
    ) -> None:
        """Record organization lifecycle or configuration evidence."""

        await self._record(
            organization_id=organization_id,
            actor_subject_id=actor_subject_id,
            action=action,
            entity_type="organization",
            entity_id=str(organization_id),
            correlation_id=correlation_id,
            outcome=outcome,
        )

    async def record_people_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        target_id: UUID,
        correlation_id: str,
        outcome: str,
    ) -> None:
        """Record people or membership governance without PII fields."""

        await self._record(
            organization_id=organization_id,
            actor_subject_id=actor_subject_id,
            action=action,
            entity_type="people_access",
            entity_id=str(target_id),
            correlation_id=correlation_id,
            outcome=outcome,
        )

    async def record_entitlement_event(
        self,
        *,
        action: str,
        organization_id: UUID | None,
        actor_subject_id: UUID,
        target_id: UUID,
        correlation_id: str,
        outcome: str,
    ) -> None:
        """Record plan and entitlement governance without commercial payloads."""

        await self._record(
            organization_id=organization_id,
            actor_subject_id=actor_subject_id,
            action=action,
            entity_type="entitlement",
            entity_id=str(target_id),
            correlation_id=correlation_id,
            outcome=outcome,
        )

    async def record_mcp_invocation(
        self,
        *,
        tool: str,
        organization_id: UUID,
        actor_subject_id: UUID | None,
        correlation_id: str,
        outcome: str,
    ) -> None:
        """Record one MCP tool invocation without prompt or result contents."""

        await self._record(
            organization_id=organization_id,
            actor_subject_id=actor_subject_id,
            action="mcp.tool_invoked",
            entity_type="mcp_tool",
            entity_id=tool,
            correlation_id=correlation_id,
            outcome=outcome,
            source=AuditSource.MCP,
        )

    async def record_final_grade_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        final_grade_id: UUID,
        correlation_id: str,
        after_term_closure: bool,
    ) -> None:
        """Record a grade mutation without score, symbol, or explanation."""

        await self._record(
            organization_id=organization_id,
            actor_subject_id=actor_subject_id,
            action=action,
            entity_type="final_grade",
            entity_id=str(final_grade_id),
            correlation_id=correlation_id,
            outcome="succeeded",
            metadata={"after_term_closure": after_term_closure},
        )

    async def record_course_selection_event(
        self,
        *,
        action: str,
        organization_id: UUID,
        actor_subject_id: UUID,
        request_id: UUID,
        correlation_id: str,
    ) -> None:
        """Record an administrative selection action without selection details."""

        await self._record(
            organization_id=organization_id,
            actor_subject_id=actor_subject_id,
            action=action,
            entity_type="course_selection_request",
            entity_id=str(request_id),
            correlation_id=correlation_id,
            outcome="succeeded",
        )

    async def record_term_closure_intent(
        self,
        *,
        organization_id: UUID,
        actor_subject_id: UUID,
        term_id: UUID,
        correlation_id: str,
        reason: str,
    ) -> None:
        """Record authorized closure intent without claiming catalog success."""

        await self._record(
            organization_id=organization_id,
            actor_subject_id=actor_subject_id,
            action="academics.term.closure_intent.authorized",
            entity_type="academic_term",
            entity_id=str(term_id),
            correlation_id=correlation_id,
            outcome="intent_recorded",
            reason=reason,
        )

    async def record_moodle_configuration_event(
        self,
        *,
        organization_id: UUID,
        actor_subject_id: UUID,
        correlation_id: str,
    ) -> None:
        """Record configuration without endpoint or credential material."""

        await self._record(
            organization_id=organization_id,
            actor_subject_id=actor_subject_id,
            action="integrations.moodle.configuration.updated",
            entity_type="moodle_integration",
            entity_id=str(organization_id),
            correlation_id=correlation_id,
            outcome="succeeded",
        )

    async def record_provisioning_attempt(
        self,
        *,
        organization_id: UUID,
        actor_subject_id: UUID | None,
        job_id: UUID,
        target: str,
        attempt: int,
        outcome: str,
        correlation_id: str,
        worker_initiated: bool,
    ) -> None:
        """Record a provider-free outcome for one claimed provisioning attempt."""

        await self._record(
            organization_id=organization_id,
            actor_subject_id=actor_subject_id,
            action="provisioning.attempt.completed",
            entity_type="provisioning_job",
            entity_id=str(job_id),
            correlation_id=correlation_id,
            outcome=outcome,
            source=(AuditSource.WORKER if worker_initiated else AuditSource.API),
            metadata={"target": target, "attempt": attempt},
        )

    async def _record(
        self,
        *,
        organization_id: UUID | None,
        actor_subject_id: UUID | None,
        action: str,
        entity_type: str,
        entity_id: str,
        correlation_id: str,
        outcome: str,
        source: AuditSource = AuditSource.API,
        reason: str | None = None,
        metadata: Mapping[str, str | int | bool] | None = None,
    ) -> None:
        """Append one normalized record through the audit application service."""

        await self._service.record(
            AuditRecord(
                id=new_uuid7(),
                organization_id=organization_id,
                actor_subject_id=actor_subject_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                occurred_at=utc_now(),
                source=source,
                outcome=outcome,
                correlation_id=correlation_id,
                reason=reason,
                metadata=dict(metadata) if metadata is not None else None,
            )
        )


__all__ = ["ApplicationAuditSink"]
