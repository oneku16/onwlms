"""Behavioral tests for OIDC state, session rotation, CSRF, and logout."""

import asyncio
import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from urllib.parse import parse_qs
from urllib.parse import urlsplit
from uuid import UUID
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from httpx import ASGITransport
from httpx import AsyncClient
from httpx import MockTransport
from httpx import Request as HTTPXRequest
from httpx import Response

from core.http import install_error_handlers
from core.settings import AppEnvironment
from core.settings import Settings
from identity.application.service import AuthenticationService
from identity.domain.exceptions import InvalidAuthorizationFlowError
from identity.domain.exceptions import InvalidCSRFTokenError
from identity.domain.exceptions import InvalidSessionError
from identity.domain.exceptions import OwnIDProviderError
from identity.domain.exceptions import SessionRefreshConflictError
from identity.domain.models import OwnIDSubject
from identity.domain.models import PendingAuthorization
from identity.domain.models import ProviderAuthentication
from identity.domain.models import ProviderTokens
from identity.domain.models import StoredSession
from identity.infrastructure.models import IdentitySessionModel
from identity.infrastructure.providers import DevelopmentIdentityProvider
from identity.infrastructure.providers import OwnIDHTTPProvider
from identity.presentation.router import router

NOW = datetime(2026, 8, 5, 12, tzinfo=UTC)


class FakeProvider:
    def __init__(self) -> None:
        self.expected_nonce = ""
        self.revocation_fails = False
        self.refresh_fails = False
        self.session_active = True
        self.introspection_fails = False
        self.provider_logout_url: str | None = "https://id.example/oauth/end-session"

    async def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        code_challenge: str,
    ) -> str:
        self.expected_nonce = nonce
        return f"https://id.example/authorize?state={state}&challenge={code_challenge}"

    async def complete_authorization(
        self,
        *,
        code: str,
        code_verifier: str,
        expected_nonce: str,
    ) -> ProviderAuthentication:
        assert code == "code"
        assert code_verifier
        assert expected_nonce == self.expected_nonce
        return self._authentication()

    async def authenticate_development(self) -> ProviderAuthentication:
        return self._authentication()

    async def refresh(
        self,
        *,
        refresh_token: str,
    ) -> ProviderTokens:
        if self.refresh_fails:
            raise OwnIDProviderError
        return ProviderTokens(
            access_token=f"{refresh_token}-access",
            id_token=f"{refresh_token}-id",
            refresh_token=f"{refresh_token}-rotated",
            expires_at=NOW + timedelta(hours=1),
        )

    async def revoke(
        self,
        *,
        refresh_token: str,
    ) -> None:
        assert refresh_token
        if self.revocation_fails:
            raise OwnIDProviderError

    async def is_session_active(
        self,
        *,
        tokens: ProviderTokens,
        expected_subject: str,
    ) -> bool:
        assert tokens.access_token
        assert expected_subject == "subject-1"
        if self.introspection_fails:
            raise OwnIDProviderError
        return self.session_active

    async def end_session_url(
        self,
        *,
        id_token: str,
        state: str,
    ) -> str | None:
        assert id_token
        assert state
        return self.provider_logout_url

    @staticmethod
    def _authentication() -> ProviderAuthentication:
        return ProviderAuthentication(
            issuer="https://id.example",
            subject="subject-1",
            email="person@example.test",
            display_name="Example Person",
            tokens=ProviderTokens(
                access_token="access-value",
                id_token="id-value",
                refresh_token="refresh-value",
                expires_at=NOW + timedelta(hours=1),
            ),
        )


class CoordinatedRefreshProvider(FakeProvider):
    """Pause one rotation and reject any provider-level token reuse."""

    def __init__(self) -> None:
        super().__init__()
        self.refresh_count = 0
        self.first_started = asyncio.Event()
        self.release = asyncio.Event()

    async def refresh(
        self,
        *,
        refresh_token: str,
    ) -> ProviderTokens:
        """Prove the application never presents the old token a second time."""

        self.refresh_count += 1
        if self.refresh_count > 1:
            raise OwnIDProviderError
        self.first_started.set()
        await self.release.wait()
        return ProviderTokens(
            access_token="access-rotated",
            id_token="id-rotated",
            refresh_token="refresh-rotated",
            expires_at=NOW + timedelta(hours=1),
        )


