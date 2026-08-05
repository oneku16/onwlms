"""MCP gateway revalidates identity, tenant, entitlement, and resource policy."""

from datetime import UTC
from datetime import datetime
from typing import cast
from uuid import UUID
from uuid import uuid7

import pytest

from core.context import TenantActorContext
from core.errors import AuthenticationError
from core.errors import AuthorizationError
from core.errors import NotFoundError
from entitlements.domain.models import FeatureCode
from entitlements.domain.models import ResolvedEntitlement
from identity.application.read_service import IdentitySubjectReadService
from identity.domain.models import OwnIDSubject
from mcp_gateway.application.gateway import ApplicationAuthorizedReadGateway
from mcp_gateway.application.owned_read_service import ActorOwnedReadService
from mcp_gateway.domain.read_models import ScheduleItem

NOW = datetime(2026, 8, 5, 12, tzinfo=UTC)


class FakeIdentities:
    """Resolve one exact provider pair without side effects."""

    def __init__(
        self,
        identity: OwnIDSubject,
    ) -> None:
        self.identity = identity
        self.calls = 0

    async def resolve_verified_subject(
        self,
        *,
        issuer: str,
        subject: str,
    ) -> OwnIDSubject:
        self.calls += 1
        if (issuer, subject) != (self.identity.issuer, self.identity.subject):
            raise AuthenticationError
        return self.identity


class FakeMemberships:
    """Resolve one subject into one exact active tenant context."""

    def __init__(
        self,
        *,
        identity_id: UUID,
        organization_id: UUID,
        permissions: frozenset[str],
    ) -> None:
        self.identity_id = identity_id
        self.organization_id = organization_id
        self.permissions = permissions
        self.calls = 0

    async def resolve_tenant_context(
        self,
        *,
        identity_subject_id: UUID,
        organization_id: UUID,
        correlation_id: str,
    ) -> TenantActorContext:
        self.calls += 1
        if (
            identity_subject_id != self.identity_id
            or organization_id != self.organization_id
        ):
            raise NotFoundError
        return TenantActorContext(
            subject_id=identity_subject_id,
            organization_id=organization_id,
            membership_id=uuid7(),
            correlation_id=correlation_id,
            permissions=self.permissions,
        )


class FakeEntitlements:
    """Record and return one MCP entitlement decision."""

    def __init__(
        self,
        *,
        enabled: bool,
    ) -> None:
        self.enabled = enabled
        self.calls = 0

    async def resolve_for_organization(
        self,
        *,
        organization_id: UUID,
        feature: FeatureCode,
        at: datetime,
    ) -> ResolvedEntitlement:
        assert organization_id
        assert feature is FeatureCode.MCP
        assert at == NOW
        self.calls += 1
        return ResolvedEntitlement(
            feature=feature,
            enabled=self.enabled,
            source="test",
        )


class FakeReads:
    """Record whether protected application reads were reached."""

    def __init__(self) -> None:
        self.schedule_calls = 0

    async def student_schedule(
        self,
        *,
        actor: TenantActorContext,
    ) -> list[ScheduleItem]:
        assert actor.organization_id
        self.schedule_calls += 1
        return []


class RecordingAudit:
    """Record privacy-safe invocation outcomes."""

    def __init__(self) -> None:
        self.outcomes: list[tuple[str, UUID | None, str]] = []

    async def record_mcp_invocation(
        self,
        *,
        tool: str,
        organization_id: UUID,
        actor_subject_id: UUID | None,
        correlation_id: str,
        outcome: str,
    ) -> None:
        assert organization_id
        assert correlation_id.startswith("mcp-")
        self.outcomes.append((tool, actor_subject_id, outcome))


def _gateway(
    *,
    enabled: bool = True,
) -> tuple[
    ApplicationAuthorizedReadGateway,
    FakeIdentities,
    FakeMemberships,
    FakeEntitlements,
    FakeReads,
    RecordingAudit,
    OwnIDSubject,
    UUID,
]:
    identity = OwnIDSubject(
        id=uuid7(),
        issuer="https://ownid.example",
        subject="verified-subject",
    )
    organization_id = uuid7()
    identities = FakeIdentities(identity)
    memberships = FakeMemberships(
        identity_id=identity.id,
        organization_id=organization_id,
        permissions=frozenset({"academics.student.read_own"}),
    )
    entitlements = FakeEntitlements(enabled=enabled)
    reads = FakeReads()
    audit = RecordingAudit()
    gateway = ApplicationAuthorizedReadGateway(
        ownid_issuer=identity.issuer,
        identities=cast(IdentitySubjectReadService, identities),
        memberships=memberships,
        reads=cast(ActorOwnedReadService, reads),
        entitlements=entitlements,
        audit=audit,
        clock=lambda: NOW,
    )
    return (
        gateway,
        identities,
        memberships,
        entitlements,
        reads,
        audit,
        identity,
        organization_id,
    )


async def test_cross_user_subject_is_denied_before_any_application_read() -> None:
    gateway, _, _, entitlements, reads, audit, _, organization_id = _gateway()

    with pytest.raises(AuthorizationError):
        await gateway.get_student_schedule(
            ownid_subject="another-subject",
            organization_id=organization_id,
        )

    assert entitlements.calls == 0
    assert reads.schedule_calls == 0
    assert audit.outcomes == [("get_own_schedule", None, "denied")]


async def test_cross_tenant_identifier_is_denied_before_entitled_read() -> None:
    gateway, _, _, entitlements, reads, audit, identity, _ = _gateway()

    with pytest.raises(AuthorizationError):
        await gateway.get_student_schedule(
            ownid_subject=identity.subject,
            organization_id=uuid7(),
        )

    assert entitlements.calls == 0
    assert reads.schedule_calls == 0
    assert audit.outcomes[0][2] == "denied"


async def test_disabled_mcp_entitlement_is_rechecked_and_denied() -> None:
    gateway, identities, memberships, entitlements, reads, audit, identity, org = (
        _gateway(enabled=False)
    )

    with pytest.raises(AuthorizationError):
        await gateway.get_student_schedule(
            ownid_subject=identity.subject,
            organization_id=org,
        )

    assert identities.calls == 1
    assert memberships.calls == 1
    assert entitlements.calls == 1
    assert reads.schedule_calls == 0
    assert audit.outcomes == [("get_own_schedule", identity.id, "denied")]


async def test_each_call_revalidates_subject_membership_and_entitlement() -> None:
    gateway, identities, memberships, entitlements, reads, audit, identity, org = (
        _gateway()
    )

    assert (
        await gateway.get_student_schedule(
            ownid_subject=identity.subject,
            organization_id=org,
        )
        == []
    )
    assert (
        await gateway.get_student_schedule(
            ownid_subject=identity.subject,
            organization_id=org,
        )
        == []
    )

    assert identities.calls == 2
    assert memberships.calls == 2
    assert entitlements.calls == 2
    assert reads.schedule_calls == 2
    assert [outcome for _, _, outcome in audit.outcomes] == [
        "succeeded",
        "succeeded",
    ]
