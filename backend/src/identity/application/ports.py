"""Ports owned by identity application workflows."""

from contextlib import AbstractAsyncContextManager
from typing import Protocol
from uuid import UUID

from core.context import TenantActorContext
from identity.domain.models import OwnIDSubject
from identity.domain.models import PendingAuthorization
from identity.domain.models import PlatformAdministrator
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

    async def is_session_active(
        self,
        *,
        tokens: ProviderTokens,
        expected_subject: str,
    ) -> bool:
        """Check the current OwnID token family without trusting browser claims."""
        ...

    async def end_session_url(
        self,
        *,
        id_token: str,
        state: str,
    ) -> str | None:
        """Build the provider browser-logout URL when discovery supports it."""
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

    def lock_for_refresh(
        self,
        *,
        key_digest: str,
    ) -> AbstractAsyncContextManager[SessionRefreshClaim | None]:
        """Lock one session across a single provider refresh-token exchange."""
        ...

    async def delete_session(
        self,
        *,
        key_digest: str,
    ) -> StoredSession | None:
        """Delete a local session and return its token material for revocation."""
        ...

    async def delete_session_if_version(
        self,
        *,
        key_digest: str,
        expected_version: int,
    ) -> StoredSession | None:
        """Delete only the exact session version that was previously checked."""
        ...


class SessionRefreshClaim(Protocol):
    """Mutate one row-locked session without opening a nested transaction."""

    @property
    def stored(self) -> StoredSession:
        """Return the exact session state protected by the row lock."""
        ...

    async def replace_tokens(self, tokens: ProviderTokens) -> None:
        """Persist one successful provider rotation in the held transaction."""
        ...

    async def delete(self) -> None:
        """Delete the held session after a provider refresh failure."""
        ...


class PlatformAdministratorRepository(Protocol):
    """Govern global administrator assignments behind atomic persistence rules."""

    async def bootstrap(self, *, subject_id: UUID) -> PlatformAdministrator:
        """Assign the first administrator only while none is active."""
        ...

    async def assign(self, *, subject_id: UUID) -> PlatformAdministrator:
        """Create or reactivate one administrator assignment."""
        ...

    async def revoke(self, *, subject_id: UUID) -> PlatformAdministrator:
        """Revoke one assignment without permitting a final-admin race."""
        ...

    async def list_all(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[PlatformAdministrator]:
        """List bounded administrator assignments without identity claims."""
        ...


class PlatformAdministrationAuditSink(Protocol):
    """Record privacy-minimized global privilege governance evidence."""

    async def record_platform_administrator_event(
        self,
        *,
        action: str,
        actor_subject_id: UUID,
        target_subject_id: UUID,
        correlation_id: str,
        outcome: str,
    ) -> None:
        """Append one intent or outcome with separate actor and target identity."""
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
    "PlatformAdministrationAuditSink",
    "PlatformAdministratorRepository",
    "SessionRefreshClaim",
    "SessionRepository",
    "SubjectRepository",
    "TenantContextResolver",
]