class StaleIntrospectionProvider(FakeProvider):
    """Return one stale inactive result after a refresh has committed."""

    def __init__(self) -> None:
        super().__init__()
        self.introspection_count = 0
        self.first_started = asyncio.Event()
        self.release_first = asyncio.Event()

    async def is_session_active(
        self,
        *,
        tokens: ProviderTokens,
        expected_subject: str,
    ) -> bool:
        assert tokens.access_token
        assert expected_subject == "subject-1"
        self.introspection_count += 1
        if self.introspection_count == 1:
            self.first_started.set()
            await self.release_first.wait()
            return False
        return True


class FakeSubjectRepository:
    def __init__(
        self,
        *,
        issuer: str = "https://id.example",
        subject: str = "subject-1",
    ) -> None:
        self.subject = OwnIDSubject(
            id=uuid4(),
            issuer=issuer,
            subject=subject,
            email="person@example.test",
            display_name="Example Person",
        )

    async def resolve(
        self,
        *,
        issuer: str,
        subject: str,
        email: str | None,
        display_name: str | None,
    ) -> OwnIDSubject:
        assert (issuer, subject) == (self.subject.issuer, self.subject.subject)
        return self.subject

    async def get(
        self,
        *,
        subject_id: UUID,
    ) -> OwnIDSubject | None:
        return self.subject if subject_id == self.subject.id else None

    async def is_platform_admin(
        self,
        *,
        subject_id: UUID,
    ) -> bool:
        return subject_id == self.subject.id


class FakeSessionRepository:
    def __init__(self) -> None:
        self.pending: dict[str, PendingAuthorization] = {}
        self.sessions: dict[str, StoredSession] = {}
        self.refresh_locks: dict[str, asyncio.Lock] = {}

    async def save_pending(self, pending: PendingAuthorization) -> None:
        self.pending[pending.key_digest] = pending

    async def consume_pending(
        self,
        *,
        key_digest: str,
    ) -> PendingAuthorization | None:
        return self.pending.pop(key_digest, None)

    async def save_session(self, session: StoredSession) -> None:
        self.sessions[session.key_digest] = session

    async def get_session(
        self,
        *,
        key_digest: str,
    ) -> StoredSession | None:
        return self.sessions.get(key_digest)

    @asynccontextmanager
    async def lock_for_refresh(
        self,
        *,
        key_digest: str,
    ) -> AsyncIterator[FakeSessionRefreshClaim | None]:
        lock = self.refresh_locks.setdefault(key_digest, asyncio.Lock())
        async with lock:
            stored = self.sessions.get(key_digest)
            yield (
                FakeSessionRefreshClaim(self, stored) if stored is not None else None
            )

    async def delete_session(
        self,
        *,
        key_digest: str,
    ) -> StoredSession | None:
        return self.sessions.pop(key_digest, None)

    async def delete_session_if_version(
        self,
        *,
        key_digest: str,
        expected_version: int,
    ) -> StoredSession | None:
        stored = self.sessions.get(key_digest)
        if stored is None or stored.version != expected_version:
            return None
        return self.sessions.pop(key_digest)


class FakeSessionRefreshClaim:
    def __init__(
        self,
        repository: FakeSessionRepository,
        stored: StoredSession,
    ) -> None:
        self.repository = repository
        self.stored = stored

    async def replace_tokens(self, tokens: ProviderTokens) -> None:
        self.repository.sessions[self.stored.key_digest] = StoredSession(
            key_digest=self.stored.key_digest,
            subject_id=self.stored.subject_id,
            csrf_digest=self.stored.csrf_digest,
            tokens=tokens,
            expires_at=self.stored.expires_at,
            version=self.stored.version + 1,
        )

    async def delete(self) -> None:
        self.repository.sessions.pop(self.stored.key_digest, None)


