"""Foundation behavior for health, configuration, and public errors."""

import pytest
from httpx import ASGITransport
from httpx import AsyncClient

from core.application import create_app
from core.settings import AppEnvironment
from core.settings import Settings
from shared.database import Database


class FakeDatabase:
    """Expose deterministic readiness behavior without owning infrastructure."""

    def __init__(self, *, is_ready: bool) -> None:
        self._is_ready = is_ready

    async def ready(self) -> bool:
        """Return configured readiness."""

        return self._is_ready

    async def close(self) -> None:
        """Satisfy the database resource contract."""


@pytest.mark.parametrize(
    ("is_ready", "expected_status"),
    [(True, 200), (False, 503)],
)
async def test_health_and_readiness_have_distinct_dependency_semantics(
    is_ready: bool,
    expected_status: int,
) -> None:
    app = create_app(database=FakeDatabase(is_ready=is_ready))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/health")
        readiness = await client.get("/ready")

    assert health.status_code == 200
    assert readiness.status_code == expected_status
    assert health.headers["x-request-id"]
    assert health.headers["x-content-type-options"] == "nosniff"


def test_production_configuration_requires_ownid_and_session_security() -> None:
    with pytest.raises(ValueError, match="Missing production security settings"):
        Settings(
            APP_ENV=AppEnvironment.PRODUCTION,
            APP_BASE_URL="https://sis.example.edu",
            COOKIE_SECURE=True,
            DEV_AUTH_ENABLED=False,
        )


async def test_database_engine_hides_statement_parameters() -> None:
    database = Database(Settings())
    try:
        assert database.engine.sync_engine.hide_parameters is True
    finally:
        await database.close()


def test_cors_rejects_wildcards_and_non_origin_paths() -> None:
    with pytest.raises(ValueError, match="explicit HTTP origins"):
        Settings(CORS_ALLOWED_ORIGINS="*")
    with pytest.raises(ValueError, match="explicit HTTP origins"):
        Settings(CORS_ALLOWED_ORIGINS="https://app.example.test/path")


def test_enabled_mcp_requires_ownid_resource_configuration() -> None:
    with pytest.raises(ValueError, match="MCP_AUDIENCE and OWNID_ISSUER"):
        Settings(MCP_ENABLED=True)


async def test_invalid_request_id_is_replaced() -> None:
    app = create_app(database=FakeDatabase(is_ready=True))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health", headers={"X-Request-ID": "bad id"})

    assert response.headers["x-request-id"] != "bad id"
