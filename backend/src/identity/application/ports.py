"""Ports owned by identity application workflows."""

from typing import Protocol
from uuid import UUID

from core.context import TenantActorContext
from identity.domain.models import OwnIDSubject
from identity.domain.models import PendingAuthorization
from identity.domain.models import ProviderAuthentication
from identity.domain.models import ProviderTokens
from identity.domain.models import StoredSession


class IdentityProvider(Protocol):
    """Translate the supported OwnID OIDC relying-party operations."""

    async def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        code_challenge: str,
    ) -> str:
        """Resolve OwnID metadata and build one authorization URL."""
        ...

    async def complete_authorization(
        self,
        *,
        code: str,
        code_verifier: str,
        expected_nonce: str,
    ) -> ProviderAuthentication:
        """Exchange an authorization code and verify the returned identity."""
        ...

    async def refresh(
        self,
        *,
        refresh_token: str,
    ) -> ProviderTokens:
        """Refresh provider tokens while preserving refresh-token rotation."""
        ...

    async def revoke(
        self,
        *,
        refresh_token: str,
    ) -> None:
        """Request revocation of one provider refresh token."""
        ...


class DevelopmentIdentity(Protocol):
    """Provide the explicitly enabled local/test authentication outcome."""

    async def authenticate_development(self) -> ProviderAuthentication:
        """Return one configured fake identity without accepting credentials."""
        ...


class SubjectRepository(Protocol):
    """Resolve the global OwnID subject independently of memberships."""

    async def resolve(
        self,
        *,
        issuer: str,
        subject: str,
        email: str | None,
        display_name: str | None,
    ) -> OwnIDSubject:
        """Resolve or atomically create one global issuer-subject binding."""
        ...

    async def get(
        self,
        *,
        subject_id: UUID,
    ) -> OwnIDSubject | None:
        """Return one global subject by its OwnSIS identifier."""
        ...

    async def is_platform_admin(
        self,
        *,
        subject_id: UUID,
    ) -> bool:
        """Return platform privilege kept separate from tenant membership."""
        ...


class SessionRepository(Protocol):
    """Persist hashed browser tokens and encrypted provider token material."""

    async def save_pending(
        self,
        pending: PendingAuthorization,
    ) -> None:
        """Persist one pending authorization request."""
        ...

    async def consume_pending(
        self,
        *,
        key_digest: str,
    ) -> PendingAuthorization | None:
        """Atomically consume a pending request so callbacks cannot replay."""
        ...

    async def save_session(
        self,
        session: StoredSession,
    ) -> None:
        """Persist a newly rotated server-side session."""
        ...

    async def get_session(
        self,
        *,
        key_digest: str,
    ) -> StoredSession | None:
        """Return an active server-side session by hashed browser token."""
        ...

    async def replace_tokens(
        self,
        *,
        key_digest: str,
        expected_version: int,
        tokens: ProviderTokens,
    ) -> bool:
        """Replace tokens only when the persisted session version still matches."""
        ...

    async def delete_session(
        self,
        *,
        key_digest: str,
    ) -> StoredSession | None:
        """Delete a local session and return its token material for revocation."""
        ...


class IdentityAuditSink(Protocol):
    """Record privacy-minimized identity security outcomes."""

    async def record_identity_event(
        self,
        *,
        action: str,
        subject_id: UUID | None,
        correlation_id: str,
        outcome: str,
    ) -> None:
        """Append one identity event without authentication or token material."""
        ...


class TenantContextResolver(Protocol):
    """Resolve a verified identity into one active tenant membership context."""

    async def resolve_tenant_context(
        self,
        *,
        identity_subject_id: UUID,
        organization_id: UUID,
        correlation_id: str,
    ) -> TenantActorContext:
        """Fail closed unless identity, organization, and membership agree."""
        ...


__all__ = [
    "DevelopmentIdentity",
    "IdentityAuditSink",
    "IdentityProvider",
    "SessionRepository",
    "SubjectRepository",
    "TenantContextResolver",
]
