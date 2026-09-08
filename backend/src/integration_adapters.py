"""Explicit adapters between Integrations evidence and owning-domain ports."""

from uuid import UUID

from academics.application.reference_service import AcademicReferenceService
from grading.domain.models import ExternalGradeEvidence
from integrations.application.service import MoodleIntegrationService


class MoodleGradeEvidenceDirectoryAdapter:
    """Expose pending Moodle evidence to Grading through Grading's own port.

    Grading never reads integration tables; it consumes the public application
    contract of the Integrations module and reports its decision back through
    that same contract so lineage stays with the evidence owner.
    """

    def __init__(self, service: MoodleIntegrationService) -> None:
        self._service = service

    async def get_pending_evidence(
        self,
        *,
        organization_id: UUID,
        evidence_id: UUID,
    ) -> ExternalGradeEvidence | None:
        """Return evidence only while the integration still holds it pending."""

        record = await self._service.pending_grade_evidence(
            organization_id=organization_id,
            evidence_id=evidence_id,
        )
        if record is None:
            return None
        return ExternalGradeEvidence(
            evidence_id=record.id,
            external_event_id=record.external_event_id,
            course_offering_id=record.course_offering_id,
            student_person_id=record.student_person_id,
            grade_value=record.grade_value,
            observed_at=record.observed_at,
            source_version=record.source_version,
        )

    async def record_acceptance(
        self,
        *,
        organization_id: UUID,
        evidence_id: UUID,
        final_grade_id: UUID,
        actor_subject_id: UUID,
        correlation_id: str,
    ) -> None:
        """Link the accepted evidence to the official grade Grading wrote."""

        await self._service.record_grade_evidence_acceptance(
            organization_id=organization_id,
            evidence_id=evidence_id,
            final_grade_id=final_grade_id,
            actor_subject_id=actor_subject_id,
            correlation_id=correlation_id,
        )

    async def record_rejection(
        self,
        *,
        organization_id: UUID,
        evidence_id: UUID,
        reason_code: str,
        actor_subject_id: UUID,
        correlation_id: str,
    ) -> None:
        """Mark the evidence rejected while the integration retains it."""

        await self._service.record_grade_evidence_rejection(
            organization_id=organization_id,
            evidence_id=evidence_id,
            reason_code=reason_code,
            actor_subject_id=actor_subject_id,
            correlation_id=correlation_id,
        )


class AcademicTermOfferingAdapter:
    """Resolve a term's offerings for Integrations through Academics references."""

    def __init__(self, references: AcademicReferenceService) -> None:
        self._references = references

    async def list_course_offering_ids(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> frozenset[UUID] | None:
        """Return the tenant term's offerings, or None for an unknown term."""

        return await self._references.list_course_offering_ids_for_term(
            organization_id=organization_id,
            term_id=term_id,
        )


__all__ = [
    "AcademicTermOfferingAdapter",
    "MoodleGradeEvidenceDirectoryAdapter",
]
