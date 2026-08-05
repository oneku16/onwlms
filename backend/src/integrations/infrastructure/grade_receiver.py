"""Safe Moodle grade-evidence intake policy for the first release."""

from uuid import UUID

from integrations.domain.moodle import MoodleFinalGradeEvidence


class ReviewRequiredGradeEvidenceReceiver:
    """Keep Moodle evidence non-authoritative until an explicit mapping exists.

    OwnSIS cannot infer an official course enrollment or grading scale from a
    Moodle user/course value alone. The surrounding integration service stores
    the evidence and marks it rejected for automatic application, leaving it
    visible for a later, explicit reconciliation flow.
    """

    async def accept_moodle_evidence(
        self,
        *,
        organization_id: UUID,
        evidence: MoodleFinalGradeEvidence,
        correlation_id: str,
    ) -> bool:
        """Decline automatic grade mutation without discarding the evidence."""

        del organization_id, evidence, correlation_id
        return False


__all__ = ["ReviewRequiredGradeEvidenceReceiver"]