class FakeIdentityAuditSink:
    def __init__(self) -> None:
        self.actions: list[tuple[str, str]] = []

    async def record_identity_event(
        self,
        *,
        action: str,
        subject_id: UUID | None,
        correlation_id: str,
        outcome: str,
    ) -> None:
        assert correlation_id
        self.actions.append((action, outcome))


def _service(
    *,
    development: bool = False,
    provider: FakeProvider | None = None,
) -> tuple[AuthenticationService, FakeProvider, FakeSessionRepository]:
    selected_provider = provider or FakeProvider()
    sessions = FakeSessionRepository()
    service = AuthenticationService(
        provider=selected_provider,
        subjects=FakeSubjectRepository(),
        sessions=sessions,
        audit=FakeIdentityAuditSink(),
        session_ttl_seconds=3600,
        development_identity=selected_provider if development else None,
        clock=lambda: NOW,
    )
    return service, selected_provider, sessions


def _development_service(
    *,
    provider: DevelopmentIdentityProvider | None = None,
    sessions: FakeSessionRepository | None = None,
    subjects: FakeSubjectRepository | None = None,
) -> tuple[
    AuthenticationService,
    DevelopmentIdentityProvider,
    FakeSessionRepository,
]:
    selected_provider = provider or DevelopmentIdentityProvider(
        subject="subject-1",
        redirect_uri="http://frontend.test/api/v1/auth/callback",
    )
    selected_sessions = sessions or FakeSessionRepository()
    selected_subjects = subjects or FakeSubjectRepository(
        issuer="urn:ownsis:development",
    )
    service = AuthenticationService(
        provider=selected_provider,
        subjects=selected_subjects,
        sessions=selected_sessions,
        audit=FakeIdentityAuditSink(),
        session_ttl_seconds=3600,
        development_identity=selected_provider,
        clock=lambda: NOW,
    )
    return service, selected_provider, selected_sessions


async def _login(
    service: AuthenticationService,
) -> tuple[str, str]:
    started = await service.start_login(return_path="/dashboard")
    state = parse_qs(urlsplit(started.authorization_url).query)["state"][0]
    established = await service.complete_login(
        pending_token=started.pending_token,
        state=state,
        code="code",
        existing_session_token=None,
        correlation_id="correlation-1",
    )
    return established.session_token, established.csrf_token


async def test_successful_callback_consumes_state_and_stores_only_hash() -> None:
    service, _, sessions = _service()
    started = await service.start_login(return_path="/dashboard")
    state = parse_qs(urlsplit(started.authorization_url).query)["state"][0]

    established = await service.complete_login(
        pending_token=started.pending_token,
        state=state,
        code="code",
        existing_session_token=None,
        correlation_id="correlation-1",
    )

    digest = hashlib.sha256(established.session_token.encode()).hexdigest()
    assert digest in sessions.sessions
    assert established.session_token not in sessions.sessions
    assert established.current.is_platform_admin is True
    with pytest.raises(InvalidAuthorizationFlowError):
        await service.complete_login(
            pending_token=started.pending_token,
            state=state,
            code="code",
            existing_session_token=None,
            correlation_id="correlation-2",
        )


