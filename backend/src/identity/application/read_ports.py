"""Read-only identity contracts for already verified provider subjects."""

from typing import Protocol

from identity.domain.models import OwnIDSubject


class IdentitySubjectReadRepository(Protocol):
    """Resolve an existing global identity without provisioning side effects."""

    async def find_by_provider_identity(
        self,
        *,
        issuer: str,
        subject: str,
    ) -> OwnIDSubject | None:
        """Return the exact issuer-subject binding when it already exists."""
        ...


__all__ = ["IdentitySubjectReadRepository"]
