"""Framework-independent identity and server-session values."""

from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class OwnIDSubject:
    """Represent one global identity asserted by the configured OwnID issuer."""

    id: UUID
    issuer: str = field(repr=False)
    subject: str = field(repr=False)
    email: str | None = field(default=None, repr=False)
    display_name: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class PlatformAdministrator:
    """Represent separately governed global platform privilege."""

    subject_id: UUID
    active: bool


@dataclass(frozen=True, slots=True)
class ProviderTokens:
    """Carry verified provider tokens only between trusted server boundaries."""

    access_token: str = field(repr=False)
    id_token: str = field(repr=False)
    expires_at: datetime
    refresh_token: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class ProviderAuthentication:
    """Describe a verified OwnID authentication result and its server tokens."""

    issuer: str = field(repr=False)
    subject: str = field(repr=False)
    email: str | None = field(repr=False)
    display_name: str | None = field(repr=False)
    tokens: ProviderTokens = field(repr=False)


@dataclass(frozen=True, slots=True)
class PendingAuthorization:
    """Hold a single-use OIDC authorization request in server-side storage."""

    key_digest: str
    state_digest: str
    nonce: str = field(repr=False)
    code_verifier: str = field(repr=False)
    return_path: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class StoredSession:
    """Hold server-side application-session state without the browser token."""

    key_digest: str
    subject_id: UUID
    csrf_digest: str
    tokens: ProviderTokens = field(repr=False)
    expires_at: datetime
    version: int = 1


@dataclass(frozen=True, slots=True)
class CurrentSession:
    """Expose the safe identity facts associated with an active session."""

    subject: OwnIDSubject
    is_platform_admin: bool
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AuthorizationStart:
    """Return the provider redirect and opaque pending-flow browser token."""

    authorization_url: str
    pending_token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class EstablishedSession:
    """Return newly rotated browser secrets and their safe identity context."""

    session_token: str = field(repr=False)
    csrf_token: str = field(repr=False)
    current: CurrentSession
    return_path: str


@dataclass(frozen=True, slots=True)
class LogoutResult:
    """Report local logout success and independent provider revocation status."""

    provider_revoked: bool
    provider_logout_url: str | None = None


__all__ = [
    "AuthorizationStart",
    "CurrentSession",
    "EstablishedSession",
    "LogoutResult",
    "OwnIDSubject",
    "PendingAuthorization",
    "PlatformAdministrator",
    "ProviderAuthentication",
    "ProviderTokens",
    "StoredSession",
]
