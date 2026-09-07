"""Secure OIDC and server-side application-session orchestration."""

import base64
import hashlib
import secrets
from collections.abc import Callable
from datetime import datetime
from datetime import timedelta
from urllib.parse import unquote
from urllib.parse import urlsplit

from core.time import utc_now
from identity.application.ports import DevelopmentIdentity
from identity.application.ports import IdentityAuditSink
from identity.application.ports import IdentityProvider
from identity.application.ports import SessionRepository
from identity.application.ports import SubjectRepository
from identity.domain.exceptions import InvalidAuthorizationFlowError
from identity.domain.exceptions import InvalidCSRFTokenError
from identity.domain.exceptions import InvalidSessionError
from identity.domain.exceptions import OwnIDProviderError
from identity.domain.exceptions import SessionRefreshConflictError
from identity.domain.models import AuthorizationStart
from identity.domain.models import CurrentSession
from identity.domain.models import EstablishedSession
from identity.domain.models import LogoutResult
from identity.domain.models import PendingAuthorization
from identity.domain.models import ProviderAuthentication
from identity.domain.models import StoredSession


class AuthenticationService:
    """Establish, validate, rotate, refresh, and revoke browser sessions."""

    def __init__(
        self,
        *,
        provider: IdentityProvider,
        subjects: SubjectRepository,
        sessions: SessionRepository,
        audit: IdentityAuditSink,
        session_ttl_seconds: int,
        development_identity: DevelopmentIdentity | None = None,
        pending_ttl_seconds: int = 600,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._provider = provider
        self._subjects = subjects
        self._sessions = sessions
        self._audit = audit
        self._session_ttl_seconds = session_ttl_seconds
        self._development_identity = development_identity
        self._pending_ttl_seconds = pending_ttl_seconds
        self._clock = clock

    async def start_login(
        self,
        *,
        return_path: str,
    ) -> AuthorizationStart:
        """Create a single-use PKCE flow and return its provider redirect URL."""

        safe_return_path = self._validate_return_path(return_path)
        pending_token = secrets.token_urlsafe(32)
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        challenge = self._code_challenge(code_verifier)
        await self._sessions.save_pending(
            PendingAuthorization(
                key_digest=self._digest(pending_token),
                state_digest=self._digest(state),
                nonce=nonce,
                code_verifier=code_verifier,
                return_path=safe_return_path,
                expires_at=self._clock() + timedelta(seconds=self._pending_ttl_seconds),
            )
        )
        return AuthorizationStart(
            authorization_url=await self._provider.authorization_url(
                state=state,
                nonce=nonce,
                code_challenge=challenge,
            ),
            pending_token=pending_token,
        )

    async def complete_login(
        self,
        *,
        pending_token: str,
        state: str,
        code: str,
        existing_session_token: str | None,
        correlation_id: str,
    ) -> EstablishedSession:
        """Consume a callback and issue a newly rotated application session."""

        pending = await self._sessions.consume_pending(
            key_digest=self._digest(pending_token),
        )
        if pending is None or pending.expires_at <= self._clock():
            await self._audit.record_identity_event(
                action="identity.login",
                subject_id=None,
                correlation_id=correlation_id,
                outcome="denied",
            )
            raise InvalidAuthorizationFlowError
        if not self._secure_equals(pending.state_digest, self._digest(state)):
            await self._audit.record_identity_event(
                action="identity.login",
                subject_id=None,
                correlation_id=correlation_id,
                outcome="denied",
            )
            raise InvalidAuthorizationFlowError
        authentication = await self._provider.complete_authorization(
            code=code,
            code_verifier=pending.code_verifier,
            expected_nonce=pending.nonce,
        )
        return await self._establish_session(
            authentication=authentication,
            return_path=pending.return_path,
            existing_session_token=existing_session_token,
            correlation_id=correlation_id,
        )

    async def development_login(
        self,
        *,
        return_path: str,
        existing_session_token: str | None,
        correlation_id: str,
    ) -> EstablishedSession:
        """Establish the explicit local/test identity or fail when not composed."""

        if self._development_identity is None:
            raise InvalidAuthorizationFlowError
        authentication = await self._development_identity.authenticate_development()
        return await self._establish_session(
            authentication=authentication,
            return_path=self._validate_return_path(return_path),
            existing_session_token=existing_session_token,
            correlation_id=correlation_id,
        )

    async def get_current_session(
        self,
        *,
        session_token: str,
        correlation_id: str,
    ) -> CurrentSession:
        """Return a locally and provider-active session without exposing tokens."""

        # A provider check happens outside the database transaction. If a
        # concurrent refresh rotates the token family while that check is in
        # flight, a version-conditional delete must not remove the fresh session.
        for _ in range(2):
            stored = await self._require_session(session_token=session_token)
            subject = await self._subjects.get(subject_id=stored.subject_id)
            if subject is None:
                await self._sessions.delete_session(key_digest=stored.key_digest)
                raise InvalidSessionError
            if await self._provider.is_session_active(
                tokens=stored.tokens,
                expected_subject=subject.subject,
            ):
                return CurrentSession(
                    subject=subject,
                    is_platform_admin=await self._subjects.is_platform_admin(
                        subject_id=subject.id,
                    ),
                    expires_at=stored.expires_at,
                )
            deleted = await self._sessions.delete_session_if_version(
                key_digest=stored.key_digest,
                expected_version=stored.version,
            )
            if deleted is not None:
                await self._audit.record_identity_event(
                    action="identity.session_invalidated",
                    subject_id=subject.id,
                    correlation_id=correlation_id,
                    outcome="provider_inactive",
                )
                raise InvalidSessionError
        # Repeated concurrent rotation is denied without deleting whichever
        # version won the race.
        raise InvalidSessionError

    async def refresh_session(
        self,
        *,
        session_token: str,
        csrf_token: str,
        correlation_id: str,
    ) -> CurrentSession:
        """Refresh provider tokens after validating session-bound CSRF state."""

        stored = await self._require_session(session_token=session_token)
        self._require_csrf(stored=stored, supplied=csrf_token)
        provider_error: OwnIDProviderError | None = None
        async with self._sessions.lock_for_refresh(
            key_digest=stored.key_digest,
        ) as claim:
            if claim is None:
                raise InvalidSessionError
            locked = claim.stored
            self._require_csrf(stored=locked, supplied=csrf_token)
            if locked.version != stored.version:
                raise SessionRefreshConflictError(
                    "The session was already refreshed; retry the request."
                )
            refresh_token = locked.tokens.refresh_token
            if refresh_token is None:
                raise InvalidSessionError
            try:
                refreshed = await self._provider.refresh(
                    refresh_token=refresh_token,
                )
            except OwnIDProviderError as exc:
                await claim.delete()
                provider_error = exc
            else:
                await claim.replace_tokens(refreshed)
        if provider_error is not None:
            await self._audit.record_identity_event(
                action="identity.session_invalidated",
                subject_id=stored.subject_id,
                correlation_id=correlation_id,
                outcome="provider_refresh_failed",
            )
            raise provider_error
        return await self.get_current_session(
            session_token=session_token,
            correlation_id=correlation_id,
        )

    async def logout(
        self,
        *,
        session_token: str,
        csrf_token: str,
        correlation_id: str,
    ) -> LogoutResult:
        """Invalidate the local session before best-effort provider revocation."""

        stored = await self._require_session(session_token=session_token)
        self._require_csrf(stored=stored, supplied=csrf_token)
        deleted = await self._sessions.delete_session(
            key_digest=stored.key_digest,
        )
        if deleted is None:
            raise InvalidSessionError
        provider_revoked = True
        refresh_token = deleted.tokens.refresh_token
        if refresh_token is not None:
            try:
                await self._provider.revoke(refresh_token=refresh_token)
            except OwnIDProviderError:
                provider_revoked = False
        provider_logout_url: str | None = None
        try:
            provider_logout_url = await self._provider.end_session_url(
                id_token=deleted.tokens.id_token,
                state=secrets.token_urlsafe(32),
            )
        except OwnIDProviderError:
            provider_logout_url = None
        await self._audit.record_identity_event(
            action="identity.logout",
            subject_id=stored.subject_id,
            correlation_id=correlation_id,
            outcome="succeeded",
        )
        return LogoutResult(
            provider_revoked=provider_revoked,
            provider_logout_url=provider_logout_url,
        )

    async def validate_csrf(
        self,
        *,
        session_token: str,
        csrf_token: str,
    ) -> None:
        """Validate CSRF binding for a state-changing cookie-authenticated request."""

        stored = await self._require_session(session_token=session_token)
        self._require_csrf(stored=stored, supplied=csrf_token)

    async def _require_session(
        self,
        *,
        session_token: str,
    ) -> StoredSession:
        """Resolve a non-expired session and remove expired state eagerly."""

        if not session_token:
            raise InvalidSessionError
        key_digest = self._digest(session_token)
        stored = await self._sessions.get_session(key_digest=key_digest)
        if stored is None:
            raise InvalidSessionError
        if stored.expires_at <= self._clock():
            await self._sessions.delete_session(key_digest=key_digest)
            raise InvalidSessionError
        return stored

    async def _establish_session(
        self,
        *,
        authentication: ProviderAuthentication,
        return_path: str,
        existing_session_token: str | None,
        correlation_id: str,
    ) -> EstablishedSession:
        """Resolve a subject, rotate browser secrets, persist, and audit login."""

        subject = await self._subjects.resolve(
            issuer=authentication.issuer,
            subject=authentication.subject,
            email=authentication.email,
            display_name=authentication.display_name,
        )
        if existing_session_token:
            await self._sessions.delete_session(
                key_digest=self._digest(existing_session_token),
            )
        session_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        expires_at = self._clock() + timedelta(seconds=self._session_ttl_seconds)
        await self._sessions.save_session(
            StoredSession(
                key_digest=self._digest(session_token),
                subject_id=subject.id,
                csrf_digest=self._digest(csrf_token),
                tokens=authentication.tokens,
                expires_at=expires_at,
            )
        )
        current = CurrentSession(
            subject=subject,
            is_platform_admin=await self._subjects.is_platform_admin(
                subject_id=subject.id,
            ),
            expires_at=expires_at,
        )
        await self._audit.record_identity_event(
            action="identity.login",
            subject_id=subject.id,
            correlation_id=correlation_id,
            outcome="succeeded",
        )
        return EstablishedSession(
            session_token=session_token,
            csrf_token=csrf_token,
            current=current,
            return_path=return_path,
        )

    @classmethod
    def _require_csrf(
        cls,
        *,
        stored: StoredSession,
        supplied: str,
    ) -> None:
        """Reject absent or non-matching CSRF tokens in constant time."""

        if not supplied or not cls._secure_equals(
            stored.csrf_digest,
            cls._digest(supplied),
        ):
            raise InvalidCSRFTokenError("Invalid CSRF token")

    @staticmethod
    def _validate_return_path(return_path: str) -> str:
        """Allow one local absolute path and reject encoded traversal or origins."""

        candidate = return_path or "/"
        parsed = urlsplit(candidate)
        decoded_path = unquote(parsed.path)
        segments = decoded_path.replace("\\", "/").split("/")
        if (
            parsed.scheme
            or parsed.netloc
            or not candidate.startswith("/")
            or candidate.startswith("//")
            or "\\" in candidate
            or decoded_path.startswith("//")
            or "\\" in decoded_path
            or ".." in segments
            or any(ord(character) < 32 for character in candidate)
            or any(ord(character) < 32 for character in decoded_path)
        ):
            raise InvalidAuthorizationFlowError
        return candidate

    @staticmethod
    def _code_challenge(code_verifier: str) -> str:
        """Build an RFC 7636 S256 challenge for one verifier."""

        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    @staticmethod
    def _digest(value: str) -> str:
        """Hash one high-entropy opaque value before persistence."""

        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _secure_equals(left: str, right: str) -> bool:
        """Compare secret-derived values in constant time and fail closed."""

        try:
            return secrets.compare_digest(left, right)
        except TypeError, ValueError:
            return False


__all__ = ["AuthenticationService"]
