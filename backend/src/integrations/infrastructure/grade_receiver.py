"""Safe Moodle grade-evidence intake policy for the first release."""

from uuid import UUID

from integrations.domain.moodle import GradeEvidenceDisposition
from integrations.domain.moodle import MoodleFinalGradeEvidence


class ReviewRequiredGradeEvidenceReceiver:
    """Keep Moodle evidence non-authoritative until a person explicitly accepts it.

    OwnSIS cannot infer an official course enrollment or grading scale from a
    Moodle user/course value alone. Intake stores the evidence as pending, and
    an authorized grading actor later accepts or rejects it through the
    grading module's explicit acceptance capability.
    """

    async def accept_moodle_evidence(
        self,
        *,
        organization_id: UUID,
        evidence: MoodleFinalGradeEvidence,
        correlation_id: str,
    ) -> GradeEvidenceDisposition:
        """Decline automatic grade mutation and request explicit review."""

        del organization_id, evidence, correlation_id
        return GradeEvidenceDisposition.REVIEW_REQUIRED


__all__ = ["ReviewRequiredGradeEvidenceReceiver"]
