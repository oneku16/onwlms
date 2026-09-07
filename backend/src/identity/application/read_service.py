"""Side-effect-free identity resolution for trusted bearer authentication."""

from core.errors import AuthenticationError
from identity.application.read_ports import IdentitySubjectReadRepository
from identity.domain.models import OwnIDSubject


class IdentitySubjectReadService:
    """Resolve verified OwnID claims to an existing internal subject."""

    def __init__(
        self,
        repository: IdentitySubjectReadRepository,
    ) -> None:
        self._repository = repository

    async def resolve_verified_subject(
        self,
        *,
        issuer: str,
        subject: str,
    ) -> OwnIDSubject:
        """Fail closed unless the exact provider binding already exists."""

        identity = await self._repository.find_by_provider_identity(
            issuer=issuer.rstrip("/"),
            subject=subject,
        )
        if identity is None:
            raise AuthenticationError("Verified OwnID subject is not registered")
        return identity


__all__ = ["IdentitySubjectReadService"]
