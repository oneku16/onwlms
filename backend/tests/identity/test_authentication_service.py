"""Behavioral tests for OIDC state, session rotation, CSRF, and logout."""

import asyncio
import hashlib
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
from identity.domain.models import OwnIDSubject
from identity.domain.models import PendingAuthorization
from identity.domain.models import ProviderAuthentication
from identity.domain.models import ProviderTokens
from identity.domain.models import StoredSession
from identity.infrastructure.models import IdentitySessionModel
from identity.infrastructure.providers import OwnIDHTTPProvider
from identity.presentation.router import router

NOW = datetime(2026, 8, 5, 12, tzinfo=UTC)


class FakeProvider:
    def __init__(self) -> None:
        self.expected_nonce = ""
        self.revocation_fails = False

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
    """Release two refresh calls together to exercise session CAS behavior."""

    def __init__(self) -> None:
        super().__init__()
        self.refresh_count = 0
        self.both_started = asyncio.Event()
        self.release = asyncio.Event()

    async def refresh(
        self,
        *,
        refresh_token: str,
    ) -> ProviderTokens:
        """Return distinct rotations only after both callers read old state."""

        self.refresh_count += 1
        sequence = self.refresh_count
        if sequence == 2:
            self.both_started.set()
        await self.release.wait()
        return ProviderTokens(
            access_token=f"access-{sequence}",
            id_token=f"id-{sequence}",
            refresh_token=f"refresh-{sequence}",
            expires_at=NOW + timedelta(hours=1),
        )


class FakeSubjectRepository:
    def __init__(self) -> None:
        self.subject = OwnIDSubject(
            id=uuid4(),
            issuer="https://id.example",
            subject="subject-1",
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

    async def replace_tokens(
        self,
        *,
        key_digest: str,
        expected_version: int,
        tokens: ProviderTokens,
    ) -> bool:
        stored = self.sessions[key_digest]
        if stored.version != expected_version:
            return False
        self.sessions[key_digest] = StoredSession(
            key_digest=stored.key_digest,
            subject_id=stored.subject_id,
            csrf_digest=stored.csrf_digest,
            tokens=tokens,
            expires_at=stored.expires_at,
            version=stored.version + 1,
        )
        return True

    async def delete_session(
        self,
        *,
        key_digest: str,
    ) -> StoredSession | None:
        return self.sessions.pop(key_digest, None)


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


async def test_concurrent_refresh_uses_session_version_compare_and_swap() -> None:
    provider = CoordinatedRefreshProvider()
    service, _, sessions = _service(provider=provider)
    session_token, csrf_token = await _login(service)

    first = asyncio.create_task(
        service.refresh_session(
            session_token=session_token,
            csrf_token=csrf_token,
        )
    )
    second = asyncio.create_task(
        service.refresh_session(
            session_token=session_token,
            csrf_token=csrf_token,
        )
    )
    await provider.both_started.wait()
    provider.release.set()
    results = await asyncio.gather(first, second, return_exceptions=True)

    assert sum(isinstance(result, InvalidSessionError) for result in results) == 1
    assert sum(not isinstance(result, Exception) for result in results) == 1
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
    assert sessions.sessions == {}


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
