"""OwnID JWT verification for MCP bearer-token authentication."""

import asyncio
from collections.abc import Callable
from time import monotonic
from time import time

import httpx
import jwt
from mcp.server.auth.provider import AccessToken


class OwnIDTokenVerifier:
    """Verify RS256 OwnID access tokens against discovery and JWKS."""

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        timeout_seconds: float,
        jwks_cache_ttl_seconds: float = 300.0,
        monotonic_clock: Callable[[], float] = monotonic,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if jwks_cache_ttl_seconds <= 0 or jwks_cache_ttl_seconds > 3600:
            raise ValueError("JWKS cache TTL must be between 0 and 3600 seconds")
        self._issuer = issuer.rstrip("/")
        self._audience = audience
        self._timeout_seconds = timeout_seconds
        self._jwks_cache_ttl_seconds = jwks_cache_ttl_seconds
        self._monotonic_clock = monotonic_clock
        self._http_client = http_client
        self._jwks: dict[str, object] | None = None
        self._jwks_cached_at: float | None = None
        self._jwks_uri: str | None = None
        self._cache_lock = asyncio.Lock()

    async def verify_token(
        self,
        token: str,
    ) -> AccessToken | None:
        """Return bounded access information only for a valid OwnID token."""

        try:
            unverified_header = jwt.get_unverified_header(token)
            key_id = unverified_header.get("kid")
            if not isinstance(key_id, str):
                return None
            jwks = await self._get_jwks()
            keys = jwks.get("keys")
            if not isinstance(keys, list):
                return None
            key_data = next(
                (
                    candidate
                    for candidate in keys
                    if isinstance(candidate, dict) and candidate.get("kid") == key_id
                ),
                None,
            )
            if key_data is None:
                self._invalidate_jwks()
                jwks = await self._get_jwks()
                refreshed = jwks.get("keys")
                if not isinstance(refreshed, list):
                    return None
                key_data = next(
                    (
                        candidate
                        for candidate in refreshed
                        if isinstance(candidate, dict)
                        and candidate.get("kid") == key_id
                    ),
                    None,
                )
            if not isinstance(key_data, dict):
                return None
            signing_key = jwt.PyJWK.from_dict(key_data).key
            claims = jwt.decode(
                token,
                key=signing_key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "iss", "sub", "aud"]},
            )
        except httpx.HTTPError, jwt.PyJWTError, ValueError:
            return None
        subject = claims.get("sub")
        expires_at = claims.get("exp")
        if not isinstance(subject, str) or not isinstance(expires_at, int):
            return None
        if expires_at <= int(time()):
            return None
        scope_value = claims.get("scope", "")
        scopes = scope_value.split() if isinstance(scope_value, str) else []
        client_id_value = claims.get("client_id") or claims.get("azp") or "unknown"
        client_id = client_id_value if isinstance(client_id_value, str) else "unknown"
        safe_claims: dict[str, object] = {
            "iss": self._issuer,
            "sub": subject,
        }
        return AccessToken(
            token=token,
            client_id=client_id,
            scopes=scopes,
            expires_at=expires_at,
            resource=self._audience,
            subject=subject,
            claims=safe_claims,
        )

    async def _get_jwks(self) -> dict[str, object]:
        """Load OwnID JWKS through a bounded TTL and bounded network time."""

        if self._cache_is_current():
            if self._jwks is None:
                raise RuntimeError("Current JWKS cache is unexpectedly empty")
            return self._jwks
        async with self._cache_lock:
            if self._cache_is_current():
                if self._jwks is None:
                    raise RuntimeError("Current JWKS cache is unexpectedly empty")
                return self._jwks
            if self._jwks_uri is None:
                discovery = await self._get_json(
                    f"{self._issuer}/.well-known/openid-configuration"
                )
                jwks_uri = discovery.get("jwks_uri")
                if not isinstance(jwks_uri, str) or not jwks_uri.startswith(
                    f"{self._issuer}/"
                ):
                    message = "OwnID discovery returned an invalid JWKS URI"
                    raise ValueError(message)
                self._jwks_uri = jwks_uri
            payload = await self._get_json(self._jwks_uri)
            self._jwks = payload
            self._jwks_cached_at = self._monotonic_clock()
            return payload

    async def _get_json(
        self,
        url: str,
    ) -> dict[str, object]:
        """Fetch one JSON object with bounded transport and redirect behavior."""

        if self._http_client is not None:
            response = await self._http_client.get(url)
        else:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                follow_redirects=False,
            ) as client:
                response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("OwnID metadata response is invalid")
        return payload

    def _cache_is_current(self) -> bool:
        """Return whether cached keys remain inside their configured lifetime."""

        return (
            self._jwks is not None
            and self._jwks_cached_at is not None
            and self._monotonic_clock() - self._jwks_cached_at
            < self._jwks_cache_ttl_seconds
        )

    def _invalidate_jwks(self) -> None:
        """Discard keys so an unknown key ID triggers one immediate refresh."""

        self._jwks = None
        self._jwks_cached_at = None


__all__ = ["OwnIDTokenVerifier"]