async def test_development_provider_completes_overlapping_flows_independently() -> None:
    service, _, _ = _development_service()
    first = await service.start_login(return_path="/first")
    second = await service.start_login(return_path="/second")
    first_query = parse_qs(urlsplit(first.authorization_url).query)
    second_query = parse_qs(urlsplit(second.authorization_url).query)

    second_session = await service.complete_login(
        pending_token=second.pending_token,
        state=second_query["state"][0],
        code=second_query["code"][0],
        existing_session_token=None,
        correlation_id="correlation-2",
    )
    first_session = await service.complete_login(
        pending_token=first.pending_token,
        state=first_query["state"][0],
        code=first_query["code"][0],
        existing_session_token=None,
        correlation_id="correlation-1",
    )

    assert first_session.return_path == "/first"
    assert second_session.return_path == "/second"
    assert first_session.session_token != second_session.session_token
    assert (
        await service.get_current_session(
            session_token=first_session.session_token,
            correlation_id="correlation-3",
        )
    ).subject == first_session.current.subject
    assert (
        await service.get_current_session(
            session_token=second_session.session_token,
            correlation_id="correlation-4",
        )
    ).subject == second_session.current.subject


async def test_development_callback_survives_provider_recreation() -> None:
    sessions = FakeSessionRepository()
    subjects = FakeSubjectRepository(issuer="urn:ownsis:development")
    original, _, _ = _development_service(
        sessions=sessions,
        subjects=subjects,
    )
    started = await original.start_login(return_path="/dashboard")
    query = parse_qs(urlsplit(started.authorization_url).query)
    recreated, _, _ = _development_service(
        sessions=sessions,
        subjects=subjects,
    )

    established = await recreated.complete_login(
        pending_token=started.pending_token,
        state=query["state"][0],
        code=query["code"][0],
        existing_session_token=None,
        correlation_id="correlation-1",
    )

    assert established.return_path == "/dashboard"
    assert (
        await recreated.get_current_session(
            session_token=established.session_token,
            correlation_id="correlation-2",
        )
    ).subject == established.current.subject


async def test_development_sessions_refresh_and_revoke_independently() -> None:
    service, _, _ = _development_service()
    first = await service.development_login(
        return_path="/first",
        existing_session_token=None,
        correlation_id="correlation-1",
    )
    second = await service.development_login(
        return_path="/second",
        existing_session_token=None,
        correlation_id="correlation-2",
    )

    await service.refresh_session(
        session_token=first.session_token,
        csrf_token=first.csrf_token,
        correlation_id="correlation-3",
    )
    assert (
        await service.get_current_session(
            session_token=second.session_token,
            correlation_id="correlation-4",
        )
    ).subject == second.current.subject

    logout = await service.logout(
        session_token=first.session_token,
        csrf_token=first.csrf_token,
        correlation_id="correlation-5",
    )

    assert logout.provider_revoked is True
    assert (
        await service.refresh_session(
            session_token=second.session_token,
            csrf_token=second.csrf_token,
            correlation_id="correlation-6",
        )
    ).subject == second.current.subject
    with pytest.raises(InvalidSessionError):
        await service.get_current_session(
            session_token=first.session_token,
            correlation_id="correlation-7",
        )


async def test_invalid_csrf_does_not_delete_local_session() -> None:
    service, _, sessions = _service()
    session_token, _ = await _login(service)

    with pytest.raises(InvalidCSRFTokenError):
        await service.logout(
            session_token=session_token,
            csrf_token="wrong",
            correlation_id="correlation-1",
        )

    digest = hashlib.sha256(session_token.encode()).hexdigest()
    assert digest in sessions.sessions


async def test_concurrent_refresh_serializes_before_provider_token_use() -> None:
    provider = CoordinatedRefreshProvider()
    service, _, sessions = _service(provider=provider)
    session_token, csrf_token = await _login(service)

    first = asyncio.create_task(
        service.refresh_session(
            session_token=session_token,
            csrf_token=csrf_token,
            correlation_id="correlation-1",
        )
    )
    await provider.first_started.wait()
    second = asyncio.create_task(
        service.refresh_session(
            session_token=session_token,
            csrf_token=csrf_token,
            correlation_id="correlation-2",
        )
    )
    await asyncio.sleep(0)
    assert provider.refresh_count == 1
    provider.release.set()
    results = await asyncio.gather(first, second, return_exceptions=True)

    assert (
        sum(isinstance(result, SessionRefreshConflictError) for result in results) == 1
    )
    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert provider.refresh_count == 1
    digest = hashlib.sha256(session_token.encode()).hexdigest()
    assert sessions.sessions[digest].version == 2


