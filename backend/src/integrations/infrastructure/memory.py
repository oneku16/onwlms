"""Functional in-memory adapters for Moodle integration application ports."""

from datetime import datetime
from uuid import UUID

from core.errors import ConflictError
from core.errors import NotFoundError
from core.identifiers import new_uuid7
from core.time import utc_now
from integrations.domain.moodle import GradeEvidenceStatus
from integrations.domain.moodle import IntegrationStatus
from integrations.domain.moodle import MoodleConfiguration
from integrations.domain.moodle import MoodleFinalGradeEvidence
from integrations.domain.moodle import MoodleGradeEvidenceRecord
from integrations.domain.moodle import MoodleGradeReconciliationRun

TenantKey = tuple[UUID, UUID]


class InMemoryMoodleIntegrationRepository:
    """Preserve tenant scoping and evidence uniqueness in memory."""

    def __init__(self) -> None:
        self.configurations: dict[UUID, MoodleConfiguration] = {}
        self.encrypted_tokens: dict[UUID, str] = {}
        self.encrypted_event_secrets: dict[UUID, str] = {}
        self.mappings: dict[tuple[UUID, str, UUID], str] = {}
        self.evidence: dict[TenantKey, MoodleGradeEvidenceRecord] = {}
        self.failures: list[tuple[UUID, str]] = []
        self.successes: list[UUID] = []

    async def configure(
        self,
        *,
        organization_id: UUID,
        base_url: str,
        encrypted_token: str,
    ) -> MoodleConfiguration:
        """Store protected configuration and reset failure state."""

        configuration = MoodleConfiguration(
            organization_id=organization_id,
            base_url=base_url,
            status=IntegrationStatus.CONFIGURED,
            last_success_at=None,
            last_error_code=None,
            grade_events_configured=organization_id in self.encrypted_event_secrets,
        )
        self.configurations[organization_id] = configuration
        self.encrypted_tokens[organization_id] = encrypted_token
        return configuration

    async def get_configuration(
        self,
        organization_id: UUID,
    ) -> MoodleConfiguration | None:
        """Return safe configuration for one tenant."""

        return self.configurations.get(organization_id)

    async def get_encrypted_token(
        self,
        organization_id: UUID,
    ) -> str | None:
        """Return the protected credential for one tenant."""

        return self.encrypted_tokens.get(organization_id)

    async def set_grade_event_secret(
        self,
        *,
        organization_id: UUID,
        encrypted_secret: str,
    ) -> MoodleConfiguration:
        """Store the protected signing secret on an existing configuration."""

        configuration = self.configurations.get(organization_id)
        if configuration is None:
            raise NotFoundError
        self.encrypted_event_secrets[organization_id] = encrypted_secret
        updated = MoodleConfiguration(
            organization_id=configuration.organization_id,
            base_url=configuration.base_url,
            status=configuration.status,
            last_success_at=configuration.last_success_at,
            last_error_code=configuration.last_error_code,
            grade_events_configured=True,
        )
        self.configurations[organization_id] = updated
        return updated

    async def get_encrypted_grade_event_secret(
        self,
        organization_id: UUID,
    ) -> str | None:
        """Return the protected signing secret for one tenant."""

        return self.encrypted_event_secrets.get(organization_id)

    async def put_mapping(
        self,
        *,
        organization_id: UUID,
        entity_type: str,
        entity_id: UUID,
        external_id: str,
    ) -> None:
        """Store one tenant mapping."""

        self.mappings[(organization_id, entity_type, entity_id)] = external_id

    async def get_mapping(
        self,
        *,
        organization_id: UUID,
        entity_type: str,
        entity_id: UUID,
    ) -> str | None:
        """Resolve one tenant mapping."""

        return self.mappings.get((organization_id, entity_type, entity_id))

    async def get_entity_id(
        self,
        *,
        organization_id: UUID,
        entity_type: str,
        external_id: str,
    ) -> UUID | None:
        """Resolve one tenant mapping from its external identifier."""

        for (tenant_id, kind, entity_id), value in self.mappings.items():
            if (
                tenant_id == organization_id
                and kind == entity_type
                and value == external_id
            ):
                return entity_id
        return None

    async def accept_grade_event_once(
        self,
        *,
        organization_id: UUID,
        evidence: MoodleFinalGradeEvidence,
    ) -> bool:
        """Store one external event key at most once per tenant."""

        if self._by_event(organization_id, evidence.external_event_id) is not None:
            return False
        record = MoodleGradeEvidenceRecord(
            id=new_uuid7(),
            organization_id=organization_id,
            external_event_id=evidence.external_event_id,
            course_offering_id=evidence.course_offering_id,
            student_person_id=evidence.student_person_id,
            grade_value=evidence.grade_value,
            observed_at=evidence.observed_at,
            source_version=evidence.source_version,
            status=GradeEvidenceStatus.PENDING,
            reason_code=None,
            received_at=utc_now(),
        )
        self.evidence[(organization_id, record.id)] = record
        return True

    async def mark_grade_event_outcome(
        self,
        *,
        organization_id: UUID,
        external_event_id: str,
        status: GradeEvidenceStatus,
        reason_code: str | None,
    ) -> None:
        """Record the intake outcome for one stored event."""

        record = self._by_event(organization_id, external_event_id)
        if record is None:
            raise NotFoundError
        self.evidence[(organization_id, record.id)] = MoodleGradeEvidenceRecord(
            id=record.id,
            organization_id=record.organization_id,
            external_event_id=record.external_event_id,
            course_offering_id=record.course_offering_id,
            student_person_id=record.student_person_id,
            grade_value=record.grade_value,
            observed_at=record.observed_at,
            source_version=record.source_version,
            status=status,
            reason_code=reason_code,
            received_at=record.received_at,
        )

    async def get_grade_evidence(
        self,
        *,
        organization_id: UUID,
        evidence_id: UUID,
    ) -> MoodleGradeEvidenceRecord | None:
        """Return one evidence record from exactly one tenant."""

        return self.evidence.get((organization_id, evidence_id))

    async def get_grade_evidence_by_event(
        self,
        *,
        organization_id: UUID,
        external_event_id: str,
    ) -> MoodleGradeEvidenceRecord | None:
        """Return stored evidence for one tenant external event key."""

        return self._by_event(organization_id, external_event_id)

    async def list_grade_evidence(
        self,
        *,
        organization_id: UUID,
        status: GradeEvidenceStatus | None,
        course_offering_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[MoodleGradeEvidenceRecord, ...]:
        """Return a newest-first stable page of tenant evidence."""

        records = sorted(
            (
                record
                for (tenant_id, _), record in self.evidence.items()
                if tenant_id == organization_id
                and (status is None or record.status is status)
                and (
                    course_offering_id is None
                    or record.course_offering_id == course_offering_id
                )
            ),
            key=lambda record: (record.received_at, str(record.id)),
            reverse=True,
        )
        return tuple(records[offset : offset + limit])

    async def resolve_grade_evidence(
        self,
        *,
        organization_id: UUID,
        evidence_id: UUID,
        status: GradeEvidenceStatus,
        reason_code: str | None,
        final_grade_id: UUID | None,
        resolved_by: UUID,
        resolved_at: datetime,
    ) -> MoodleGradeEvidenceRecord:
        """Resolve pending evidence exactly once."""

        record = self.evidence.get((organization_id, evidence_id))
        if record is None:
            raise NotFoundError("Moodle grade evidence was not found.")
        if record.status is not GradeEvidenceStatus.PENDING:
            raise ConflictError("Moodle grade evidence was already resolved.")
        resolved = MoodleGradeEvidenceRecord(
            id=record.id,
            organization_id=record.organization_id,
            external_event_id=record.external_event_id,
            course_offering_id=record.course_offering_id,
            student_person_id=record.student_person_id,
            grade_value=record.grade_value,
            observed_at=record.observed_at,
            source_version=record.source_version,
            status=status,
            reason_code=reason_code,
            received_at=record.received_at,
            accepted_final_grade_id=final_grade_id,
            resolved_by=resolved_by,
            resolved_at=resolved_at,
        )
        self.evidence[(organization_id, evidence_id)] = resolved
        return resolved

    async def record_success(
        self,
        organization_id: UUID,
    ) -> None:
        """Record a successful provider exchange."""

        self.successes.append(organization_id)
        configuration = self.configurations.get(organization_id)
        if configuration is not None:
            self.configurations[organization_id] = MoodleConfiguration(
                organization_id=configuration.organization_id,
                base_url=configuration.base_url,
                status=IntegrationStatus.HEALTHY,
                last_success_at=utc_now(),
                last_error_code=None,
                grade_events_configured=configuration.grade_events_configured,
            )

    async def record_failure(
        self,
        *,
        organization_id: UUID,
        error_code: str,
    ) -> None:
        """Record a safe degraded state."""

        self.failures.append((organization_id, error_code))
        configuration = self.configurations.get(organization_id)
        if configuration is not None:
            self.configurations[organization_id] = MoodleConfiguration(
                organization_id=configuration.organization_id,
                base_url=configuration.base_url,
                status=IntegrationStatus.DEGRADED,
                last_success_at=configuration.last_success_at,
                last_error_code=error_code,
                grade_events_configured=configuration.grade_events_configured,
            )

    def _by_event(
        self,
        organization_id: UUID,
        external_event_id: str,
    ) -> MoodleGradeEvidenceRecord | None:
        """Find one tenant record by its external event key."""

        return next(
            (
                record
                for (tenant_id, _), record in self.evidence.items()
                if tenant_id == organization_id
                and record.external_event_id == external_event_id
            ),
            None,
        )


class InMemoryMoodleReconciliationRunRepository:
    """Keep tenant reconciliation runs in memory."""

    def __init__(self) -> None:
        self.runs: dict[TenantKey, MoodleGradeReconciliationRun] = {}

    async def create_run(
        self,
        run: MoodleGradeReconciliationRun,
    ) -> None:
        """Persist one newly started run."""

        self.runs[(run.organization_id, run.id)] = run

    async def complete_run(
        self,
        run: MoodleGradeReconciliationRun,
    ) -> None:
        """Persist the terminal outcome of an existing run."""

        if (run.organization_id, run.id) not in self.runs:
            raise NotFoundError("Reconciliation run was not found.")
        self.runs[(run.organization_id, run.id)] = run

    async def get_run(
        self,
        *,
        organization_id: UUID,
        run_id: UUID,
    ) -> MoodleGradeReconciliationRun | None:
        """Return one run from exactly one tenant."""

        return self.runs.get((organization_id, run_id))

    async def list_runs(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[MoodleGradeReconciliationRun, ...]:
        """Return a newest-first stable page of tenant runs."""

        runs = sorted(
            (
                run
                for (tenant_id, _), run in self.runs.items()
                if tenant_id == organization_id
            ),
            key=lambda run: (run.started_at, str(run.id)),
            reverse=True,
        )
        return tuple(runs[offset : offset + limit])


__all__ = [
    "InMemoryMoodleIntegrationRepository",
    "InMemoryMoodleReconciliationRunRepository",
]
