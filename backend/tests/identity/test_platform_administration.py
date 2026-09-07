"""Behavioral tests for governed platform-administrator lifecycle."""

from uuid import UUID
from uuid import uuid4

import pytest

from core.context import PlatformActorContext
from core.errors import AuthorizationError
from identity.application.platform_administration import (
    MANAGE_PLATFORM_ADMINISTRATORS_PERMISSION,
)
from identity.application.platform_administration import PlatformAdministrationService
from identity.domain.exceptions import FinalPlatformAdministratorError
from identity.domain.exceptions import PlatformAdministratorBootstrapClosedError
from identity.domain.exceptions import PlatformAdministratorNotFoundError
from identity.domain.models import PlatformAdministrator

BOOTSTRAP_SECRET = "bootstrap-secret-with-at-least-32-characters"


class FakePlatformAdministratorRepository:
    """Model the repository's serialized first/final-admin invariants."""

    def __init__(self, known_subjects: set[UUID]) -> None:
        self.known_subjects = known_subjects
        self.values: dict[UUID, bool] = {}
        self.mutations = 0

    async def bootstrap(self, *, subject_id: UUID) -> PlatformAdministrator:
        if any(self.values.values()):
            raise PlatformAdministratorBootstrapClosedError
        return await self.assign(subject_id=subject_id)

    async def assign(self, *, subject_id: UUID) -> PlatformAdministrator:
        if subject_id not in self.known_subjects:
            raise PlatformAdministratorNotFoundError
        self.values[subject_id] = True
        self.mutations += 1
        return PlatformAdministrator(subject_id=subject_id, active=True)

    async def revoke(self, *, subject_id: UUID) -> PlatformAdministrator:
        if subject_id not in self.values:
            raise PlatformAdministratorNotFoundError
        if self.values[subject_id] and sum(self.values.values()) <= 1:
            raise FinalPlatformAdministratorError
        self.values[subject_id] = False
        self.mutations += 1
        return PlatformAdministrator(subject_id=subject_id, active=False)

    async def list_all(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[PlatformAdministrator]:
        values = [
            PlatformAdministrator(subject_id=subject_id, active=active)
            for subject_id, active in self.values.items()
        ]
        return values[offset : offset + limit]


class FakePlatformAdministrationAuditSink:
    def __init__(self, *, fail_on_action: str | None = None) -> None:
        self.fail_on_action = fail_on_action
        self.events: list[tuple[str, UUID, UUID, str]] = []

    async def record_platform_administrator_event(
        self,
        *,
        action: str,
        actor_subject_id: UUID,
        target_subject_id: UUID,
        correlation_id: str,
        outcome: str,
    ) -> None:
        assert correlation_id
        if action == self.fail_on_action:
            raise RuntimeError("audit unavailable")
        self.events.append((action, actor_subject_id, target_subject_id, outcome))


def _actor(subject_id: UUID) -> PlatformActorContext:
    return PlatformActorContext(
        subject_id=subject_id,
        correlation_id="correlation-1",
        permissions=frozenset({MANAGE_PLATFORM_ADMINISTRATORS_PERMISSION}),
    )


async def test_bootstrap_is_single_use_and_audited_before_assignment() -> None:
    subject_id = uuid4()
    repository = FakePlatformAdministratorRepository({subject_id})
    audit = FakePlatformAdministrationAuditSink()
    service = PlatformAdministrationService(
        administrators=repository,
        audit=audit,
        bootstrap_secret=BOOTSTRAP_SECRET,
    )

    administrator = await service.bootstrap(
        subject_id=subject_id,
        supplied_secret=BOOTSTRAP_SECRET,
        correlation_id="correlation-1",
    )

    assert administrator.active is True
    assert audit.events == [
        (
            "platform_administrator.bootstrap_intent",
            subject_id,
            subject_id,
            "intent_recorded",
        ),
        (
            "platform_administrator.bootstrapped",
            subject_id,
            subject_id,
            "succeeded",
        ),
    ]
    with pytest.raises(PlatformAdministratorBootstrapClosedError):
        await service.bootstrap(
            subject_id=subject_id,
            supplied_secret=BOOTSTRAP_SECRET,
            correlation_id="correlation-2",
        )


async def test_invalid_bootstrap_secret_never_mutates_assignment() -> None:
    subject_id = uuid4()
    repository = FakePlatformAdministratorRepository({subject_id})
    service = PlatformAdministrationService(
        administrators=repository,
        audit=FakePlatformAdministrationAuditSink(),
        bootstrap_secret=BOOTSTRAP_SECRET,
    )

    with pytest.raises(AuthorizationError):
        await service.bootstrap(
            subject_id=subject_id,
            supplied_secret="wrong-secret",
            correlation_id="correlation-1",
        )

    assert repository.mutations == 0


async def test_assignment_intent_audit_failure_aborts_mutation() -> None:
    actor_id = uuid4()
    target_id = uuid4()
    repository = FakePlatformAdministratorRepository({actor_id, target_id})
    repository.values[actor_id] = True
    service = PlatformAdministrationService(
        administrators=repository,
        audit=FakePlatformAdministrationAuditSink(
            fail_on_action="platform_administrator.assignment_intent"
        ),
        bootstrap_secret=BOOTSTRAP_SECRET,
    )

    with pytest.raises(RuntimeError, match="audit unavailable"):
        await service.assign(actor=_actor(actor_id), subject_id=target_id)

    assert target_id not in repository.values
    assert repository.mutations == 0


async def test_final_platform_administrator_cannot_be_revoked() -> None:
    subject_id = uuid4()
    repository = FakePlatformAdministratorRepository({subject_id})
    repository.values[subject_id] = True
    service = PlatformAdministrationService(
        administrators=repository,
        audit=FakePlatformAdministrationAuditSink(),
        bootstrap_secret=BOOTSTRAP_SECRET,
    )

    with pytest.raises(FinalPlatformAdministratorError):
        await service.revoke(actor=_actor(subject_id), subject_id=subject_id)

    assert repository.values[subject_id] is True


async def test_admin_may_be_revoked_when_another_active_admin_remains() -> None:
    actor_id = uuid4()
    target_id = uuid4()
    repository = FakePlatformAdministratorRepository({actor_id, target_id})
    repository.values = {actor_id: True, target_id: True}
    service = PlatformAdministrationService(
        administrators=repository,
        audit=FakePlatformAdministrationAuditSink(),
        bootstrap_secret=BOOTSTRAP_SECRET,
    )

    revoked = await service.revoke(actor=_actor(actor_id), subject_id=target_id)

    assert revoked == PlatformAdministrator(subject_id=target_id, active=False)
    assert repository.values == {actor_id: True, target_id: False}
