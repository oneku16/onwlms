"""OwnID MCP bearer verification refreshes JWKS through a bounded cache."""

from datetime import UTC
from datetime import datetime
from datetime import timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import AsyncClient
from httpx import MockTransport
from httpx import Request
from httpx import Response

from mcp_gateway.infrastructure.token_verifier import OwnIDTokenVerifier


async def test_jwks_is_reused_only_inside_its_bounded_ttl() -> None:
    issuer = "https://ownid.example"
    audience = "https://api.example/mcp"
    signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_id = "signing-key"
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(
        signing_key.public_key(),
        as_dict=True,
    )
    public_jwk.update({"kid": key_id, "alg": "RS256", "use": "sig"})
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "iss": issuer,
            "sub": "subject-1",
            "aud": audience,
            "iat": now,
            "exp": now + timedelta(minutes=10),
            "scope": "ownsis:mcp:read",
        },
        signing_key,
        algorithm="RS256",
        headers={"kid": key_id},
    )
    counts = {"discovery": 0, "jwks": 0}

    def handle(request: Request) -> Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            counts["discovery"] += 1
            return Response(200, json={"jwks_uri": f"{issuer}/jwks"})
        if request.url.path == "/jwks":
            counts["jwks"] += 1
            return Response(200, json={"keys": [public_jwk]})
        return Response(404)

    monotonic_time = [100.0]
    async with AsyncClient(transport=MockTransport(handle)) as client:
        verifier = OwnIDTokenVerifier(
            issuer=issuer,
            audience=audience,
            timeout_seconds=2,
            jwks_cache_ttl_seconds=30,
            monotonic_clock=lambda: monotonic_time[0],
            http_client=client,
        )

        first = await verifier.verify_token(token)
        monotonic_time[0] = 129.0
        second = await verifier.verify_token(token)
        monotonic_time[0] = 131.0
        third = await verifier.verify_token(token)

    assert first is not None and first.subject == "subject-1"
    assert second is not None and third is not None
    assert counts == {"discovery": 1, "jwks": 2}


def test_jwks_cache_ttl_must_be_positive_and_bounded() -> None:
    with pytest.raises(ValueError):
        OwnIDTokenVerifier(
            issuer="https://ownid.example",
            audience="mcp",
            timeout_seconds=2,
            jwks_cache_ttl_seconds=0,
        )
    with pytest.raises(ValueError):
        OwnIDTokenVerifier(
            issuer="https://ownid.example",
            audience="mcp",
            timeout_seconds=2,
            jwks_cache_ttl_seconds=3601,
        )