async def test_provider_refresh_failure_deletes_local_session() -> None:
    service, provider, sessions = _service()
    session_token, csrf_token = await _login(service)
    provider.refresh_fails = True

    with pytest.raises(OwnIDProviderError):
        await service.refresh_session(
            session_token=session_token,
            csrf_token=csrf_token,
            correlation_id="correlation-1",
        )

    assert sessions.sessions == {}


async def test_stale_inactive_introspection_preserves_concurrent_rotation() -> None:
    provider = StaleIntrospectionProvider()
    service, _, sessions = _service(provider=provider)
    session_token, csrf_token = await _login(service)

    stale_read = asyncio.create_task(
        service.get_current_session(
            session_token=session_token,
            correlation_id="correlation-1",
        )
    )
    await provider.first_started.wait()
    refreshed = await service.refresh_session(
        session_token=session_token,
        csrf_token=csrf_token,
        correlation_id="correlation-2",
    )
    provider.release_first.set()
    reread = await stale_read

    assert refreshed.subject == reread.subject
    digest = hashlib.sha256(session_token.encode()).hexdigest()
    assert sessions.sessions[digest].version == 2


async def test_logout_remains_local_success_when_provider_revocation_fails() -> None:
    service, provider, sessions = _service()
    session_token, csrf_token = await _login(service)
    provider.revocation_fails = True

    result = await service.logout(
        session_token=session_token,
        csrf_token=csrf_token,
        correlation_id="correlation-1",
    )

    assert result.provider_revoked is False
    assert result.provider_logout_url == "https://id.example/oauth/end-session"
    assert sessions.sessions == {}


async def test_provider_revocation_invalidates_local_session_fail_closed() -> None:
    service, provider, sessions = _service()
    session_token, _ = await _login(service)
    provider.session_active = False

    with pytest.raises(InvalidSessionError):
        await service.get_current_session(
            session_token=session_token,
            correlation_id="correlation-1",
        )

    assert sessions.sessions == {}


async def test_provider_introspection_outage_never_authorizes_session() -> None:
    service, provider, sessions = _service()
    session_token, _ = await _login(service)
    provider.introspection_fails = True

    with pytest.raises(OwnIDProviderError):
        await service.get_current_session(
            session_token=session_token,
            correlation_id="correlation-1",
        )

    assert sessions.sessions


async def test_development_login_requires_explicit_development_provider() -> None:
    disabled, _, _ = _service(development=False)
    with pytest.raises(InvalidAuthorizationFlowError):
        await disabled.development_login(
            return_path="/",
            existing_session_token=None,
            correlation_id="correlation-1",
        )

    enabled, _, _ = _service(development=True)
    established = await enabled.development_login(
        return_path="/",
        existing_session_token=None,
        correlation_id="correlation-1",
    )
    assert established.current.subject.subject == "subject-1"


@pytest.mark.parametrize(
    "return_path",
    [
        "https://evil.example",
        "//evil.example",
        "/safe/%2e%2e/admin",
        "/a\\b",
        "/%5cevil.example",
        "/safe/%00path",
    ],
)
async def test_login_rejects_unsafe_return_paths(return_path: str) -> None:
    service, _, _ = _service()
    with pytest.raises(InvalidAuthorizationFlowError):
        await service.start_login(return_path=return_path)


def test_session_model_repr_does_not_leak_secret_columns() -> None:
    model = IdentitySessionModel(id=uuid4())
    rendered = repr(model)
    assert "token" not in rendered
    assert "csrf" not in rendered


def test_identity_domain_repr_does_not_leak_personal_claims() -> None:
    subject = OwnIDSubject(
        id=uuid4(),
        issuer="https://id.example",
        subject="subject-1",
        email="person@example.test",
        display_name="Private Name",
    )

    rendered = repr(subject)
    assert "person@example.test" not in rendered
    assert "Private Name" not in rendered


