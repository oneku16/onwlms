"""OwnID OIDC HTTP/JWT adapter and explicit development-only provider."""

import asyncio
import json
import secrets
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlencode

import httpx
import jwt

from core.settings import AppEnvironment
from core.settings import Settings
from core.time import utc_now
from identity.application.ports import IdentityProvider
from identity.domain.exceptions import OwnIDProviderError
from identity.domain.models import ProviderAuthentication
from identity.domain.models import ProviderTokens


@dataclass(frozen=True, slots=True)
class OwnIDDiscovery:
    """Contain the verified endpoint subset required by the relying party."""

    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    revocation_endpoint: str | None


class OwnIDHTTPProvider:
    """Perform OwnID discovery, token exchange, refresh, revocation, and JWT checks."""

    def __init__(
        self,
        *,
        issuer: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: tuple[str, ...],
        http_client: httpx.AsyncClient,
    ) -> None:
        self._issuer = issuer.rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._scopes = scopes
        self._http_client = http_client
        self._discovery: OwnIDDiscovery | None = None
        self._discovery_lock = asyncio.Lock()

    async def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        code_challenge: str,
    ) -> str:
        """Build an authorization URL from verified OwnID discovery metadata."""

        discovery = await self._get_discovery()
        query = urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "scope": " ".join(self._scopes),
                "state": state,
                "nonce": nonce,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{discovery.authorization_endpoint}?{query}"

    async def complete_authorization(
        self,
        *,
        code: str,
        code_verifier: str,
        expected_nonce: str,
    ) -> ProviderAuthentication:
        """Exchange a code and verify issuer, audience, signature, time, and nonce."""

        discovery = await self._get_discovery()
        payload = await self._post_form(
            discovery.token_endpoint,
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._redirect_uri,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "code_verifier": code_verifier,
            },
        )
        tokens = self._tokens_from_payload(payload)
        claims = await self._verified_claims(
            token=tokens.id_token,
            jwks_uri=discovery.jwks_uri,
            require_nonce=True,
        )
        nonce = self._required_string(claims, "nonce")
        if not self._secure_equals(nonce, expected_nonce):
            raise OwnIDProviderError
        return ProviderAuthentication(
            issuer=self._required_string(claims, "iss"),
            subject=self._required_string(claims, "sub"),
            email=self._optional_string(claims, "email"),
            display_name=self._optional_string(claims, "name"),
            tokens=tokens,
        )

    async def refresh(
        self,
        *,
        refresh_token: str,
    ) -> ProviderTokens:
        """Refresh OwnID tokens and preserve a token when rotation omits replacement."""

        discovery = await self._get_discovery()
        payload = await self._post_form(
            discovery.token_endpoint,
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
        tokens = self._tokens_from_payload(
            payload,
            fallback_refresh_token=refresh_token,
        )
        await self._verified_claims(
            token=tokens.id_token,
            jwks_uri=discovery.jwks_uri,
            require_nonce=False,
        )
        return tokens

    async def revoke(
        self,
        *,
        refresh_token: str,
    ) -> None:
        """Revoke a refresh token when OwnID advertises the standard endpoint."""

        discovery = await self._get_discovery()
        if discovery.revocation_endpoint is None:
            raise OwnIDProviderError
        try:
            response = await self._http_client.post(
                discovery.revocation_endpoint,
                data={
                    "token": refresh_token,
                    "token_type_hint": "refresh_token",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OwnIDProviderError from exc

    async def _get_discovery(self) -> OwnIDDiscovery:
        """Load and process-cache OwnID discovery metadata."""

        if self._discovery is not None:
            return self._discovery
        async with self._discovery_lock:
            if self._discovery is not None:
                return self._discovery
            try:
                response = await self._http_client.get(
                    f"{self._issuer}/.well-known/openid-configuration"
                )
                response.raise_for_status()
                payload = self._json_object(response)
                discovered_issuer = self._required_string(payload, "issuer").rstrip("/")
                if not self._secure_equals(discovered_issuer, self._issuer):
                    raise OwnIDProviderError
                self._discovery = OwnIDDiscovery(
                    authorization_endpoint=self._https_endpoint(
                        payload,
                        "authorization_endpoint",
                    ),
                    token_endpoint=self._https_endpoint(payload, "token_endpoint"),
                    jwks_uri=self._https_endpoint(payload, "jwks_uri"),
                    revocation_endpoint=self._optional_https_endpoint(
                        payload,
                        "revocation_endpoint",
                    ),
                )
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                raise OwnIDProviderError from exc
            return self._discovery

    async def _verified_claims(
        self,
        *,
        token: str,
        jwks_uri: str,
        require_nonce: bool,
    ) -> dict[str, object]:
        """Verify an RS256 token using the matching key from OwnID JWKS."""

        try:
            response = await self._http_client.get(jwks_uri)
            response.raise_for_status()
            jwks = self._json_object(response)
            unverified: object = jwt.get_unverified_header(token)
            if not isinstance(unverified, dict):
                raise OwnIDProviderError
            header = {str(key): value for key, value in unverified.items()}
            if header.get("alg") != "RS256":
                raise OwnIDProviderError
            key_id = self._required_string(header, "kid")
            key_set = jwt.PyJWKSet.from_dict(jwks)
            signing_key = next(
                (key for key in key_set.keys if key.key_id == key_id),
                None,
            )
            if signing_key is None:
                raise OwnIDProviderError
            required_claims = ["aud", "exp", "iat", "iss", "sub"]
            if require_nonce:
                required_claims.append("nonce")
            decoded: object = jwt.decode(
                token,
                key=signing_key.key,
                algorithms=["RS256"],
                audience=self._client_id,
                issuer=self._issuer,
                options={
                    "require": required_claims,
                },
            )
            if not isinstance(decoded, dict):
                raise OwnIDProviderError
            return {str(key): value for key, value in decoded.items()}
        except (httpx.HTTPError, jwt.PyJWTError, ValueError, TypeError) as exc:
            raise OwnIDProviderError from exc

    async def _post_form(
        self,
        endpoint: str,
        form: dict[str, str],
    ) -> dict[str, object]:
        """POST one OIDC form and translate all transport failures safely."""

        try:
            response = await self._http_client.post(endpoint, data=form)
            response.raise_for_status()
            return self._json_object(response)
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise OwnIDProviderError from exc

    @staticmethod
    def _tokens_from_payload(
        payload: dict[str, object],
        *,
        fallback_refresh_token: str | None = None,
    ) -> ProviderTokens:
        """Translate a validated token response into protected server values."""

        access_token = OwnIDHTTPProvider._required_string(payload, "access_token")
        id_token = OwnIDHTTPProvider._required_string(payload, "id_token")
        refresh_token = OwnIDHTTPProvider._optional_string(payload, "refresh_token")
        expires_value = payload.get("expires_in")
        if not isinstance(expires_value, (int, float)) or isinstance(
            expires_value,
            bool,
        ):
            raise OwnIDProviderError
        expires_seconds = int(expires_value)
        if expires_seconds <= 0:
            raise OwnIDProviderError
        return ProviderTokens(
            access_token=access_token,
            id_token=id_token,
            refresh_token=refresh_token or fallback_refresh_token,
            expires_at=utc_now() + timedelta(seconds=expires_seconds),
        )

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, object]:
        """Parse one JSON object without allowing arbitrary vendor values inward."""

        parsed: object = json.loads(response.text)
        if not isinstance(parsed, dict):
            raise ValueError
        return {str(key): value for key, value in parsed.items()}

    @staticmethod
    def _required_string(
        payload: dict[str, object],
        name: str,
    ) -> str:
        """Return one required non-empty string from an external object."""

        value = payload.get(name)
        if not isinstance(value, str) or not value:
            raise OwnIDProviderError
        return value

    @staticmethod
    def _optional_string(
        payload: dict[str, object],
        name: str,
    ) -> str | None:
        """Return one optional external string while rejecting wrong types."""

        value = payload.get(name)
        if value is None:
            return None
        if not isinstance(value, str):
            raise OwnIDProviderError
        return value or None

    @classmethod
    def _https_endpoint(
        cls,
        payload: dict[str, object],
        name: str,
    ) -> str:
        """Require one HTTPS endpoint from discovery metadata."""

        endpoint = cls._required_string(payload, name)
        if not endpoint.startswith("https://"):
            raise OwnIDProviderError
        return endpoint

    @classmethod
    def _optional_https_endpoint(
        cls,
        payload: dict[str, object],
        name: str,
    ) -> str | None:
        """Validate an optional discovery endpoint when advertised."""

        endpoint = cls._optional_string(payload, name)
        if endpoint is not None and not endpoint.startswith("https://"):
            raise OwnIDProviderError
        return endpoint

    @staticmethod
    def _secure_equals(left: str, right: str) -> bool:
        """Compare security-sensitive identity values in constant time."""

        try:
            return secrets.compare_digest(left, right)
        except TypeError, ValueError:
            return False


class DevelopmentIdentityProvider:
    """Provide an explicit non-production identity path for local development."""

    def __init__(
        self,
        *,
        subject: str,
        redirect_uri: str,
    ) -> None:
        self._subject = subject
        self._redirect_uri = redirect_uri
        self._expected_nonce: str | None = None
        self._access_value = secrets.token_urlsafe(32)
        self._id_value = secrets.token_urlsafe(32)
        self._refresh_value = secrets.token_urlsafe(32)

    async def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        code_challenge: str,
    ) -> str:
        """Build a deterministic local callback only when explicitly constructed."""

        del code_challenge
        self._expected_nonce = nonce
        query = urlencode({"code": "development", "state": state})
        return f"{self._redirect_uri}?{query}"

    async def complete_authorization(
        self,
        *,
        code: str,
        code_verifier: str,
        expected_nonce: str,
    ) -> ProviderAuthentication:
        """Return the configured local subject after validating the fake flow."""

        del code_verifier
        if (
            code != "development"
            or self._expected_nonce is None
            or not secrets.compare_digest(self._expected_nonce, expected_nonce)
        ):
            raise OwnIDProviderError
        return await self.authenticate_development()

    async def authenticate_development(self) -> ProviderAuthentication:
        """Return the configured fake identity without accepting credentials."""

        return ProviderAuthentication(
            issuer="urn:ownsis:development",
            subject=self._subject,
            email=None,
            display_name="Development User",
            tokens=ProviderTokens(
                access_token=self._access_value,
                id_token=self._id_value,
                refresh_token=self._refresh_value,
                expires_at=utc_now() + timedelta(hours=1),
            ),
        )

    async def refresh(
        self,
        *,
        refresh_token: str,
    ) -> ProviderTokens:
        """Rotate explicit development token strings for local testing."""

        if not secrets.compare_digest(refresh_token, self._refresh_value):
            raise OwnIDProviderError
        self._access_value = secrets.token_urlsafe(32)
        self._id_value = secrets.token_urlsafe(32)
        return ProviderTokens(
            access_token=self._access_value,
            id_token=self._id_value,
            refresh_token=self._refresh_value,
            expires_at=utc_now() + timedelta(hours=1),
        )

    async def revoke(
        self,
        *,
        refresh_token: str,
    ) -> None:
        """Validate the local refresh token without an external side effect."""

        if not secrets.compare_digest(refresh_token, self._refresh_value):
            raise OwnIDProviderError


def create_identity_provider(
    *,
    settings: Settings,
    http_client: httpx.AsyncClient | None = None,
) -> tuple[IdentityProvider, httpx.AsyncClient | None]:
    """Create the sole allowed provider path and report owned HTTP resources."""

    if settings.DEV_AUTH_ENABLED:
        if settings.APP_ENV is AppEnvironment.PRODUCTION:
            message = "Development identity cannot be enabled in production"
            raise ValueError(message)
        return (
            DevelopmentIdentityProvider(
                subject=settings.DEV_AUTH_SUBJECT,
                redirect_uri=settings.OWNID_REDIRECT_URI,
            ),
            None,
        )
    if not settings.ownid_configured:
        message = "OwnID configuration is required when development auth is disabled"
        raise ValueError(message)
    if "openid" not in settings.OWNID_SCOPES.split():
        message = "OwnID OIDC scopes must include openid"
        raise ValueError(message)
    if settings.APP_ENV is AppEnvironment.PRODUCTION and (
        not settings.OWNID_ISSUER.startswith("https://")
        or not settings.OWNID_REDIRECT_URI.startswith("https://")
    ):
        message = "Production OwnID issuer and redirect URI must use HTTPS"
        raise ValueError(message)
    owned_client = http_client is None
    client = http_client or httpx.AsyncClient(
        timeout=settings.OWNID_HTTP_TIMEOUT_SECONDS,
        follow_redirects=False,
    )
    provider = OwnIDHTTPProvider(
        issuer=settings.OWNID_ISSUER,
        client_id=settings.OWNID_CLIENT_ID,
        client_secret=settings.OWNID_CLIENT_SECRET,
        redirect_uri=settings.OWNID_REDIRECT_URI,
        scopes=tuple(settings.OWNID_SCOPES.split()),
        http_client=client,
    )
    return provider, client if owned_client else None


__all__ = [
    "DevelopmentIdentityProvider",
    "OwnIDDiscovery",
    "OwnIDHTTPProvider",
    "create_identity_provider",
]