async def test_dev_login_route_sets_server_session_and_csrf_cookies() -> None:
    service, _, _ = _service(development=True)
    app = FastAPI()
    app.state.settings = Settings(
        APP_ENV=AppEnvironment.TEST,
        DEV_AUTH_ENABLED=True,
        COOKIE_SECURE=False,
    )
    app.state.identity_service = service
    install_error_handlers(app)
    app.include_router(router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/auth/dev-login",
            json={"return_path": "/dashboard"},
        )

    assert response.status_code == 200
    assert response.json()["return_path"] == "/dashboard"
    assert "platform_administrators.manage" in response.json()["user"]["permissions"]
    cookies = response.headers.get_list("set-cookie")
    assert any(
        "ownsis_session=" in cookie and "HttpOnly" in cookie for cookie in cookies
    )
    assert any(
        "ownsis_csrf=" in cookie and "HttpOnly" not in cookie for cookie in cookies
    )


async def test_dev_login_route_fails_when_not_explicitly_enabled() -> None:
    service, _, _ = _service(development=True)
    app = FastAPI()
    app.state.settings = Settings(
        APP_ENV=AppEnvironment.TEST,
        DEV_AUTH_ENABLED=False,
        COOKIE_SECURE=False,
    )
    app.state.identity_service = service
    install_error_handlers(app)
    app.include_router(router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/auth/dev-login",
            json={"return_path": "/"},
        )

    assert response.status_code == 401


async def test_callback_redirects_to_absolute_frontend_url() -> None:
    service, _, _ = _service()
    app = FastAPI()
    app.state.settings = Settings(
        APP_ENV=AppEnvironment.TEST,
        APP_BASE_URL="http://frontend.test/portal",
        COOKIE_SECURE=False,
    )
    app.state.identity_service = service
    install_error_handlers(app)
    app.include_router(router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://backend.test",
    ) as client:
        started = await client.post(
            "/api/v1/auth/login",
            json={"return_path": "/dashboard?view=today"},
        )
        state = parse_qs(urlsplit(started.json()["authorization_url"]).query)["state"][
            0
        ]
        completed = await client.get(
            "/api/v1/auth/callback",
            params={"code": "code", "state": state},
            follow_redirects=False,
        )

    assert completed.status_code == 303
    assert completed.headers["location"] == (
        "http://frontend.test/portal/dashboard?view=today"
    )


async def test_refresh_id_token_may_omit_nonce_but_callback_may_not() -> None:
    issuer = "https://id.example"
    signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_id = "test-key"
    now = datetime.now(UTC)
    id_token = jwt.encode(
        {
            "iss": issuer,
            "sub": "subject-1",
            "aud": "client-1",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        signing_key,
        algorithm="RS256",
        headers={"kid": key_id},
    )
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(
        signing_key.public_key(),
        as_dict=True,
    )
    public_jwk["kid"] = key_id
    public_jwk["alg"] = "RS256"
    public_jwk["use"] = "sig"

    def handle(request: HTTPXRequest) -> Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            return Response(
                200,
                json={
                    "issuer": issuer,
                    "authorization_endpoint": f"{issuer}/authorize",
                    "token_endpoint": f"{issuer}/token",
                    "jwks_uri": f"{issuer}/jwks",
                    "introspection_endpoint": f"{issuer}/introspect",
                },
            )
        if request.url.path == "/token":
            return Response(
                200,
                json={
                    "access_token": "access-token",
                    "id_token": id_token,
                    "refresh_token": "refresh-token",
                    "expires_in": 300,
                },
            )
        if request.url.path == "/jwks":
            return Response(200, json={"keys": [public_jwk]})
        return Response(404)

    async with AsyncClient(transport=MockTransport(handle)) as http_client:
        provider = OwnIDHTTPProvider(
            issuer=issuer,
            client_id="client-1",
            client_secret="client-secret",
            redirect_uri="https://app.example/api/v1/auth/callback",
            scopes=("openid",),
            http_client=http_client,
        )

        refreshed = await provider.refresh(refresh_token="refresh-token")
        assert refreshed.id_token == id_token
        with pytest.raises(OwnIDProviderError):
            await provider.complete_authorization(
                code="authorization-code",
                code_verifier="code-verifier",
                expected_nonce="required-nonce",
            )


async def test_ownid_session_check_uses_refresh_introspection_contract() -> None:
    issuer = "https://id.example"
    introspected_forms: list[dict[str, list[str]]] = []

    def handle(request: HTTPXRequest) -> Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            return Response(
                200,
                json={
                    "issuer": issuer,
                    "authorization_endpoint": f"{issuer}/authorize",
                    "token_endpoint": f"{issuer}/token",
                    "jwks_uri": f"{issuer}/jwks",
                    "introspection_endpoint": f"{issuer}/introspect",
                },
            )
        if request.url.path == "/introspect":
            form = parse_qs(request.content.decode("ascii"))
            introspected_forms.append(form)
            if form["token"] == ["inactive-refresh"]:
                return Response(200, json={"active": False})
            return Response(
                200,
                json={
                    "active": True,
                    "client_id": "client-1",
                    "sub": "subject-1",
                    "token_type": "refresh_token",
                    "exp": 1_900_000_000,
                },
            )
        return Response(404)

    async with AsyncClient(transport=MockTransport(handle)) as http_client:
        provider = OwnIDHTTPProvider(
            issuer=issuer,
            client_id="client-1",
            client_secret="client-secret",
            redirect_uri="https://app.example/api/v1/auth/callback",
            scopes=("openid", "offline_access"),
            http_client=http_client,
        )
        active_tokens = ProviderTokens(
            access_token="access-token",
            id_token="id-token",
            refresh_token="refresh-token",
            expires_at=NOW + timedelta(hours=1),
        )
        inactive_tokens = ProviderTokens(
            access_token="access-token",
            id_token="id-token",
            refresh_token="inactive-refresh",
            expires_at=NOW + timedelta(hours=1),
        )

        assert await provider.is_session_active(
            tokens=active_tokens,
            expected_subject="subject-1",
        )
        assert not await provider.is_session_active(
            tokens=inactive_tokens,
            expected_subject="subject-1",
        )

    assert introspected_forms[0] == {
        "token": ["refresh-token"],
        "token_type_hint": ["refresh_token"],
        "client_id": ["client-1"],
        "client_secret": ["client-secret"],
    }


async def test_ownid_logout_url_uses_advertised_end_session_contract() -> None:
    issuer = "https://id.example"

    def handle(request: HTTPXRequest) -> Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            return Response(
                200,
                json={
                    "issuer": issuer,
                    "authorization_endpoint": f"{issuer}/authorize",
                    "token_endpoint": f"{issuer}/token",
                    "jwks_uri": f"{issuer}/jwks",
                    "introspection_endpoint": f"{issuer}/introspect",
                    "end_session_endpoint": f"{issuer}/oauth/end-session",
                },
            )
        return Response(404)

    async with AsyncClient(transport=MockTransport(handle)) as http_client:
        provider = OwnIDHTTPProvider(
            issuer=issuer,
            client_id="client-1",
            client_secret="client-secret",
            redirect_uri="https://app.example/api/v1/auth/callback",
            scopes=("openid",),
            http_client=http_client,
            post_logout_redirect_uri="https://app.example/sign-in",
        )

        logout_url = await provider.end_session_url(
            id_token="signed-id-token",
            state="logout-state",
        )

    assert logout_url is not None
    parsed = urlsplit(logout_url)
    assert parsed.path == "/oauth/end-session"
    assert parse_qs(parsed.query) == {
        "id_token_hint": ["signed-id-token"],
        "post_logout_redirect_uri": ["https://app.example/sign-in"],
        "state": ["logout-state"],
    }
